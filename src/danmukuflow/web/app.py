import asyncio
import io
import json
import tempfile
import threading
import zipfile
from functools import partial
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from danmukuflow.bilibili.service import BilibiliService
from danmukuflow.models import (
    BVSource,
    BatchExportRequest,
    DEFAULT_BATCH_NAMING_TEMPLATE,
    EpisodeSource,
    OutputConfig,
    OutputMode,
    SeasonSource,
    XMLSource,
)
from danmukuflow.parsers.bilibili_input import source_from_input
from danmukuflow.services import (
    BatchExportError,
    BatchExportService,
    ExportRequest,
    ExportService,
    ExportError,
    OutputConflictError,
    OutputPathEscapeError,
    OutputRegistry,
    OutputService,
    InputNotFoundError,
    InvalidEpisodeSelectionError,
    PageNotFoundError,
    SeasonNotFoundError,
    EpisodeNotFoundError,
    VideoNotFoundError,
    VideoDirectoryAccessError,
    VideoDirectoryNotFoundError,
    VideoDirectoryNotDirectoryError,
    NoVideoFilesError,
)
from danmukuflow.web.schemas import (
    BatchExportRequestSchema,
    DirectorySelectRequestSchema,
    ResolveRequestSchema,
    SingleExportRequestSchema,
    episode_to_dict,
    season_to_dict,
    video_to_dict,
)

_directory_picker_lock = threading.Lock()


class DirectoryPickerUnavailableError(RuntimeError):
    """Raised when the host cannot open a native directory picker."""


async def _run_in_threadpool(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


def create_app(
    *,
    bilibili_service=None,
    output_service=None,
    export_service=None,
    batch_export_service=None,
    allowed_output_roots=None,
    frontend_dist_dir=None,
):
    if allowed_output_roots is None:
        allowed_output_roots = ()
    allowed_output_roots = tuple(Path(item) for item in allowed_output_roots)

    registry = OutputRegistry()
    output_service = output_service or OutputService(
        allowed_output_roots=allowed_output_roots,
        registry=registry,
    )
    bilibili_service = bilibili_service or BilibiliService()
    export_service = export_service or ExportService(
        bilibili_service=bilibili_service,
        output_service=output_service,
    )
    batch_export_service = batch_export_service or BatchExportService(
        bilibili_service=bilibili_service,
        export_service=export_service,
        output_service=output_service,
    )

    app = FastAPI(title="DanmukuFlow API")
    app.state.output_service = output_service
    app.state.export_service = export_service
    app.state.batch_export_service = batch_export_service
    app.state.bilibili_service = bilibili_service

    @app.post("/api/directories/select")
    async def select_directory(request: DirectorySelectRequestSchema):
        try:
            selected_path = await _run_in_threadpool(
                _pick_directory,
                request.kind,
            )
        except DirectoryPickerUnavailableError as exc:
            return _error_response(503, str(exc))
        if selected_path is None:
            return Response(status_code=204)
        return {"path": str(selected_path)}

    @app.post("/api/resolve")
    @app.post("/api/seasons/resolve")
    async def resolve(request: ResolveRequestSchema):
        try:
            request = _coerce_schema(request, ResolveRequestSchema)
            source = source_from_input(request.input, page=request.page)
            if isinstance(source, BVSource):
                video = await _run_in_threadpool(
                    app.state.bilibili_service.resolve_video,
                    source,
                )
                return {"kind": "bv", "video": video_to_dict(video)}
            if isinstance(source, EpisodeSource):
                season, episode = await _run_in_threadpool(
                    app.state.bilibili_service.resolve_episode,
                    source,
                )
                return {
                    "kind": "ep",
                    "season": season_to_dict(season),
                    "episode": episode_to_dict(episode),
                }
            if isinstance(source, SeasonSource):
                season = await _run_in_threadpool(
                    app.state.bilibili_service.resolve_season,
                    source,
                )
                return {
                    "kind": "ss",
                    "season": season_to_dict(season),
                    "episodes": [episode_to_dict(item) for item in season.episodes],
                }
            return _error_response(400, "unsupported input")
        except (ExportError, BatchExportError) as exc:
            return _error_response(_service_status(exc), str(exc))

    @app.post("/api/exports")
    async def export(request: Request):
        temp_path = None
        try:
            payload = await _read_payload(request)
            xml_upload = payload.pop("_xml_upload", None)
            schema = SingleExportRequestSchema(**payload)
            source, temp_path = _build_single_source(schema, xml_upload)
            output_config = _build_single_output_config(schema, app.state.output_service)
            request_model = ExportRequest(
                source=source,
                output_path=Path(schema.output_path) if schema.output_path else None,
                output_config=output_config,
                render_config=schema.render_config.to_model(),
            )
            result = await _run_in_threadpool(
                app.state.export_service.export,
                request_model,
            )
            if result.artifact is not None and _should_download(schema, result):
                return _download_response(result.artifact)
            return _json_response(_export_result_payload(result))
        except ValidationError as exc:
            return _error_response(422, exc.errors())
        except (ExportError, BatchExportError) as exc:
            return _error_response(_service_status(exc), str(exc))
        except HTTPException as exc:
            return _error_response(exc.status_code, exc.detail)
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    @app.post("/api/batch-exports")
    async def batch_export(request: BatchExportRequestSchema):
        try:
            request = _coerce_schema(request, BatchExportRequestSchema)
            if request.video_dir and request.output_dir:
                return _error_response(
                    422,
                    "video_dir and output_dir cannot be used together",
                )
            video_dir = None
            if request.video_dir:
                try:
                    video_dir = app.state.output_service.validate_path(
                        Path(request.video_dir),
                        output_config=OutputConfig(
                            allowed_output_roots=(
                                app.state.output_service.allowed_output_roots
                            ),
                        ),
                    )
                except OutputPathEscapeError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

            output_dir = None
            if request.output_dir:
                try:
                    output_dir = app.state.output_service.validate_path(
                        Path(request.output_dir),
                        output_config=OutputConfig(
                            allowed_output_roots=(
                                app.state.output_service.allowed_output_roots
                            ),
                        ),
                    )
                except OutputPathEscapeError as exc:
                    return _error_response(400, str(exc))

            output_config = _build_batch_output_config(
                request,
                app.state.output_service,
                video_dir=video_dir,
                output_dir=output_dir,
            )
            batch_request = BatchExportRequest(
                source=SeasonSource(request.season_id),
                video_dir=video_dir,
                selected_episode_ids=tuple(request.selected_episode_ids),
                output_config=output_config,
                concurrency=request.concurrency,
                conflict_policy=request.conflict_policy,
                render_config=request.render_config.to_model(),
            )
            result = await _run_in_threadpool(
                app.state.batch_export_service.export,
                batch_request,
            )
            if output_config.is_download and video_dir is None:
                artifacts = [
                    item.artifact or (item.result.artifact if item.result else None)
                    for item in result.items
                    if item.status.value in ("succeeded", "fallback")
                ]
                artifacts = [item for item in artifacts if item is not None]
                if len(artifacts) == 1 and not _batch_result_is_partial(result):
                    return _download_response(artifacts[0])
                if artifacts:
                    return _download_zip_response(
                        artifacts,
                        request.season_id,
                        result=result,
                    )
            return _json_response(_batch_result_payload(result))
        except ValidationError as exc:
            return _error_response(422, exc.errors())
        except (ExportError, BatchExportError) as exc:
            return _error_response(_service_status(exc), str(exc))
        except HTTPException as exc:
            return _error_response(exc.status_code, exc.detail)

    @app.get("/api/files/{artifact_id}")
    async def file(artifact_id: str):
        artifact = app.state.output_service.registry.get(artifact_id)
        if artifact is None:
            return _error_response(404, "file not found")
        if artifact.path is not None:
            try:
                path = app.state.output_service.resolve_existing_path(
                    artifact.path,
                    output_config=OutputConfig(
                        allowed_output_roots=app.state.output_service.allowed_output_roots,
                    ),
                )
            except OutputPathEscapeError:
                return _error_response(404, "file not found")
            if not path.exists():
                return _error_response(404, "file not found")
            return FileResponse(
                path,
                filename=artifact.filename,
                media_type=artifact.media_type,
            )
        if artifact.content is None:
            return _error_response(404, "file not available")
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={
                "Content-Disposition": _content_disposition(artifact.filename),
            },
        )

    if frontend_dist_dir is None:
        frontend_dist_dir = (
            Path(__file__).resolve().parents[3] / "web" / "dist"
        )
    frontend_dist_dir = Path(frontend_dist_dir)
    if frontend_dist_dir.is_dir() and hasattr(app, "mount"):
        app.mount(
            "/",
            StaticFiles(directory=str(frontend_dist_dir), html=True),
            name="frontend",
        )
    elif frontend_dist_dir.is_dir():
        index_path = frontend_dist_dir / "index.html"

        @app.get("/")
        async def frontend_index(request: Request = None):
            return FileResponse(index_path, media_type="text/html")

    return app


async def _read_payload(request):
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data") or not content_type:
        try:
            form = await request.form()
            form_items = list(form.multi_items())
        except Exception:
            form_items = []
        if form_items:
            payload = {
                key: value for key, value in form_items if key != "xml_file"
            }
            xml_file = form.get("xml_file")
            if xml_file is not None:
                payload["_xml_upload"] = xml_file
            if "render_config" in payload and isinstance(
                payload["render_config"],
                str,
            ):
                payload["render_config"] = _maybe_json(payload["render_config"])
            return payload

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        payload = {key: value for key, value in form.multi_items() if key != "xml_file"}
        xml_file = form.get("xml_file")
        if xml_file is not None:
            payload["_xml_upload"] = xml_file
        if "render_config" in payload and isinstance(payload["render_config"], str):
            payload["render_config"] = _maybe_json(payload["render_config"])
        return payload
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid JSON body") from exc
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")
    if isinstance(payload.get("render_config"), str):
        payload["render_config"] = _maybe_json(payload["render_config"])
    return payload


def _build_single_source(schema, xml_upload):
    if xml_upload is not None:
        return _xml_upload_source(xml_upload, schema.xml_filename)
    if schema.xml_content is not None:
        return _xml_text_source(schema.xml_content, schema.xml_filename)
    if not schema.input:
        raise HTTPException(status_code=400, detail="input is required")
    return source_from_input(schema.input, page=schema.page), None


def _build_single_output_config(schema, output_service):
    if schema.output_path:
        return OutputConfig(
            output_dir=Path(schema.output_path).parent,
            naming_template=Path(schema.output_path).name,
            organization_mode=schema.organization_mode,
            conflict_policy=schema.conflict_policy,
            mode=OutputMode.DIRECTORY,
            allowed_output_roots=output_service.allowed_output_roots,
        )
    if schema.output_dir:
        return OutputConfig(
            output_dir=Path(schema.output_dir),
            naming_template=schema.naming_template,
            organization_mode=schema.organization_mode,
            conflict_policy=schema.conflict_policy,
            mode=OutputMode.DIRECTORY,
            allowed_output_roots=output_service.allowed_output_roots,
        )
    return OutputConfig(
        naming_template=schema.naming_template,
        organization_mode=schema.organization_mode,
        conflict_policy=schema.conflict_policy,
        mode=OutputMode.DOWNLOAD,
        allowed_output_roots=output_service.allowed_output_roots,
    )


def _build_batch_output_config(
    schema,
    output_service,
    *,
    video_dir=None,
    output_dir=None,
):
    if video_dir is not None:
        return OutputConfig(
            output_dir=video_dir,
            naming_template=schema.naming_template,
            organization_mode=schema.organization_mode,
            conflict_policy=schema.conflict_policy,
            mode=OutputMode.DIRECTORY,
            allowed_output_roots=output_service.allowed_output_roots,
        )
    if schema.output_dir:
        return OutputConfig(
            output_dir=output_dir or Path(schema.output_dir),
            naming_template=(
                schema.naming_template
                or DEFAULT_BATCH_NAMING_TEMPLATE
            ),
            organization_mode=schema.organization_mode,
            conflict_policy=schema.conflict_policy,
            mode=OutputMode.DIRECTORY,
            allowed_output_roots=output_service.allowed_output_roots,
        )
    return OutputConfig(
        naming_template=(
            schema.naming_template
            or DEFAULT_BATCH_NAMING_TEMPLATE
        ),
        organization_mode=schema.organization_mode,
        conflict_policy=schema.conflict_policy,
        mode=OutputMode.DOWNLOAD,
        allowed_output_roots=output_service.allowed_output_roots,
    )


def _should_download(schema, result):
    return schema.output_path is None and schema.output_dir is None and result.skipped is False


def _content_disposition(filename):
    filename = str(filename or "download.ass")
    fallback = filename if filename.isascii() else "download"
    if not fallback.lower().endswith((".ass", ".zip")):
        suffix = Path(filename).suffix
        fallback = "download{}".format(suffix if suffix.isascii() else "")
    encoded = quote(filename, safe="")
    return 'attachment; filename="{}"; filename*=UTF-8\'\'{}'.format(
        fallback,
        encoded,
    )


def _download_response(artifact):
    return Response(
        content=artifact.content or b"",
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": _content_disposition(artifact.filename),
        },
    )


def _download_zip_response(artifacts, season_id, result=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact in artifacts:
            name = artifact.relative_path or artifact.filename
            name = str(name).replace("\\", "/")
            archive.writestr(
                name,
                artifact.content or b"",
            )
        if result is not None and _batch_result_is_partial(result):
            archive.writestr(
                "batch-result.json",
                json.dumps(
                    _batch_download_manifest(result),
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8"),
            )
    buffer.seek(0)
    partial = result is not None and _batch_result_is_partial(result)
    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={
            "Content-Disposition": _content_disposition(
                "season-{}.zip".format(season_id)
            ),
            "X-DanmukuFlow-Partial": "true" if partial else "false",
            "X-DanmukuFlow-Failed-Count": str(result.failed if result else 0),
        },
    )


def _batch_result_is_partial(result):
    return any(
        (
            result.failed,
            result.skipped,
            result.unmatched_local,
            result.unmatched_episode,
            result.ambiguous,
        )
    )


def _batch_download_manifest(result):
    return {
        "total": result.total,
        "matched": result.matched,
        "selected": result.selected,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "skipped": result.skipped,
        "unmatched_local": result.unmatched_local,
        "unmatched_episode": result.unmatched_episode,
        "ambiguous": result.ambiguous,
        "pending": result.pending,
        "running": result.running,
        "fallback": result.fallback,
        "items": [
            _batch_item_payload(item)
            for item in result.items
            if (
                (item.status.value if hasattr(item.status, "value") else str(item.status))
                not in ("succeeded", "fallback")
            )
        ],
    }


def _export_result_payload(result):
    return {
        "success": result.success,
        "output_path": str(result.output_path) if result.output_path else None,
        "danmaku_count": result.danmaku_count,
        "skipped": result.skipped,
        "metadata": _json_safe(result.metadata),
        "artifact": _artifact_payload(result.artifact),
    }


def _batch_result_payload(result):
    return {
        "total": result.total,
        "matched": result.matched,
        "selected": result.selected,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "skipped": result.skipped,
        "unmatched_local": result.unmatched_local,
        "unmatched_episode": result.unmatched_episode,
        "ambiguous": result.ambiguous,
        "pending": result.pending,
        "running": result.running,
        "fallback": result.fallback,
        "items": [_batch_item_payload(item) for item in result.items],
    }


def _batch_item_payload(item):
    status = item.status.value if hasattr(item.status, "value") else str(item.status)
    if status == "unmatched":
        status = (
            "unmatched_local"
            if item.local_video_path is not None
            else "unmatched_episode"
        )
    return {
        "episode_id": item.episode_id,
        "display_number": item.display_number,
        "episode_title": item.episode_title,
        "local_video_path": str(item.local_video_path) if item.local_video_path else None,
        "output_path": str(item.output_path) if item.output_path else None,
        "status": status,
        "reason": item.reason,
        "error": str(item.error) if item.error else None,
        "fallback": item.fallback,
        "artifact": _artifact_payload(item.artifact),
    }


def _artifact_payload(artifact):
    if artifact is None:
        return None
    return {
        "artifact_id": artifact.artifact_id,
        "filename": artifact.filename,
        "media_type": artifact.media_type,
        "path": str(artifact.path) if artifact.path else None,
        "relative_path": str(artifact.relative_path) if artifact.relative_path else None,
        "metadata": _json_safe(artifact.metadata),
        "skipped": artifact.skipped,
    }


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _maybe_json(value):
    try:
        return json.loads(value)
    except Exception:
        return value


def _json_response(payload, status_code=200):
    from fastapi.responses import JSONResponse

    return JSONResponse(content=payload, status_code=status_code)


def _error_response(status_code, detail):
    return _json_response({"detail": detail}, status_code=status_code)


def _pick_directory(kind):
    if not _directory_picker_lock.acquire(blocking=False):
        raise DirectoryPickerUnavailableError(
            "directory picker is already open"
        )

    root = None
    try:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except Exception as exc:
            raise DirectoryPickerUnavailableError(
                "native directory picker is unavailable"
            ) from exc

        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            root.update()
            title = (
                "选择普通输出目录"
                if kind == "output"
                else "选择本地视频目录"
            )
            selected = filedialog.askdirectory(
                parent=root,
                title=title,
                mustexist=False,
            )
        except Exception as exc:
            raise DirectoryPickerUnavailableError(
                "native directory picker is unavailable"
            ) from exc

        if not selected:
            return None
        return Path(selected).expanduser().resolve()
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        _directory_picker_lock.release()


def _coerce_schema(value, schema_type):
    if isinstance(value, schema_type):
        return value
    if isinstance(value, dict):
        return schema_type(**value)
    return value


def _service_status(error):
    if isinstance(
        error,
        (
            OutputConflictError,
        ),
    ):
        return 409
    if isinstance(
        error,
        (
            InputNotFoundError,
            PageNotFoundError,
            SeasonNotFoundError,
            EpisodeNotFoundError,
            VideoNotFoundError,
            VideoDirectoryNotFoundError,
            VideoDirectoryNotDirectoryError,
            NoVideoFilesError,
            VideoDirectoryAccessError,
            InvalidEpisodeSelectionError,
        ),
    ):
        return 400
    return 400


def _xml_upload_source(upload, filename):
    suffix = Path(filename or getattr(upload, "filename", "upload.xml")).suffix or ".xml"
    with tempfile.NamedTemporaryFile("wb", delete=False, suffix=suffix) as handle:
        data = upload.file.read()
        handle.write(data)
        temp_path = Path(handle.name)
    return XMLSource(temp_path), temp_path


def _xml_text_source(content, filename):
    suffix = Path(filename or "upload.xml").suffix or ".xml"
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=suffix, encoding="utf-8") as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    return XMLSource(temp_path), temp_path


def create_default_app():
    return create_app()


app = create_default_app()

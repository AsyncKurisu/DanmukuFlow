import asyncio
import io
import json
import tempfile
import zipfile
from functools import partial
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from danmukuflow.bilibili.service import BilibiliService
from danmukuflow.models import (
    BVSource,
    BatchExportRequest,
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
    PageNotFoundError,
    SeasonNotFoundError,
    EpisodeNotFoundError,
    VideoNotFoundError,
    VideoDirectoryNotFoundError,
    VideoDirectoryNotDirectoryError,
    NoVideoFilesError,
)
from danmukuflow.web.schemas import (
    BatchExportRequestSchema,
    ResolveRequestSchema,
    SingleExportRequestSchema,
    episode_to_dict,
    season_to_dict,
    video_to_dict,
)


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
):
    if allowed_output_roots is None:
        allowed_output_roots = (Path.cwd(),)
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

    @app.post("/api/resolve")
    @app.post("/api/seasons/resolve")
    async def resolve(request: ResolveRequestSchema):
        try:
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
            raise HTTPException(status_code=400, detail="unsupported input")
        except (ExportError, BatchExportError) as exc:
            raise HTTPException(status_code=_service_status(exc), detail=str(exc))

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
            raise HTTPException(status_code=422, detail=exc.errors())
        except (ExportError, BatchExportError) as exc:
            raise HTTPException(status_code=_service_status(exc), detail=str(exc))
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    @app.post("/api/batch-exports")
    async def batch_export(request: BatchExportRequestSchema):
        try:
            output_config = _build_batch_output_config(request, app.state.output_service)
            batch_request = BatchExportRequest(
                source=SeasonSource(request.season_id),
                selected_episode_ids=tuple(request.selected_episode_ids),
                output_config=output_config,
                concurrency=request.concurrency,
                render_config=request.render_config.to_model(),
            )
            result = await _run_in_threadpool(
                app.state.batch_export_service.export,
                batch_request,
            )
            if output_config.is_download and result.failed == 0:
                artifacts = [
                    item.artifact or (item.result.artifact if item.result else None)
                    for item in result.items
                    if item.status.value in ("succeeded", "fallback")
                ]
                artifacts = [item for item in artifacts if item is not None]
                if len(artifacts) == 1:
                    return _download_response(artifacts[0])
                if len(artifacts) > 1:
                    return _download_zip_response(artifacts, request.season_id)
            return _json_response(_batch_result_payload(result))
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors())
        except (ExportError, BatchExportError) as exc:
            raise HTTPException(status_code=_service_status(exc), detail=str(exc))

    @app.get("/api/files/{artifact_id}")
    async def file(artifact_id: str):
        artifact = app.state.output_service.registry.get(artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="file not found")
        if artifact.path is not None:
            try:
                path = app.state.output_service.resolve_existing_path(
                    artifact.path,
                    output_config=OutputConfig(
                        allowed_output_roots=app.state.output_service.allowed_output_roots,
                    ),
                )
            except OutputPathEscapeError:
                raise HTTPException(status_code=404, detail="file not found")
            if not path.exists():
                raise HTTPException(status_code=404, detail="file not found")
            return FileResponse(
                path,
                filename=artifact.filename,
                media_type=artifact.media_type,
            )
        if artifact.content is None:
            raise HTTPException(status_code=404, detail="file not available")
        return Response(
            content=artifact.content,
            media_type=artifact.media_type,
            headers={
                "Content-Disposition": 'attachment; filename="{}"'.format(
                    artifact.filename
                )
            },
        )

    return app


async def _read_payload(request):
    content_type = request.headers.get("content-type", "")
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


def _build_batch_output_config(schema, output_service):
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


def _should_download(schema, result):
    return schema.output_path is None and schema.output_dir is None and result.skipped is False


def _download_response(artifact):
    return Response(
        content=artifact.content or b"",
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": 'attachment; filename="{}"'.format(
                artifact.filename
            )
        },
    )


def _download_zip_response(artifacts, season_id):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact in artifacts:
            name = artifact.relative_path or artifact.filename
            name = str(name).replace("\\", "/")
            archive.writestr(
                name,
                artifact.content or b"",
            )
    buffer.seek(0)
    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="season-{}.zip"'.format(
                season_id
            )
        },
    )


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
    return {
        "episode_id": item.episode_id,
        "display_number": item.display_number,
        "episode_title": item.episode_title,
        "local_video_path": str(item.local_video_path) if item.local_video_path else None,
        "output_path": str(item.output_path) if item.output_path else None,
        "status": item.status.value if hasattr(item.status, "value") else str(item.status),
        "reason": item.reason,
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
        ),
    ):
        return 404
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

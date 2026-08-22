import re
from dataclasses import dataclass, field
from pathlib import Path

from danmukuflow.bilibili.service import BilibiliService
from danmukuflow.models import (
    BVSource,
    EpisodeSource,
    RenderConfig,
    SeasonSource,
    XMLSource,
)
from danmukuflow.parsers.bilibili_xml import DanmakuParseError
from danmukuflow.renderers.ass import render_ass_document
from danmukuflow.services.conversion import convert_xml_to_ass
from danmukuflow.services.errors import (
    DanmakuContentError,
    ExportError,
    InputNotFoundError,
    InvalidXmlError,
    OutputDirectoryError,
    OutputWriteError,
    PageNotFoundError,
    RenderError,
    SeasonExportUnsupportedError,
    UnsupportedSourceError,
)


@dataclass(frozen=True)
class ExportRequest:
    source: object
    output_path: object = None
    render_config: RenderConfig = field(default_factory=RenderConfig)
    force: bool = False


@dataclass(frozen=True)
class ExportResult:
    success: bool
    output_path: Path
    danmaku_count: int
    metadata: dict


class ExportService:
    def __init__(self, bilibili_service=None):
        self.bilibili_service = (
            bilibili_service if bilibili_service is not None else BilibiliService()
        )

    def export(self, request):
        if isinstance(request.source, XMLSource):
            return self._export_xml(request)
        if isinstance(request.source, BVSource):
            return self._export_bv(request)
        if isinstance(request.source, EpisodeSource):
            return self._export_episode(request)
        if isinstance(request.source, SeasonSource):
            raise SeasonExportUnsupportedError(
                "ss input is currently supported for season parsing only; "
                "season export will be added in a later release"
            )
        raise UnsupportedSourceError(
            "source type {} is not supported yet".format(
                type(request.source).__name__
            )
        )

    def _export_xml(self, request):
        input_path = Path(request.source.path)
        if not input_path.exists():
            raise InputNotFoundError("input file does not exist: {}".format(input_path))
        if not input_path.is_file():
            raise InputNotFoundError("input path is not a file: {}".format(input_path))

        output_path = self._resolve_output_path(input_path, request.output_path)
        self._ensure_output_directory(output_path)

        try:
            conversion = convert_xml_to_ass(
                input_path,
                output_path,
                request.render_config,
                force=request.force,
            )
        except DanmakuParseError as exc:
            if str(exc).startswith("XML file parse error"):
                raise InvalidXmlError("invalid XML file: {}".format(input_path)) from exc
            raise DanmakuContentError(
                "danmaku content could not be parsed: {}".format(input_path)
            ) from exc
        except IsADirectoryError as exc:
            raise OutputWriteError(
                "output path is a directory: {}".format(output_path)
            ) from exc
        except PermissionError as exc:
            raise OutputWriteError(
                "output file is not writable: {}".format(output_path)
            ) from exc
        except OSError as exc:
            raise OutputWriteError(
                "output file could not be written: {}".format(output_path)
            ) from exc
        except ExportError:
            raise
        except Exception as exc:
            raise RenderError("rendering failed for {}".format(input_path)) from exc

        return ExportResult(
            success=True,
            output_path=conversion.output_path,
            danmaku_count=conversion.rendered_count,
            metadata={
                "source_type": "xml",
                "input_path": conversion.input_path,
                "title": input_path.stem,
                "parsed_count": conversion.parsed_count,
                "rendered_count": conversion.rendered_count,
                "skipped_count": conversion.skipped_count,
                "segment_count": 0,
                "skipped_due_to_newer_output": conversion.skipped_due_to_newer_output,
            },
        )

    def _export_bv(self, request):
        video = self.bilibili_service.resolve_video(request.source)
        page = next(
            (item for item in video.pages if item.page == request.source.page),
            None,
        )
        if page is None:
            raise PageNotFoundError(
                "video page {} does not exist for {}".format(
                    request.source.page,
                    request.source.bv,
                )
            )

        fetch = self._fetch_danmaku(page.cid, page.duration_s)
        output_path = self._resolve_network_output_path(
            request.output_path,
            video.title,
        )
        metadata = {
            "source_type": "bv",
            "title": video.title,
            "bvid": video.bvid,
            "cid": page.cid,
            "page": page.page,
        }
        return self._render_network_result(
            fetch,
            title=video.title,
            output_path=output_path,
            config=request.render_config,
            metadata=metadata,
        )

    def _export_episode(self, request):
        season, episode = self.bilibili_service.resolve_episode(request.source)
        fetch = self._fetch_danmaku(episode.cid, episode.duration_s)
        episode_title = episode.title or episode.long_title or str(episode.episode_id)
        title = "{} - {}".format(season.title, episode_title)
        output_path = self._resolve_network_output_path(
            request.output_path,
            title,
        )
        metadata = {
            "source_type": "ep",
            "title": title,
            "season_id": season.season_id,
            "episode_id": episode.episode_id,
            "bvid": episode.bvid,
            "cid": episode.cid,
            "page": None,
        }
        return self._render_network_result(
            fetch,
            title=title,
            output_path=output_path,
            config=request.render_config,
            metadata=metadata,
        )

    def _fetch_danmaku(self, cid, duration_s):
        fetch_with_stats = getattr(
            self.bilibili_service,
            "fetch_danmaku_with_stats",
            None,
        )
        if fetch_with_stats is not None:
            return fetch_with_stats(cid, duration_s)

        from danmukuflow.bilibili.service import DanmakuFetchResult
        import math

        return DanmakuFetchResult(
            danmakus=self.bilibili_service.fetch_danmaku(cid, duration_s),
            segment_count=max(1, int(math.ceil(float(duration_s) / 360.0))),
            skipped_count=0,
        )

    def _render_network_result(
        self,
        fetch,
        title,
        output_path,
        config,
        metadata,
    ):
        self._ensure_output_directory(output_path)
        try:
            rendered = render_ass_document(fetch.danmakus, title, config)
            with output_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered.content)
        except IsADirectoryError as exc:
            raise OutputWriteError(
                "output path is a directory: {}".format(output_path)
            ) from exc
        except PermissionError as exc:
            raise OutputWriteError(
                "output file is not writable: {}".format(output_path)
            ) from exc
        except OSError as exc:
            raise OutputWriteError(
                "output file could not be written: {}".format(output_path)
            ) from exc
        except ExportError:
            raise
        except Exception as exc:
            raise RenderError("rendering failed for {}".format(title)) from exc

        metadata = dict(metadata)
        metadata.update(
            {
                "parsed_count": rendered.parsed_count,
                "rendered_count": rendered.rendered_count,
                "skipped_count": rendered.skipped_count + fetch.skipped_count,
                "segment_count": fetch.segment_count,
                "skipped_due_to_newer_output": False,
            }
        )
        return ExportResult(
            success=True,
            output_path=output_path,
            danmaku_count=rendered.rendered_count,
            metadata=metadata,
        )

    def _resolve_output_path(self, input_path, output_path):
        if output_path is None:
            return input_path.with_suffix(".ass")
        return Path(output_path)

    def _resolve_network_output_path(self, output_path, title):
        if output_path is not None:
            return Path(output_path)
        return Path(_safe_filename(title) + ".ass")

    def _ensure_output_directory(self, output_path):
        parent = output_path.parent
        if not str(parent) or parent == Path("."):
            return
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputDirectoryError(
                "output directory could not be created: {}".format(parent)
            ) from exc


def _safe_filename(value):
    value = str(value).strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or "danmaku"
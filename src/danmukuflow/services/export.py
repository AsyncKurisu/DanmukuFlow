from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from danmukuflow.bilibili.service import BilibiliService
from danmukuflow.models import (
    BVSource,
    Episode,
    EpisodeSource,
    OutputArtifact,
    OutputConfig,
    OutputMode,
    RenderConfig,
    Season,
    SeasonSource,
    TemplateContext,
    XMLSource,
)
from danmukuflow.parsers.bilibili_xml import DanmakuParseError, parse_xml
from danmukuflow.renderers.ass import render_ass_document
from danmukuflow.services.errors import (
    DanmakuContentError,
    ExportError,
    InputNotFoundError,
    InvalidXmlError,
    OutputConflictError,
    OutputDirectoryError,
    OutputPathEscapeError,
    OutputWriteError,
    PageNotFoundError,
    RenderError,
    SeasonExportUnsupportedError,
    UnsupportedSourceError,
)
from danmukuflow.services.output import OutputService, safe_filename as _safe_filename


@dataclass(frozen=True)
class ExportRequest:
    source: object
    output_path: object = None
    output_config: OutputConfig = None
    render_config: RenderConfig = field(default_factory=RenderConfig)


@dataclass(frozen=True)
class ExportResult:
    success: bool
    output_path: Optional[Path]
    danmaku_count: int
    metadata: dict
    artifact: Optional[OutputArtifact] = None
    skipped: bool = False


class ExportService:
    def __init__(self, bilibili_service=None, output_service=None):
        self.bilibili_service = (
            bilibili_service if bilibili_service is not None else BilibiliService()
        )
        self.output_service = output_service or OutputService()

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

    def export_resolved_episode(
        self,
        season: Season,
        episode: Episode,
        output_path,
        config=None,
        output_config=None,
    ):
        config = config or RenderConfig()
        title = self._episode_title(season, episode)
        fetch = self._fetch_danmaku(episode.cid, episode.duration_s)
        rendered = render_ass_document(fetch.danmakus, title, config)
        metadata = {
            "source_type": "ep",
            "title": title,
            "season_id": season.season_id,
            "episode_id": episode.episode_id,
            "display_number": episode.display_number,
            "bvid": episode.bvid,
            "cid": episode.cid,
            "page": None,
            "parsed_count": rendered.parsed_count,
            "rendered_count": rendered.rendered_count,
            "skipped_count": rendered.skipped_count + fetch.skipped_count,
            "segment_count": fetch.segment_count,
            "skipped_due_to_newer_output": False,
        }
        artifact, output_path, skipped = self._materialize_rendered(
            rendered.content,
            title=title,
            output_path=output_path,
            output_config=output_config,
            default_root=Path(output_path).parent if output_path is not None else None,
            default_template="{season_title} - {episode_title}.ass",
            context=self._episode_context(season, episode),
            metadata=metadata,
        )
        return ExportResult(
            success=True,
            output_path=output_path,
            danmaku_count=rendered.rendered_count,
            metadata=metadata,
            artifact=artifact,
            skipped=skipped,
        )

    def _export_xml(self, request):
        input_path = Path(request.source.path)
        if not input_path.exists():
            raise InputNotFoundError("input file does not exist: {}".format(input_path))
        if not input_path.is_file():
            raise InputNotFoundError("input path is not a file: {}".format(input_path))

        context = TemplateContext(input_stem=input_path.stem, source_type="xml")
        metadata = {
            "source_type": "xml",
            "input_path": input_path,
            "title": input_path.stem,
            "parsed_count": 0,
            "rendered_count": 0,
            "skipped_count": 0,
            "segment_count": 0,
            "skipped_due_to_newer_output": False,
        }
        skipped_artifact = self._preview_skip(
            request.output_path,
            request.output_config,
            context=context,
            default_root=input_path.parent,
            default_template="{input_stem}.ass",
            metadata=metadata,
        )
        if skipped_artifact is not None:
            return ExportResult(
                success=True,
                output_path=skipped_artifact.path,
                danmaku_count=0,
                metadata={**metadata, "skipped_due_to_existing_output": True},
                artifact=skipped_artifact,
                skipped=True,
            )

        try:
            danmakus = parse_xml(input_path)
            rendered = render_ass_document(danmakus, input_path.stem, request.render_config)
        except DanmakuParseError as exc:
            if str(exc).startswith("XML file parse error"):
                raise InvalidXmlError("invalid XML file: {}".format(input_path)) from exc
            raise DanmakuContentError(
                "danmaku content could not be parsed: {}".format(input_path)
            ) from exc
        except ExportError:
            raise
        except Exception as exc:
            raise RenderError("rendering failed for {}".format(input_path)) from exc

        metadata.update(
            {
                "parsed_count": rendered.parsed_count,
                "rendered_count": rendered.rendered_count,
                "skipped_count": rendered.skipped_count,
            }
        )
        artifact, output_path, skipped = self._materialize_rendered(
            rendered.content,
            title=input_path.stem,
            output_path=request.output_path,
            output_config=request.output_config,
            default_root=input_path.parent,
            default_template="{input_stem}.ass",
            context=context,
            metadata=metadata,
        )
        return ExportResult(
            success=True,
            output_path=output_path,
            danmaku_count=rendered.rendered_count,
            metadata=metadata,
            artifact=artifact,
            skipped=skipped,
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

        context = TemplateContext(
            video_title=video.title,
            bvid=video.bvid,
            page=page.page,
            part=page.part,
            cid=page.cid,
            source_type="bv",
        )
        metadata = {
            "source_type": "bv",
            "title": video.title,
            "bvid": video.bvid,
            "cid": page.cid,
            "page": page.page,
            "part": page.part,
            "parsed_count": 0,
            "rendered_count": 0,
            "skipped_count": 0,
            "segment_count": 0,
            "skipped_due_to_newer_output": False,
        }
        default_template = self._bv_default_template(video)
        skipped_artifact = self._preview_skip(
            request.output_path,
            request.output_config,
            context=context,
            default_root=Path.cwd(),
            default_template=default_template,
            metadata=metadata,
        )
        if skipped_artifact is not None:
            return ExportResult(
                success=True,
                output_path=skipped_artifact.path,
                danmaku_count=0,
                metadata={**metadata, "skipped_due_to_existing_output": True},
                artifact=skipped_artifact,
                skipped=True,
            )

        fetch = self._fetch_danmaku(page.cid, page.duration_s)
        title = video.title
        rendered = render_ass_document(fetch.danmakus, title, request.render_config)
        metadata.update(
            {
                "parsed_count": rendered.parsed_count,
                "rendered_count": rendered.rendered_count,
                "skipped_count": rendered.skipped_count + fetch.skipped_count,
                "segment_count": fetch.segment_count,
            }
        )
        artifact, output_path, skipped = self._materialize_rendered(
            rendered.content,
            title=title,
            output_path=request.output_path,
            output_config=request.output_config,
            default_root=Path.cwd(),
            default_template=default_template,
            context=context,
            metadata=metadata,
        )
        return ExportResult(
            success=True,
            output_path=output_path,
            danmaku_count=rendered.rendered_count,
            metadata=metadata,
            artifact=artifact,
            skipped=skipped,
        )

    def _export_episode(self, request):
        season, episode = self.bilibili_service.resolve_episode(request.source)
        title = self._episode_title(season, episode)
        context = self._episode_context(season, episode)
        metadata = {
            "source_type": "ep",
            "title": title,
            "season_id": season.season_id,
            "episode_id": episode.episode_id,
            "display_number": episode.display_number,
            "bvid": episode.bvid,
            "cid": episode.cid,
            "page": None,
            "parsed_count": 0,
            "rendered_count": 0,
            "skipped_count": 0,
            "segment_count": 0,
            "skipped_due_to_newer_output": False,
        }
        skipped_artifact = self._preview_skip(
            request.output_path,
            request.output_config,
            context=context,
            default_root=Path.cwd(),
            default_template="{season_title} - {episode_title}.ass",
            metadata=metadata,
        )
        if skipped_artifact is not None:
            return ExportResult(
                success=True,
                output_path=skipped_artifact.path,
                danmaku_count=0,
                metadata={**metadata, "skipped_due_to_existing_output": True},
                artifact=skipped_artifact,
                skipped=True,
            )

        fetch = self._fetch_danmaku(episode.cid, episode.duration_s)
        rendered = render_ass_document(fetch.danmakus, title, request.render_config)
        metadata.update(
            {
                "parsed_count": rendered.parsed_count,
                "rendered_count": rendered.rendered_count,
                "skipped_count": rendered.skipped_count + fetch.skipped_count,
                "segment_count": fetch.segment_count,
            }
        )
        artifact, output_path, skipped = self._materialize_rendered(
            rendered.content,
            title=title,
            output_path=request.output_path,
            output_config=request.output_config,
            default_root=Path.cwd(),
            default_template="{season_title} - {episode_title}.ass",
            context=self._episode_context(season, episode),
            metadata=metadata,
        )
        return ExportResult(
            success=True,
            output_path=output_path,
            danmaku_count=rendered.rendered_count,
            metadata=metadata,
            artifact=artifact,
            skipped=skipped,
        )

    def _materialize_rendered(
        self,
        content,
        *,
        title,
        output_path,
        output_config,
        default_root,
        default_template,
        context,
        metadata,
    ):
        output_config = output_config or OutputConfig()
        if output_path is not None:
            path = Path(output_path)
            if output_config.mode is OutputMode.DOWNLOAD:
                output_config = OutputConfig(
                    output_dir=path.parent,
                    naming_template=path.name,
                    organization_mode=output_config.organization_mode,
                    conflict_policy=output_config.conflict_policy,
                    mode=OutputMode.DIRECTORY,
                    allowed_output_roots=output_config.allowed_output_roots,
                )
            try:
                artifact = self.output_service.materialize_text(
                    content,
                    output_config=output_config,
                    context=context,
                    default_template=default_template,
                    default_root=path.parent,
                    explicit_path=path,
                    metadata=metadata,
                )
            except OutputPathEscapeError:
                raise
            except OutputConflictError:
                raise
            except OutputDirectoryError:
                raise
            except OutputWriteError:
                raise
            return artifact, path, artifact.skipped

        if output_config.mode is OutputMode.DOWNLOAD:
            artifact = self.output_service.materialize_text(
                content,
                output_config=output_config,
                context=context,
                default_template=default_template,
                default_root=default_root,
                metadata=metadata,
            )
            return artifact, None, artifact.skipped

        artifact = self.output_service.materialize_text(
            content,
            output_config=output_config,
            context=context,
            default_template=default_template,
            default_root=default_root,
            metadata=metadata,
        )
        return artifact, artifact.path, artifact.skipped

    def _preview_skip(
        self,
        output_path,
        output_config,
        *,
        context,
        default_root,
        default_template,
        metadata,
    ):
        if output_path is None and (output_config is None or output_config.mode is OutputMode.DOWNLOAD):
            return None
        return self.output_service.preview_conflict(
            output_config=output_config,
            context=context,
            default_template=default_template,
            default_root=default_root,
            explicit_path=Path(output_path) if output_path is not None else None,
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

    @staticmethod
    def _episode_context(season, episode):
        episode_title = episode.title or episode.long_title or str(episode.episode_id)
        return TemplateContext(
            season_title=season.title,
            season_id=season.season_id,
            episode_no=episode.display_number,
            episode_id=episode.episode_id,
            episode_title=episode_title,
            long_title=episode.long_title,
            bvid=episode.bvid,
            cid=episode.cid,
            source_type="ep",
        )

    @staticmethod
    def _episode_title(season, episode):
        episode_title = episode.title or episode.long_title or str(episode.episode_id)
        return "{} - {}".format(season.title, episode_title)

    @staticmethod
    def _bv_default_template(video):
        if len(video.pages) <= 1:
            return "{video_title}.ass"
        return "{video_title}-{page}.ass"


def safe_filename(value):
    return _safe_filename(value)

from dataclasses import dataclass, field
from pathlib import Path

from danmukuflow.models import RenderConfig, XMLSource
from danmukuflow.parsers.bilibili_xml import DanmakuParseError
from danmukuflow.services.conversion import convert_xml_to_ass
from danmukuflow.services.errors import (
    DanmakuContentError,
    ExportError,
    InputNotFoundError,
    InvalidXmlError,
    OutputDirectoryError,
    OutputWriteError,
    RenderError,
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
    def export(self, request):
        if not isinstance(request.source, XMLSource):
            raise UnsupportedSourceError(
                "source type {} is not supported yet".format(
                    type(request.source).__name__
                )
            )

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
                "parsed_count": conversion.parsed_count,
                "rendered_count": conversion.rendered_count,
                "skipped_count": conversion.skipped_count,
                "skipped_due_to_newer_output": conversion.skipped_due_to_newer_output,
            },
        )

    def _resolve_output_path(self, input_path, output_path):
        if output_path is None:
            return input_path.with_suffix(".ass")
        return Path(output_path)

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

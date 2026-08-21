from dataclasses import dataclass
from pathlib import Path

from danmukuflow.models import RenderConfig
from danmukuflow.parsers import parse_xml
from danmukuflow.renderers.ass import render_ass_document


@dataclass(frozen=True)
class ConversionResult:
    input_path: Path
    output_path: Path
    parsed_count: int
    rendered_count: int
    skipped_count: int
    skipped_due_to_newer_output: bool = False


def convert_xml_to_ass(input_path, output_path, config=None, *, force=False):
    input_path = Path(input_path)
    output_path = Path(output_path)
    config = config or RenderConfig()

    if not input_path.exists():
        raise FileNotFoundError(str(input_path))
    if output_path.is_dir():
        raise IsADirectoryError(str(output_path))

    if not force and output_path.exists():
        if input_path.stat().st_mtime < output_path.stat().st_mtime:
            return ConversionResult(
                input_path=input_path,
                output_path=output_path,
                parsed_count=0,
                rendered_count=0,
                skipped_count=0,
                skipped_due_to_newer_output=True,
            )

    danmakus = parse_xml(input_path)
    title = input_path.stem
    result = render_ass_document(danmakus, title, config)

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(result.content)

    return ConversionResult(
        input_path=input_path,
        output_path=output_path,
        parsed_count=result.parsed_count,
        rendered_count=result.rendered_count,
        skipped_count=result.skipped_count,
        skipped_due_to_newer_output=False,
    )

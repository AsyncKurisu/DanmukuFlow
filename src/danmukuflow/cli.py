import argparse
import sys
from pathlib import Path

from danmukuflow import source_from_input
from danmukuflow.models import BVSource, RenderConfig
from danmukuflow.services import (
    ExportError,
    ExportRequest,
    ExportService,
    InvalidBilibiliIdentifierError,
    InputNotFoundError,
    InvalidXmlError,
    OutputDirectoryError,
    OutputWriteError,
)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 0

    return args.handler(args)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="danmukuflow",
        description="Convert Bilibili XML, BV, or episode danmaku to ASS subtitles.",
    )
    subparsers = parser.add_subparsers(dest="command")

    convert = subparsers.add_parser(
        "convert",
        help="convert one XML, BV, or episode source to ASS",
    )
    convert.add_argument("input", help="XML path, BV/ss/ep id, or Bilibili URL")
    convert.add_argument(
        "--output",
        "-o",
        help="output ASS file, defaults to a source-based filename",
    )
    convert.add_argument(
        "--page",
        type=int,
        help="BV video page to export (defaults to 1)",
    )
    convert.set_defaults(handler=_handle_convert)

    return parser


def _handle_convert(args):
    try:
        source = source_from_input(args.input, page=args.page)
        if args.page is not None and not isinstance(source, BVSource):
            raise InvalidBilibiliIdentifierError(
                "--page is only valid for BV video input"
            )
        request = ExportRequest(
            source=source,
            output_path=Path(args.output) if args.output else None,
            render_config=RenderConfig(),
        )
        result = ExportService().export(request)
    except ExportError as exc:
        print(_format_error(exc), file=sys.stderr)
        return 1

    if result.metadata.get("skipped_due_to_newer_output"):
        print("Skipped: output is newer ({})".format(result.output_path))
    else:
        print(
            "Converted {} danmaku to {}".format(
                result.danmaku_count,
                result.output_path,
            )
        )
    return 0


def _format_error(error):
    if isinstance(error, InputNotFoundError):
        return "error: input file not found: {}".format(error)
    if isinstance(error, InvalidXmlError):
        return "error: invalid XML: {}".format(error)
    if isinstance(error, OutputDirectoryError):
        return "error: output directory error: {}".format(error)
    if isinstance(error, OutputWriteError):
        return "error: output write error: {}".format(error)
    if isinstance(error, InvalidBilibiliIdentifierError):
        return "error: invalid Bilibili input: {}".format(error)
    return "error: {}".format(error)


if __name__ == "__main__":
    sys.exit(main())
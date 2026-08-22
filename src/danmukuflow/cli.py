import argparse
import sys
from pathlib import Path

from danmukuflow.models import RenderConfig, XMLSource
from danmukuflow.services import (
    ExportError,
    ExportRequest,
    ExportService,
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
        prog="danmu2ass",
        description="Convert Bilibili XML danmaku files to ASS subtitles.",
    )
    subparsers = parser.add_subparsers(dest="command")

    convert = subparsers.add_parser(
        "convert",
        help="convert one local XML danmaku file to ASS",
    )
    convert.add_argument("input", help="input XML file")
    convert.add_argument(
        "--output",
        "-o",
        help="output ASS file, defaults to the input filename with .ass extension",
    )
    convert.set_defaults(handler=_handle_convert)

    return parser


def _handle_convert(args):
    request = ExportRequest(
        source=XMLSource(Path(args.input)),
        output_path=Path(args.output) if args.output else None,
        render_config=RenderConfig(),
    )

    try:
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
    return "error: {}".format(error)


if __name__ == "__main__":
    sys.exit(main())

import argparse
import sys
from pathlib import Path

from danmukuflow import source_from_input
from danmukuflow.models import (
    BVSource,
    BatchExportRequest,
    ConflictPolicy,
    DEFAULT_CONCURRENCY,
    RenderConfig,
)
from danmukuflow.services import (
    BatchExportService,
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

    batch = subparsers.add_parser(
        "batch",
        help="export matched Season episodes beside local video files",
    )
    batch.add_argument(
        "input",
        help="Season identifier such as ss123 or a Bilibili Season URL",
    )
    batch.add_argument(
        "--video-dir",
        default=".",
        help=(
            "directory containing local video files; defaults to the "
            "current command directory"
        ),
    )
    batch.add_argument(
        "--episodes",
        default=None,
        help="episode selection: all, 1-12, 1,3,5, or 1,3-5,8",
    )
    batch.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="maximum concurrent episode exports (default: {})".format(
            DEFAULT_CONCURRENCY
        ),
    )
    batch.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing ASS files instead of skipping them",
    )
    batch.set_defaults(handler=_handle_batch)

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


def _handle_batch(args):
    try:
        source = source_from_input(args.input)
        request = BatchExportRequest(
            source=source,
            video_dir=Path(args.video_dir),
            episodes=args.episodes,
            concurrency=args.concurrency,
            conflict_policy=(
                ConflictPolicy.OVERWRITE
                if args.overwrite
                else ConflictPolicy.SKIP
            ),
            render_config=RenderConfig(),
        )
        result = BatchExportService().export(request)
    except ExportError as exc:
        print(_format_error(exc), file=sys.stderr)
        return 1

    print(
        "Batch total={total} matched={matched} selected={selected} "
        "succeeded={succeeded} failed={failed} skipped={skipped} "
        "fallback={fallback} "
        "unmatched_local={unmatched_local} "
        "unmatched_episode={unmatched_episode} ambiguous={ambiguous}".format(
            total=result.total,
            matched=result.matched,
            selected=result.selected,
            succeeded=result.succeeded,
            failed=result.failed,
            skipped=result.skipped,
            fallback=result.fallback,
            unmatched_local=result.unmatched_local,
            unmatched_episode=result.unmatched_episode,
            ambiguous=result.ambiguous,
        )
    )
    for item in result.items:
        if item.status.value == "failed":
            print(
                "Failed episode {}: {}".format(
                    item.display_number or item.episode_id or "?",
                    item.error,
                ),
                file=sys.stderr,
            )
    return 1 if result.failed else 0


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

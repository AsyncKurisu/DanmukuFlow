import argparse
import sys
from pathlib import Path

from danmukuflow import source_from_input
from danmukuflow.models import (
    BVSource,
    BatchExportRequest,
    ConflictPolicy,
    DEFAULT_CONCURRENCY,
    OutputConfig,
    OutputMode,
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
    InvalidOutputTemplateError,
    OutputConflictError,
    OutputDirectoryError,
    OutputPathEscapeError,
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
        "--output-dir",
        help="output directory for directory mode",
    )
    convert.add_argument(
        "--template",
        help="output naming template",
    )
    convert.add_argument(
        "--conflict-policy",
        choices=("overwrite", "skip", "error"),
        help="output conflict policy",
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
        default=None,
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
        "--output-dir",
        help="output directory for season batch exports",
    )
    batch.add_argument(
        "--template",
        help="output naming template",
    )
    batch.add_argument(
        "--conflict-policy",
        choices=("overwrite", "skip", "error"),
        help="output conflict policy",
    )
    batch.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing ASS files instead of skipping them",
    )
    batch.add_argument(
        "--skip-existing",
        action="store_true",
        help="skip existing ASS files instead of overwriting them",
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
        output_path = Path(args.output) if args.output else None
        if output_path is not None and args.output_dir:
            raise InvalidOutputTemplateError(
                "--output and --output-dir cannot be used together"
            )
        output_config = None
        if args.output_dir or args.template or args.conflict_policy:
            output_config = OutputConfig(
                output_dir=Path(args.output_dir) if args.output_dir else None,
                naming_template=args.template,
                conflict_policy=_parse_conflict_policy(
                    args.conflict_policy,
                    default=ConflictPolicy.OVERWRITE,
                ),
                mode=OutputMode.DIRECTORY,
            )
        request = ExportRequest(
            source=source,
            output_path=output_path,
            output_config=output_config,
            render_config=RenderConfig(),
        )
        result = ExportService().export(request)
    except ExportError as exc:
        print(_format_error(exc), file=sys.stderr)
        return 1

    if result.skipped:
        print("Skipped: output already exists ({})".format(result.output_path))
    elif result.metadata.get("skipped_due_to_newer_output"):
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
        conflict_policy = _parse_conflict_policy(
            args.conflict_policy,
            default=(
                ConflictPolicy.OVERWRITE
                if args.overwrite
                else (
                    ConflictPolicy.SKIP
                    if not args.skip_existing
                    else ConflictPolicy.SKIP
                )
            ),
        )
        video_dir = Path(args.video_dir) if args.video_dir is not None else None
        if args.output_dir is None and video_dir is None:
            video_dir = Path(".")
        output_config = None
        if args.output_dir or args.template or args.conflict_policy:
            output_config = OutputConfig(
                output_dir=Path(args.output_dir) if args.output_dir else None,
                naming_template=args.template,
                conflict_policy=conflict_policy,
                mode=OutputMode.DIRECTORY,
        )
        request = BatchExportRequest(
            source=source,
            video_dir=video_dir,
            episodes=args.episodes,
            concurrency=args.concurrency,
            conflict_policy=conflict_policy,
            output_config=output_config,
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
    if isinstance(error, OutputPathEscapeError):
        return "error: output path is outside allowed roots: {}".format(error)
    if isinstance(error, OutputConflictError):
        return "error: output conflict: {}".format(error)
    if isinstance(error, OutputWriteError):
        return "error: output write error: {}".format(error)
    if isinstance(error, InvalidBilibiliIdentifierError):
        return "error: invalid Bilibili input: {}".format(error)
    if isinstance(error, InvalidOutputTemplateError):
        return "error: invalid output template: {}".format(error)
    return "error: {}".format(error)


def _parse_conflict_policy(value, default):
    if value:
        return ConflictPolicy(value)
    return default


if __name__ == "__main__":
    sys.exit(main())

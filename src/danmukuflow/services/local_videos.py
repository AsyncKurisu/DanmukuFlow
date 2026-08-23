from pathlib import Path

from danmukuflow.models import LocalVideoFile
from danmukuflow.services.errors import (
    NoVideoFilesError,
    VideoDirectoryAccessError,
    VideoDirectoryNotDirectoryError,
    VideoDirectoryNotFoundError,
)


SUPPORTED_VIDEO_SUFFIXES = (
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".wmv",
    ".m4v",
    ".ts",
)


class LocalVideoScanner:
    def scan(self, video_dir):
        directory = Path(video_dir)
        if not directory.exists():
            raise VideoDirectoryNotFoundError(
                "video directory does not exist: {}".format(directory)
            )
        if not directory.is_dir():
            raise VideoDirectoryNotDirectoryError(
                "video path is not a directory: {}".format(directory)
            )

        try:
            files = [
                path
                for path in directory.iterdir()
                if path.is_file()
                and path.suffix.casefold() in SUPPORTED_VIDEO_SUFFIXES
            ]
        except OSError as exc:
            raise VideoDirectoryAccessError(
                "video directory could not be scanned: {}".format(directory)
            ) from exc

        if not files:
            raise NoVideoFilesError(
                "video directory contains no supported video files: {}".format(
                    directory
                )
            )

        files.sort(key=lambda path: (path.name.casefold(), path.name))
        return tuple(
            LocalVideoFile(
                path=path,
                filename=path.name,
                stem=path.stem,
                suffix=path.suffix,
            )
            for path in files
        )

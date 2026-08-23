class ExportError(Exception):
    """Base class for user-facing export failures."""


class InputNotFoundError(ExportError):
    pass


class InvalidXmlError(ExportError):
    pass


class DanmakuContentError(ExportError):
    pass


class OutputDirectoryError(ExportError):
    pass


class OutputWriteError(ExportError):
    pass


class RenderError(ExportError):
    pass


class UnsupportedSourceError(ExportError):
    pass


class InvalidBilibiliIdentifierError(ExportError):
    pass


class BilibiliNetworkError(ExportError):
    pass


class BilibiliTimeoutError(BilibiliNetworkError):
    pass


class BilibiliHttpError(ExportError):
    pass


class BilibiliApiError(ExportError):
    pass


class BilibiliDataError(ExportError):
    pass


class BilibiliDecodeError(ExportError):
    pass


class VideoNotFoundError(BilibiliApiError):
    pass


class PageNotFoundError(ExportError):
    pass


class SeasonNotFoundError(BilibiliApiError):
    pass


class EpisodeNotFoundError(BilibiliApiError):
    pass


class SeasonExportUnsupportedError(UnsupportedSourceError):
    pass


class BatchExportError(ExportError):
    pass


class VideoDirectoryNotFoundError(BatchExportError):
    pass


class VideoDirectoryNotDirectoryError(BatchExportError):
    pass


class VideoDirectoryAccessError(BatchExportError):
    pass


class NoVideoFilesError(BatchExportError):
    pass


class SeasonEpisodeNumberError(BatchExportError):
    pass


class InvalidEpisodeSelectionError(BatchExportError):
    pass


class InvalidBatchConcurrencyError(BatchExportError):
    pass


class InvalidBatchConflictPolicyError(BatchExportError):
    pass

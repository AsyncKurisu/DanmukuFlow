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

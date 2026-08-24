import os
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Optional

from danmukuflow.models import (
    ConflictPolicy,
    OutputArtifact,
    OutputConfig,
    OutputMode,
    TemplateContext,
)
from danmukuflow.services.errors import (
    InvalidOutputTemplateError,
    OutputConflictError,
    OutputDirectoryError,
    OutputPathEscapeError,
    OutputWriteError,
)


_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


@dataclass(frozen=True)
class OutputPlan:
    root: Optional[Path]
    target: Optional[Path]
    relative_path: Optional[Path]
    filename: str


class OutputRegistry:
    def __init__(self):
        self._items = {}
        self._lock = threading.Lock()

    def register(self, artifact):
        with self._lock:
            self._items[artifact.artifact_id] = artifact
        return artifact

    def get(self, artifact_id):
        with self._lock:
            return self._items.get(artifact_id)

    def values(self):
        with self._lock:
            return tuple(self._items.values())


class OutputService:
    def __init__(self, allowed_output_roots=None, registry=None):
        self.allowed_output_roots = tuple(
            Path(item) for item in (allowed_output_roots or ())
        )
        self.registry = registry or OutputRegistry()
        self._formatter = Formatter()

    def build_context(self, **values):
        return TemplateContext(**values)

    def render_template(self, template, context):
        template = str(template or "").strip()
        if not template:
            raise InvalidOutputTemplateError("output template cannot be empty")

        mapping = context.as_dict() if isinstance(context, TemplateContext) else dict(context)
        safe_mapping = {}
        for key, value in mapping.items():
            safe_mapping[key] = _sanitize_filename(value) if value is not None else "danmaku"

        try:
            rendered = self._formatter.vformat(template, (), _TemplateMapping(safe_mapping))
        except KeyError as exc:
            raise InvalidOutputTemplateError(
                "unknown output template variable: {}".format(exc.args[0])
            ) from exc
        except ValueError as exc:
            raise InvalidOutputTemplateError(str(exc)) from exc
        return rendered

    def build_plan(
        self,
        output_config,
        context,
        *,
        default_template,
        default_root=None,
        explicit_path=None,
    ):
        if explicit_path is not None:
            target = Path(explicit_path)
            root = target.parent
            relative_path = target.name
            return OutputPlan(root=root, target=target, relative_path=Path(relative_path), filename=target.name)

        output_config = output_config or OutputConfig()
        template = output_config.naming_template or default_template
        rendered = self.render_template(template, context)
        relative_path = _sanitize_relative_path(rendered)
        filename = relative_path.name if relative_path is not None else _sanitize_filename(rendered)

        if output_config.is_download and explicit_path is None:
            root = None
        else:
            root = output_config.output_dir or default_root
            if root is None:
                root = Path.cwd()
        root = Path(root) if root is not None else None
        target = (root / relative_path) if root is not None and relative_path is not None else None
        if root is not None and relative_path is None:
            target = root / filename
        return OutputPlan(root=root, target=target, relative_path=relative_path, filename=filename)

    def materialize_text(
        self,
        content,
        *,
        output_config=None,
        context=None,
        default_template=None,
        default_root=None,
        explicit_path=None,
        metadata=None,
    ):
        output_config = output_config or OutputConfig()
        context = context or TemplateContext()
        plan = self.build_plan(
            output_config,
            context,
            default_template=default_template,
            default_root=default_root,
            explicit_path=explicit_path,
        )

        if output_config.is_download and explicit_path is None:
            artifact = self._build_artifact(
                filename=plan.filename,
                content=content,
                metadata=metadata,
                path=None,
                relative_path=plan.relative_path,
            )
            return self.registry.register(artifact)

        if plan.target is None:
            raise OutputDirectoryError("output target could not be resolved")

        path = self._prepare_path(plan.target, output_config)
        conflict = self._materialized_conflict(
            path,
            output_config,
            metadata=metadata,
            relative_path=plan.relative_path,
        )
        if conflict is not None:
            return conflict

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputDirectoryError(
                "output directory could not be created: {}".format(path.parent)
            ) from exc
        try:
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        except OSError as exc:
            raise OutputWriteError(
                "output file could not be written: {}".format(path)
            ) from exc

        artifact = self._build_artifact(
            filename=path.name,
            content=content,
            metadata=metadata,
            path=path,
            relative_path=plan.relative_path,
        )
        return self.registry.register(artifact)

    def preview_conflict(
        self,
        *,
        output_config=None,
        context=None,
        default_template=None,
        default_root=None,
        explicit_path=None,
        metadata=None,
    ):
        output_config = output_config or OutputConfig()
        context = context or TemplateContext()
        plan = self.build_plan(
            output_config,
            context,
            default_template=default_template,
            default_root=default_root,
            explicit_path=explicit_path,
        )
        if plan.target is None:
            return None
        path = self._prepare_path(plan.target, output_config)
        return self._materialized_conflict(
            path,
            output_config,
            metadata=metadata,
            relative_path=plan.relative_path,
        )

    def resolve_existing_path(self, path, *, output_config=None):
        output_config = output_config or OutputConfig()
        path = Path(path)
        self._ensure_allowed(path, output_config)
        return _resolve_path(path)

    def _prepare_path(self, path, output_config):
        path = Path(path)
        self._ensure_allowed(path, output_config)
        return _resolve_path(path)

    def _ensure_allowed(self, path, output_config):
        roots = output_config.allowed_output_roots or self.allowed_output_roots
        if not roots:
            return
        resolved = _resolve_path(path)
        for root in roots:
            root_path = _resolve_path(root)
            if _is_within(resolved, root_path):
                return
        raise OutputPathEscapeError(
            "path is outside the allowed output roots: {}".format(path)
        )

    def _build_artifact(
        self,
        *,
        filename,
        content,
        metadata,
        path=None,
        relative_path=None,
        skipped=False,
    ):
        if content is not None and isinstance(content, str):
            content = content.encode("utf-8")
        return OutputArtifact(
            artifact_id=uuid.uuid4().hex,
            filename=filename,
            content=content,
            path=path,
            relative_path=relative_path,
            metadata=dict(metadata or {}),
            skipped=skipped,
        )

    def _materialized_conflict(self, path, output_config, *, metadata, relative_path):
        if not path.exists():
            return None
        if output_config.conflict_policy is ConflictPolicy.SKIP:
            artifact = self._build_artifact(
                filename=path.name,
                content=None,
                metadata=metadata,
                path=path,
                relative_path=relative_path,
                skipped=True,
            )
            return self.registry.register(artifact)
        if output_config.conflict_policy is ConflictPolicy.ERROR:
            raise OutputConflictError("output file already exists: {}".format(path))
        return None


class _TemplateMapping(dict):
    def __missing__(self, key):
        raise KeyError(key)


def _sanitize_relative_path(rendered):
    rendered = str(rendered).strip()
    if not rendered:
        raise InvalidOutputTemplateError("output template rendered an empty path")
    if rendered.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rendered):
        raise OutputPathEscapeError("output template rendered an absolute path")

    raw_parts = [part for part in re.split(r"[\\/]+", rendered) if part]
    if not raw_parts:
        raise InvalidOutputTemplateError("output template rendered an empty path")

    cleaned = []
    for part in raw_parts:
        if part in (".", ".."):
            raise OutputPathEscapeError(
                "output template rendered a path traversal component"
            )
        cleaned.append(_sanitize_filename(part))
    return Path(*cleaned)


def _sanitize_filename(value):
    text = str(value).strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        return "danmaku"
    stem = text.split(".")[0].casefold()
    if stem in _WINDOWS_RESERVED:
        text = "_{}".format(text)
    if text in (".", ".."):
        return "danmaku"
    return text


def _resolve_path(path):
    path = Path(path)
    try:
        return path.resolve(strict=False)
    except TypeError:
        return Path(os.path.abspath(str(path)))


def _is_within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def safe_filename(value):
    return _sanitize_filename(value)

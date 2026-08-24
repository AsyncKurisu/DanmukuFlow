from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class OutputMode(str, Enum):
    DIRECTORY = "directory"
    DOWNLOAD = "download"


class OutputOrganizationMode(str, Enum):
    FLAT = "flat"
    SEASON = "season"
    LOCAL_VIDEO = "local_video"


class ConflictPolicy(str, Enum):
    OVERWRITE = "overwrite"
    SKIP = "skip"
    ERROR = "error"


@dataclass(frozen=True)
class TemplateContext:
    input_stem: Optional[str] = None
    video_title: Optional[str] = None
    bvid: Optional[str] = None
    page: Optional[int] = None
    part: Optional[str] = None
    cid: Optional[int] = None
    season_title: Optional[str] = None
    season_id: Optional[int] = None
    episode_no: Optional[int] = None
    episode_id: Optional[int] = None
    episode_title: Optional[str] = None
    long_title: Optional[str] = None
    local_video_stem: Optional[str] = None
    local_video_name: Optional[str] = None
    source_type: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self):
        data = {
            "input_stem": self.input_stem,
            "video_title": self.video_title,
            "bvid": self.bvid,
            "page": self.page,
            "part": self.part,
            "cid": self.cid,
            "season_title": self.season_title,
            "season_id": self.season_id,
            "episode_no": self.episode_no,
            "episode_id": self.episode_id,
            "episode_title": self.episode_title,
            "long_title": self.long_title,
            "local_video_stem": self.local_video_stem,
            "local_video_name": self.local_video_name,
            "source_type": self.source_type,
        }
        data.update(self.extra)
        return data


@dataclass(frozen=True)
class OutputConfig:
    output_dir: Optional[Path] = None
    naming_template: Optional[str] = None
    organization_mode: OutputOrganizationMode = OutputOrganizationMode.FLAT
    conflict_policy: ConflictPolicy = ConflictPolicy.OVERWRITE
    mode: OutputMode = OutputMode.DIRECTORY
    allowed_output_roots: Tuple[Path, ...] = ()

    def __post_init__(self):
        if self.output_dir is not None:
            object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(
            self,
            "organization_mode",
            _coerce_enum(OutputOrganizationMode, self.organization_mode),
        )
        object.__setattr__(
            self,
            "conflict_policy",
            _coerce_enum(ConflictPolicy, self.conflict_policy),
        )
        object.__setattr__(
            self,
            "mode",
            _coerce_enum(OutputMode, self.mode),
        )
        object.__setattr__(
            self,
            "allowed_output_roots",
            tuple(Path(item) for item in self.allowed_output_roots),
        )

    @property
    def is_download(self):
        return self.mode is OutputMode.DOWNLOAD

    @property
    def is_directory(self):
        return self.mode is OutputMode.DIRECTORY


def _coerce_enum(enum_type, value):
    if isinstance(value, enum_type):
        return value
    return enum_type(str(value).casefold())


@dataclass(frozen=True)
class OutputArtifact:
    artifact_id: str
    filename: str
    media_type: str = "text/plain; charset=utf-8"
    content: Optional[bytes] = None
    path: Optional[Path] = None
    relative_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    skipped: bool = False

    def as_bytes(self):
        if self.content is None:
            return None
        return bytes(self.content)


@dataclass(frozen=True)
class BatchItemResult:
    episode_id: Optional[int]
    display_number: Optional[int]
    episode_title: Optional[str]
    local_video_path: Optional[Path]
    output_path: Optional[Path]
    status: Any
    result: Optional[Any] = None
    error: Optional[BaseException] = None
    reason: Optional[str] = None
    fallback: bool = False
    artifact: Optional[OutputArtifact] = None


@dataclass(frozen=True)
class BatchExportResult:
    total: int
    matched: int
    selected: int
    succeeded: int
    failed: int
    skipped: int
    unmatched_local: int
    unmatched_episode: int
    ambiguous: int
    pending: int = 0
    running: int = 0
    items: Tuple[BatchItemResult, ...] = ()
    fallback: int = 0

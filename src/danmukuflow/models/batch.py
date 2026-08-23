from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

from danmukuflow.models.bilibili import Episode
from danmukuflow.models.config import RenderConfig
from danmukuflow.models.sources import SeasonSource


DEFAULT_CONCURRENCY = 3


class LocalEpisodeKind(str, Enum):
    NORMAL = "normal"
    SPECIAL = "special"
    UNRECOGNIZED = "unrecognized"
    AMBIGUOUS = "ambiguous"


class ConflictPolicy(str, Enum):
    SKIP = "skip"
    OVERWRITE = "overwrite"


class BatchItemStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FALLBACK = "fallback"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class LocalEpisodeKey:
    kind: LocalEpisodeKind
    raw: Optional[str] = None
    number: Optional[int] = None


@dataclass(frozen=True)
class NumericField:
    raw: str
    number: int
    signature: tuple


@dataclass(frozen=True)
class LocalVideoFile:
    path: Path
    filename: str
    stem: str
    suffix: str
    episode_key: Optional[LocalEpisodeKey] = None


@dataclass(frozen=True)
class EpisodeMatch:
    episode: Optional[Episode] = None
    video: Optional[LocalVideoFile] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class EpisodeMatchResult:
    matched: Tuple[EpisodeMatch, ...] = ()
    unmatched_local: Tuple[EpisodeMatch, ...] = ()
    unmatched_episode: Tuple[EpisodeMatch, ...] = ()
    ambiguous: Tuple[EpisodeMatch, ...] = ()


@dataclass(frozen=True)
class DirectoryEpisodeResolution:
    matches: EpisodeMatchResult
    fallback_mode: bool = False
    fallback_video: Optional[LocalVideoFile] = None


@dataclass(frozen=True)
class BatchExportRequest:
    source: SeasonSource
    video_dir: Path
    episodes: Optional[str] = None
    concurrency: int = DEFAULT_CONCURRENCY
    conflict_policy: ConflictPolicy = ConflictPolicy.SKIP
    render_config: RenderConfig = field(default_factory=RenderConfig)


@dataclass(frozen=True)
class BatchExportItem:
    episode_id: Optional[int]
    display_number: Optional[int]
    episode_title: Optional[str]
    local_video_path: Optional[Path]
    output_path: Optional[Path]
    status: BatchItemStatus
    result: Optional[object] = None
    error: Optional[BaseException] = None
    reason: Optional[str] = None
    fallback: bool = False


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
    items: Tuple[BatchExportItem, ...] = ()
    fallback: int = 0

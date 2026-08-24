from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

from danmukuflow.models.bilibili import Episode
from danmukuflow.models.config import RenderConfig
from danmukuflow.models.output import (
    BatchExportResult,
    BatchItemResult,
    ConflictPolicy,
    OutputConfig,
    OutputMode,
    OutputOrganizationMode,
    OutputArtifact,
    TemplateContext,
)
from danmukuflow.models.sources import SeasonSource


DEFAULT_CONCURRENCY = 3


class LocalEpisodeKind(str, Enum):
    NORMAL = "normal"
    SPECIAL = "special"
    UNRECOGNIZED = "unrecognized"
    AMBIGUOUS = "ambiguous"


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
    video_dir: Optional[Path] = None
    episodes: Optional[str] = None
    selected_episode_ids: Optional[Tuple[int, ...]] = None
    concurrency: int = DEFAULT_CONCURRENCY
    conflict_policy: ConflictPolicy = ConflictPolicy.SKIP
    render_config: RenderConfig = field(default_factory=RenderConfig)
    output_config: Optional[OutputConfig] = None


BatchExportItem = BatchItemResult

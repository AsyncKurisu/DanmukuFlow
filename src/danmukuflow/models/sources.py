from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class XMLSource:
    path: Path


@dataclass(frozen=True)
class BVSource:
    bv: str
    page: int = 1


@dataclass(frozen=True)
class SeasonSource:
    season_id: int


@dataclass(frozen=True)
class EpisodeSource:
    episode_id: int


@dataclass(frozen=True)
class BilibiliIdentifier:
    kind: str
    value: object
    page: Optional[int] = None

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class XMLSource:
    path: Path


@dataclass(frozen=True)
class BVSource:
    bv: str


@dataclass(frozen=True)
class SeasonSource:
    season_id: int


@dataclass(frozen=True)
class EpisodeSource:
    episode_id: int

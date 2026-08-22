from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class VideoPage:
    page: int
    part: str
    cid: int
    duration_s: float


@dataclass(frozen=True)
class Video:
    bvid: str
    title: str
    pages: List[VideoPage]


@dataclass(frozen=True)
class Episode:
    episode_id: int
    aid: int
    bvid: str
    cid: int
    title: str
    long_title: str
    duration_s: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Season:
    season_id: int
    title: str
    episodes: List[Episode]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawDanmaku:
    progress: int
    mode: int
    fontsize: int
    color: int
    content: str
    ctime: Optional[int] = None
    id: Optional[int] = None

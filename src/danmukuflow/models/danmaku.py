from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class DanmakuType(Enum):
    FLOAT = 1
    BOTTOM = 4
    TOP = 5
    REVERSE = 6

    @classmethod
    def from_xml_num(cls, value):
        try:
            return cls(value)
        except ValueError:
            return None


@dataclass(frozen=True)
class Danmaku:
    timeline_s: float
    content: str
    type: DanmakuType
    fontsize: int
    rgb: Tuple[int, int, int]
    send_timestamp_ms: Optional[int] = None
    raw_fields: Tuple[str, ...] = ()

    def length(self, config):
        width_units = sum(2 if ch.isascii() else 3 for ch in self.content)
        points = config.font_size * width_units // 3
        return float(points) * config.width_ratio

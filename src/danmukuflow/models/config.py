from dataclasses import dataclass


@dataclass(frozen=True)
class RenderConfig:
    duration: float = 15.0
    width: int = 1280
    height: int = 720
    font: str = "\u9ed1\u4f53"
    font_size: int = 25
    width_ratio: float = 1.2
    horizontal_gap: float = 20.0
    lane_size: int = 32
    float_percentage: float = 0.5
    alpha: float = 0.7
    bold: bool = False
    outline: float = 0.8
    time_offset: float = 0.0
    denylist: tuple = ()

    def __post_init__(self):
        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError("alpha must be between 0 and 1")
        if not 0.0 <= self.float_percentage <= 1.0:
            raise ValueError("float_percentage must be between 0 and 1")
        if self.lane_size <= 0:
            raise ValueError("lane_size must be greater than 0")
        if self.duration <= 0.0:
            raise ValueError("duration must be greater than 0")

    @property
    def opacity(self):
        return int((1.0 - self.alpha) * 255.0)

    @property
    def bold_value(self):
        return 1 if self.bold else 0

    @property
    def float_lane_count(self):
        return int(self.float_percentage * float(self.height) / float(self.lane_size))

    @property
    def bottom_lane_count(self):
        return int(0.3 * float(self.height) / float(self.lane_size))

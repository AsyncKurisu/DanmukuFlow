from dataclasses import dataclass, replace

from danmukuflow.models import DanmakuType


@dataclass(frozen=True)
class MoveEffect:
    start: tuple
    end: tuple


@dataclass(frozen=True)
class Drawable:
    danmaku: object
    duration: float
    style_name: str
    effect: MoveEffect


@dataclass(frozen=True)
class _Collision:
    kind: str
    value: float


@dataclass(frozen=True)
class _Lane:
    last_shoot_time: float
    last_length: float

    @classmethod
    def draw(cls, danmaku, config):
        return cls(
            last_shoot_time=danmaku.timeline_s,
            last_length=danmaku.length(config),
        )

    def available_for(self, other, config):
        duration = config.duration
        width = float(config.width)
        gap = config.horizontal_gap

        t1 = self.last_shoot_time
        t2 = other.timeline_s
        l1 = self.last_length
        l2 = other.length(config)

        v1 = (width + l1) / duration
        v2 = (width + l2) / duration

        delta_t = t2 - t1
        delta_x = v1 * delta_t - l1

        if delta_x < gap:
            if l2 <= l1:
                return _Collision("collide", (gap - delta_x) / v1)
            return _Collision("collide", (duration - (width - gap) / v2) - delta_t)

        if l2 <= l1:
            return _Collision("separate", delta_x - gap)

        pos = v2 * (duration - delta_t)
        if pos < (width - gap):
            return _Collision("not_enough_time", (width - gap) - pos)
        return _Collision("collide", (pos - (width - gap)) / v2)


class Canvas:
    def __init__(self, config):
        self.config = config
        self.float_lanes = [None] * config.float_lane_count
        self.bottom_lanes = [None] * config.bottom_lane_count

    def draw(self, danmaku):
        danmaku = replace(danmaku, timeline_s=danmaku.timeline_s + self.config.time_offset)
        if danmaku.timeline_s < 0.0:
            return None

        if danmaku.type is not DanmakuType.FLOAT:
            danmaku = replace(danmaku, type=DanmakuType.FLOAT)

        return self._draw_float(danmaku)

    def _draw_float(self, danmaku):
        collisions = []
        for idx, lane in enumerate(self.float_lanes):
            if lane is None:
                return self._draw_float_in_lane(danmaku, idx)

            collision = lane.available_for(danmaku, self.config)
            if collision.kind in ("separate", "not_enough_time"):
                return self._draw_float_in_lane(danmaku, idx)
            collisions.append((collision.value, idx))

        if collisions:
            collisions.sort()
            time_needed, lane_idx = collisions[0]
            if time_needed < 1.0:
                danmaku = replace(danmaku, timeline_s=danmaku.timeline_s + time_needed + 0.01)
                return self._draw_float_in_lane(danmaku, lane_idx)

        return None

    def _draw_float_in_lane(self, danmaku, lane_idx):
        self.float_lanes[lane_idx] = _Lane.draw(danmaku, self.config)
        y = int(lane_idx * self.config.lane_size)
        length = danmaku.length(self.config)
        return Drawable(
            danmaku=danmaku,
            duration=self.config.duration,
            style_name="Float",
            effect=MoveEffect(
                start=(int(self.config.width), y),
                end=(-int(length), y),
            ),
        )

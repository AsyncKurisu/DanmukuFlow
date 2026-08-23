import math
from dataclasses import dataclass

from danmukuflow.bilibili.client import BilibiliClient
from danmukuflow.models import (
    Danmaku,
    DanmakuType,
    Episode,
    EpisodeSource,
    RawDanmaku,
    Season,
    SeasonSource,
    Video,
    VideoPage,
)
from danmukuflow.protocols.dm_pb2 import DecodeError, DmSegMobileReply
from danmukuflow.services.errors import (
    BilibiliApiError,
    BilibiliDataError,
    BilibiliDecodeError,
    EpisodeNotFoundError,
    PageNotFoundError,
    SeasonNotFoundError,
    VideoNotFoundError,
)


class BilibiliService:
    VIDEO_URL = "https://api.bilibili.com/x/web-interface/view"
    SEASON_URL = "https://api.bilibili.com/pgc/view/web/season"
    DANMAKU_URL = "http://api.bilibili.com/x/v2/dm/web/seg.so"

    def __init__(self, client=None):
        self.client = client or BilibiliClient()

    def resolve_video(self, source):
        payload = self.client.get_json(self.VIDEO_URL, {"bvid": source.bv})
        data = _require_success(
            payload,
            "data",
            not_found_error=VideoNotFoundError,
        )
        if not data:
            raise VideoNotFoundError("video not found: {}".format(source.bv))
        try:
            pages = [
                VideoPage(
                    page=int(item["page"]),
                    part=str(item.get("part") or ""),
                    cid=int(item["cid"]),
                    duration_s=float(item.get("duration") or 0),
                )
                for item in data["pages"]
            ]
            video = Video(
                bvid=str(data.get("bvid") or source.bv),
                title=str(data["title"]),
                pages=pages,
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise BilibiliDataError("video response has an invalid shape") from exc
        if not video.pages:
            raise BilibiliDataError("video response contains no pages")
        return video

    def resolve_season(self, source):
        if isinstance(source, SeasonSource):
            params = {"season_id": source.season_id}
            not_found_error = SeasonNotFoundError
        elif isinstance(source, EpisodeSource):
            params = {"ep_id": source.episode_id}
            not_found_error = EpisodeNotFoundError
        else:
            raise TypeError(
                "resolve_season expects SeasonSource or EpisodeSource"
            )
        payload = self.client.get_json(self.SEASON_URL, params)
        data = _require_success(
            payload,
            "result",
            allow_data=True,
            not_found_error=not_found_error,
        )
        if not data:
            raise not_found_error("Bilibili resource was not found")
        try:
            episodes = [_parse_episode(item) for item in data["episodes"]]
            return Season(
                season_id=int(data.get("season_id") or data.get("media_id") or 0),
                title=str(data.get("season_title") or data.get("title") or ""),
                episodes=episodes,
                metadata={
                    key: value
                    for key, value in data.items()
                    if key not in ("episodes", "season_id", "season_title", "title")
                },
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise BilibiliDataError("season response has an invalid shape") from exc

    def resolve_episode(self, source):
        season = self.resolve_season(source)
        for episode in season.episodes:
            if episode.episode_id == source.episode_id:
                return season, episode
        raise EpisodeNotFoundError(
            "episode was not found in returned season: {}".format(source.episode_id)
        )

    def fetch_danmaku(self, cid, duration_s):
        return self.fetch_danmaku_with_stats(cid, duration_s).danmakus

    def fetch_danmaku_with_stats(self, cid, duration_s):
        segment_count = max(1, int(math.ceil(float(duration_s) / 360.0)))
        result = []
        skipped_count = 0
        for segment_index in range(1, segment_count + 1):
            response = self.client.get(
                self.DANMAKU_URL,
                {"oid": cid, "segment_index": segment_index, "type": 1},
            )
            if response.status_code == 304 or not response.content:
                continue
            content_type = _header(response.headers, "content-type")
            if content_type.lower().startswith("application/json"):
                _require_success_json_bytes(response.content)
                continue
            try:
                reply = DmSegMobileReply.FromString(response.content)
            except (DecodeError, UnicodeDecodeError, ValueError, TypeError) as exc:
                raise BilibiliDecodeError(
                    "danmaku protobuf response could not be decoded"
                ) from exc
            for item in reply.elems:
                danmaku = _to_danmaku(item)
                if danmaku is None:
                    skipped_count += 1
                else:
                    result.append(danmaku)
        return DanmakuFetchResult(
            danmakus=sorted(result, key=lambda item: item.timeline_s),
            segment_count=segment_count,
            skipped_count=skipped_count,
        )


def _require_success(payload, key, allow_data=False, not_found_error=None):
    if not isinstance(payload, dict) or "code" not in payload:
        raise BilibiliDataError("Bilibili response is missing code")
    try:
        code = int(payload.get("code", 0))
    except (TypeError, ValueError) as exc:
        raise BilibiliDataError("Bilibili response code is invalid") from exc
    if code != 0:
        if code == -404 and not_found_error is not None:
            raise not_found_error("Bilibili resource was not found")
        raise BilibiliApiError(
            "Bilibili API error {}: {}".format(code, payload.get("message", ""))
        )
    if key not in payload and allow_data and "data" in payload:
        data = payload.get("data")
    elif key in payload:
        data = payload.get(key)
    else:
        raise BilibiliDataError("Bilibili response is missing {}".format(key))
    if data is None:
        return None
    return data


def _parse_episode(item):
    duration = float(item.get("duration") or 0)
    title = str(item.get("title") or "")
    display_number = (
        int(title) if title.isascii() and title.isdigit() else None
    )
    return Episode(
        episode_id=int(item["id"]),
        aid=int(item.get("aid") or 0),
        bvid=str(item.get("bvid") or ""),
        cid=int(item["cid"]),
        title=title,
        long_title=str(item.get("long_title") or ""),
        duration_s=duration / 1000.0,
        metadata={
            key: value
            for key, value in item.items()
            if key not in ("id", "aid", "bvid", "cid", "title", "long_title", "duration")
        },
        display_number=display_number,
    )


def _to_danmaku(item):
    raw = RawDanmaku(
        progress=item.progress,
        mode=item.mode,
        fontsize=item.fontsize,
        color=item.color,
        content=item.content,
        ctime=item.ctime,
        id=item.id,
    )
    danmaku_type = DanmakuType.from_xml_num(raw.mode)
    if danmaku_type is None:
        return None
    ctime_ms = raw.ctime * 1000 if raw.ctime is not None else None
    return Danmaku(
        timeline_s=raw.progress / 1000.0,
        content=raw.content,
        type=danmaku_type,
        fontsize=raw.fontsize,
        rgb=((raw.color >> 16) & 0xFF, (raw.color >> 8) & 0xFF, raw.color & 0xFF),
        send_timestamp_ms=ctime_ms,
    )


@dataclass(frozen=True)
class DanmakuFetchResult:
    danmakus: list
    segment_count: int
    skipped_count: int


def _header(headers, name):
    name = name.lower()
    return next((value for key, value in headers.items() if key.lower() == name), "")


def _require_success_json_bytes(content):
    import json

    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BilibiliDataError("Bilibili danmaku error response is not JSON") from exc
    _require_success(payload, "data", allow_data=True)

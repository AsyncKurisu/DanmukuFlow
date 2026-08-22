from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

from danmukuflow.models import (
    BVSource,
    BilibiliIdentifier,
    EpisodeSource,
    SeasonSource,
    XMLSource,
)
from danmukuflow.services.errors import InvalidBilibiliIdentifierError


_BV_RE = re.compile(r"^BV[0-9A-Za-z]+$")
_SS_RE = re.compile(r"^ss([0-9]+)$", re.IGNORECASE)
_EP_RE = re.compile(r"^ep([0-9]+)$", re.IGNORECASE)


def parse_bilibili_identifier(value, page=None):
    raw = str(value).strip()
    if not raw:
        raise InvalidBilibiliIdentifierError("input identifier is empty")

    if raw.lower().startswith(("http://", "https://")):
        return _parse_url(raw, page)
    if _BV_RE.match(raw):
        return BilibiliIdentifier("BV", raw, _validate_page(page))

    season_match = _SS_RE.match(raw)
    if season_match:
        _reject_page_for_non_video(page)
        return BilibiliIdentifier("SEASON", _parse_id(season_match.group(1), raw))

    episode_match = _EP_RE.match(raw)
    if episode_match:
        _reject_page_for_non_video(page)
        return BilibiliIdentifier("EPISODE", _parse_id(episode_match.group(1), raw))

    raise InvalidBilibiliIdentifierError("unsupported Bilibili identifier: {}".format(raw))


def source_from_input(value, page=None):
    path = Path(value)
    if not str(value).lower().startswith(("http://", "https://")):
        if path.exists() or path.suffix.lower() == ".xml":
            return XMLSource(path)

    identifier = parse_bilibili_identifier(value, page=page)
    if identifier.kind == "BV":
        return BVSource(identifier.value, identifier.page or 1)
    if identifier.kind == "SEASON":
        return SeasonSource(identifier.value)
    if identifier.kind == "EPISODE":
        return EpisodeSource(identifier.value)
    raise InvalidBilibiliIdentifierError("unsupported identifier kind")


def _parse_url(value, page):
    parsed = urlparse(value)
    if parsed.netloc.lower() not in ("www.bilibili.com", "bilibili.com"):
        raise InvalidBilibiliIdentifierError("unsupported Bilibili domain: {}".format(parsed.netloc))

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0].lower() == "video":
        if not _BV_RE.match(parts[1]):
            raise InvalidBilibiliIdentifierError("invalid BV video URL")
        query_page = _query_page(parsed.query)
        selected_page = page if page is not None else query_page
        return BilibiliIdentifier("BV", parts[1], _validate_page(selected_page))

    if len(parts) >= 3 and parts[0].lower() == "bangumi" and parts[1].lower() == "play":
        season_match = _SS_RE.match(parts[2])
        if season_match:
            _reject_page_for_non_video(page)
            return BilibiliIdentifier(
                "SEASON",
                _parse_id(season_match.group(1), parts[2]),
            )
        episode_match = _EP_RE.match(parts[2])
        if episode_match:
            _reject_page_for_non_video(page)
            return BilibiliIdentifier(
                "EPISODE",
                _parse_id(episode_match.group(1), parts[2]),
            )

    raise InvalidBilibiliIdentifierError("unsupported Bilibili URL: {}".format(value))


def _query_page(query):
    raw = parse_qs(query).get("p", [None])[0]
    if raw is None:
        return None
    try:
        return _validate_page(int(raw))
    except ValueError as exc:
        raise InvalidBilibiliIdentifierError("invalid video page: {}".format(raw)) from exc


def _validate_page(page):
    if page is None:
        return None
    try:
        page = int(page)
    except (TypeError, ValueError) as exc:
        raise InvalidBilibiliIdentifierError("video page must be an integer") from exc
    if page < 1:
        raise InvalidBilibiliIdentifierError("video page must be at least 1")
    return page


def _reject_page_for_non_video(page):
    if page is not None:
        raise InvalidBilibiliIdentifierError(
            "video page is only valid for BV input"
        )


def _parse_id(value, raw):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise InvalidBilibiliIdentifierError(
            "invalid Bilibili id: {}".format(raw)
        ) from exc
    if parsed < 1:
        raise InvalidBilibiliIdentifierError("Bilibili id must be greater than 0")
    return parsed

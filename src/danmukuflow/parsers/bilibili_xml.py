from pathlib import Path
import xml.etree.ElementTree as ET

from danmukuflow.models import Danmaku, DanmakuType


class DanmakuParseError(ValueError):
    pass


def parse_xml(path):
    path = Path(path)
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError as exc:
        raise DanmakuParseError("XML file parse error: {}".format(exc)) from exc

    return _parse_root(root)


def parse_xml_text(text):
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise DanmakuParseError("XML text parse error: {}".format(exc)) from exc

    return _parse_root(root)


def _parse_root(root):
    danmakus = []
    for elem in root.iter():
        if _local_name(elem.tag) != "d":
            continue
        p_attr = elem.attrib.get("p")
        if p_attr is None:
            raise DanmakuParseError("danmaku <d> element is missing p attribute")
        parsed = parse_p_attr(p_attr)
        if parsed is None:
            continue
        danmakus.append(
            Danmaku(
                timeline_s=parsed.timeline_s,
                content=elem.text or "",
                type=parsed.type,
                fontsize=parsed.fontsize,
                rgb=parsed.rgb,
                send_timestamp_ms=parsed.send_timestamp_ms,
                raw_fields=parsed.raw_fields,
            )
        )
    return danmakus


def parse_p_attr(p_attr):
    fields = tuple(p_attr.split(","))
    if len(fields) < 4:
        raise DanmakuParseError("p attribute must contain at least 4 fields")

    try:
        timeline_s = float(fields[0])
    except ValueError as exc:
        raise DanmakuParseError("invalid danmaku timeline: {!r}".format(fields[0])) from exc

    try:
        mode_num = int(fields[1])
    except ValueError as exc:
        raise DanmakuParseError("invalid danmaku mode: {!r}".format(fields[1])) from exc

    danmaku_type = DanmakuType.from_xml_num(mode_num)
    if danmaku_type is None:
        return None

    try:
        fontsize = int(fields[2])
    except ValueError as exc:
        raise DanmakuParseError("invalid danmaku font size: {!r}".format(fields[2])) from exc

    try:
        rgb_num = int(fields[3])
    except ValueError as exc:
        raise DanmakuParseError("invalid danmaku color: {!r}".format(fields[3])) from exc
    rgb = _parse_rgb(rgb_num)

    send_timestamp_ms = None
    if len(fields) >= 5 and fields[4] != "":
        try:
            send_timestamp_ms = int(fields[4])
        except ValueError as exc:
            raise DanmakuParseError(
                "invalid danmaku send timestamp: {!r}".format(fields[4])
            ) from exc

    return Danmaku(
        timeline_s=timeline_s,
        content="",
        type=danmaku_type,
        fontsize=fontsize,
        rgb=rgb,
        send_timestamp_ms=send_timestamp_ms,
        raw_fields=fields,
    )


def _parse_rgb(rgb):
    if rgb < 0:
        raise DanmakuParseError("invalid danmaku color: {}".format(rgb))

    if rgb >> 24 == 0:
        return ((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF)

    if rgb <= 255255255:
        return (
            ((rgb // 1000 // 1000) % 1000) & 0xFF,
            ((rgb // 1000) % 1000) & 0xFF,
            (rgb % 1000) & 0xFF,
        )

    raise DanmakuParseError("invalid danmaku color: {:x}".format(rgb))


def _local_name(tag):
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag

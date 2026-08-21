import pytest

from danmukuflow.models import DanmakuType
from danmukuflow.parsers.bilibili_xml import DanmakuParseError, parse_xml, parse_xml_text


def test_parse_xml_reads_danmaku_nodes_entities_and_bom(tmp_path):
    path = tmp_path / "sample.xml"
    path.write_bytes(
        (
            "\ufeff<i>"
            "<gift ts=\"1\" />"
            "<d p=\"0.581,1,25,14893055,1647777083220,0,398452452,0\">A&amp;B</d>"
            "<d p=\"2.000,4,30,16711680,1647777083221\">bottom</d>"
            "</i>"
        ).encode("utf-8")
    )

    danmakus = parse_xml(path)

    assert len(danmakus) == 2
    assert danmakus[0].timeline_s == 0.581
    assert danmakus[0].content == "A&B"
    assert danmakus[0].type is DanmakuType.FLOAT
    assert danmakus[0].fontsize == 25
    assert danmakus[0].rgb == (0xE3, 0x3F, 0xFF)
    assert danmakus[0].send_timestamp_ms == 1647777083220
    assert danmakus[1].type is DanmakuType.BOTTOM


def test_parse_modes_and_unknown_modes_are_skipped():
    danmakus = parse_xml_text(
        "<i>"
        "<d p=\"1,1,25,0\">float</d>"
        "<d p=\"2,4,25,0\">bottom</d>"
        "<d p=\"3,5,25,0\">top</d>"
        "<d p=\"4,6,25,0\">reverse</d>"
        "<d p=\"5,9,25,0\">unknown</d>"
        "</i>"
    )

    assert [item.type for item in danmakus] == [
        DanmakuType.FLOAT,
        DanmakuType.BOTTOM,
        DanmakuType.TOP,
        DanmakuType.REVERSE,
    ]


@pytest.mark.parametrize(
    "xml",
    [
        "<i><d>missing p</d></i>",
        "<i><d p=\"1,1,25\">too few</d></i>",
        "<i><d p=\"x,1,25,0\">bad time</d></i>",
        "<i><d p=\"1,x,25,0\">bad mode</d></i>",
        "<i><d p=\"1,1,x,0\">bad size</d></i>",
        "<i><d p=\"1,1,25,x\">bad color</d></i>",
        "<i><d p=\"1,1,25,999999999\">bad color</d></i>",
        "<i><d p=\"1,1,25,0,bad\">bad ts</d></i>",
        "<i><d p=\"1,1,25,0\">broken</i>",
    ],
)
def test_parse_invalid_xml_or_attributes_raise(xml):
    with pytest.raises(DanmakuParseError):
        parse_xml_text(xml)


def test_parse_decimal_rgb_and_empty_danmaku():
    danmakus = parse_xml_text(
        "<i>"
        "<d p=\"1036.83700,1,25,255255255,1764772645\">white</d>"
        "<d p=\"2,1,25,0\" />"
        "</i>"
    )

    assert danmakus[0].rgb == (255, 255, 255)
    assert danmakus[1].content == ""


def test_empty_xml_has_no_danmakus():
    assert parse_xml_text("<i></i>") == []

import os

from danmukuflow.models import RenderConfig
from danmukuflow.services import convert_xml_to_ass


def test_convert_xml_to_ass_writes_file_and_counts(tmp_path):
    xml_path = tmp_path / "input.xml"
    ass_path = tmp_path / "output.ass"
    xml_path.write_text(
        "<i>"
        "<d p=\"0,1,25,16711680\">red</d>"
        "<d p=\"1,5,25,65280\">top</d>"
        "</i>",
        encoding="utf-8",
    )

    result = convert_xml_to_ass(
        xml_path,
        ass_path,
        RenderConfig(width=100, height=100, lane_size=50, float_percentage=1.0),
    )

    assert result.input_path == xml_path
    assert result.output_path == ass_path
    assert result.parsed_count == 2
    assert result.rendered_count == 2
    assert result.skipped_count == 0
    assert result.skipped_due_to_newer_output is False
    content = ass_path.read_text(encoding="utf-8")
    assert "Title: input" in content
    assert "red" in content
    assert "top" in content


def test_convert_skips_when_output_is_newer_and_force_overrides(tmp_path):
    xml_path = tmp_path / "input.xml"
    ass_path = tmp_path / "output.ass"
    xml_path.write_text("<i><d p=\"0,1,25,0\">fresh</d></i>", encoding="utf-8")
    ass_path.write_text("old output", encoding="utf-8")
    os.utime(xml_path, (100, 100))
    os.utime(ass_path, (200, 200))

    skipped = convert_xml_to_ass(xml_path, ass_path)

    assert skipped.skipped_due_to_newer_output is True
    assert skipped.parsed_count == 0
    assert ass_path.read_text(encoding="utf-8") == "old output"

    forced = convert_xml_to_ass(xml_path, ass_path, force=True)

    assert forced.skipped_due_to_newer_output is False
    assert forced.parsed_count == 1
    assert "fresh" in ass_path.read_text(encoding="utf-8")

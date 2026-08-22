import pytest

from danmukuflow.models import RenderConfig, SeasonSource, XMLSource
from danmukuflow.services import (
    DanmakuContentError,
    ExportRequest,
    ExportService,
    InputNotFoundError,
    InvalidXmlError,
    OutputDirectoryError,
    OutputWriteError,
    UnsupportedSourceError,
)


def write_xml(path, content="hello"):
    path.write_text(
        '<i><d p="0,1,25,16711680">{}</d></i>'.format(content),
        encoding="utf-8",
    )


def test_export_service_converts_xml_with_default_output(tmp_path):
    xml_path = tmp_path / "input.xml"
    write_xml(xml_path)

    result = ExportService().export(
        ExportRequest(
            source=XMLSource(xml_path),
            render_config=RenderConfig(width=100, height=100, lane_size=50),
        )
    )

    assert result.success is True
    assert result.output_path == tmp_path / "input.ass"
    assert result.danmaku_count == 1
    assert result.metadata["source_type"] == "xml"
    assert result.metadata["parsed_count"] == 1
    assert result.metadata["rendered_count"] == 1
    assert result.metadata["skipped_count"] == 0
    assert "hello" in result.output_path.read_text(encoding="utf-8")


def test_export_service_converts_xml_with_specified_output_and_creates_parent(tmp_path):
    xml_path = tmp_path / "input.xml"
    output_path = tmp_path / "nested" / "result.ass"
    write_xml(xml_path)

    result = ExportService().export(
        ExportRequest(source=XMLSource(xml_path), output_path=output_path)
    )

    assert result.output_path == output_path
    assert output_path.exists()


def test_export_service_maps_missing_input():
    with pytest.raises(InputNotFoundError) as exc_info:
        ExportService().export(ExportRequest(source=XMLSource("missing.xml")))

    assert exc_info.value.__cause__ is None


def test_export_service_maps_invalid_xml(tmp_path):
    xml_path = tmp_path / "broken.xml"
    xml_path.write_text('<i><d p="0,1,25,0">broken</i>', encoding="utf-8")

    with pytest.raises(InvalidXmlError) as exc_info:
        ExportService().export(ExportRequest(source=XMLSource(xml_path)))

    assert exc_info.value.__cause__ is not None


def test_export_service_maps_danmaku_content_error(tmp_path):
    xml_path = tmp_path / "bad-content.xml"
    xml_path.write_text('<i><d p="bad,1,25,0">broken</d></i>', encoding="utf-8")

    with pytest.raises(DanmakuContentError) as exc_info:
        ExportService().export(ExportRequest(source=XMLSource(xml_path)))

    assert exc_info.value.__cause__ is not None


def test_export_service_maps_output_directory_creation_failure(tmp_path):
    xml_path = tmp_path / "input.xml"
    blocker = tmp_path / "blocked"
    write_xml(xml_path)
    blocker.write_text("not a directory", encoding="utf-8")

    with pytest.raises(OutputDirectoryError) as exc_info:
        ExportService().export(
            ExportRequest(
                source=XMLSource(xml_path),
                output_path=blocker / "result.ass",
            )
        )

    assert exc_info.value.__cause__ is not None


def test_export_service_maps_output_write_failure(tmp_path):
    xml_path = tmp_path / "input.xml"
    output_dir = tmp_path / "out.ass"
    write_xml(xml_path)
    output_dir.mkdir()

    with pytest.raises(OutputWriteError) as exc_info:
        ExportService().export(
            ExportRequest(source=XMLSource(xml_path), output_path=output_dir)
        )

    assert exc_info.value.__cause__ is not None


def test_export_service_rejects_reserved_sources():
    with pytest.raises(UnsupportedSourceError):
        ExportService().export(ExportRequest(source=object()))


def test_export_service_rejects_season_export():
    with pytest.raises(UnsupportedSourceError):
        ExportService().export(ExportRequest(source=SeasonSource(123)))

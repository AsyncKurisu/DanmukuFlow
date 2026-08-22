import inspect

import danmukuflow.cli as cli
from danmukuflow.models import BVSource, XMLSource
from danmukuflow.services import ExportRequest, ExportResult, ExportService


def write_xml(path, content="hello"):
    path.write_text(
        '<i><d p="0,1,25,16711680">{}</d></i>'.format(content),
        encoding="utf-8",
    )


def test_cli_convert_uses_default_output(tmp_path, capsys):
    xml_path = tmp_path / "input.xml"
    write_xml(xml_path)

    exit_code = cli.main(["convert", str(xml_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert (tmp_path / "input.ass").exists()
    assert "Converted 1 danmaku" in captured.out
    assert captured.err == ""


def test_cli_convert_uses_specified_output(tmp_path, capsys):
    xml_path = tmp_path / "input.xml"
    output_path = tmp_path / "output" / "result.ass"
    write_xml(xml_path)

    exit_code = cli.main(["convert", str(xml_path), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert output_path.exists()
    assert str(output_path) in captured.out


def test_cli_missing_xml_returns_nonzero(tmp_path, capsys):
    exit_code = cli.main(["convert", str(tmp_path / "missing.xml")])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "input file not found" in captured.err


def test_cli_invalid_xml_returns_nonzero(tmp_path, capsys):
    xml_path = tmp_path / "broken.xml"
    xml_path.write_text('<i><d p="0,1,25,0">broken</i>', encoding="utf-8")

    exit_code = cli.main(["convert", str(xml_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "invalid XML" in captured.err


def test_cli_output_failure_returns_nonzero(tmp_path, capsys):
    xml_path = tmp_path / "input.xml"
    output_path = tmp_path / "out.ass"
    write_xml(xml_path)
    output_path.mkdir()

    exit_code = cli.main(["convert", str(xml_path), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "output write error" in captured.err


def test_cli_output_matches_export_service(tmp_path, capsys):
    xml_path = tmp_path / "input.xml"
    cli_output = tmp_path / "cli.ass"
    service_output = tmp_path / "service.ass"
    write_xml(xml_path, "same")

    assert cli.main(["convert", str(xml_path), "--output", str(cli_output)]) == 0
    capsys.readouterr()
    ExportService().export(
        ExportRequest(source=XMLSource(xml_path), output_path=service_output)
    )

    assert cli_output.read_text(encoding="utf-8") == service_output.read_text(
        encoding="utf-8"
    )


def test_cli_does_not_import_parser_renderer_or_layout_modules():
    source = inspect.getsource(cli)

    assert "danmukuflow.parsers" not in source
    assert "danmukuflow.renderers" not in source
    assert "danmukuflow.core" not in source


def test_cli_builds_bv_request_with_page_and_output(monkeypatch, tmp_path, capsys):
    captured = {}

    class FakeExportService:
        def export(self, request):
            captured["request"] = request
            return ExportResult(
                success=True,
                output_path=tmp_path / "result.ass",
                danmaku_count=2,
                metadata={"source_type": "bv"},
            )

    monkeypatch.setattr(cli, "ExportService", FakeExportService)

    exit_code = cli.main(
        [
            "convert",
            "BV1z44y1E7m6",
            "--page",
            "2",
            "--output",
            str(tmp_path / "result.ass"),
        ]
    )

    captured_output = capsys.readouterr()
    assert exit_code == 0
    assert isinstance(captured["request"].source, BVSource)
    assert captured["request"].source.page == 2
    assert captured["request"].output_path == tmp_path / "result.ass"
    assert "Converted 2 danmaku" in captured_output.out


def test_cli_reports_ss_export_is_not_supported(capsys):
    exit_code = cli.main(["convert", "ss123"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "season parsing only" in captured.err

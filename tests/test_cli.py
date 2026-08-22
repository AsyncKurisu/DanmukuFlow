import inspect

import danmukuflow.cli as cli
from danmukuflow.models import XMLSource
from danmukuflow.services import ExportRequest, ExportService


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

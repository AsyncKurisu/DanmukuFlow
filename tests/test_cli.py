import inspect
from pathlib import Path

import danmukuflow.cli as cli
from danmukuflow.models import (
    BVSource,
    BatchExportItem,
    BatchExportResult,
    BatchItemStatus,
    ConflictPolicy,
    SeasonSource,
    XMLSource,
)
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


def test_cli_batch_builds_request_and_reports_summary(
    monkeypatch, tmp_path, capsys
):
    captured = {}

    class FakeBatchExportService:
        def export(self, request):
            captured["request"] = request
            return BatchExportResult(
                total=3,
                matched=2,
                selected=2,
                succeeded=1,
                failed=0,
                skipped=1,
                unmatched_local=1,
                unmatched_episode=0,
                ambiguous=0,
            )

    monkeypatch.setattr(cli, "BatchExportService", FakeBatchExportService)

    exit_code = cli.main(
        [
            "batch",
            "ss123",
            "--video-dir",
            str(tmp_path),
            "--episodes",
            "1,3-5,8",
            "--concurrency",
            "2",
            "--overwrite",
        ]
    )

    captured_output = capsys.readouterr()
    request = captured["request"]
    assert exit_code == 0
    assert request.source == SeasonSource(123)
    assert request.video_dir == tmp_path
    assert request.episodes == "1,3-5,8"
    assert request.concurrency == 2
    assert request.conflict_policy is ConflictPolicy.OVERWRITE
    assert "succeeded=1" in captured_output.out
    assert "skipped=1" in captured_output.out


def test_cli_batch_with_output_dir_uses_directory_mode(monkeypatch, tmp_path, capsys):
    captured = {}

    class FakeBatchExportService:
        def export(self, request):
            captured["request"] = request
            return BatchExportResult(
                total=1,
                matched=1,
                selected=1,
                succeeded=1,
                failed=0,
                skipped=0,
                unmatched_local=0,
                unmatched_episode=0,
                ambiguous=0,
            )

    monkeypatch.setattr(cli, "BatchExportService", FakeBatchExportService)

    exit_code = cli.main(
        [
            "batch",
            "ss123",
            "--output-dir",
            str(tmp_path),
            "--episodes",
            "1",
        ]
    )

    capsys.readouterr()
    request = captured["request"]
    assert exit_code == 0
    assert request.video_dir is None
    assert request.output_config is not None
    assert request.output_config.output_dir == tmp_path


def test_cli_batch_returns_nonzero_for_episode_failure(
    monkeypatch, tmp_path, capsys
):
    class FakeBatchExportService:
        def export(self, request):
            return BatchExportResult(
                total=1,
                matched=1,
                selected=1,
                succeeded=0,
                failed=1,
                skipped=0,
                unmatched_local=0,
                unmatched_episode=0,
                ambiguous=0,
                items=(
                    BatchExportItem(
                        episode_id=456,
                        display_number=2,
                        episode_title="2",
                        local_video_path=tmp_path / "[02].mkv",
                        output_path=tmp_path / "[02].ass",
                        status=BatchItemStatus.FAILED,
                        error=RuntimeError("download failed"),
                    ),
                ),
            )

    monkeypatch.setattr(cli, "BatchExportService", FakeBatchExportService)

    exit_code = cli.main(
        ["batch", "ss123", "--video-dir", str(tmp_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "failed=1" in captured.out
    assert "Failed episode 2" in captured.err


def test_cli_batch_defaults_video_directory_to_current_directory(
    monkeypatch, tmp_path, capsys
):
    captured = {}

    class FakeBatchExportService:
        def export(self, request):
            captured["request"] = request
            return BatchExportResult(
                total=0,
                matched=0,
                selected=0,
                succeeded=0,
                failed=0,
                skipped=0,
                unmatched_local=0,
                unmatched_episode=0,
                ambiguous=0,
            )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "BatchExportService", FakeBatchExportService)

    assert cli.main(["batch", "ss123"]) == 0
    capsys.readouterr()
    assert captured["request"].video_dir == Path(".")

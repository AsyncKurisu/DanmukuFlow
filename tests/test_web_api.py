import io
import importlib
import zipfile
from types import SimpleNamespace
from pathlib import Path
from urllib.parse import unquote

import pytest

from fastapi.testclient import TestClient

from danmukuflow.models import (
    Danmaku,
    DanmakuType,
    Episode,
    OutputArtifact,
    OutputConfig,
    OutputMode,
    Season,
    TemplateContext,
)
from danmukuflow.bilibili.credentials import BilibiliCredentials
from danmukuflow.services import OutputPathEscapeError, OutputService
from danmukuflow.web import create_app
from danmukuflow.web.app import DirectoryPickerUnavailableError


class FakeBilibiliService:
    def __init__(self):
        self.client = SimpleNamespace(
            credentials=BilibiliCredentials(),
            set_cookie=self._set_cookie,
        )
        self.video = SimpleNamespace(
            bvid="BV1",
            title="Demo Video",
            pages=[
                SimpleNamespace(page=1, part="P1", cid=101, duration_s=1.0),
                SimpleNamespace(page=2, part="P2", cid=102, duration_s=1.0),
            ],
        )
        self.season = Season(
            season_id=1,
            title="Demo Season",
            episodes=[
                Episode(
                    episode_id=11,
                    aid=1,
                    bvid="BV1",
                    cid=201,
                    title="Episode 1",
                    long_title="Long 1",
                    duration_s=1.0,
                    display_number=1,
                ),
                Episode(
                    episode_id=22,
                    aid=2,
                    bvid="BV2",
                    cid=202,
                    title="Episode 2",
                    long_title="Long 2",
                    duration_s=1.0,
                    display_number=2,
                ),
            ],
        )

    def _set_cookie(self, cookie):
        self.client.credentials = BilibiliCredentials.from_cookie(cookie)

    def resolve_video(self, source):
        return self.video

    def resolve_episode(self, source):
        return self.season, self.season.episodes[1]

    def resolve_season(self, source):
        return self.season

    def fetch_danmaku_with_stats(self, cid, duration_s):
        return SimpleNamespace(
            danmakus=[
                Danmaku(
                    timeline_s=0,
                    content="hello {}".format(cid),
                    type=DanmakuType.FLOAT,
                    fontsize=25,
                    rgb=(1, 2, 3),
                )
            ],
            segment_count=1,
            skipped_count=0,
        )


class PartiallyFailingBilibiliService(FakeBilibiliService):
    def fetch_danmaku_with_stats(self, cid, duration_s):
        if cid == 202:
            raise RuntimeError("episode 2 failed")
        return super().fetch_danmaku_with_stats(cid, duration_s)


def test_output_service_renders_safe_nested_paths(tmp_path):
    service = OutputService(allowed_output_roots=(tmp_path,))
    context = TemplateContext(
        season_title="Season",
        episode_no=1,
        episode_title="Episode",
        episode_id=11,
    )

    artifact = service.materialize_text(
        "hello",
        output_config=OutputConfig(
            output_dir=tmp_path,
            naming_template="{season_title}/{episode_no}_{episode_title}.ass",
            mode=OutputMode.DIRECTORY,
            allowed_output_roots=(tmp_path,),
        ),
        context=context,
        default_template="{season_title}.ass",
        metadata={"kind": "demo"},
    )

    assert artifact.path == tmp_path / "Season" / "1_Episode.ass"
    assert artifact.path.exists()
    assert artifact.metadata["kind"] == "demo"


def test_output_service_rejects_path_escape(tmp_path):
    service = OutputService(allowed_output_roots=(tmp_path,))
    with pytest.raises(OutputPathEscapeError):
        service.materialize_text(
            "hello",
            output_config=OutputConfig(
                output_dir=tmp_path,
                naming_template="../escape.ass",
                mode=OutputMode.DIRECTORY,
                allowed_output_roots=(tmp_path,),
            ),
            context=TemplateContext(),
            default_template="{input_stem}.ass",
        )


def test_output_service_sanitizes_template_values_and_empty_variables(tmp_path):
    service = OutputService(allowed_output_roots=(tmp_path,))
    artifact = service.materialize_text(
        "hello",
        output_config=OutputConfig(
            output_dir=tmp_path,
            naming_template="{season_title}/{episode_title}.ass",
            mode=OutputMode.DIRECTORY,
            allowed_output_roots=(tmp_path,),
        ),
        context=TemplateContext(
            season_title="Season/One",
            episode_title=None,
        ),
        default_template="{input_stem}.ass",
    )

    assert artifact.path == tmp_path / "Season_One" / "danmaku.ass"
    assert artifact.path.exists()


def test_web_resolve_and_export_and_batch_download(tmp_path):
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)

    resolve = client.post("/api/resolve", json={"input": "BV1", "page": 1})
    assert resolve.status_code == 200
    assert resolve.json()["video"]["title"] == "Demo Video"

    season_resolve = client.post("/api/seasons/resolve", json={"input": "ss1"})
    assert season_resolve.status_code == 200
    assert season_resolve.json()["season"]["title"] == "Demo Season"

    export = client.post(
        "/api/exports",
        json={
            "input": "BV1",
            "page": 1,
            "output_dir": str(tmp_path),
            "naming_template": "{video_title}.ass",
            "conflict_policy": "overwrite",
            "render_config": {},
        },
    )
    assert export.status_code == 200
    payload = export.json()
    assert payload["success"] is True
    assert Path(payload["output_path"]).exists()

    batch = client.post(
        "/api/batch-exports",
        json={
            "season_id": 1,
            "selected_episode_ids": [11, 22],
            "output_dir": str(tmp_path),
            "naming_template": "{season_title}/{episode_no}_{episode_title}.ass",
            "conflict_policy": "overwrite",
            "concurrency": 2,
            "render_config": {},
        },
    )
    assert batch.status_code == 200
    batch_payload = batch.json()
    assert batch_payload["succeeded"] == 2
    assert len(batch_payload["items"]) == 2


def test_web_bilibili_settings_persist_and_apply_cookie(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setenv("DANMUKUFLOW_ENV_FILE", str(env_path))
    service = FakeBilibiliService()
    client = TestClient(create_app(bilibili_service=service))

    assert client.get("/api/settings/bilibili").json() == {
        "configured": False,
        "cookie_count": 0,
    }
    response = client.put(
        "/api/settings/bilibili",
        json={"cookie": "SESSDATA=session; buvid3=device"},
    )

    assert response.status_code == 200
    assert response.json() == {"configured": True, "cookie_count": 2}
    assert service.client.credentials.cookie_header == (
        "SESSDATA=session; buvid3=device"
    )
    assert "SESSDATA=session" in env_path.read_text(encoding="utf-8")


def test_web_bilibili_settings_reject_invalid_cookie(tmp_path, monkeypatch):
    monkeypatch.setenv("DANMUKUFLOW_ENV_FILE", str(tmp_path / ".env"))
    client = TestClient(create_app(bilibili_service=FakeBilibiliService()))

    response = client.put(
        "/api/settings/bilibili",
        json={"cookie": "bili_jct=csrf"},
    )

    assert response.status_code == 422
    assert "SESSDATA" in response.json()["detail"]


def test_web_directory_picker_returns_selected_path(tmp_path, monkeypatch):
    web_app = importlib.import_module("danmukuflow.web.app")
    selected = tmp_path / "selected"
    selected.mkdir()
    monkeypatch.setattr(web_app, "_pick_directory", lambda kind: selected)

    client = TestClient(create_app())

    response = client.post(
        "/api/directories/select",
        json={"kind": "output"},
    )

    assert response.status_code == 200
    assert response.json() == {"path": str(selected.resolve())}


def test_web_directory_picker_cancel_keeps_request_empty(monkeypatch):
    web_app = importlib.import_module("danmukuflow.web.app")
    monkeypatch.setattr(web_app, "_pick_directory", lambda kind: None)

    response = TestClient(create_app()).post(
        "/api/directories/select",
        json={"kind": "video"},
    )

    assert response.status_code == 204
    assert response.content == b""


def test_web_directory_picker_unavailable_returns_service_error(monkeypatch):
    web_app = importlib.import_module("danmukuflow.web.app")

    def unavailable(kind):
        raise DirectoryPickerUnavailableError("native directory picker is unavailable")

    monkeypatch.setattr(web_app, "_pick_directory", unavailable)

    response = TestClient(create_app()).post(
        "/api/directories/select",
        json={"kind": "output"},
    )

    assert response.status_code == 503
    assert "native directory picker" in response.json()["detail"]


def test_web_default_allows_output_directory_outside_project_root(tmp_path):
    output_dir = tmp_path / "test_ss"
    app = create_app(bilibili_service=FakeBilibiliService())

    response = TestClient(app).post(
        "/api/batch-exports",
        json={
            "season_id": 1,
            "selected_episode_ids": [11],
            "output_dir": str(output_dir),
            "conflict_policy": "overwrite",
            "render_config": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["succeeded"] == 1
    output_path = Path(payload["items"][0]["output_path"])
    assert output_path == output_dir / "Demo Season-1.ass"
    assert output_path.exists()
    assert not (output_dir / "Demo Season").exists()


def test_web_download_responses_use_attachments(tmp_path):
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)

    single = client.post(
        "/api/exports",
        json={
            "input": "BV1",
            "page": 1,
            "render_config": {},
        },
    )
    assert single.status_code == 200
    assert single.headers["Content-Disposition"].startswith("attachment;")
    assert "filename*=UTF-8''" in single.headers["Content-Disposition"]
    assert "filename*=UTF-8''Demo%20Video-1.ass" in single.headers["Content-Disposition"]

    batch = client.post(
        "/api/batch-exports",
        json={
            "season_id": 1,
            "selected_episode_ids": [11, 22],
            "render_config": {},
        },
    )
    assert batch.status_code == 200
    assert batch.headers["Content-Disposition"].startswith("attachment;")
    assert "filename*=UTF-8''season-1.zip" in batch.headers["Content-Disposition"]
    assert batch.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(batch.content)) as archive:
        assert archive.namelist() == [
            "Demo Season-1.ass",
            "Demo Season-2.ass",
        ]


def test_web_single_page_bv_download_omits_page_suffix(tmp_path):
    bilibili_service = FakeBilibiliService()
    bilibili_service.video.pages = [
        SimpleNamespace(page=1, part="P1", cid=101, duration_s=1.0),
    ]
    app = create_app(
        bilibili_service=bilibili_service,
        allowed_output_roots=(tmp_path,),
    )

    response = TestClient(app).post(
        "/api/exports",
        json={
            "input": "BV1",
            "page": 1,
            "render_config": {},
        },
    )

    assert response.status_code == 200
    assert "filename*=UTF-8''Demo%20Video.ass" in response.headers["Content-Disposition"]


def test_web_partial_batch_download_contains_successes_and_manifest(tmp_path):
    app = create_app(
        bilibili_service=PartiallyFailingBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    response = TestClient(app).post(
        "/api/batch-exports",
        json={
            "season_id": 1,
            "selected_episode_ids": [11, 22],
            "render_config": {},
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-danmukuflow-partial"] == "true"
    assert response.headers["x-danmukuflow-failed-count"] == "1"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["Demo Season-1.ass", "batch-result.json"]
        manifest = __import__("json").loads(
            archive.read("batch-result.json").decode("utf-8")
        )
    assert manifest["succeeded"] == 1
    assert manifest["failed"] == 1
    assert manifest["items"][0]["reason"] == "episode 2 failed"


def test_web_custom_batch_template_keeps_episode_id_and_subdirectories(tmp_path):
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    response = TestClient(app).post(
        "/api/batch-exports",
        json={
            "season_id": 1,
            "selected_episode_ids": [11],
            "output_dir": str(tmp_path),
            "naming_template": "{season_title}/{episode_no}_{episode_id}.ass",
            "render_config": {},
        },
    )

    assert response.status_code == 200
    assert Path(response.json()["items"][0]["output_path"]) == (
        tmp_path / "Demo Season" / "1_11.ass"
    )


def test_web_download_supports_unicode_filenames(tmp_path):
    bilibili_service = FakeBilibiliService()
    bilibili_service.video.title = "中文视频"
    app = create_app(
        bilibili_service=bilibili_service,
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)

    response = client.post(
        "/api/exports",
        json={
            "input": "BV1",
            "page": 1,
            "naming_template": "{video_title}.ass",
            "render_config": {},
        },
    )

    assert response.status_code == 200
    disposition = response.headers["Content-Disposition"]
    assert 'filename="download.ass"' in disposition
    encoded = disposition.split("filename*=UTF-8''", 1)[1]
    assert unquote(encoded) == "中文视频.ass"


def test_web_file_access_uses_registry(tmp_path):
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)

    export = client.post(
        "/api/exports",
        json={
            "input": "BV1",
            "page": 1,
            "output_dir": str(tmp_path),
            "naming_template": "{video_title}.ass",
            "conflict_policy": "overwrite",
            "render_config": {},
        },
    )
    artifact_id = export.json()["artifact"]["artifact_id"]

    response = client.get("/api/files/{}".format(artifact_id))
    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith("attachment;")


def test_web_file_access_supports_unicode_memory_artifacts(tmp_path):
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)
    artifact = OutputArtifact(
        artifact_id="unicode",
        filename="中文.ass",
        content=b"[Script Info]\n",
    )
    app.state.output_service.registry.register(artifact)

    response = client.get("/api/files/unicode")

    assert response.status_code == 200
    disposition = response.headers["Content-Disposition"]
    assert 'filename="download.ass"' in disposition
    encoded = disposition.split("filename*=UTF-8''", 1)[1]
    assert unquote(encoded) == "中文.ass"


def test_web_file_access_rejects_paths_outside_allowed_roots(tmp_path):
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)
    outside = tmp_path.parent / "outside.ass"
    artifact = OutputArtifact(
        artifact_id="outside",
        filename="outside.ass",
        path=outside,
    )
    app.state.output_service.registry.register(artifact)

    response = client.get("/api/files/outside")
    assert response.status_code == 404


def test_web_xml_upload_returns_ass_attachment(tmp_path):
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)

    response = client.post(
        "/api/exports",
        files={
            "xml_file": (
                "uploaded.xml",
                b'<i><d p="0,1,25,16711680">uploaded</d></i>',
                "application/xml",
            )
        },
        data={"render_config": "{}"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert b"uploaded" in response.content


def test_web_batch_video_dir_uses_local_video_output_and_real_episode_ids(
    tmp_path,
):
    (tmp_path / "[Show] [01].mkv").write_text("", encoding="utf-8")
    (tmp_path / "[Show] [09].mkv").write_text("", encoding="utf-8")
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)

    response = client.post(
        "/api/batch-exports",
        json={
            "season_id": 1,
            "selected_episode_ids": [11, 22],
            "video_dir": str(tmp_path),
            "conflict_policy": "overwrite",
            "concurrency": 1,
            "render_config": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["succeeded"] == 1
    assert payload["unmatched_local"] == 1
    assert payload["unmatched_episode"] == 1
    statuses = {item["status"] for item in payload["items"]}
    assert "succeeded" in statuses
    assert "unmatched_local" in statuses
    assert "unmatched_episode" in statuses
    assert (tmp_path / "[Show] [01].ass").exists()
    assert not (tmp_path / "[Show] [09].ass").exists()


def test_web_batch_rejects_video_and_output_dirs_together(tmp_path):
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)

    response = client.post(
        "/api/batch-exports",
        json={
            "season_id": 1,
            "selected_episode_ids": [11],
            "video_dir": str(tmp_path),
            "output_dir": str(tmp_path / "out"),
            "render_config": {},
        },
    )

    assert response.status_code == 422
    assert "cannot be used together" in response.json()["detail"]


def test_web_batch_rejects_episode_not_in_season(tmp_path):
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)

    response = client.post(
        "/api/batch-exports",
        json={
            "season_id": 1,
            "selected_episode_ids": [999],
            "render_config": {},
        },
    )

    assert response.status_code == 400
    assert "do not belong to this season" in response.json()["detail"]


def test_web_batch_rejects_output_outside_allowed_roots(tmp_path):
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
    )
    client = TestClient(app)

    response = client.post(
        "/api/batch-exports",
        json={
            "season_id": 1,
            "selected_episode_ids": [11],
            "output_dir": str(tmp_path.parent / "outside"),
            "render_config": {},
        },
    )

    assert response.status_code == 400
    assert "allowed output roots" in response.json()["detail"]


def test_web_static_frontend_can_be_served(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<html><body>DanmukuFlow</body></html>",
        encoding="utf-8",
    )
    app = create_app(
        bilibili_service=FakeBilibiliService(),
        allowed_output_roots=(tmp_path,),
        frontend_dist_dir=dist,
    )
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "DanmukuFlow" in response.text

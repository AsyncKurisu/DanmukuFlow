import io
import zipfile
from types import SimpleNamespace
from pathlib import Path

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
from danmukuflow.services import OutputPathEscapeError, OutputService
from danmukuflow.web import create_app


class FakeBilibiliService:
    def __init__(self):
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
    assert batch.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(batch.content)) as archive:
        assert archive.namelist() == [
            "Demo Season/1_Episode 1_11.ass",
            "Demo Season/2_Episode 2_22.ass",
        ]


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

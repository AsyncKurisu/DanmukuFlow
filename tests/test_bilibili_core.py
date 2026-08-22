import json

import httpx
import pytest

from danmukuflow.bilibili.client import BilibiliClient, HttpResponse
from danmukuflow.bilibili.service import BilibiliService
from danmukuflow.models import (
    BVSource,
    DanmakuType,
    Episode,
    EpisodeSource,
    Season,
    SeasonSource,
    Video,
    VideoPage,
)
from danmukuflow.parsers import parse_bilibili_identifier, source_from_input
from danmukuflow.services import (
    BilibiliApiError,
    BilibiliDecodeError,
    EpisodeNotFoundError,
    ExportRequest,
    ExportService,
    PageNotFoundError,
    SeasonNotFoundError,
    SeasonExportUnsupportedError,
    VideoNotFoundError,
)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, params=None, headers=None, timeout=10.0):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def json_response(payload, status_code=200):
    return HttpResponse(
        status_code=status_code,
        headers={"content-type": "application/json"},
        content=json.dumps(payload).encode("utf-8"),
    )


def varint(value):
    output = bytearray()
    while value >= 0x80:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


def protobuf_field(number, wire_type, value):
    key = varint((number << 3) | wire_type)
    if wire_type == 0:
        return key + varint(value)
    if wire_type == 2:
        return key + varint(len(value)) + value
    raise AssertionError("test helper only supports varint and bytes fields")


def protobuf_elem(progress, mode, fontsize, color, content, ctime):
    body = b"".join(
        [
            protobuf_field(2, 0, progress),
            protobuf_field(3, 0, mode),
            protobuf_field(4, 0, fontsize),
            protobuf_field(5, 0, color),
            protobuf_field(7, 2, content.encode("utf-8")),
            protobuf_field(8, 0, ctime),
        ]
    )
    return protobuf_field(1, 2, body)


def protobuf_reply(*elements):
    return b"".join(elements)


def test_bilibili_identifier_parser_supports_ids_urls_and_pages():
    assert parse_bilibili_identifier("BV1z44y1E7m6").kind == "BV"
    assert parse_bilibili_identifier("ss28296").value == 28296
    assert parse_bilibili_identifier("ep473502").kind == "EPISODE"

    parsed = parse_bilibili_identifier(
        "https://www.bilibili.com/video/BV1z44y1E7m6?p=2"
    )
    assert parsed.value == "BV1z44y1E7m6"
    assert parsed.page == 2

    assert source_from_input("https://www.bilibili.com/bangumi/play/ss28296") == SeasonSource(
        28296
    )
    assert source_from_input("https://www.bilibili.com/bangumi/play/ep473502") == EpisodeSource(
        473502
    )

    with pytest.raises(Exception):
        parse_bilibili_identifier("https://example.com/video/BV1z44y1E7m6")

    with pytest.raises(Exception):
        parse_bilibili_identifier("ss28296", page=2)


def test_bilibili_service_resolves_video_and_page():
    transport = FakeTransport(
        [
            json_response(
                {
                    "code": 0,
                    "data": {
                        "bvid": "BV1z44y1E7m6",
                        "title": "Demo",
                        "pages": [
                            {"page": 1, "part": "Part 1", "cid": 101, "duration": 12},
                            {"page": 2, "part": "Part 2", "cid": 102, "duration": 34},
                        ],
                    },
                }
            )
        ]
    )
    service = BilibiliService(BilibiliClient(transport=transport, max_attempts=1))

    video = service.resolve_video(BVSource("BV1z44y1E7m6"))

    assert video.title == "Demo"
    assert video.pages[1].cid == 102
    assert transport.calls[0]["params"] == {"bvid": "BV1z44y1E7m6"}


def test_bilibili_service_resolves_episode_by_exact_id():
    transport = FakeTransport(
        [
            json_response(
                {
                    "code": 0,
                    "result": {
                        "season_id": 88,
                        "season_title": "Season",
                        "episodes": [
                            {
                                "id": 10,
                                "aid": 20,
                                "bvid": "BV1",
                                "cid": 30,
                                "title": "Episode 1",
                                "long_title": "Long 1",
                                "duration": 120000,
                            },
                            {
                                "id": 20,
                                "aid": 21,
                                "bvid": "BV2",
                                "cid": 31,
                                "title": "Episode 2",
                                "long_title": "Long 2",
                                "duration": 130000,
                            },
                        ],
                    },
                }
            )
        ]
    )
    service = BilibiliService(BilibiliClient(transport=transport, max_attempts=1))

    season, episode = service.resolve_episode(EpisodeSource(20))

    assert season.season_id == 88
    assert episode.episode_id == 20
    assert episode.cid == 31
    assert episode.duration_s == 130.0
    assert transport.calls[0]["params"] == {"ep_id": 20}

    transport.responses.append(
        json_response(
            {
                "code": 0,
                "result": {
                    "season_id": 88,
                    "season_title": "Season",
                    "episodes": [],
                },
            }
        )
    )
    with pytest.raises(EpisodeNotFoundError):
        service.resolve_episode(EpisodeSource(20))


def test_bilibili_service_resolves_season_source():
    transport = FakeTransport(
        [
            json_response(
                {
                    "code": 0,
                    "result": {
                        "season_id": 88,
                        "season_title": "Season",
                        "episodes": [
                            {
                                "id": 20,
                                "aid": 21,
                                "bvid": "BV2",
                                "cid": 31,
                                "title": "Episode",
                                "long_title": "Long",
                                "duration": 130000,
                            }
                        ],
                    },
                }
            )
        ]
    )
    service = BilibiliService(BilibiliClient(transport=transport, max_attempts=1))

    season = service.resolve_season(SeasonSource(88))

    assert season.season_id == 88
    assert len(season.episodes) == 1
    assert season.episodes[0].episode_id == 20
    assert transport.calls[0]["params"] == {"season_id": 88}


def test_bilibili_service_fetches_segments_decodes_and_sorts():
    transport = FakeTransport(
        [
            HttpResponse(
                status_code=200,
                headers={"content-type": "application/octet-stream"},
                content=protobuf_reply(
                    protobuf_elem(3000, 1, 25, 0x112233, "late", 20),
                    protobuf_elem(1000, 4, 30, 0xAABBCC, "early", 10),
                    protobuf_elem(2000, 8, 25, 0x000000, "unknown", 15),
                ),
            ),
            HttpResponse(status_code=304, content=b""),
        ]
    )
    service = BilibiliService(BilibiliClient(transport=transport, max_attempts=1))

    result = service.fetch_danmaku_with_stats(101, 361)

    assert result.segment_count == 2
    assert result.skipped_count == 1
    assert [item.content for item in result.danmakus] == ["early", "late"]
    assert result.danmakus[0].type is DanmakuType.BOTTOM
    assert result.danmakus[0].rgb == (0xAA, 0xBB, 0xCC)
    assert result.danmakus[0].send_timestamp_ms == 10000
    assert [call["params"]["segment_index"] for call in transport.calls] == [1, 2]


def test_bilibili_service_maps_api_and_decode_errors():
    api_transport = FakeTransport(
        [json_response({"code": -404, "message": "not found", "data": None})]
    )
    api_service = BilibiliService(
        BilibiliClient(transport=api_transport, max_attempts=1)
    )
    with pytest.raises(VideoNotFoundError):
        api_service.resolve_video(BVSource("BV1"))

    decode_transport = FakeTransport(
        [
            HttpResponse(
                status_code=200,
                headers={"content-type": "application/octet-stream"},
                content=b"\xff\x00",
            )
        ]
    )
    decode_service = BilibiliService(
        BilibiliClient(transport=decode_transport, max_attempts=1)
    )
    with pytest.raises(BilibiliDecodeError):
        decode_service.fetch_danmaku(101, 1)


@pytest.mark.parametrize(
    ("source", "expected_error"),
    [
        (SeasonSource(88), SeasonNotFoundError),
        (EpisodeSource(20), EpisodeNotFoundError),
    ],
)
def test_bilibili_service_maps_not_found_by_source(source, expected_error):
    transport = FakeTransport(
        [json_response({"code": -404, "message": "not found", "result": None})]
    )
    service = BilibiliService(BilibiliClient(transport=transport, max_attempts=1))

    with pytest.raises(expected_error):
        service.resolve_season(source)


def test_bilibili_client_accepts_httpx_mock_transport():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"code": 0, "data": {"ok": True}},
        )

    client = BilibiliClient(
        transport=httpx.MockTransport(handler),
        max_attempts=1,
    )

    assert client.get_json("https://example.test", {"cid": 101}) == {
        "code": 0,
        "data": {"ok": True},
    }
    assert calls[0].url.params["cid"] == "101"


def test_bilibili_client_retries_temporary_http_errors_only():
    transport = FakeTransport(
        [
            HttpResponse(status_code=503),
            HttpResponse(status_code=200, content=b"ok"),
        ]
    )
    client = BilibiliClient(
        transport=transport,
        max_attempts=3,
        sleeper=lambda _: None,
    )

    response = client.get("https://example.test")

    assert response.content == b"ok"
    assert len(transport.calls) == 2

    no_retry_transport = FakeTransport([HttpResponse(status_code=404)])
    no_retry_client = BilibiliClient(
        transport=no_retry_transport,
        max_attempts=3,
        sleeper=lambda _: None,
    )
    with pytest.raises(Exception):
        no_retry_client.get("https://example.test")
    assert len(no_retry_transport.calls) == 1


class StubBilibiliService:
    def __init__(self, danmakus):
        self.danmakus = danmakus

    def resolve_video(self, source):
        return Video(
            bvid=source.bv,
            title="A:/ Demo",
            pages=[VideoPage(page=1, part="Part", cid=101, duration_s=1)],
        )

    def fetch_danmaku_with_stats(self, cid, duration_s):
        from danmukuflow.bilibili.service import DanmakuFetchResult

        return DanmakuFetchResult(self.danmakus, 1, 0)

    def resolve_episode(self, source):
        return (
            Season(season_id=88, title="Season", episodes=[]),
            Episode(
                episode_id=source.episode_id,
                aid=20,
                bvid="BV1",
                cid=202,
                title="Episode",
                long_title="Long episode",
                duration_s=1,
            ),
        )


def test_bv_export_reuses_ass_renderer_and_sanitizes_default_filename(tmp_path):
    from danmukuflow.models import Danmaku

    service = ExportService(
        StubBilibiliService(
            [
                Danmaku(
                    timeline_s=0,
                    content="from api",
                    type=DanmakuType.FLOAT,
                    fontsize=25,
                    rgb=(1, 2, 3),
                )
            ]
        )
    )

    result = service.export(
        ExportRequest(
            source=BVSource("BV1"),
            output_path=tmp_path / "result.ass",
        )
    )

    assert result.success
    assert result.metadata["source_type"] == "bv"
    assert result.metadata["cid"] == 101
    assert "from api" in (tmp_path / "result.ass").read_text(encoding="utf-8")


def test_bv_page_not_found_and_ss_export_are_explicit():
    class EmptyVideoService(StubBilibiliService):
        def resolve_video(self, source):
            return Video(bvid=source.bv, title="Demo", pages=[])

    with pytest.raises(PageNotFoundError):
        ExportService(EmptyVideoService([])).export(
            ExportRequest(source=BVSource("BV1", page=2))
        )

    with pytest.raises(SeasonExportUnsupportedError):
        ExportService(StubBilibiliService([])).export(
            ExportRequest(source=SeasonSource(1))
        )


def test_episode_export_uses_episode_metadata_and_common_renderer(tmp_path):
    from danmukuflow.models import Danmaku

    result = ExportService(
        StubBilibiliService(
            [
                Danmaku(
                    timeline_s=0,
                    content="episode danmaku",
                    type=DanmakuType.FLOAT,
                    fontsize=25,
                    rgb=(4, 5, 6),
                )
            ]
        )
    ).export(
        ExportRequest(
            source=EpisodeSource(20),
            output_path=tmp_path / "episode.ass",
        )
    )

    assert result.metadata["source_type"] == "ep"
    assert result.metadata["season_id"] == 88
    assert result.metadata["episode_id"] == 20
    assert result.metadata["cid"] == 202
    assert "Title: Season - Episode" in (tmp_path / "episode.ass").read_text(
        encoding="utf-8"
    )

import threading
import time

import pytest

from danmukuflow.bilibili.service import DanmakuFetchResult
from danmukuflow.core.matching import EpisodeMatcher, EpisodeSelector
from danmukuflow.models import (
    BatchExportRequest,
    BatchItemStatus,
    ConflictPolicy,
    Danmaku,
    DanmakuType,
    Episode,
    LocalEpisodeKind,
    RenderConfig,
    Season,
    SeasonSource,
)
from danmukuflow.parsers.local_episode import parse_local_episode_key
from danmukuflow.services import (
    BatchExportService,
    BilibiliNetworkError,
    ExportService,
    InvalidBatchConcurrencyError,
    InvalidEpisodeSelectionError,
    LocalVideoScanner,
    NoVideoFilesError,
    VideoDirectoryNotDirectoryError,
    VideoDirectoryNotFoundError,
)


def make_episode(number, episode_id=None):
    return Episode(
        episode_id=episode_id or number * 100 + 7,
        aid=number,
        bvid="BV{}".format(number),
        cid=number * 10,
        title=str(number),
        long_title="Episode {}".format(number),
        duration_s=1,
        display_number=number,
    )


def make_videos(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_text("", encoding="utf-8")
    return tmp_path


def test_local_video_scanner_filters_sorts_and_does_not_recurse(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    make_videos(
        tmp_path,
        "b.MP4",
        "A.mkv",
        "ignore.txt",
    )
    make_videos(nested, "nested.mkv")

    videos = LocalVideoScanner().scan(tmp_path)

    assert [video.filename for video in videos] == ["A.mkv", "b.MP4"]
    assert all(video.path.parent == tmp_path for video in videos)
    assert videos[0].stem == "A"
    assert videos[0].suffix == ".mkv"


@pytest.mark.parametrize(
    "directory_error",
    [
        VideoDirectoryNotFoundError,
        VideoDirectoryNotDirectoryError,
        NoVideoFilesError,
    ],
)
def test_local_video_scanner_reports_directory_errors(tmp_path, directory_error):
    if directory_error is VideoDirectoryNotFoundError:
        path = tmp_path / "missing"
    elif directory_error is VideoDirectoryNotDirectoryError:
        path = tmp_path / "video.mkv"
        path.write_text("", encoding="utf-8")
    else:
        path = tmp_path / "empty"
        path.mkdir()
        (path / "readme.txt").write_text("", encoding="utf-8")

    with pytest.raises(directory_error):
        LocalVideoScanner().scan(path)


@pytest.mark.parametrize(
    ("stem", "kind", "raw", "number"),
    [
        ("[01]", LocalEpisodeKind.NORMAL, "01", 1),
        ("[09]", LocalEpisodeKind.NORMAL, "09", 9),
        (
            "[VCB-Studio] One-Punch Man [09][Ma10p_1080p][x265_flac_aac]",
            LocalEpisodeKind.NORMAL,
            "09",
            9,
        ),
        ("[SP01]", LocalEpisodeKind.SPECIAL, "SP01", None),
        ("[OVA]", LocalEpisodeKind.SPECIAL, "OVA", None),
        ("episode-final", LocalEpisodeKind.UNRECOGNIZED, None, None),
    ],
)
def test_local_episode_parser_recognizes_normal_and_special_names(
    stem, kind, raw, number
):
    result = parse_local_episode_key(stem)

    assert result.kind is kind
    assert result.raw == raw
    assert result.number == number


def test_local_episode_parser_marks_multiple_numeric_tokens_ambiguous():
    result = parse_local_episode_key("[Show] [01][02][1080p]")

    assert result.kind is LocalEpisodeKind.AMBIGUOUS
    assert result.number is None


def test_episode_selector_supports_all_ranges_and_combinations():
    assert [EpisodeSelector().includes(number) for number in (1, 2, 3)] == [
        True,
        True,
        True,
    ]
    selector = EpisodeSelector("1,3-5,8")
    assert [selector.includes(number) for number in range(1, 10)] == [
        True,
        False,
        True,
        True,
        True,
        False,
        False,
        True,
        False,
    ]
    assert not EpisodeSelector("1-2").includes(3)
    assert not EpisodeSelector("1-2").includes(None)


@pytest.mark.parametrize("spec", ["", "0", "3-1", "1,,2", "episode"])
def test_episode_selector_rejects_invalid_specs(spec):
    with pytest.raises(InvalidEpisodeSelectionError):
        EpisodeSelector(spec)


def test_episode_matcher_uses_display_number_not_episode_id_or_position(tmp_path):
    episodes = [
        make_episode(1, episode_id=9001),
        make_episode(2, episode_id=100),
        make_episode(3, episode_id=5000),
        make_episode(4, episode_id=42),
    ]
    videos = LocalVideoScanner().scan(
        make_videos(
            tmp_path,
            "[Show] [04].mkv",
            "[Show] [01].mkv",
            "[Show] [02].mkv",
        )
    )
    videos = tuple(
        video.__class__(
            path=video.path,
            filename=video.filename,
            stem=video.stem,
            suffix=video.suffix,
            episode_key=parse_local_episode_key(video.stem),
        )
        for video in videos
    )

    result = EpisodeMatcher().match(episodes, videos)

    assert [item.episode.display_number for item in result.matched] == [1, 2, 4]
    assert [item.episode.display_number for item in result.unmatched_episode] == [3]


def test_episode_matcher_does_not_choose_between_duplicate_local_files(tmp_path):
    videos = LocalVideoScanner().scan(
        make_videos(tmp_path, "[Show] [01] a.mkv", "[Show] [01] b.mkv")
    )
    videos = tuple(
        video.__class__(
            path=video.path,
            filename=video.filename,
            stem=video.stem,
            suffix=video.suffix,
            episode_key=parse_local_episode_key(video.stem),
        )
        for video in videos
    )

    result = EpisodeMatcher().match([make_episode(1)], videos)

    assert result.matched == ()
    assert len(result.ambiguous) == 2
    assert result.unmatched_episode == ()


def test_episode_matcher_marks_duplicate_season_numbers_ambiguous_without_local(
    tmp_path,
):
    video = LocalVideoScanner().scan(make_videos(tmp_path, "unrelated.mkv"))[0]
    episodes = [make_episode(1, episode_id=101), make_episode(1, episode_id=202)]

    result = EpisodeMatcher().match(episodes, (video,))

    assert result.matched == ()
    assert len(result.ambiguous) == 2
    assert result.unmatched_episode == ()


class FakeBatchBilibiliService:
    def __init__(self, episodes, fail_numbers=()):
        self.season = Season(season_id=123, title="Demo Season", episodes=episodes)
        self.fail_numbers = set(fail_numbers)
        self.resolve_calls = 0
        self.fetch_calls = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def resolve_season(self, source):
        self.resolve_calls += 1
        return self.season

    def fetch_danmaku_with_stats(self, cid, duration_s):
        number = cid // 10
        with self._lock:
            self.fetch_calls.append(number)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.02)
            if number in self.fail_numbers:
                raise BilibiliNetworkError("network failure for episode {}".format(number))
            return DanmakuFetchResult(
                danmakus=[
                    Danmaku(
                        timeline_s=0,
                        content="episode {}".format(number),
                        type=DanmakuType.FLOAT,
                        fontsize=25,
                        rgb=(1, 2, 3),
                    )
                ],
                segment_count=1,
                skipped_count=0,
            )
        finally:
            with self._lock:
                self.active -= 1


def run_batch(tmp_path, fake_service, **kwargs):
    return BatchExportService(bilibili_service=fake_service).export(
        BatchExportRequest(
            source=SeasonSource(123),
            video_dir=tmp_path,
            render_config=kwargs.pop("render_config", None)
            or RenderConfig(),
            **kwargs
        )
    )


def test_batch_export_writes_ass_beside_matching_video(tmp_path):
    make_videos(tmp_path, "[Show] [01].mkv", "[Show] [02].mkv")
    fake = FakeBatchBilibiliService([make_episode(1), make_episode(2)])

    result = run_batch(tmp_path, fake, concurrency=1)

    assert result.total == 2
    assert result.matched == 2
    assert result.selected == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert result.items[0].status is BatchItemStatus.SUCCEEDED
    for video_name in ("[Show] [01].mkv", "[Show] [02].mkv"):
        video_path = tmp_path / video_name
        ass_path = video_path.with_suffix(".ass")
        assert ass_path.exists()
        assert ass_path.parent == video_path.parent
        assert ass_path.stem == video_path.stem


def test_batch_export_skips_existing_ass_without_fetching_episode(tmp_path):
    make_videos(tmp_path, "[Show] [01].mkv", "[Show] [02].mkv")
    (tmp_path / "[Show] [01].ass").write_text("existing", encoding="utf-8")
    fake = FakeBatchBilibiliService([make_episode(1), make_episode(2)])

    result = run_batch(tmp_path, fake, concurrency=1)

    assert result.skipped == 1
    assert result.succeeded == 1
    assert fake.resolve_calls == 1
    assert fake.fetch_calls == [2]
    assert (tmp_path / "[Show] [01].ass").read_text(encoding="utf-8") == "existing"


def test_batch_export_overwrites_existing_ass_and_continues_after_failure(tmp_path):
    make_videos(
        tmp_path,
        "[Show] [01].mkv",
        "[Show] [02].mkv",
        "[Show] [03].mkv",
        "[Show] [04].mkv",
    )
    existing = tmp_path / "[Show] [01].ass"
    existing.write_text("old", encoding="utf-8")
    fake = FakeBatchBilibiliService(
        [make_episode(number) for number in range(1, 5)],
        fail_numbers=(2,),
    )

    result = run_batch(
        tmp_path,
        fake,
        concurrency=2,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )

    assert result.succeeded == 3
    assert result.failed == 1
    assert result.skipped == 0
    assert fake.max_active <= 2
    assert existing.read_text(encoding="utf-8") != "old"
    assert not (tmp_path / "[Show] [02].ass").exists()


def test_batch_export_selection_and_unmatched_counts(tmp_path):
    make_videos(
        tmp_path,
        "[Show] [01].mkv",
        "[Show] [02].mkv",
        "[Show] [04].mkv",
        "[Show] [09].mkv",
    )
    fake = FakeBatchBilibiliService(
        [make_episode(number) for number in range(1, 5)]
    )

    result = run_batch(tmp_path, fake, episodes="1-4", concurrency=1)

    assert result.matched == 3
    assert result.selected == 4
    assert result.unmatched_local == 1
    assert result.unmatched_episode == 0
    assert result.succeeded == 4
    assert result.fallback == 1
    assert (tmp_path / "Demo Season-ep3.ass").exists()
    assert not (tmp_path / "[Show] [09].ass").exists()


def test_batch_export_rejects_invalid_concurrency(tmp_path):
    make_videos(tmp_path, "[Show] [01].mkv")
    fake = FakeBatchBilibiliService([make_episode(1)])

    with pytest.raises(InvalidBatchConcurrencyError):
        run_batch(tmp_path, fake, concurrency=9)


def test_directory_episode_inference_supports_s01e_names(tmp_path):
    make_videos(
        tmp_path,
        "[Judas] Durarara - S01E01.mkv",
        "[Judas] Durarara - S01E02.mkv",
        "[Judas] Durarara - S01E03.mkv",
    )
    fake = FakeBatchBilibiliService(
        [make_episode(number) for number in range(1, 4)]
    )

    result = run_batch(tmp_path, fake, concurrency=1)

    assert result.matched == 3
    assert result.succeeded == 3
    assert result.fallback == 0
    for number in range(1, 4):
        video = tmp_path / "[Judas] Durarara - S01E{:02d}.mkv".format(number)
        assert video.with_suffix(".ass").exists()


def test_single_video_without_cross_file_variation_falls_back_to_first_episode(
    tmp_path,
):
    make_videos(tmp_path, "[Judas] Durarara - S01E24.mkv")
    fake = FakeBatchBilibiliService([make_episode(1), make_episode(2)])

    result = run_batch(tmp_path, fake, concurrency=1)

    assert result.matched == 0
    assert result.selected == 1
    assert result.succeeded == 1
    assert result.fallback == 1
    assert (tmp_path / "Demo Season-ep1.ass").exists()
    assert not (tmp_path / "[Judas] Durarara - S01E24.ass").exists()
    assert fake.fetch_calls == [1]
    assert any(
        item.status is BatchItemStatus.FALLBACK for item in result.items
    )


def test_unrecognized_files_use_explicit_episode_fallback_names(tmp_path):
    make_videos(tmp_path, "movie-a.mkv", "movie-b.mkv")
    fake = FakeBatchBilibiliService(
        [make_episode(number) for number in range(1, 4)]
    )

    result = run_batch(tmp_path, fake, episodes="2,3", concurrency=1)

    assert result.selected == 2
    assert result.succeeded == 2
    assert result.fallback == 2
    assert (tmp_path / "Demo Season-ep2.ass").exists()
    assert (tmp_path / "Demo Season-ep3.ass").exists()
    assert fake.fetch_calls == [2, 3]


def test_multiple_files_without_changing_number_only_use_first_as_fallback(
    tmp_path,
):
    make_videos(tmp_path, "show-1080p-a.mkv", "show-1080p-b.mkv")
    fake = FakeBatchBilibiliService([make_episode(1), make_episode(2)])

    result = run_batch(tmp_path, fake, concurrency=1)

    assert result.selected == 1
    assert result.succeeded == 1
    assert result.fallback == 1
    assert fake.fetch_calls == [1]
    assert len([path for path in tmp_path.iterdir() if path.suffix == ".ass"]) == 1


def test_multiple_changing_episode_candidates_are_ambiguous(tmp_path):
    make_videos(
        tmp_path,
        "Show-S01E01-1080p01.mkv",
        "Show-S01E02-1080p02.mkv",
    )
    fake = FakeBatchBilibiliService([make_episode(1), make_episode(2)])

    result = run_batch(tmp_path, fake, concurrency=1)

    assert result.matched == 0
    assert result.selected == 0
    assert result.succeeded == 0
    assert result.ambiguous == 2
    assert fake.fetch_calls == []

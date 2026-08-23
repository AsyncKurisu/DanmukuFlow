from concurrent.futures import ThreadPoolExecutor

from danmukuflow.bilibili.service import BilibiliService
from danmukuflow.core.matching import EpisodeMatcher, EpisodeSelector
from danmukuflow.models import (
    BatchExportItem,
    BatchExportRequest,
    BatchExportResult,
    BatchItemStatus,
    ConflictPolicy,
    SeasonSource,
)
from danmukuflow.services.errors import (
    InvalidBatchConcurrencyError,
    InvalidBatchConflictPolicyError,
    SeasonEpisodeNumberError,
    UnsupportedSourceError,
)
from danmukuflow.services.export import ExportService, safe_filename
from danmukuflow.services.local_videos import LocalVideoScanner


MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 8


class BatchExportService:
    def __init__(
        self,
        bilibili_service=None,
        export_service=None,
        scanner=None,
        episode_parser=None,
        matcher=None,
    ):
        if export_service is not None:
            self.export_service = export_service
            self.bilibili_service = (
                bilibili_service
                if bilibili_service is not None
                else export_service.bilibili_service
            )
        else:
            self.bilibili_service = bilibili_service or BilibiliService()
            self.export_service = ExportService(self.bilibili_service)
        self.scanner = scanner or LocalVideoScanner()
        # Kept for compatibility with callers that injected the old parser.
        self.episode_parser = episode_parser
        self.matcher = matcher or EpisodeMatcher()

    def export(self, request):
        self._validate_request(request)
        selector = EpisodeSelector.from_spec(request.episodes)
        conflict_policy = self._conflict_policy(request.conflict_policy)
        season = self.bilibili_service.resolve_season(request.source)
        videos = self.scanner.scan(request.video_dir)
        resolution = self.matcher.resolve(season.episodes, videos)
        matches = resolution.matches

        items = []
        fallback_video = (
            resolution.fallback_video if resolution.fallback_mode else None
        )
        fallback_context_video = (
            fallback_video if request.episodes is None else None
        )
        items.extend(
            self._unmatched_local_item(item)
            for item in matches.unmatched_local
            if item.video is not fallback_context_video
        )
        items.extend(self._ambiguous_item(item) for item in matches.ambiguous)

        matched_ids = {
            item.episode.episode_id
            for item in matches.matched
            if item.episode is not None
        }
        ambiguous_ids = {
            item.episode.episode_id
            for item in matches.ambiguous
            if item.episode is not None
        }
        selected_matches = tuple(
            item
            for item in matches.matched
            if selector.includes(item.episode.display_number)
        )

        fallback_episodes = self._fallback_episodes(
            season,
            selector,
            request.episodes,
            resolution,
            matched_ids,
            ambiguous_ids,
        )
        fallback_ids = {episode.episode_id for episode in fallback_episodes}
        selected_unmatched_episodes = tuple(
            item
            for item in matches.unmatched_episode
            if selector.includes(item.episode.display_number)
            and item.episode.episode_id not in fallback_ids
        )
        items.extend(
            self._unmatched_episode_item(item)
            for item in selected_unmatched_episodes
        )

        pending = []
        for match in selected_matches:
            output_path = match.video.path.with_suffix(".ass")
            if conflict_policy is ConflictPolicy.SKIP and output_path.exists():
                items.append(
                    self._completed_item(
                        match,
                        output_path,
                        BatchItemStatus.SKIPPED,
                    )
                )
            else:
                pending.append((match.episode, match.video, output_path, False))

        for episode in fallback_episodes:
            output_path = self._fallback_output_path(
                request.video_dir,
                season,
                episode,
            )
            context_video = fallback_context_video
            if conflict_policy is ConflictPolicy.SKIP and output_path.exists():
                items.append(
                    self._completed_episode_item(
                        episode,
                        context_video,
                        output_path,
                        BatchItemStatus.SKIPPED,
                        reason="fallback filename; output already exists",
                    )
                )
            else:
                pending.append((episode, context_video, output_path, True))

        items.extend(self._run_exports(pending, season, request))
        items.sort(key=_batch_item_sort_key)

        succeeded = sum(
            item.status in (BatchItemStatus.SUCCEEDED, BatchItemStatus.FALLBACK)
            for item in items
        )
        fallback_count = sum(item.fallback for item in items)
        failed = sum(item.status is BatchItemStatus.FAILED for item in items)
        skipped = sum(item.status is BatchItemStatus.SKIPPED for item in items)

        return BatchExportResult(
            total=len(videos),
            matched=len(matches.matched),
            selected=len(selected_matches) + len(fallback_episodes),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            unmatched_local=max(
                0,
                len(matches.unmatched_local)
                - (1 if fallback_context_video is not None else 0),
            ),
            unmatched_episode=len(selected_unmatched_episodes),
            ambiguous=len(matches.ambiguous),
            fallback=fallback_count,
            items=tuple(items),
        )

    def _run_exports(self, pending, season, request):
        if not pending:
            return []

        def export_one(task):
            episode, video, output_path, is_fallback = task
            try:
                result = self.export_service.export_resolved_episode(
                    season,
                    episode,
                    output_path,
                    request.render_config,
                )
            except Exception as exc:
                return self._failed_item(
                    episode,
                    video,
                    output_path,
                    exc,
                    is_fallback,
                )
            return self._completed_episode_item(
                episode,
                video,
                output_path,
                (
                    BatchItemStatus.FALLBACK
                    if is_fallback
                    else BatchItemStatus.SUCCEEDED
                ),
                result=result,
                reason="fallback filename" if is_fallback else None,
            )

        with ThreadPoolExecutor(max_workers=request.concurrency) as executor:
            futures = [executor.submit(export_one, task) for task in pending]
            return [future.result() for future in futures]

    def _fallback_episodes(
        self,
        season,
        selector,
        selection_spec,
        resolution,
        matched_ids,
        ambiguous_ids,
    ):
        selectable = tuple(
            episode
            for episode in season.episodes
            if episode.display_number is not None
            and selector.includes(episode.display_number)
        )
        if selection_spec is None:
            if not resolution.fallback_mode:
                return ()
            return (_first_episode(selectable, season),)

        if resolution.fallback_mode:
            return selectable
        return tuple(
            episode
            for episode in selectable
            if episode.episode_id not in matched_ids
            and episode.episode_id not in ambiguous_ids
        )

    @staticmethod
    def _fallback_output_path(video_dir, season, episode):
        raw_title = str(season.title).strip()
        title = safe_filename(raw_title) if raw_title else "season-{}".format(
            season.season_id
        )
        return video_dir / "{}-ep{}.ass".format(
            title,
            episode.display_number,
        )

    def _validate_request(self, request):
        if not isinstance(request.source, SeasonSource):
            raise UnsupportedSourceError(
                "batch export requires a SeasonSource (ss input)"
            )
        if not isinstance(request.concurrency, int) or isinstance(
            request.concurrency, bool
        ):
            raise InvalidBatchConcurrencyError(
                "concurrency must be an integer between {} and {}".format(
                    MIN_CONCURRENCY, MAX_CONCURRENCY
                )
            )
        if not MIN_CONCURRENCY <= request.concurrency <= MAX_CONCURRENCY:
            raise InvalidBatchConcurrencyError(
                "concurrency must be between {} and {}".format(
                    MIN_CONCURRENCY, MAX_CONCURRENCY
                )
            )

    @staticmethod
    def _conflict_policy(policy):
        if isinstance(policy, ConflictPolicy):
            return policy
        try:
            return ConflictPolicy(str(policy).casefold())
        except ValueError as exc:
            raise InvalidBatchConflictPolicyError(
                "unsupported conflict policy: {}".format(policy)
            ) from exc

    @staticmethod
    def _completed_item(match, output_path, status, result=None):
        return BatchExportService._completed_episode_item(
            match.episode,
            match.video,
            output_path,
            status,
            result=result,
        )

    @staticmethod
    def _completed_episode_item(
        episode,
        video,
        output_path,
        status,
        result=None,
        reason=None,
    ):
        return BatchExportItem(
            episode_id=episode.episode_id if episode else None,
            display_number=episode.display_number if episode else None,
            episode_title=episode.title if episode else None,
            local_video_path=video.path if video else None,
            output_path=output_path,
            status=status,
            result=result,
            reason=reason,
            fallback=(
                status is BatchItemStatus.FALLBACK
                or (
                    reason is not None
                    and reason.startswith("fallback filename")
                )
            ),
        )

    @staticmethod
    def _failed_item(episode, video, output_path, error, is_fallback=False):
        return BatchExportItem(
            episode_id=episode.episode_id if episode else None,
            display_number=episode.display_number if episode else None,
            episode_title=episode.title if episode else None,
            local_video_path=video.path if video else None,
            output_path=output_path,
            status=BatchItemStatus.FAILED,
            error=error,
            reason=("fallback filename: " if is_fallback else "") + str(error),
            fallback=is_fallback,
        )

    @staticmethod
    def _unmatched_local_item(match):
        return BatchExportItem(
            episode_id=None,
            display_number=(
                match.video.episode_key.number
                if match.video and match.video.episode_key
                else None
            ),
            episode_title=None,
            local_video_path=match.video.path if match.video else None,
            output_path=(
                match.video.path.with_suffix(".ass")
                if match.video
                else None
            ),
            status=BatchItemStatus.UNMATCHED,
            reason=match.reason,
        )

    @staticmethod
    def _ambiguous_item(match):
        return BatchExportItem(
            episode_id=match.episode.episode_id if match.episode else None,
            display_number=(
                match.episode.display_number
                if match.episode
                else (
                    match.video.episode_key.number
                    if match.video and match.video.episode_key
                    else None
                )
            ),
            episode_title=match.episode.title if match.episode else None,
            local_video_path=match.video.path if match.video else None,
            output_path=(
                match.video.path.with_suffix(".ass")
                if match.video
                else None
            ),
            status=BatchItemStatus.AMBIGUOUS,
            reason=match.reason,
        )

    @staticmethod
    def _unmatched_episode_item(match):
        return BatchExportItem(
            episode_id=match.episode.episode_id if match.episode else None,
            display_number=match.episode.display_number if match.episode else None,
            episode_title=match.episode.title if match.episode else None,
            local_video_path=None,
            output_path=None,
            status=BatchItemStatus.UNMATCHED,
            reason=match.reason,
        )


def _first_episode(selectable, season):
    if selectable:
        return sorted(selectable, key=lambda item: item.display_number)[0]
    raise SeasonEpisodeNumberError(
        "Season {} has no episode with a numeric display number".format(
            season.season_id
        )
    )


def _batch_item_sort_key(item):
    return (
        item.display_number is None,
        item.display_number if item.display_number is not None else 0,
        str(item.local_video_path or "").casefold(),
        str(item.local_video_path or ""),
        item.status.value,
    )

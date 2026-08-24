from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from danmukuflow.bilibili.service import BilibiliService
from danmukuflow.core.matching import EpisodeMatcher, EpisodeSelector
from danmukuflow.models import (
    BatchExportResult,
    BatchItemResult,
    BatchItemStatus,
    ConflictPolicy,
    DEFAULT_CONCURRENCY,
    OutputConfig,
    SeasonSource,
    TemplateContext,
)
from danmukuflow.services.errors import (
    InvalidBatchConcurrencyError,
    InvalidBatchConflictPolicyError,
    InvalidEpisodeSelectionError,
    OutputConflictError,
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
        output_service=None,
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
            self.export_service = ExportService(
                self.bilibili_service,
                output_service=output_service,
            )
        self.output_service = output_service or self.export_service.output_service
        self.scanner = scanner or LocalVideoScanner()
        # Kept for compatibility with callers that injected the old parser.
        self.episode_parser = episode_parser
        self.matcher = matcher or EpisodeMatcher()

    def export(self, request):
        self._validate_request(request)
        season = self.bilibili_service.resolve_season(request.source)
        if request.video_dir is not None:
            return self._export_local_videos(season, request)
        return self._export_selected_episodes(season, request)

    def _export_local_videos(self, season, request):
        selector = EpisodeSelector.from_spec(request.episodes)
        conflict_policy = self._conflict_policy(request.conflict_policy)
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
            conflict = self._conflict_item(
                output_path,
                conflict_policy,
                match.episode.episode_id,
                match.episode.display_number,
                match.episode.title,
                match.video.path,
            )
            if conflict is not None:
                items.append(conflict)
            else:
                pending.append((match.episode, match.video, output_path, False))

        for episode in fallback_episodes:
            output_path = self._fallback_output_path(
                request.video_dir,
                season,
                episode,
            )
            context_video = fallback_context_video
            conflict = self._conflict_item(
                output_path,
                conflict_policy,
                episode.episode_id,
                episode.display_number,
                episode.title,
                context_video.path if context_video else None,
            )
            if conflict is not None:
                items.append(conflict)
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
            pending=0,
            running=0,
            items=tuple(items),
            fallback=fallback_count,
        )

    def _export_selected_episodes(self, season, request):
        output_config = request.output_config or OutputConfig(
            conflict_policy=self._conflict_policy(request.conflict_policy),
        )
        if request.selected_episode_ids is not None:
            selected_ids = tuple(int(item) for item in request.selected_episode_ids)
            invalid_ids = [item for item in selected_ids if item < 1]
            if invalid_ids:
                raise InvalidEpisodeSelectionError(
                    "episode ids must be greater than zero"
                )
            season_ids = {episode.episode_id for episode in season.episodes}
            missing_ids = [item for item in selected_ids if item not in season_ids]
            if missing_ids:
                raise InvalidEpisodeSelectionError(
                    "selected episode ids do not belong to this season: {}".format(
                        ",".join(str(item) for item in missing_ids)
                    )
                )
            episodes = tuple(
                episode
                for episode in season.episodes
                if episode.episode_id in set(selected_ids)
            )
        else:
            selector = EpisodeSelector.from_spec(request.episodes)
            episodes = tuple(
                episode
                for episode in season.episodes
                if selector.includes(episode.display_number)
            )

        items = []
        pending = []
        default_root = None if output_config.is_download else (
            output_config.output_dir or Path.cwd()
        )
        for episode in episodes:
            context = self._episode_context(season, episode)
            plan = self.output_service.build_plan(
                output_config,
                context,
                default_template="{season_title}/{episode_no}_{episode_title}_{episode_id}.ass",
                default_root=default_root,
            )
            target_path = plan.target
            if target_path is not None:
                conflict = self._conflict_item(
                    target_path,
                    self._conflict_policy(output_config.conflict_policy),
                    episode.episode_id,
                    episode.display_number,
                    episode.title,
                )
                if conflict is not None:
                    items.append(conflict)
                    continue
            pending.append((episode, target_path, context))

        items.extend(self._run_selected_exports(pending, season, request, output_config))
        items.sort(key=_batch_item_sort_key)

        succeeded = sum(
            item.status in (BatchItemStatus.SUCCEEDED, BatchItemStatus.FALLBACK)
            for item in items
        )
        skipped = sum(item.status is BatchItemStatus.SKIPPED for item in items)
        failed = sum(item.status is BatchItemStatus.FAILED for item in items)

        return BatchExportResult(
            total=len(episodes),
            matched=len(episodes),
            selected=len(episodes),
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            unmatched_local=0,
            unmatched_episode=0,
            ambiguous=0,
            pending=0,
            running=0,
            items=tuple(items),
            fallback=0,
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
                    output_config=request.output_config,
                )
            except Exception as exc:
                return self._failed_item(
                    episode,
                    video,
                    output_path,
                    exc,
                    is_fallback,
                )
            if result.skipped:
                return self._completed_episode_item(
                    episode,
                    video,
                    output_path,
                    BatchItemStatus.SKIPPED,
                    result=result,
                    reason="output already exists",
                    artifact=result.artifact,
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
                artifact=result.artifact,
            )

        with ThreadPoolExecutor(max_workers=request.concurrency) as executor:
            futures = [executor.submit(export_one, task) for task in pending]
            return [future.result() for future in futures]

    def _run_selected_exports(self, pending, season, request, output_config):
        if not pending:
            return []

        def export_one(task):
            episode, output_path, context = task
            try:
                result = self.export_service.export_resolved_episode(
                    season,
                    episode,
                    output_path,
                    request.render_config,
                    output_config=output_config,
                )
            except Exception as exc:
                return self._failed_item(episode, None, output_path, exc, False)
            if result.skipped:
                return self._completed_episode_item(
                    episode,
                    None,
                    output_path,
                    BatchItemStatus.SKIPPED,
                    result=result,
                    reason="output already exists",
                    artifact=result.artifact,
                )
            return self._completed_episode_item(
                episode,
                None,
                output_path,
                BatchItemStatus.SUCCEEDED,
                result=result,
                artifact=result.artifact,
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
        if request.concurrency is None:
            request_concurrency = DEFAULT_CONCURRENCY
        else:
            request_concurrency = request.concurrency
        if not isinstance(request_concurrency, int) or isinstance(
            request_concurrency, bool
        ):
            raise InvalidBatchConcurrencyError(
                "concurrency must be an integer between {} and {}".format(
                    MIN_CONCURRENCY, MAX_CONCURRENCY
                )
            )
        if not MIN_CONCURRENCY <= request_concurrency <= MAX_CONCURRENCY:
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

    def _conflict_item(
        self,
        output_path,
        policy,
        episode_id,
        display_number,
        episode_title,
        local_video_path=None,
    ):
        if output_path is None or not output_path.exists():
            return None
        if policy is ConflictPolicy.OVERWRITE:
            return None
        if policy is ConflictPolicy.SKIP:
            return BatchItemResult(
                episode_id=episode_id,
                display_number=display_number,
                episode_title=episode_title,
                local_video_path=local_video_path,
                output_path=output_path,
                status=BatchItemStatus.SKIPPED,
                reason="output already exists",
                fallback=False,
            )
        if policy is ConflictPolicy.ERROR:
            return BatchItemResult(
                episode_id=episode_id,
                display_number=display_number,
                episode_title=episode_title,
                local_video_path=local_video_path,
                output_path=output_path,
                status=BatchItemStatus.FAILED,
                error=OutputConflictError(
                    "output file already exists: {}".format(output_path)
                ),
                reason="output already exists",
                fallback=False,
            )
        return None

    @staticmethod
    def _completed_item(match, output_path, status, result=None, artifact=None):
        return BatchExportService._completed_episode_item(
            match.episode,
            match.video,
            output_path,
            status,
            result=result,
            artifact=artifact,
        )

    @staticmethod
    def _completed_episode_item(
        episode,
        video,
        output_path,
        status,
        result=None,
        reason=None,
        artifact=None,
    ):
        return BatchItemResult(
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
            artifact=artifact,
        )

    @staticmethod
    def _failed_item(episode, video, output_path, error, is_fallback=False):
        return BatchItemResult(
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
        return BatchItemResult(
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
        return BatchItemResult(
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
        return BatchItemResult(
            episode_id=match.episode.episode_id if match.episode else None,
            display_number=match.episode.display_number if match.episode else None,
            episode_title=match.episode.title if match.episode else None,
            local_video_path=None,
            output_path=None,
            status=BatchItemStatus.UNMATCHED,
            reason=match.reason,
        )

    @staticmethod
    def _episode_context(season, episode):
        episode_title = episode.title or episode.long_title or str(episode.episode_id)
        return TemplateContext(
            season_title=season.title,
            season_id=season.season_id,
            episode_no=episode.display_number,
            episode_id=episode.episode_id,
            episode_title=episode_title,
            long_title=episode.long_title,
            bvid=episode.bvid,
            cid=episode.cid,
            source_type="ep",
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

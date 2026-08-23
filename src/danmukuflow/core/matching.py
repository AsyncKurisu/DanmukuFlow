import re
from collections import defaultdict

from danmukuflow.models import (
    DirectoryEpisodeResolution,
    EpisodeMatch,
    EpisodeMatchResult,
    LocalEpisodeKind,
)
from danmukuflow.parsers.local_episode import analyze_filename, parse_local_episode_key
from danmukuflow.services.errors import InvalidEpisodeSelectionError


class EpisodeMatcher:
    def match(self, episodes, videos):
        return self.resolve(episodes, videos).matches

    def resolve(self, episodes, videos):
        episodes = tuple(episodes)
        videos = tuple(videos)
        episodes_by_number = defaultdict(list)
        for episode in episodes:
            if episode.display_number is not None:
                episodes_by_number[episode.display_number].append(episode)

        analyses = {
            video: analyze_filename(video.stem)
            for video in videos
        }
        groups = defaultdict(list)
        for video, fields in analyses.items():
            groups[frozenset(field.signature for field in fields)].append(video)

        videos_by_number = defaultdict(list)
        unmatched_local = []
        ambiguous = []
        ambiguous_local_numbers = set()
        ambiguous_numbers = {
            number
            for number, season_episodes in episodes_by_number.items()
            if len(season_episodes) > 1
        }
        matched = []
        for group_videos in groups.values():
            candidate_signatures = _episode_candidates(
                group_videos,
                analyses,
                set(episodes_by_number),
            )
            if len(candidate_signatures) > 1:
                for video in group_videos:
                    ambiguous.append(
                        EpisodeMatch(
                            video=video,
                            reason="multiple changing numeric fields could be episode numbers",
                        )
                    )
                continue
            if not candidate_signatures:
                _record_unresolved_group(
                    group_videos,
                    unmatched_local,
                    ambiguous,
                    ambiguous_numbers,
                    ambiguous_local_numbers,
                )
                continue

            signature = candidate_signatures[0]
            for video in group_videos:
                number = _field_number(analyses[video], signature)
                if number is None:
                    unmatched_local.append(
                        EpisodeMatch(
                            video=video,
                            reason="episode number field is missing",
                        )
                    )
                else:
                    videos_by_number[number].append(video)

        for number, local_videos in videos_by_number.items():
            season_episodes = episodes_by_number.get(number, [])
            if len(local_videos) == 1 and len(season_episodes) == 1:
                matched.append(
                    EpisodeMatch(episode=season_episodes[0], video=local_videos[0])
                )
                continue

            if len(local_videos) > 1 or len(season_episodes) > 1:
                ambiguous_numbers.add(number)
                reason = (
                    "episode number {} maps to multiple local files or episodes"
                    .format(number)
                )
                for video in local_videos:
                    ambiguous.append(
                        EpisodeMatch(
                            episode=(
                                season_episodes[0]
                                if len(season_episodes) == 1
                                else None
                            ),
                            video=video,
                            reason=reason,
                        )
                    )
                continue

            for video in local_videos:
                unmatched_local.append(
                    EpisodeMatch(
                        video=video,
                        reason="no Bilibili episode has display number {}".format(
                            number
                        ),
                    )
                )

        matched_episode_ids = {
            item.episode.episode_id for item in matched if item.episode is not None
        }
        unmatched_episode = []
        for episode in episodes:
            number = episode.display_number
            if episode.episode_id in matched_episode_ids:
                continue
            if number is not None and number in ambiguous_numbers:
                continue
            reason = (
                "episode has no numeric display number"
                if number is None
                else "no local video has display number {}".format(number)
            )
            unmatched_episode.append(EpisodeMatch(episode=episode, reason=reason))

        for number in sorted(ambiguous_numbers):
            if (
                number not in videos_by_number
                and number not in ambiguous_local_numbers
            ):
                for episode in episodes_by_number[number]:
                    ambiguous.append(
                        EpisodeMatch(
                            episode=episode,
                            reason=(
                                "Bilibili Season contains multiple episodes "
                                "with display number {}".format(number)
                            ),
                        )
                    )

        result = EpisodeMatchResult(
            matched=tuple(
                sorted(
                    matched,
                    key=lambda item: _episode_sort_key(item.episode, item.video),
                )
            ),
            unmatched_local=tuple(
                sorted(unmatched_local, key=lambda item: _video_sort_key(item.video))
            ),
            unmatched_episode=tuple(
                sorted(
                    unmatched_episode,
                    key=lambda item: _episode_sort_key(item.episode, None),
                )
            ),
            ambiguous=tuple(
                sorted(ambiguous, key=lambda item: _video_sort_key(item.video))
            ),
        )
        fallback_mode = not result.matched and not result.ambiguous
        fallback_video = videos[0] if fallback_mode and videos else None
        return DirectoryEpisodeResolution(
            matches=result,
            fallback_mode=fallback_mode,
            fallback_video=fallback_video,
        )


class EpisodeSelector:
    _TOKEN = re.compile(r"^([0-9]+)(?:\s*-\s*([0-9]+))?$")

    def __init__(self, spec=None):
        self._all = spec is None or str(spec).strip().casefold() == "all"
        self._intervals = () if self._all else self._parse_intervals(spec)

    @property
    def is_all(self):
        return self._all

    def includes(self, number):
        if self._all:
            return True
        if number is None:
            return False
        return any(start <= number <= end for start, end in self._intervals)

    @classmethod
    def from_spec(cls, spec):
        return cls(spec)

    def _parse_intervals(self, spec):
        raw_spec = str(spec).strip()
        if not raw_spec:
            raise InvalidEpisodeSelectionError(
                "episode selection cannot be empty"
            )

        intervals = []
        for raw_token in raw_spec.split(","):
            token = raw_token.strip()
            match = self._TOKEN.match(token)
            if match is None:
                raise InvalidEpisodeSelectionError(
                    "invalid episode selection token: {}".format(token)
                )
            start = int(match.group(1))
            end = int(match.group(2) or match.group(1))
            if start < 1 or end < 1 or start > end:
                raise InvalidEpisodeSelectionError(
                    "invalid episode selection range: {}".format(token)
                )
            intervals.append((start, end))

        intervals.sort()
        merged = []
        for start, end in intervals:
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return tuple(merged)


def _video_sort_key(video):
    if video is None:
        return ("", "")
    return (video.filename.casefold(), video.filename)


def _episode_sort_key(episode, video):
    number = episode.display_number if episode is not None else None
    return (
        number is None,
        number if number is not None else 0,
        _video_sort_key(video),
    )


def _episode_candidates(videos, analyses, season_numbers):
    values_by_signature = defaultdict(list)
    for video in videos:
        for field in analyses[video]:
            values_by_signature[field.signature].append(field.number)

    candidates = []
    for signature, values in values_by_signature.items():
        if len(set(values)) <= 1:
            continue
        if set(values).intersection(season_numbers):
            candidates.append(signature)
    return tuple(candidates)


def _field_number(fields, signature):
    for field in fields:
        if field.signature == signature:
            return field.number
    return None


def _record_unresolved_group(
    videos,
    unmatched_local,
    ambiguous,
    ambiguous_numbers,
    ambiguous_local_numbers,
):
    if len(videos) > 1:
        keys = [parse_local_episode_key(video.stem) for video in videos]
        numbers = [
            key.number
            for key in keys
            if key.kind is LocalEpisodeKind.NORMAL and key.number is not None
        ]
        if numbers and len(set(numbers)) == 1:
            ambiguous_numbers.update(numbers)
            ambiguous_local_numbers.update(numbers)
            for video in videos:
                ambiguous.append(
                    EpisodeMatch(
                        video=video,
                        reason="multiple local files use the same episode number",
                    )
                )
            return

    for video in videos:
        unmatched_local.append(
            EpisodeMatch(
                video=video,
                reason="filename has no reliable changing episode number",
            )
        )

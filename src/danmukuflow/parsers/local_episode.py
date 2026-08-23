import re

from danmukuflow.models import LocalEpisodeKey, LocalEpisodeKind, NumericField


_BRACKET_TOKEN = re.compile(r"\[([^\]]+)\]")
_NUMERIC_TOKEN = re.compile(r"^[0-9]+$")
_SPECIAL_TOKEN = re.compile(
    r"^(?:SP[0-9]*|OVA|NCOP|NCED|PV|OP|ED|SPECIAL)$",
    re.IGNORECASE,
)
_NUMERIC_FIELD = re.compile(r"\d+")


class LocalEpisodeParser:
    def parse(self, stem):
        return parse_local_episode_key(stem)

    def analyze(self, stem):
        return analyze_filename(stem)


def analyze_filename(stem):
    """Extract numeric fields while retaining their textual position context."""
    text = str(stem)
    occurrences = {}
    fields = []
    for match in _NUMERIC_FIELD.finditer(text):
        context = _numeric_context(text, match.start())
        occurrence = occurrences.get(context, 0)
        occurrences[context] = occurrence + 1
        fields.append(
            NumericField(
                raw=match.group(0),
                number=int(match.group(0)),
                signature=(context, occurrence),
            )
        )
    return tuple(fields)


def parse_local_episode_key(stem):
    tokens = _BRACKET_TOKEN.findall(str(stem))
    numeric_tokens = [token for token in tokens if _NUMERIC_TOKEN.match(token)]
    special_tokens = [token for token in tokens if _SPECIAL_TOKEN.match(token)]

    if len(numeric_tokens) > 1 or (numeric_tokens and special_tokens):
        return LocalEpisodeKey(
            kind=LocalEpisodeKind.AMBIGUOUS,
            raw=numeric_tokens[0] if numeric_tokens else special_tokens[0],
        )

    if len(numeric_tokens) == 1:
        raw = numeric_tokens[0]
        return LocalEpisodeKey(
            kind=LocalEpisodeKind.NORMAL,
            raw=raw,
            number=int(raw),
        )

    if special_tokens:
        return LocalEpisodeKey(
            kind=LocalEpisodeKind.SPECIAL,
            raw=special_tokens[0],
        )

    return LocalEpisodeKey(kind=LocalEpisodeKind.UNRECOGNIZED)


def _numeric_context(text, start):
    if start == 0:
        return "^"
    character = text[start - 1]
    if character.isalnum():
        return character.casefold()
    return character

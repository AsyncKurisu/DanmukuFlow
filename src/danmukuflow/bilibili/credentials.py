import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from dotenv import dotenv_values


_COOKIE_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_LEGACY_KEYS = {
    "BILIBILI_SESSDATA",
    "BILIBILI_BILI_JCT",
    "BILIBILI_DEDEUSERID",
    "BILIBILI_DEDEUSERID_CKMD5",
    "BILIBILI_BUVID3",
    "BILIBILI_BUVID4",
    "BILIBILI_BILI_TICKET",
    "BILIBILI_BILI_TICKET_EXPIRES",
}


@dataclass(frozen=True)
class BilibiliCredentials:
    cookie: str = ""

    @classmethod
    def from_cookie(cls, cookie: str):
        values = parse_cookie(cookie)
        if not values.get("SESSDATA"):
            raise ValueError("Bilibili Cookie must contain SESSDATA")
        return cls(_serialize_cookie(values))

    @classmethod
    def from_env(
        cls,
        env_path: Optional[Path] = None,
        environ: Optional[Mapping[str, str]] = None,
    ):
        values = {}
        selected_path = (
            Path(env_path).expanduser().resolve()
            if env_path is not None
            else _env_path_from_environment(environ)
        )
        if selected_path is not None and selected_path.is_file():
            values.update(
                {
                    key: value
                    for key, value in dotenv_values(selected_path).items()
                    if value is not None
                }
            )
        values.update(dict(os.environ if environ is None else environ))
        raw_cookie = values.get("BILIBILI_COOKIE")
        if not raw_cookie:
            return cls()
        return cls.from_cookie(raw_cookie)

    @property
    def cookie_header(self):
        return self.cookie

    @property
    def cookie_count(self):
        return len(parse_cookie(self.cookie)) if self.cookie else 0


def parse_cookie(cookie: str):
    if cookie is None:
        return {}
    raw = str(cookie).strip()
    if not raw:
        return {}
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in raw):
        raise ValueError("Bilibili Cookie contains invalid control characters")

    values = {}
    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        name, separator, value = item.partition("=")
        name = name.strip()
        value = value.strip()
        if not separator or not name or not value or not _COOKIE_NAME.match(name):
            raise ValueError("Bilibili Cookie contains an invalid item")
        values[name] = value
    return values


def write_cookie_to_env(cookie: str, env_path: Optional[Path] = None, environ=None):
    credentials = BilibiliCredentials.from_cookie(cookie)
    path = _env_write_path(env_path, environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = existing.splitlines(keepends=True)
    output = []
    replaced = False
    for line in lines:
        match = _ENV_ASSIGNMENT.match(line)
        if match and (
            match.group(1) == "BILIBILI_COOKIE"
            or match.group(1) in _LEGACY_KEYS
        ):
            if not replaced:
                output.append("BILIBILI_COOKIE={}\n".format(_dotenv_quote(credentials.cookie)))
                replaced = True
            continue
        output.append(line)
    if not replaced:
        if output and not output[-1].endswith(("\n", "\r")):
            output.append("\n")
        output.append("BILIBILI_COOKIE={}\n".format(_dotenv_quote(credentials.cookie)))

    fd, temporary = tempfile.mkstemp(
        prefix=".danmukuflow-",
        suffix=".env",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write("".join(output))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return credentials


def _dotenv_quote(value):
    return '"{}"'.format(value.replace("\\", "\\\\").replace('"', '\\"'))


def _env_write_path(env_path, environ):
    if env_path is not None:
        return Path(env_path).expanduser().resolve()
    configured = (os.environ if environ is None else environ).get("DANMUKUFLOW_ENV_FILE")
    if configured:
        return Path(configured).expanduser().resolve()
    return _env_path_from_environment(environ) or (
        Path(__file__).resolve().parents[3] / ".env"
    )


def _env_path_from_environment(environ):
    source = os.environ if environ is None else environ
    configured_path = source.get("DANMUKUFLOW_ENV_FILE")
    if configured_path:
        return Path(configured_path).expanduser().resolve()

    current = Path.cwd().resolve()
    project_root = Path(__file__).resolve().parents[3]
    candidates = (current, *current.parents, project_root)
    for directory in candidates:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def _serialize_cookie(values):
    return "; ".join("{}={}".format(name, value) for name, value in values.items())

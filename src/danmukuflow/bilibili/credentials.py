import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from dotenv import dotenv_values


_COOKIE_FIELDS = (
    ("SESSDATA", "BILIBILI_SESSDATA"),
    ("bili_jct", "BILIBILI_BILI_JCT"),
    ("DedeUserID", "BILIBILI_DEDEUSERID"),
    ("DedeUserID__ckMd5", "BILIBILI_DEDEUSERID_CKMD5"),
    ("buvid3", "BILIBILI_BUVID3"),
    ("buvid4", "BILIBILI_BUVID4"),
    ("bili_ticket", "BILIBILI_BILI_TICKET"),
    ("bili_ticket_expires", "BILIBILI_BILI_TICKET_EXPIRES"),
)


@dataclass(frozen=True)
class BilibiliCredentials:
    sessdata: str = ""
    bili_jct: str = ""
    dede_user_id: str = ""
    dede_user_id_ckmd5: str = ""
    buvid3: str = ""
    buvid4: str = ""
    bili_ticket: str = ""
    bili_ticket_expires: str = ""

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

        return cls(
            sessdata=_clean_value(values.get("BILIBILI_SESSDATA")),
            bili_jct=_clean_value(values.get("BILIBILI_BILI_JCT")),
            dede_user_id=_clean_value(values.get("BILIBILI_DEDEUSERID")),
            dede_user_id_ckmd5=_clean_value(
                values.get("BILIBILI_DEDEUSERID_CKMD5")
            ),
            buvid3=_clean_value(values.get("BILIBILI_BUVID3")),
            buvid4=_clean_value(values.get("BILIBILI_BUVID4")),
            bili_ticket=_clean_value(values.get("BILIBILI_BILI_TICKET")),
            bili_ticket_expires=_clean_value(
                values.get("BILIBILI_BILI_TICKET_EXPIRES")
            ),
        )

    @property
    def cookie_header(self):
        fields = {
            "BILIBILI_SESSDATA": self.sessdata,
            "BILIBILI_BILI_JCT": self.bili_jct,
            "BILIBILI_DEDEUSERID": self.dede_user_id,
            "BILIBILI_DEDEUSERID_CKMD5": self.dede_user_id_ckmd5,
            "BILIBILI_BUVID3": self.buvid3,
            "BILIBILI_BUVID4": self.buvid4,
            "BILIBILI_BILI_TICKET": self.bili_ticket,
            "BILIBILI_BILI_TICKET_EXPIRES": self.bili_ticket_expires,
        }
        values = []
        for cookie_name, env_name in _COOKIE_FIELDS:
            value = fields[env_name]
            if value:
                values.append("{}={}".format(cookie_name, value))
        return "; ".join(values)


def _clean_value(value):
    value = "" if value is None else str(value).strip()
    if "\r" in value or "\n" in value:
        raise ValueError("Bilibili credential values cannot contain newlines")
    return value


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

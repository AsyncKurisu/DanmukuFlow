import pytest

from danmukuflow.bilibili.credentials import (
    BilibiliCredentials,
    parse_cookie,
    write_cookie_to_env,
)


COOKIE = "SESSDATA=session; bili_jct=csrf; buvid3=buvid"


def test_credentials_load_cookie_from_dotenv(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text('BILIBILI_COOKIE="{}"\n'.format(COOKIE), encoding="utf-8")

    credentials = BilibiliCredentials.from_env(env_path=env_path, environ={})

    assert credentials.cookie_header == COOKIE
    assert credentials.cookie_count == 3


def test_environment_cookie_overrides_dotenv_value(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("BILIBILI_COOKIE=from-file\n", encoding="utf-8")

    credentials = BilibiliCredentials.from_env(
        env_path=env_path,
        environ={"BILIBILI_COOKIE": COOKIE},
    )

    assert credentials.cookie_header == COOKIE


def test_credentials_support_custom_env_file_variable(tmp_path):
    env_path = tmp_path / "custom.env"
    env_path.write_text('BILIBILI_COOKIE="{}"\n'.format(COOKIE), encoding="utf-8")

    credentials = BilibiliCredentials.from_env(
        environ={"DANMUKUFLOW_ENV_FILE": str(env_path)}
    )

    assert credentials.cookie_header == COOKIE


def test_cookie_requires_sessdata_and_valid_items():
    with pytest.raises(ValueError, match="SESSDATA"):
        BilibiliCredentials.from_cookie("bili_jct=csrf")
    with pytest.raises(ValueError, match="invalid item"):
        BilibiliCredentials.from_cookie("SESSDATA")


def test_cookie_rejects_control_characters():
    with pytest.raises(ValueError, match="control characters"):
        BilibiliCredentials.from_cookie("SESSDATA=valid\ninjected")


def test_write_cookie_updates_env_and_removes_legacy_fields(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OTHER=value\nBILIBILI_SESSDATA=old\nBILIBILI_BILI_JCT=old\n",
        encoding="utf-8",
    )

    write_cookie_to_env(COOKIE, env_path=env_path, environ={})

    content = env_path.read_text(encoding="utf-8")
    assert 'BILIBILI_COOKIE="{}"'.format(COOKIE) in content
    assert "BILIBILI_SESSDATA" not in content
    assert "BILIBILI_BILI_JCT" not in content
    assert "OTHER=value" in content


def test_parse_cookie_preserves_full_cookie_fields():
    assert parse_cookie("SESSDATA=session; buvid3=buvid; bili_ticket=ticket") == {
        "SESSDATA": "session",
        "buvid3": "buvid",
        "bili_ticket": "ticket",
    }


def test_empty_credentials_do_not_add_cookie_header():
    credentials = BilibiliCredentials.from_env(env_path="missing.env", environ={})

    assert credentials.cookie_header == ""
    assert credentials.cookie_count == 0

from danmukuflow.bilibili.credentials import BilibiliCredentials


def test_credentials_load_dotenv_and_build_cookie_header(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "BILIBILI_SESSDATA=session",
                "BILIBILI_BILI_JCT=csrf",
                "BILIBILI_DEDEUSERID=123",
                "BILIBILI_BUVID3=buvid",
                "BILIBILI_BILI_TICKET=",
            ]
        ),
        encoding="utf-8",
    )

    credentials = BilibiliCredentials.from_env(
        env_path=env_path,
        environ={},
    )

    assert credentials.cookie_header == (
        "SESSDATA=session; bili_jct=csrf; DedeUserID=123; buvid3=buvid"
    )


def test_environment_values_override_dotenv_values(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("BILIBILI_SESSDATA=from-file\n", encoding="utf-8")

    credentials = BilibiliCredentials.from_env(
        env_path=env_path,
        environ={"BILIBILI_SESSDATA": "from-environment"},
    )

    assert credentials.sessdata == "from-environment"


def test_credentials_support_custom_env_file_variable(tmp_path):
    env_path = tmp_path / "custom.env"
    env_path.write_text("BILIBILI_DEDEUSERID=456\n", encoding="utf-8")

    credentials = BilibiliCredentials.from_env(
        environ={"DANMUKUFLOW_ENV_FILE": str(env_path)}
    )

    assert credentials.dede_user_id == "456"


def test_credentials_reject_newlines():
    try:
        BilibiliCredentials.from_env(
            environ={"BILIBILI_SESSDATA": "valid\ninjected"}
        )
    except ValueError as exc:
        assert "newlines" in str(exc)
    else:
        raise AssertionError("newline credentials should be rejected")


def test_empty_credentials_do_not_add_cookie_header():
    credentials = BilibiliCredentials.from_env(
        env_path="missing.env",
        environ={},
    )

    assert credentials.cookie_header == ""

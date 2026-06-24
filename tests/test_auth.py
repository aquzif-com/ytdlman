import secrets
from ytdlman.config import default_config
from ytdlman.auth import hash_password, verify_password, is_configured, create_account


def test_hash_password_deterministic_for_same_salt():
    salt = b"\x01" * 16
    h1 = hash_password("hunter2", salt, 1000)
    h2 = hash_password("hunter2", salt, 1000)
    assert h1 == h2
    assert h1 != hash_password("hunter2", b"\x02" * 16, 1000)  # salt matters
    assert isinstance(h1, str)


def test_is_configured():
    cfg = default_config()
    assert is_configured(cfg.auth) is False
    cfg.auth.username = "admin"
    cfg.auth.salt = "aa"
    cfg.auth.password_hash = "bb"
    assert is_configured(cfg.auth) is True


def test_create_account_then_verify():
    cfg = default_config()
    saved = {"n": 0}
    create_account(cfg, "admin", "s3cret", save=lambda: saved.__setitem__("n", saved["n"] + 1))
    assert cfg.auth.username == "admin"
    assert cfg.auth.password_hash and cfg.auth.salt and cfg.auth.secret_key
    assert saved["n"] == 1
    assert verify_password("s3cret", cfg.auth) is True
    assert verify_password("wrong", cfg.auth) is False


def test_verify_password_false_when_not_configured():
    assert verify_password("anything", default_config().auth) is False


def test_create_account_keeps_existing_secret_key():
    cfg = default_config()
    cfg.auth.secret_key = "preexisting"
    create_account(cfg, "admin", "pw", save=lambda: None)
    assert cfg.auth.secret_key == "preexisting"

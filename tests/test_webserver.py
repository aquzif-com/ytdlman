import pytest
from ytdlman.config import default_config, save_config
from ytdlman.webserver import create_app


def _client(tmp_path, account=False):
    cfg = default_config()
    config_file = tmp_path / "config.json"
    if account:
        from ytdlman.auth import create_account
        create_account(cfg, "admin", "pw", save=lambda: save_config(cfg, config_file))
    else:
        save_config(cfg, config_file)
    app = create_app(cfg, config_file)
    app.config.update(TESTING=True)
    return app, cfg, config_file


def test_no_account_redirects_to_setup(tmp_path):
    app, _, _ = _client(tmp_path)
    c = app.test_client()
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/setup" in r.headers["Location"]


def test_setup_creates_account_and_logs_in(tmp_path):
    app, cfg, _ = _client(tmp_path)
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf_token"] = "tok"
    r = c.post("/setup", data={"csrf_token": "tok", "username": "admin",
                               "password": "pw", "confirm": "pw"},
               follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    assert cfg.auth.username == "admin"


def test_setup_redirects_to_login_when_account_exists(tmp_path):
    app, _, _ = _client(tmp_path, account=True)
    c = app.test_client()
    r = c.get("/setup", follow_redirects=False)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_login_wrong_then_right(tmp_path):
    app, _, _ = _client(tmp_path, account=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf_token"] = "tok"
    bad = c.post("/login", data={"csrf_token": "tok", "username": "admin",
                                 "password": "nope"}, follow_redirects=False)
    assert bad.status_code == 200  # re-renders form, not redirect
    with c.session_transaction() as s:
        s["csrf_token"] = "tok"
    ok = c.post("/login", data={"csrf_token": "tok", "username": "admin",
                                "password": "pw"}, follow_redirects=False)
    assert ok.status_code == 302 and ok.headers["Location"].endswith("/")


def test_dashboard_requires_login(tmp_path):
    app, _, _ = _client(tmp_path, account=True)
    c = app.test_client()
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_dashboard_renders_when_logged_in(tmp_path):
    app, _, _ = _client(tmp_path, account=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
    r = c.get("/")
    assert r.status_code == 200
    assert "yt-dlp" in r.get_data(as_text=True)  # dependency table present


def test_csrf_rejected_on_setup(tmp_path):
    app, _, _ = _client(tmp_path)
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf_token"] = "tok"
    r = c.post("/setup", data={"csrf_token": "WRONG", "username": "a",
                               "password": "p", "confirm": "p"})
    assert r.status_code == 400

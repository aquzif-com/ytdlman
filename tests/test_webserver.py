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


def test_csrf_rejected_on_login(tmp_path):
    app, _, _ = _client(tmp_path, account=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["csrf_token"] = "tok"
    r = c.post("/login", data={"csrf_token": "WRONG", "username": "admin",
                               "password": "pw"})
    assert r.status_code == 400


def test_csrf_rejected_on_logout(tmp_path):
    app, _, _ = _client(tmp_path, account=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
        s["csrf_token"] = "tok"
    r = c.post("/logout", data={"csrf_token": "WRONG"})
    assert r.status_code == 400


def _logged_in_client(tmp_path):
    app, cfg, config_file = _client(tmp_path, account=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
        s["csrf_token"] = "tok"
    return app, cfg, config_file, c


def test_deps_refresh_calls_bootstrap(tmp_path, monkeypatch):
    import ytdlman.webserver as ws
    calls = {}
    monkeypatch.setattr(ws.bootstrap, "ensure_ytdlp",
                        lambda config, save=None: calls.__setitem__("ytdlp", True))
    app, cfg, config_file, c = _logged_in_client(tmp_path)
    r = c.post("/deps/yt-dlp/refresh", data={"csrf_token": "tok"}, follow_redirects=False)
    assert r.status_code == 302
    assert calls.get("ytdlp") is True


def test_deps_refresh_unknown_name_404(tmp_path):
    app, cfg, config_file, c = _logged_in_client(tmp_path)
    r = c.post("/deps/bogus/refresh", data={"csrf_token": "tok"})
    assert r.status_code == 404


def test_update_check_reports(tmp_path, monkeypatch):
    import ytdlman.webserver as ws
    from ytdlman.updater import UpdateCheck
    monkeypatch.setattr(ws.updater, "check_for_update",
                        lambda v: UpdateCheck(current=v, latest="v9.9.9", available=True))
    app, cfg, config_file, c = _logged_in_client(tmp_path)
    r = c.post("/update/check", data={"csrf_token": "tok"}, follow_redirects=True)
    assert "v9.9.9" in r.get_data(as_text=True)


def test_pages_render_real_html_not_escaped(tmp_path):
    # Guard against double-escaping: the body must be real HTML markup,
    # not HTML-escaped text. Check the setup page (no account yet).
    app, _, _ = _client(tmp_path)
    c = app.test_client()
    html = c.get("/setup", follow_redirects=False).get_data(as_text=True)
    assert "<h1>" in html                      # real heading tag
    assert '<input name="username"' in html    # real form input
    assert "&lt;h1&gt;" not in html            # NOT escaped


def test_dashboard_renders_real_html(tmp_path):
    app, _, _ = _client(tmp_path, account=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = True
    html = c.get("/").get_data(as_text=True)
    assert "<table" in html                     # real dependency table
    assert "&lt;table" not in html


def test_cookies_save_and_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("YTDLMAN_HOME", str(tmp_path))
    app, cfg, config_file, c = _logged_in_client(tmp_path)
    body = ".youtube.com\tTRUE\t/\tTRUE\t1799999999\tSID\tx\n"
    c.post("/cookies", data={"csrf_token": "tok", "content": body})
    from ytdlman import paths
    assert paths.cookies_path().exists()
    assert paths.cookies_path().read_text(encoding="utf-8") == body
    c.post("/cookies", data={"csrf_token": "tok", "action": "delete"})
    assert not paths.cookies_path().exists()

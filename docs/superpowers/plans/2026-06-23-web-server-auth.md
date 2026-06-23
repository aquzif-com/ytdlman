# Web Server Mode + Auth (Sub-project A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--serve PORT` mode that, after the headless dependency/update checks, runs a Flask web server on `0.0.0.0:PORT` gated by a login/password account (created in the browser on first run), exposing a panel for dependency refresh, app-update check, cookies management, and a read-only playlist list. Without `--serve`, the app behaves exactly as today.

**Architecture:** A new `auth` section in `config.json` stores the single account (pbkdf2 hash + salt + session secret). `ytdlman/auth.py` holds the pure password/crypto helpers. `ytdlman/webserver.py` is a Flask app factory (`create_app`) with inline templates (no external files → trivial `--onefile` bundling) plus a headless `run(port)`. `main.py` becomes an argparse entry that dispatches to console or server mode.

**Tech Stack:** Python 3.12, Flask (new dependency), stdlib `hashlib`/`secrets`/`argparse`, `pytest` (Flask `test_client`). Existing `ytdlman` modules reused (bootstrap, updater, cookies, paths, config).

## Global Constraints

- Without `--serve`, console mode is unchanged. `--serve PORT` binds `0.0.0.0:PORT`; port must be 1–65535 else a clear error and non-zero exit.
- Single account (admin). Stored in `config.json` `auth` section: `username`, `password_hash`, `salt`, `secret_key`, `iterations` (default 200000). Password via `hashlib.pbkdf2_hmac("sha256", password, salt, iterations)`, salt `secrets.token_bytes(16)`, stored hex. Never store plaintext.
- `secret_key` (Flask session signing) is `secrets.token_hex(32)`, generated once and persisted in config so sessions survive restart. Session cookie: permanent, 7-day lifetime, `HttpOnly`, `SameSite=Lax`.
- Backward compat: an old `config.json` without `auth` loads with an empty default `AuthConfig` (merge over `asdict(default)`), exactly like `settings`.
- Server startup order: `setup_logging` → `load_config` → `bootstrap.ensure_all` (BootstrapError → log + continue, do NOT abort) → `updater.check_for_update` (log only, no swap) → print server URL → `app.run`.
- First run (no account) → every route except `/setup` (and `static`) redirects to `/setup`. After the account exists, every route except `/login` and `/setup` requires login; `/setup` then redirects to `/login`.
- All POST forms carry a CSRF token stored in the session; a POST whose `csrf_token` field doesn't match the session token is rejected with HTTP 400.
- Templates rendered inline via `render_template_string` with inline CSS — no external template/static files. All user-facing text Polish.
- "Sprawdź aktualizację" only reports availability (no binary swap in sub-project A).
- Out of scope (→ sub-project B): playlist add/remove, sync with live progress, settings editing via web, full server self-update, HTTPS, multiple users.

---

## File Structure

```
ytdlman/config.py      # + AuthConfig dataclass, Config.auth field, (de)serialization
ytdlman/auth.py        # NEW: pure pbkdf2 hash/verify, is_configured, create_account
ytdlman/webserver.py   # NEW: Flask create_app, login_required, CSRF, routes, inline templates, run()
main.py                # argparse: console vs --serve
requirements.txt       # + flask
tests/test_config.py    # + auth round-trip + backward compat
tests/test_auth.py      # NEW
tests/test_main.py      # NEW (argparse dispatch)
tests/test_webserver.py # NEW (Flask test_client)
```

---

### Task 1: Config `auth` section

**Files:**
- Modify: `ytdlman/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: existing `Config`, `default_config`, `_config_from_dict`, `save_config`.
- Produces: `AuthConfig(username=None, password_hash=None, salt=None, secret_key=None, iterations=200000)`; `Config.auth: AuthConfig`; round-trip + backward-compatible load.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_config.py`

```python
from ytdlman.config import AuthConfig


def test_auth_defaults_empty():
    a = AuthConfig()
    assert a.username is None and a.password_hash is None
    assert a.salt is None and a.secret_key is None
    assert a.iterations == 200000


def test_config_has_auth_section():
    assert isinstance(default_config().auth, AuthConfig)


def test_auth_roundtrip(tmp_path):
    cfg = default_config()
    cfg.auth.username = "admin"
    cfg.auth.password_hash = "deadbeef"
    cfg.auth.salt = "abcd"
    cfg.auth.secret_key = "key123"
    p = tmp_path / "config.json"
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.auth.username == "admin"
    assert loaded.auth.password_hash == "deadbeef"
    assert loaded.auth.salt == "abcd"
    assert loaded.auth.secret_key == "key123"


def test_old_config_without_auth_loads_empty(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(
        '{"settings": {}, "dependencies": {}, "playlists": []}', encoding="utf-8")
    cfg = load_config(p)
    assert cfg.auth.username is None
    assert cfg.auth.iterations == 200000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -k auth -v`
Expected: FAIL — `ImportError: cannot import name 'AuthConfig'`

- [ ] **Step 3: Add `AuthConfig` and wire it into `Config`** — in `ytdlman/config.py`:

Add the dataclass after `DependencyInfo`:

```python
@dataclass
class AuthConfig:
    username: str | None = None
    password_hash: str | None = None
    salt: str | None = None
    secret_key: str | None = None
    iterations: int = 200000
```

Add the field to `Config`:

```python
@dataclass
class Config:
    settings: Settings = field(default_factory=Settings)
    dependencies: dict = field(default_factory=dict)
    playlists: list[Playlist] = field(default_factory=list)
    auth: AuthConfig = field(default_factory=AuthConfig)
```

In `default_config()`, pass `auth=AuthConfig()`:

```python
def default_config() -> Config:
    return Config(
        settings=Settings(),
        dependencies={name: DependencyInfo() for name in _DEP_NAMES},
        playlists=[],
        auth=AuthConfig(),
    )
```

In `_config_from_dict`, parse the auth section (add before the final `return`, and include `auth=auth` in the returned `Config`):

```python
    auth = AuthConfig(**{**asdict(AuthConfig()), **data.get("auth", {})})
    return Config(settings=settings, dependencies=dependencies,
                  playlists=playlists, auth=auth)
```

In `save_config`, add `auth` to the payload:

```python
    payload = {
        "settings": asdict(config.settings),
        "dependencies": {k: asdict(v) for k, v in config.dependencies.items()},
        "playlists": [asdict(p) for p in config.playlists],
        "auth": asdict(config.auth),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (existing config tests + 4 new auth tests)

- [ ] **Step 5: Commit**

```bash
git add ytdlman/config.py tests/test_config.py
git commit -m "feat: add auth section to config"
```

---

### Task 2: Auth crypto helpers

**Files:**
- Create: `ytdlman/auth.py`, `tests/test_auth.py`

**Interfaces:**
- Consumes: `config.save_config` is NOT imported here; `create_account` takes a `save` callable.
- Produces (all flask-free, pure):
  - `hash_password(password: str, salt: bytes, iterations: int) -> str` (hex digest)
  - `is_configured(auth_cfg) -> bool` (username + password_hash + salt all set)
  - `verify_password(password: str, auth_cfg) -> bool` (constant-time compare)
  - `create_account(config, username: str, password: str, *, save) -> None` — sets username/salt/hash, generates `secret_key` if missing, calls `save()`.

  Note: `login_required` (a Flask concern) lives in `webserver.py`, not here, so `auth.py` stays dependency-free and unit-testable without Flask.

- [ ] **Step 1: Write the failing tests** in `tests/test_auth.py`

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ytdlman.auth'`

- [ ] **Step 3: Create `ytdlman/auth.py`**

```python
import hashlib
import secrets


def hash_password(password: str, salt: bytes, iterations: int) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return dk.hex()


def is_configured(auth_cfg) -> bool:
    return bool(auth_cfg.username and auth_cfg.password_hash and auth_cfg.salt)


def verify_password(password: str, auth_cfg) -> bool:
    if not is_configured(auth_cfg):
        return False
    candidate = hash_password(password, bytes.fromhex(auth_cfg.salt), auth_cfg.iterations)
    return secrets.compare_digest(candidate, auth_cfg.password_hash)


def create_account(config, username: str, password: str, *, save) -> None:
    salt = secrets.token_bytes(16)
    config.auth.username = username
    config.auth.salt = salt.hex()
    config.auth.password_hash = hash_password(password, salt, config.auth.iterations)
    if not config.auth.secret_key:
        config.auth.secret_key = secrets.token_hex(32)
    save()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_auth.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add ytdlman/auth.py tests/test_auth.py
git commit -m "feat: pbkdf2 auth helpers (hash/verify/create account)"
```

---

### Task 3: `main.py` argparse dispatch

**Files:**
- Modify: `main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `ytdlman.app.main` (console), `ytdlman.webserver.run` (server) — both imported lazily inside `main()` so console mode never imports Flask and tests can monkeypatch them at the source module.
- Produces: `main(argv=None) -> int` — returns 0 on success, 2 on an out-of-range port; a non-integer port makes argparse exit 2 (SystemExit). `--serve PORT` (1–65535) calls `webserver.run(PORT)`; no `--serve` calls console `main()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_main.py`

```python
import pytest
import main as entry


def test_no_serve_runs_console(monkeypatch):
    called = {"console": 0, "server": None}
    import ytdlman.app as app_mod
    monkeypatch.setattr(app_mod, "main", lambda: called.__setitem__("console", called["console"] + 1))
    assert entry.main([]) == 0
    assert called["console"] == 1


def test_serve_runs_server(monkeypatch):
    called = {}
    import ytdlman.webserver as ws
    monkeypatch.setattr(ws, "run", lambda port: called.__setitem__("port", port))
    assert entry.main(["--serve", "8080"]) == 0
    assert called["port"] == 8080


def test_serve_rejects_out_of_range_port(monkeypatch):
    import ytdlman.webserver as ws
    monkeypatch.setattr(ws, "run", lambda port: (_ for _ in ()).throw(AssertionError("should not run")))
    assert entry.main(["--serve", "0"]) == 2
    assert entry.main(["--serve", "99999"]) == 2


def test_serve_rejects_non_integer_port():
    with pytest.raises(SystemExit):  # argparse rejects non-int
        entry.main(["--serve", "abc"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: FAIL — `entry.main` is not callable with argv (current `main.py` imports a no-arg console main).

- [ ] **Step 3: Rewrite `main.py`**

```python
import argparse
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ytdlman",
        description="Pobieranie playlist/kanałów YouTube jako MP3.")
    parser.add_argument(
        "--serve", metavar="PORT", type=int, default=None,
        help="Uruchom serwer WWW na 0.0.0.0:PORT zamiast trybu konsolowego.")
    args = parser.parse_args(argv)

    if args.serve is None:
        from ytdlman.app import main as console_main
        console_main()
        return 0

    if not (1 <= args.serve <= 65535):
        print(f"Błąd: port musi być w zakresie 1-65535 (podano {args.serve}).",
              file=sys.stderr)
        return 2

    from ytdlman.webserver import run as server_run
    server_run(args.serve)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_main.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: argparse entry — console vs --serve server mode"
```

---

### Task 4: Web server core (Flask app, auth pages, dashboard shell)

**Files:**
- Create: `ytdlman/webserver.py`
- Modify: `requirements.txt`
- Test: `tests/test_webserver.py`

**Interfaces:**
- Consumes: `config` (Config + load/save), `auth` (is_configured/verify_password/create_account), `paths`, `bootstrap.current_status`, `cookies.inspect_cookies`, `version.APP_VERSION`.
- Produces:
  - `login_required(view)` decorator (redirects to `/login` when no session).
  - `create_app(config, config_file) -> flask.Flask` — ensures a `secret_key` exists (generates + saves if missing), sets session config, registers routes `setup`, `login`, `logout`, `dashboard` (the dashboard in this task is read-only: dependency status table + read-only playlist list; action buttons/forms and their routes arrive in Task 5), plus a `before_request` guard that forces `/setup` until an account exists.
  - CSRF helpers `_csrf_token()` (get-or-create token in session) and `_check_csrf()` (abort 400 on mismatch).

- [ ] **Step 1: Add Flask dependency and install it**

In `requirements.txt` add a line:

```
flask>=3.0
```

Run: `.venv/bin/python -m pip install "flask>=3.0"`
Expected: Flask installs into the venv.

- [ ] **Step 2: Write the failing tests** in `tests/test_webserver.py`

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_webserver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ytdlman.webserver'`

- [ ] **Step 4: Create `ytdlman/webserver.py`** (core; Task 5 adds the operation routes)

```python
import secrets
from datetime import timedelta
from functools import wraps

from flask import (Flask, session, redirect, url_for, request,
                   render_template_string, flash, abort)

from . import bootstrap, paths
from .auth import is_configured, verify_password, create_account
from .config import save_config
from .cookies import inspect_cookies

SESSION_DAYS = 7

_BASE = """<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YTDLMAN</title><style>
body{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#222}
h1,h2{font-weight:600} table{border-collapse:collapse;width:100%;margin:1rem 0}
td,th{border:1px solid #ddd;padding:.4rem .6rem;text-align:left}
.flash{padding:.6rem .8rem;border-radius:6px;margin:.4rem 0}
.flash.success{background:#e6f4ea;color:#1e7e34}.flash.error{background:#fdecea;color:#b71c1c}
button{padding:.4rem .8rem;border:0;border-radius:6px;background:#2962ff;color:#fff;cursor:pointer}
input,textarea{padding:.4rem;border:1px solid #ccc;border-radius:6px;width:100%;box-sizing:border-box}
form{margin:.5rem 0}label{display:block;margin:.5rem 0 .2rem}
</style></head><body>
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% for cat, msg in msgs %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}
{% endwith %}
{{ body }}
</body></html>"""

_SETUP = """<h1>Utwórz konto</h1>
<p>To pierwsze uruchomienie — załóż konto administratora.</p>
<form method="post" action="{{ url_for('setup') }}">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<label>Login</label><input name="username" autofocus required>
<label>Hasło</label><input name="password" type="password" required>
<label>Powtórz hasło</label><input name="confirm" type="password" required>
<p><button type="submit">Utwórz konto</button></p></form>"""

_LOGIN = """<h1>Logowanie</h1>
<form method="post" action="{{ url_for('login') }}">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<label>Login</label><input name="username" autofocus required>
<label>Hasło</label><input name="password" type="password" required>
<p><button type="submit">Zaloguj</button></p></form>"""

# Dashboard body for Task 4 is read-only (no action forms yet).
_DASHBOARD = """<h1>YTDLMAN</h1>
<form method="post" action="{{ url_for('logout') }}" style="float:right">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<button type="submit">Wyloguj</button></form>
<h2>Zależności</h2>
<table><tr><th>Nazwa</th><th>Obecna</th><th>Wersja</th></tr>
{% for d in deps %}<tr><td>{{ d.name }}</td>
<td>{{ "tak" if d.present else "nie" }}</td><td>{{ d.version or "—" }}</td></tr>{% endfor %}
</table>
<h2>Playlisty</h2>
{% if playlists %}<table><tr><th>Autor</th><th>Album</th><th>Utworów</th></tr>
{% for p in playlists %}<tr><td>{{ p.author }}</td><td>{{ p.album }}</td>
<td>{{ p.tracks|length }}</td></tr>{% endfor %}</table>
{% else %}<p>Brak playlist.</p>{% endif %}"""


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["csrf_token"] = token
    return token


def _check_csrf() -> None:
    if request.form.get("csrf_token") != session.get("csrf_token"):
        abort(400)


def create_app(config, config_file):
    def save():
        save_config(config, config_file)

    if not config.auth.secret_key:
        config.auth.secret_key = secrets.token_hex(32)
        save()

    app = Flask(__name__)
    app.secret_key = config.auth.secret_key
    app.permanent_session_lifetime = timedelta(days=SESSION_DAYS)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

    @app.before_request
    def _require_account():
        if request.endpoint in ("setup", "static"):
            return None
        if not is_configured(config.auth):
            return redirect(url_for("setup"))
        return None

    @app.route("/setup", methods=["GET", "POST"])
    def setup():
        if is_configured(config.auth):
            return redirect(url_for("login"))
        if request.method == "POST":
            _check_csrf()
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            confirm = request.form.get("confirm") or ""
            if not username or not password:
                flash("Login i hasło są wymagane.", "error")
            elif password != confirm:
                flash("Hasła nie są identyczne.", "error")
            else:
                create_account(config, username, password, save=save)
                session.permanent = True
                session["logged_in"] = True
                return redirect(url_for("dashboard"))
        return render_template_string(_BASE, body=render_template_string(
            _SETUP, csrf=_csrf_token()))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            _check_csrf()
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            if username == config.auth.username and verify_password(password, config.auth):
                session.permanent = True
                session["logged_in"] = True
                return redirect(url_for("dashboard"))
            flash("Błędny login lub hasło.", "error")
        return render_template_string(_BASE, body=render_template_string(
            _LOGIN, csrf=_csrf_token()))

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        _check_csrf()
        session.clear()
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def dashboard():
        return render_template_string(_BASE, body=render_template_string(
            _DASHBOARD, csrf=_csrf_token(),
            deps=bootstrap.current_status(config), playlists=config.playlists))

    return app
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_webserver.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add ytdlman/webserver.py tests/test_webserver.py requirements.txt
git commit -m "feat: Flask web server core — setup/login/logout, dashboard, CSRF"
```

---

### Task 5: Operations (deps refresh, update check, cookies) + headless run

**Files:**
- Modify: `ytdlman/webserver.py`
- Test: `tests/test_webserver.py`

**Interfaces:**
- Consumes: Task 4's `create_app`/`_check_csrf`/`login_required`, plus `bootstrap.ensure_ytdlp/ensure_ffmpeg/ensure_deno/BootstrapError`, `updater.check_for_update`, `paths.*_path`, `cookies.inspect_cookies`, `version.APP_VERSION`, `logging_setup.setup_logging/get_logger`, `config.load_config`.
- Produces:
  - Routes (all `login_required`, all CSRF-checked, all POST→redirect to dashboard): `POST /deps/<name>/refresh` (name ∈ yt-dlp/ffmpeg/deno; delete file(s) then `ensure_*`), `POST /update/check` (report only), `POST /cookies` (save pasted/uploaded content or delete).
  - Dashboard template gains: a refresh button per dependency, app version + "Sprawdź aktualizację" button, cookies status + textarea/file form + delete.
  - `run(port: int) -> None` — headless startup (logging → load → ensure_all (continue on BootstrapError) → check_for_update (log only) → print URL → `app.run(host="0.0.0.0", port=port)`).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_webserver.py`

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_webserver.py -k "deps or update_check or cookies" -v`
Expected: FAIL — routes don't exist yet (404 from Flask for the unknown rules, so assertions on redirect/calls fail).

- [ ] **Step 3: Add the operation routes and `run()`** — in `ytdlman/webserver.py`:

Extend the imports at the top:

```python
from . import bootstrap, paths, updater
from .config import load_config, save_config
from .logging_setup import setup_logging, get_logger
from version import APP_VERSION
```

(Keep the existing `from .auth ...` and `from .cookies ...` imports.)

Replace the `_DASHBOARD` template string with the action-enabled version:

```python
_DASHBOARD = """<h1>YTDLMAN</h1>
<form method="post" action="{{ url_for('logout') }}" style="float:right">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<button type="submit">Wyloguj</button></form>
<h2>Aplikacja</h2>
<p>Wersja: {{ app_version }}.
<form method="post" action="{{ url_for('update_check') }}" style="display:inline">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<button type="submit">Sprawdź aktualizację</button></form></p>
<h2>Zależności</h2>
<table><tr><th>Nazwa</th><th>Obecna</th><th>Wersja</th><th></th></tr>
{% for d in deps %}<tr><td>{{ d.name }}</td>
<td>{{ "tak" if d.present else "nie" }}</td><td>{{ d.version or "—" }}</td>
<td><form method="post" action="{{ url_for('deps_refresh', name=d.name) }}">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<button type="submit">Pobierz / Aktualizuj</button></form></td></tr>{% endfor %}
</table>
<h2>Cookies</h2>
<p>Status: {% if cookies.present %}wykryto ({{ cookies.entry_count }} wpisów,
YouTube: {{ "tak" if cookies.has_youtube else "nie" }}){% else %}brak pliku{% endif %}.</p>
<form method="post" action="{{ url_for('cookies_save') }}">
<input type="hidden" name="csrf_token" value="{{ csrf }}">
<label>Treść cookies.txt</label>
<textarea name="content" rows="6" placeholder="# Netscape HTTP Cookie File ..."></textarea>
<p><button type="submit">Zapisz cookies</button>
<button type="submit" name="action" value="delete">Usuń cookies</button></p></form>
<h2>Playlisty</h2>
{% if playlists %}<table><tr><th>Autor</th><th>Album</th><th>Utworów</th></tr>
{% for p in playlists %}<tr><td>{{ p.author }}</td><td>{{ p.album }}</td>
<td>{{ p.tracks|length }}</td></tr>{% endfor %}</table>
{% else %}<p>Brak playlist.</p>{% endif %}"""
```

Update the `dashboard` view to pass the new context (replace its body):

```python
    @app.route("/")
    @login_required
    def dashboard():
        return render_template_string(_BASE, body=render_template_string(
            _DASHBOARD, csrf=_csrf_token(), app_version=APP_VERSION,
            deps=bootstrap.current_status(config),
            cookies=inspect_cookies(paths.cookies_path()),
            playlists=config.playlists))
```

Add the three operation routes inside `create_app` (before `return app`):

```python
    @app.route("/deps/<name>/refresh", methods=["POST"])
    @login_required
    def deps_refresh(name):
        _check_csrf()
        try:
            if name == "yt-dlp":
                paths.ytdlp_path().unlink(missing_ok=True)
                bootstrap.ensure_ytdlp(config, save=save)
            elif name == "ffmpeg":
                paths.ffmpeg_path().unlink(missing_ok=True)
                paths.ffprobe_path().unlink(missing_ok=True)
                bootstrap.ensure_ffmpeg(config, save=save)
            elif name == "deno":
                paths.deno_path().unlink(missing_ok=True)
                bootstrap.ensure_deno(config, save=save)
            else:
                abort(404)
            flash(f"Zaktualizowano: {name}.", "success")
        except bootstrap.BootstrapError as exc:
            flash(f"Błąd aktualizacji {name}: {exc}", "error")
        return redirect(url_for("dashboard"))

    @app.route("/update/check", methods=["POST"])
    @login_required
    def update_check():
        _check_csrf()
        chk = updater.check_for_update(APP_VERSION)
        if chk.latest is None:
            flash("Nie udało się sprawdzić aktualizacji (szczegóły w logs/).", "error")
        elif chk.available:
            flash(f"Dostępna nowsza wersja {chk.latest} (masz {APP_VERSION}).", "success")
        else:
            flash(f"Masz najnowszą wersję ({APP_VERSION}).", "success")
        return redirect(url_for("dashboard"))

    @app.route("/cookies", methods=["POST"])
    @login_required
    def cookies_save():
        _check_csrf()
        path = paths.cookies_path()
        if request.form.get("action") == "delete":
            path.unlink(missing_ok=True)
            flash("Usunięto cookies.txt.", "success")
        else:
            content = request.form.get("content", "")
            upload = request.files.get("file")
            if upload and upload.filename:
                content = upload.read().decode("utf-8", errors="replace")
            path.write_text(content, encoding="utf-8")
            info = inspect_cookies(path)
            flash(f"Zapisano cookies.txt ({info.entry_count} wpisów).", "success")
        return redirect(url_for("dashboard"))
```

Add `run()` at module level (after `create_app`):

```python
def run(port: int) -> None:
    setup_logging()
    log = get_logger()
    config_file = paths.config_path()
    config = load_config(config_file)

    def save():
        save_config(config, config_file)

    log.info("Sprawdzam zależności...")
    try:
        bootstrap.ensure_all(config, save=save)
    except bootstrap.BootstrapError as exc:
        log.error("Problem z zależnościami: %s (start kontynuowany).", exc)

    chk = updater.check_for_update(APP_VERSION)
    if chk.latest and chk.available:
        log.info("Dostępna nowsza wersja aplikacji: %s (masz %s).", chk.latest, APP_VERSION)
    elif chk.latest:
        log.info("Aplikacja aktualna (%s).", APP_VERSION)

    app = create_app(config, config_file)
    log.info("Serwer WWW: http://0.0.0.0:%d "
             "(pierwsze wejście poprosi o założenie konta)", port)
    app.run(host="0.0.0.0", port=port)
```

- [ ] **Step 4: Run the webserver tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_webserver.py -v`
Expected: PASS (Task 4 tests + the 4 new operation tests)

- [ ] **Step 5: Smoke-test the server boots and serves `/setup`** (non-interactive, time-boxed)

Run:
```bash
YTDLMAN_HOME=$(mktemp -d) .venv/bin/python -c "
from ytdlman.config import default_config, save_config
from ytdlman.webserver import create_app
import pathlib
home = pathlib.Path('$(mktemp -d)')
cfg = default_config(); cf = home/'config.json'; save_config(cfg, cf)
app = create_app(cfg, cf); app.config.update(TESTING=True)
c = app.test_client()
r = c.get('/', follow_redirects=False)
print('redirect to setup:', r.status_code, r.headers.get('Location'))
assert r.status_code == 302 and '/setup' in r.headers['Location']
print('OK')
"
```
Expected: prints the redirect line and `OK`.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add ytdlman/webserver.py tests/test_webserver.py
git commit -m "feat: web panel operations (deps refresh, update check, cookies) + headless run"
```

---

## Self-Review Notes

- **Spec coverage:** `--serve PORT` + port validation + console default (Task 3); `auth` config section + backward compat (Task 1); pbkdf2 hash/verify/create_account + secret_key persistence (Task 2, secret_key also ensured in `create_app` Task 4); first-run `/setup` guard, `/login`, `/logout`, session (HttpOnly/SameSite/permanent 7-day), CSRF (Task 4); dashboard with dep status + per-dep refresh button, app version + check-update, cookies status + form + delete, read-only playlists (Tasks 4+5); headless startup order deps→update→serve (Task 5 `run`); inline templates / Flask dep / `--onefile` friendliness (Task 4). All covered.
- **Inter-task green:** Task 4 ships a read-only dashboard (no action routes referenced), so its template doesn't `url_for` a missing endpoint; Task 5 swaps in the action template at the same time it adds those routes. Suite stays green at each boundary.
- **Placeholder scan:** none — every code/test step is complete.
- **Type consistency:** `create_app(config, config_file)`, `_check_csrf()`, `login_required`, `_csrf_token()` defined in Task 4 and reused unchanged in Task 5; `AuthConfig` fields (Task 1) consumed by `auth.py` (Task 2) and `webserver` (Tasks 4-5); `create_account(config, username, password, *, save)` signature consistent across auth tests and both setup-route call sites; `updater.UpdateCheck(current/latest/available)` and `bootstrap.current_status`/`ensure_*`/`BootstrapError` match the existing modules.

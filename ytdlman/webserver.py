import secrets
from datetime import timedelta
from functools import wraps

from flask import (Flask, session, redirect, url_for, request,
                   render_template_string, flash, abort)

from . import bootstrap, paths, updater
from .auth import is_configured, verify_password, create_account
from .config import load_config, save_config
from .cookies import inspect_cookies
from .logging_setup import setup_logging, get_logger
from version import APP_VERSION

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
            _DASHBOARD, csrf=_csrf_token(), app_version=APP_VERSION,
            deps=bootstrap.current_status(config),
            cookies=inspect_cookies(paths.cookies_path()),
            playlists=config.playlists))

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

    return app


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

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

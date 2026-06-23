from . import bootstrap, paths, ui
from .config import load_config, save_config
from .logging_setup import setup_logging, get_logger
from .sync import sync_all, sync_playlist


def main() -> None:
    setup_logging()
    log = get_logger()
    config_file = paths.config_path()
    config = load_config(config_file)

    def save():
        save_config(config, config_file)

    cookies = paths.cookies_path() if paths.cookies_path().exists() else None
    music_root = paths.music_root(config.settings.music_dir)

    ui.info("Sprawdzam zależności...")
    try:
        statuses = bootstrap.ensure_all(config, save=save)
        ui.show_dependencies(statuses)
    except bootstrap.BootstrapError as exc:
        ui.error(f"Problem z zależnościami: {exc} (szczegóły w logs/). "
                 "Niektóre funkcje mogą nie działać.")

    sync_kwargs = dict(music_root=music_root, ytdlp=paths.ytdlp_path(),
                       ffmpeg_dir=paths.ffmpeg_dir(), bin_dir=paths.bin_dir(),
                       cookies=cookies, save=save, on_progress=ui.progress)

    while True:
        try:
            choice = ui.main_menu()
            if choice == "exit":
                save(); ui.info("Do zobaczenia!"); return
            elif choice == "sync_all":
                results = sync_all(config, **sync_kwargs)
                total = sum(r.downloaded for r in results.values())
                fails = sum(r.failed for r in results.values())
                ui.success(f"Gotowe. Pobrano {total}, błędów {fails}.")
            elif choice == "sync_one":
                pl = ui.select_playlist(config.playlists)
                if pl:
                    r = sync_playlist(config, pl, **sync_kwargs)
                    ui.success(f"Gotowe. Pobrano {r.downloaded}, błędów {r.failed}.")
            elif choice == "add":
                data = ui.prompt_add_playlist()
                if data:
                    config.playlists.append(ui.new_playlist(*data))
                    save()
                    ui.success("Dodano playlistę.")
            elif choice == "list":
                ui.show_playlists(config.playlists)
            elif choice == "remove":
                pl = ui.select_playlist(config.playlists)
                if pl and ui.confirm(f"Usunąć '{pl.author} — {pl.album}' z konfiguracji? "
                                     "(pliki MP3 zostaną na dysku)"):
                    config.playlists = [p for p in config.playlists if p.id != pl.id]
                    save()
                    ui.success("Usunięto wpis playlisty.")
            elif choice == "deps":
                ui.show_dependencies(bootstrap.current_status(config))
                if ui.confirm("Wymusić ponowne pobranie brakujących/aktualizację?"):
                    for path in (paths.ytdlp_path(), paths.ffmpeg_path(),
                                 paths.ffprobe_path(), paths.deno_path()):
                        if path.exists():
                            path.unlink()
                    try:
                        ui.show_dependencies(bootstrap.ensure_all(config, save=save))
                    except bootstrap.BootstrapError as exc:
                        ui.error(f"Problem z aktualizacją: {exc} (szczegóły w logs/).")
            elif choice == "settings":
                ui.info(f"music_dir={config.settings.music_dir}, "
                        f"audio_quality={config.settings.audio_quality}, "
                        f"auto_check_updates={config.settings.auto_check_updates}")
        except KeyboardInterrupt:
            save(); ui.warn("Przerwano. Zapisano konfigurację. Wychodzę."); return
        except Exception as exc:  # last-resort guard — no raw stacktrace to user
            save()
            log.exception("Nieobsłużony błąd w menu")
            ui.error(f"Wystąpił nieoczekiwany błąd: {exc} (szczegóły w logs/).")

import uuid
import questionary
from rich.console import Console
from rich.table import Table

from .clock import now_iso
from .config import Playlist, validate_throttle

console = Console()

MENU_CHOICES = {
    "Synchronizuj wszystko": "sync_all",
    "Synchronizuj jedną": "sync_one",
    "Dodaj playlistę": "add",
    "Lista playlist": "list",
    "Usuń playlistę": "remove",
    "Zależności / aktualizacje": "deps",
    "Aktualizuj aplikację": "update",
    "Ustawienia": "settings",
    "Wyjście": "exit",
}


def main_menu() -> str:
    answer = questionary.select("YTDLMAN — wybierz opcję:",
                                choices=list(MENU_CHOICES.keys())).ask()
    if answer is None:
        return "exit"
    return MENU_CHOICES[answer]


def prompt_add_playlist():
    url = questionary.text("URL playlisty YouTube:").ask()
    if not url:
        return None
    author = questionary.text("Autor utworów (Artist):").ask()
    album = questionary.text("Album:").ask()
    if not author or not album:
        warn("Autor i album są wymagane — anuluję dodawanie.")
        return None
    return url.strip(), author.strip(), album.strip()


def select_playlist(playlists: list[Playlist]):
    if not playlists:
        warn("Brak playlist.")
        return None
    labels = {f"{p.author} — {p.album} ({len(p.tracks)} utw.)": p for p in playlists}
    answer = questionary.select("Wybierz playlistę:",
                                choices=list(labels.keys())).ask()
    return labels.get(answer) if answer else None


def show_playlists(playlists: list[Playlist]) -> None:
    if not playlists:
        warn('Brak playlist. Dodaj pierwszą opcją „Dodaj playlistę“.')
        return
    table = Table(title="Playlisty")
    table.add_column("Autor"); table.add_column("Album")
    table.add_column("Utworów", justify="right"); table.add_column("Ostatnia sync")
    for p in playlists:
        table.add_row(p.author, p.album, str(len(p.tracks)), p.last_sync or "—")
    console.print(table)


def show_dependencies(statuses) -> None:
    table = Table(title="Zależności")
    table.add_column("Nazwa"); table.add_column("Obecna"); table.add_column("Wersja")
    for s in statuses:
        mark = "[green]tak[/green]" if s.present else "[red]nie[/red]"
        table.add_row(s.name, mark, s.version or "—")
    console.print(table)


def confirm(message: str) -> bool:
    return bool(questionary.confirm(message, default=False).ask())


def info(msg): console.print(f"[cyan]{msg}[/cyan]")
def success(msg): console.print(f"[green]{msg}[/green]")
def warn(msg): console.print(f"[yellow]{msg}[/yellow]")
def error(msg): console.print(f"[red]{msg}[/red]")


def pause(message: str = "Naciśnij Enter, aby wrócić do menu...") -> None:
    try:
        questionary.press_any_key_to_continue(message).ask()
    except Exception:
        try:
            input(message)
        except EOFError:
            pass


def edit_settings(settings) -> bool:
    """Edit settings in place. Returns True if applied, False if cancelled."""
    audio_quality = questionary.text(
        "Jakość audio (np. 320):", default=settings.audio_quality).ask()
    if audio_quality is None:
        return False
    while True:
        sleep_raw = questionary.text(
            "Przerwa min (s):", default=str(settings.sleep_interval)).ask()
        if sleep_raw is None:
            return False
        max_raw = questionary.text(
            "Przerwa max (s):", default=str(settings.max_sleep_interval)).ask()
        if max_raw is None:
            return False
        limit_raw = questionary.text(
            "Limit pasma (puste / 500K / 1M):", default=settings.limit_rate).ask()
        if limit_raw is None:
            return False
        try:
            sleep_interval, max_sleep_interval, limit_rate = validate_throttle(
                sleep_raw, max_raw, limit_raw)
            break
        except ValueError as exc:
            error(str(exc))
    auto = questionary.confirm(
        "Auto-sprawdzanie aktualizacji aplikacji?",
        default=settings.auto_check_updates).ask()
    if auto is None:
        return False
    settings.audio_quality = audio_quality.strip() or settings.audio_quality
    settings.sleep_interval = sleep_interval
    settings.max_sleep_interval = max_sleep_interval
    settings.limit_rate = limit_rate
    settings.auto_check_updates = bool(auto)
    return True


def progress(index: int, total: int, title: str) -> None:
    console.print(f"[cyan]\\[{index}/{total}][/cyan] Pobieram: {title}")


def show_cookies_status(status) -> None:
    if not status.present:
        info("Nie wykryto pliku cookies.txt — pobieranie bez cookies "
             "(część filmów może wymagać zalogowania).")
        return
    if not status.valid:
        warn("Wykryto cookies.txt, ale wygląda niepoprawnie (brak poprawnych "
             "wpisów cookie). Mimo to zostanie dołączony do yt-dlp.")
        return
    yt = "tak" if status.has_youtube else "nie"
    success(f"Wykryto cookies.txt ({status.entry_count} wpisów, YouTube: {yt}) — "
            "zostanie dołączony do yt-dlp.")


def new_playlist(url: str, author: str, album: str) -> Playlist:
    return Playlist(id=str(uuid.uuid4()), url=url, author=author, album=album,
                    added_at=now_iso())

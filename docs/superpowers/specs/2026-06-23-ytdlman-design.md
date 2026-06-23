# YTDLMAN — projekt aplikacji

**Data:** 2026-06-23
**Status:** zatwierdzony
**Repo:** https://github.com/aquzif-com/ytdlman (zainicjowane z README.md)

## Cel

Portable, konsolowa aplikacja na Windows (pakowana do samowystarczalnego `.exe`)
do pobierania muzyki z playlist YouTube jako MP3 w najlepszej jakości, z myślą
o bibliotece Plex / Plexamp. Aplikacja zapamiętuje listę playlist i przy kolejnych
uruchomieniach synchronizuje je — wykrywa nowe wpisy i dociąga tylko brakujące.

Założenie kluczowe: **jedna playlista = jeden autor + jeden album** (oba podawane
ręcznie przy dodawaniu playlisty i nadpisujące to, co wykryje yt-dlp).

## Środowisko docelowe

- **Target:** Windows (na razie wyłącznie).
- **Runtime:** aplikacja w Pythonie pakowana przez PyInstaller w trybie `--onefile` —
  cały interpreter Pythona i biblioteki są w `.exe`. Komputer docelowy **nie** musi
  mieć zainstalowanego Pythona.
- **Build:** PyInstaller buduje pod system, na którym działa → build pod Windows
  (np. GitHub Actions z runnerem Windows lub maszyna/VM z Windows). Dev odbywa się
  na macOS.
- **Portable:** wszystko działa względem katalogu aplikacji; brak instalacji,
  brak zapisu poza własnym katalogiem.

## Architektura i moduły

| Moduł | Odpowiedzialność |
|---|---|
| `main.py` | punkt wejścia, pętla menu |
| `ui.py` | menu i interakcja (`rich` + `questionary`) |
| `config.py` | wczytywanie/zapis `config.json`, model danych, atomowość, migracja |
| `bootstrap.py` | sprawdzanie i pobieranie zależności (yt-dlp, ffmpeg, deno) + auto-update |
| `downloader.py` | wołanie yt-dlp, pobieranie MP3, postęp |
| `metadata.py` | czyszczenie tytułu, tagowanie ID3 + okładka (`mutagen`) |
| `sync.py` | pobierz listę wpisów playlisty, porównaj ze stanem, dociągnij nowe, numeracja |
| `paths.py` | ścieżki względem katalogu aplikacji (działa też ze spakowanego exe) |
| `logging_setup.py` | logi do pliku w `logs/` + czytelne komunikaty na ekranie |

**Zależności Python (pakowane w exe):** `rich`, `questionary`, `mutagen`.
**Binaria pobierane do `bin/`:** yt-dlp, ffmpeg (+ffprobe), deno.

## Układ katalogów (portable)

```
/ (katalog aplikacji)
├── ytdlman.exe
├── yt-dlp.exe            (pobierany/aktualizowany automatycznie)
├── cookies.txt           (opcjonalny; jeśli jest, przekazywany do yt-dlp)
├── config.json           (lista playlist + ustawienia + wersje zależności)
├── logs/
│   └── ytdlman_YYYY-MM-DD.log
├── bin/                   (ffmpeg.exe, ffprobe.exe, deno.exe — auto-pobrane)
└── music/
    └── <Autor>/
        └── <Album>/
            ├── 01 - Tytuł.mp3
            ├── 02 - Tytuł.mp3
            └── folder.jpg  (okładka albumu)
```

Struktura `Artysta/Album/## - Tytuł.mp3` jest dobrana pod Plex/Plexamp.
Dwie playlisty tego samego autora trafiają pod wspólny folder artysty.

## Bootstrap zależności

Przy starcie aplikacja sprawdza `bin/` (oraz `yt-dlp.exe` obok aplikacji)
i pobiera, czego brakuje. Każda zależność ma wersję i może być wymuszona
do aktualizacji z menu.

| Zależność | Źródło | Logika |
|---|---|---|
| **yt-dlp.exe** | GitHub releases `yt-dlp/yt-dlp` | leży obok aplikacji; brak → pobierz najnowszy; update sprawdza najnowszy tag i podmienia |
| **ffmpeg** | build Windows (np. gyan.dev / BtbN) | pobierz ZIP, rozpakuj `ffmpeg.exe`+`ffprobe.exe` do `bin/` |
| **Deno** | GitHub releases `denoland/deno` | pobierz ZIP Windows do `bin/`; przekazywany yt-dlp jako runtime JS |

Zasady:
- Każdy krok pokazuje pasek postępu (`rich`) i loguje do pliku.
- Błąd (brak sieci, 404) → czytelny komunikat „Nie udało się pobrać X, powód: …,
  szczegóły w logs/…", bez crasha ze stacktrace.
- Wersje zależności zapisywane w `config.json` (sekcja `dependencies`) i pokazywane
  w menu „Zależności / aktualizacje".
- Dokładne URL-e buildów ffmpeg/Deno są konfigurowalne w jednym miejscu (źródła
  bywają nietrwałe).
- `cookies.txt` obok aplikacji (jeśli istnieje) → automatyczny `--cookies` do yt-dlp.

## Model danych (`config.json`)

```json
{
  "settings": {
    "music_dir": "music",
    "audio_quality": "320",
    "auto_check_updates": true
  },
  "dependencies": {
    "yt-dlp":  { "version": "2026.06.01", "checked_at": "..." },
    "ffmpeg":  { "version": "...", "checked_at": "..." },
    "deno":    { "version": "...", "checked_at": "..." }
  },
  "playlists": [
    {
      "id": "uuid",
      "url": "https://www.youtube.com/playlist?list=...",
      "author": "Podany przez użytkownika",
      "album": "Podany przez użytkownika",
      "added_at": "2026-06-23T...",
      "last_sync": "2026-06-23T...",
      "next_track_number": 14,
      "tracks": [
        {
          "video_id": "abc123",
          "track_number": 1,
          "title": "Wyczyszczony tytuł",
          "status": "downloaded",
          "file": "music/Autor/Album/01 - Tytuł.mp3",
          "downloaded_at": "..."
        }
      ]
    }
  ]
}
```

Zasady:
- `tracks` to pamięć stanu — po `video_id` wiemy, co już mamy.
- `next_track_number` rośnie monotonicznie → **stałe numery ścieżek** (wariant A:
  numer wg kolejności pobrania, nowe utwory zawsze na końcu albumu, nigdy się
  nie przesuwają).
- `status` wpisu: `downloaded` / `failed` (failed = ponawiamy przy następnej sync).
- Zapis **atomowy** (zapis do `.tmp` + rename).
- **Config zapisywany po każdej pojedynczej akcji** — m.in. po pobraniu i otagowaniu
  *każdego* utworu, nie zbiorczo. Przerwanie w połowie nie traci postępu.

## Menu i operacje

```
1. Synchronizuj wszystko        — sprawdź każdą playlistę, dociągnij nowe
2. Synchronizuj jedną           — wybór z listy
3. Dodaj playlistę              — URL + pytanie o Autora i Album
4. Lista playlist               — podgląd: ile utworów, ostatnia sync
5. Usuń playlistę               — usuwa TYLKO wpis z configu (pliki MP3 zostają)
6. Zależności / aktualizacje    — status yt-dlp/ffmpeg/deno, wymuś update
7. Ustawienia
0. Wyjście
```

- Po starcie pokazuje się **menu** (brak trybu auto-sync na starcie).
- Dodawanie playlisty pyta o `author` i `album` (nadpisują dane z yt-dlp).
- Usuwanie playlisty kasuje tylko wpis z `config.json`; pliki MP3 nie są ruszane.

## Przepływ synchronizacji

Dla każdej playlisty:

1. **Pobierz listę wpisów:** `yt-dlp --flat-playlist --print id,title <url>`
   (szybkie, bez pobierania mediów).
2. **Wykryj nowe:** odfiltruj `video_id` nieobecne w `tracks` ze statusem
   `downloaded`. Wpisy `failed` trafiają do ponowienia.
3. **Dla każdego nowego utworu (sekwencyjnie):**
   a. przydziel `track_number = next_track_number`, zinkrementuj, zapisz config
      (rezerwacja numeru),
   b. pobierz najlepsze audio + konwersja do MP3 320k (yt-dlp + ffmpeg),
   c. wyczyść tytuł, zapisz tagi ID3 (Artist, Album Artist, Album, Title, Track#,
      Year, okładka = miniatura),
   d. `status=downloaded`, ścieżka pliku, `downloaded_at` → zapisz config,
   e. przy błędzie: `status=failed`, log z powodem → zapisz config, kolejny utwór.
4. Po playliście: ustaw `last_sync` → zapisz config.
5. Zapisz `folder.jpg` (okładka) raz na album.

Na ekranie: nazwa playlisty, licznik „[3/12] Pobieram: Tytuł", pasek postępu,
podsumowanie na końcu (pobrano X, błędów Y, pominięto Z).

## Tagowanie i czyszczenie tytułu

**Czyszczenie tytułu** (zachowawcze, „best-effort", reguły w jednej rozszerzalnej liście):
- nawiasy/klamry z frazami: `(Official Video)`, `(Official Music Video)`,
  `[Official Audio]`, `(Lyrics)`, `[Lyric Video]`, `(Visualizer)`, `(HD/4K)`,
  `(Audio)` itp.,
- końcówki typu `| Official Video`,
- przycięcie nadmiarowych spacji.
- Gdy coś nietypowego — zostaw tytuł w miarę nienaruszony (lepiej za mało niż uciąć
  nazwę utworu).

**Tagi ID3 (`mutagen`):**

| Tag | Wartość |
|---|---|
| Artist (TPE1) | autor playlisty |
| Album Artist (TPE2) | autor playlisty (dla Plex) |
| Album (TALB) | album playlisty |
| Title (TIT2) | wyczyszczony tytuł |
| Track (TRCK) | `track_number` |
| Year (TDRC) | rok uploadu |
| Cover (APIC) | miniatura YT (JPEG) |

Plus `folder.jpg` w folderze albumu.

## Logi i obsługa błędów

**Logowanie:**
- `logs/ytdlman_YYYY-MM-DD.log` — pełne logi (DEBUG: komendy yt-dlp, kody wyjścia,
  stacktrace).
- Ekran: zwięzłe, kolorowane komunikaty (`rich`): INFO / sukces / ostrzeżenie / błąd.
- Każdy błąd: **co** się nie udało, **dlaczego**, **gdzie** szukać szczegółów.
- Użytkownik nigdy nie widzi surowego stacktrace — wyjątki łapane na granicach akcji
  i tłumaczone na komunikat.

**Obsługa błędów:**
- Brak sieci / błąd pobrania zależności → komunikat + powrót do menu (nie crash).
- Nieudany utwór → `status=failed`, log, kolejny utwór; ponowienie przy następnej sync.
- Uszkodzony `config.json` → backup pliku + start z czystym configiem + ostrzeżenie.
- `Ctrl+C` → czysty zapis configu i wyjście.

## Build i release (GitHub Actions)

Workflow CI (`.github/workflows/release.yml`) buduje samowystarczalny `.exe`
i publikuje go w GitHub Release.

- **Runner:** `windows-latest` (PyInstaller buduje pod system, na którym działa).
- **Wyzwalacze:** push tagu `v*` (np. `v1.0.0`) oraz `workflow_dispatch` (ręczne
  uruchomienie do testów).
- **Kroki:**
  1. checkout,
  2. `actions/setup-python` (3.12),
  3. instalacja zależności (`requirements.txt`) + `pyinstaller`,
  4. `pyinstaller --onefile --name ytdlman main.py` → `dist/ytdlman.exe`,
  5. upload artefaktu (`actions/upload-artifact`) — dostępny też dla
     `workflow_dispatch`,
  6. dla pushu tagu: utworzenie/aktualizacja GitHub Release i dołączenie
     `ytdlman.exe` (`softprops/action-gh-release` lub `gh release`).
- **Wersja aplikacji:** trzymana w jednym miejscu (`version.py`, stała
  `APP_VERSION`); workflow weryfikuje, że tag zgadza się z `APP_VERSION`.

### Przyszłość: auto-update aplikacji (poza zakresem MVP)

Zaprojektowane jako rozszerzenie istniejącego mechanizmu wersji/zależności:
aplikacja przy starcie (gdy `auto_check_updates`) sprawdza najnowszy GitHub Release
repozytorium, porównuje z `APP_VERSION` i — jeśli jest nowsza — proponuje pobranie
i podmianę własnego `.exe` (analogicznie do aktualizacji yt-dlp). Implementacja
w osobnym module `updater.py` w kolejnej iteracji. MVP tylko przygotowuje grunt:
stała `APP_VERSION` i spójny format wersji w release'ach.

## Testy (pytest)

- `metadata.py` — czyszczenie tytułów (zestaw przypadków), budowa tagów (czyste funkcje).
- `config.py` — odczyt/zapis/atomowość, migracja uszkodzonego pliku.
- `sync.py` — wykrywanie nowych wpisów i numeracja (yt-dlp i pobieranie zamockowane).
- `paths.py` — rozwiązywanie ścieżek portable (zwykły Python vs spakowany exe).
- Bootstrap i realne wołanie yt-dlp — testy ręczne / integracyjne (zależne od sieci).

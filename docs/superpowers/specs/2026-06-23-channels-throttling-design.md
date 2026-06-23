# Obsługa kanałów + grzeczne pobieranie (throttling + stop na 429)

**Data:** 2026-06-23
**Status:** zatwierdzony
**Repo:** https://github.com/aquzif-com/ytdlman
**Bazuje na:** [2026-06-23-ytdlman-design.md](2026-06-23-ytdlman-design.md)

## Cel

Umożliwić pobieranie zawartości całych kanałów YouTube (nie tylko playlist) jako
MP3, w sposób „grzeczny" dla YouTube: z konfigurowalnymi przerwami między
utworami, a w razie ograniczenia po stronie YouTube (HTTP 429) — z czystym
przerwaniem synchronizacji, komunikatem i powrotem do menu po reakcji
użytkownika.

## Założenia kluczowe

- **Kanał = kolejne źródło**, identyczne jak playlista. Ten sam przepływ „Dodaj
  playlistę": użytkownik wkleja URL kanału (`https://www.youtube.com/@nazwa`,
  `.../@nazwa/videos`), podaje autora i album, całość kanału ląduje w jednym
  albumie `music/<Autor>/<Album>/`. **Zero zmian w modelu metadanych.** yt-dlp
  listuje kanał jak playlistę.
- **Throttling tylko przez spowolnienie** (przerwy między utworami + opcjonalny
  limit pasma). Bez limitu liczby utworów na sesję.
- **HTTP 429 = twardy stop:** przerwij cały sync, pokaż komunikat, poczekaj na
  klawisz, wróć do menu.

## Zmiany w modułach

| Moduł | Zmiana |
|---|---|
| `config.py` | nowe pola w `Settings`: `sleep_interval`, `max_sleep_interval`, `limit_rate` |
| `downloader.py` | flagi throttlingu w komendach yt-dlp + wykrywanie 429 → `RateLimitError(DownloadError)` |
| `sync.py` | 429 = przerwij cały sync, cofnij zarezerwowany numer, nie oznaczaj utworu jako `failed`, przepuść `RateLimitError` w górę |
| `ui.py` | `pause()` („naciśnij klawisz…") + edytowalny ekran ustawień |
| `app.py` | łapie `RateLimitError` z sync → komunikat + `pause()` + powrót do menu |

Kanały nie wymagają nowego kodu poza weryfikacją w testach (listowanie URL
kanału przez `--flat-playlist`).

## Ustawienia throttlingu (`config.json`)

```json
"settings": {
  "music_dir": "music",
  "audio_quality": "320",
  "auto_check_updates": true,
  "sleep_interval": 5,
  "max_sleep_interval": 20,
  "limit_rate": ""
}
```

Domyślne wartości: losowa przerwa 5–20 s przed każdym utworem, brak limitu pasma.
Stary `config.json` bez tych pól musi wczytać się z wartościami domyślnymi
(zgodność wstecz).

### Mapowanie na yt-dlp

- `sleep_interval` + `max_sleep_interval` → `--sleep-interval <min> --max-sleep-interval <max>`
  (losowa przerwa przed każdym pobraniem),
- `--sleep-requests 1` — stała 1 s przerwy między zapytaniami metadanych, ale
  tylko gdy `sleep_interval > 0`; przy `sleep_interval == 0` flaga pomijana (cały
  throttling wyłączony),
- `limit_rate` (jeśli niepuste, np. `1M`) → `--limit-rate <wartość>`; puste = brak,
- `build_entries_command` (listowanie playlisty/kanału) również dorzuca
  `--sleep-requests`, bo tam najłatwiej o 429 przy dużym kanale.

### Walidacja (ekran ustawień)

- `sleep_interval`, `max_sleep_interval`: liczby całkowite ≥ 0,
- `max_sleep_interval ≥ sleep_interval` (gdy odwrotnie — ponowne pytanie z
  komunikatem),
- `limit_rate`: pusty string albo format `^\d+[KMG]?$` (np. `500K`, `1M`).

## Wykrywanie 429 i przerwanie sync

**Wykrywanie:** po wywołaniu yt-dlp `stderr` sprawdzany pod kątem markerów:
`HTTP Error 429`, `Too Many Requests`, `429`. Trafienie → `RateLimitError`
(podklasa `DownloadError`). Dotyczy obu miejsc: `list_playlist_entries` i
`download_track`.

**`sync.py`:** obsługa `RateLimitError` przed ogólnym `except`:
- **nie** oznacza utworu jako `failed` (ma się pobrać następnym razem),
- **cofa** zarezerwowany numer ścieżki (`next_track_number -= 1`) i zapisuje
  config — żeby nie robić dziury w numeracji (bezpieczne: sekwencyjnie był to
  ostatnio zarezerwowany numer),
- przepuszcza `RateLimitError` w górę → przerywa `sync_playlist` i całe
  `sync_all` (kolejne źródła też dostałyby 429).

Zwykłe błędy pojedynczych utworów działają jak dotąd (`failed` + kontynuacja).

**`app.py`:** `sync_all`/`sync_one` opakowane tak, że `RateLimitError` daje:
- komunikat: „YouTube ogranicza pobieranie (błąd 429). Przerwano synchronizację.
  Zwiększ przerwy w Ustawieniach i spróbuj później.",
- `pause()` („Naciśnij Enter, aby wrócić do menu…"),
- powrót do menu (pętla aplikacji).

Co już pobrane/otagowane przed 429 zostaje (config zapisywany po każdym utworze),
więc kolejny sync ruszy od miejsca przerwania.

## UI

- **`pause(message)`** — czeka na klawisz (`questionary.press_any_key_to_continue`,
  fallback `input()`).
- **Ekran ustawień** (dziś tylko wyświetla) staje się edytowalny — pyta po kolei
  o: `audio_quality`, `sleep_interval`, `max_sleep_interval`, `limit_rate`,
  `auto_check_updates`. Enter bez zmiany zostawia obecną wartość; niepoprawne
  dane → ponowne pytanie z komunikatem; po zatwierdzeniu zapis configu.
  `music_dir` pozostaje tylko do odczytu (zmiana rozjechałaby istniejącą
  bibliotekę).

## Testy (pytest)

- `config.py` — round-trip nowych pól + wartości domyślne; stary `config.json`
  bez tych pól wczytuje się z domyślnymi (zgodność wstecz).
- `downloader.py` — `build_download_command`/`build_entries_command` zawierają
  flagi throttlingu wg ustawień; `limit_rate` pomijane gdy puste; wykrywanie
  429 → `RateLimitError` (listowanie i pobieranie); URL kanału przechodzi przez
  `parse_flat_playlist`.
- `sync.py` — `RateLimitError` przerywa sync, cofa zarezerwowany numer, **nie**
  dodaje wpisu `failed`; zwykły błąd dalej działa jak wcześniej.
- Walidacja ustawień (czysta funkcja, np. `validate_settings_input` lub
  pomocnicze) — przypadki brzegowe (`max < min`, zły `limit_rate`).
- UI interaktywne (`pause`, pętla ustawień) — weryfikacja przez smoke-test, bez
  testów jednostkowych.

## Poza zakresem

- Limit liczby utworów na sesję (batch size).
- Throttling per źródło (ustawienia są globalne).
- Automatyczne ponawianie po 429 z backoffem (świadomie: użytkownik decyduje,
  kiedy wznowić).
- Osobny album per rok / per zakładka kanału (single album, jak playlista).

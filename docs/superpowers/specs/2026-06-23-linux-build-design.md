# Build i runtime pod Linux (aplikacja konsolowa, cross-platform)

**Data:** 2026-06-23
**Status:** zatwierdzony
**Repo:** https://github.com/aquzif-com/ytdlman
**Bazuje na:** [2026-06-23-ytdlman-design.md](2026-06-23-ytdlman-design.md)

## Cel

Udostępnić w pełni działającą **konsolową** wersję YTDLMAN na Linuksie (x86_64),
obok istniejącej wersji Windows. CI buduje binarkę linuksową, a kod staje się
cross-platform: ścieżki, bootstrap zależności i auto-update wybierają właściwe
binarki/URL-e/mechanizmy zależnie od platformy. (Tryb z interfejsem webowym to
osobny, późniejszy projekt — poza zakresem.)

## Założenia i zakres

- **Targety produkcyjne: Windows + Linux x86_64.** macOS to wyłącznie maszyna
  deweloperska/testowa (kod traktuje ją „jak Linux", ale realny bootstrap odpala
  się tam tylko w testach z zamockowanym pobieraniem). macOS nie jest wspierany
  produkcyjnie.
- **Tylko architektura x86_64 (amd64).** Bez ARM.
- **Release ma dwa pliki:** `ytdlman.exe` (Windows, bez zmian) + `ytdlman-linux`
  (Linux, bez rozszerzenia).
- Poza zakresem: ARM, macOS jako target, interfejs webowy, bump wersji akcji
  GitHub (ostrzeżenie o Node 20).

## Wykrywanie platformy — jedno źródło prawdy

Nowy moduł `ytdlman/platform_target.py`:

```python
def target_os() -> str:    # "windows" | "linux"
def is_windows() -> bool
def exe_suffix() -> str     # ".exe" na Windows, "" na Linux
```

Wykrywanie: jeśli ustawiona zmienna środowiskowa `YTDLMAN_PLATFORM` (override do
testów, analogicznie do `YTDLMAN_HOME`) → użyj jej wartości; inaczej autodetekcja
z `sys.platform` (`win*` → `"windows"`, reszta → `"linux"`). Dzięki temu testy
wymuszają obie platformy niezależnie od maszyny.

## `paths.py` — nazwy binarek zależne od platformy

| Funkcja | Windows | Linux |
|---|---|---|
| `ytdlp_path()` | `yt-dlp.exe` (obok aplikacji) | `yt-dlp` (obok aplikacji) |
| `ffmpeg_path()` | `bin/ffmpeg.exe` | `bin/ffmpeg` |
| `ffprobe_path()` | `bin/ffprobe.exe` | `bin/ffprobe` |
| `deno_path()` | `bin/deno.exe` | `bin/deno` |

Nazwy składane z `platform_target.exe_suffix()`. Reszta (`app_dir`, `bin_dir`,
`music_root`, `sanitize_filename`, `album_dir`) bez zmian.

**Wpływ na testy:** obecny `tests/test_paths.py` twardo zakłada `.exe`. Testy
zostaną zaktualizowane na świadome platformy — asercje windowsowe pod
`YTDLMAN_PLATFORM=windows`, bliźniacze asercje linuksowe pod
`YTDLMAN_PLATFORM=linux` (bez `.exe`).

## `bootstrap.py` — źródła i rozpakowywanie per platforma

Stałe URL-i pogrupowane per platforma (jedno miejsce do zmiany). Wybór wg
`target_os()`.

| Zależność | Windows (obecnie) | Linux (nowe) |
|---|---|---|
| **yt-dlp** | `yt-dlp.exe` z release'u | `yt-dlp_linux` z release'u → zapis jako `yt-dlp`, `chmod +x` |
| **ffmpeg** | zip gyan.dev | `ffmpeg-release-amd64-static.tar.xz` (johnvansickle) → wyciągnij `ffmpeg`+`ffprobe`, `chmod +x` |
| **Deno** | `deno-...-windows-msvc.zip` | `deno-x86_64-unknown-linux-gnu.zip` → wyciągnij `deno`, `chmod +x` |

Zmiany techniczne:
- **Rozpakowywanie `.tar.xz`** — obok istniejącego `extract_members` (zip)
  dodać wariant dla tar.xz (stdlib `tarfile` obsługuje xz), wspólny interfejs
  „wyciągnij pliki o danych basename do `bin/`, spłaszczając ścieżki".
- **`chmod +x`** — pomocnik nadający bit wykonywalny (`0o755`) na nie-Windows;
  na Windows no-op. Stosowany po pobraniu/rozpakowaniu binarek.
- **Wybór źródła** — `ensure_ytdlp`/`ensure_ffmpeg`/`ensure_deno` czytają
  `target_os()`. Logika „brak pliku → pobierz", zapis wersji, `BootstrapError`
  bez zmian. Domyślny `fetch` (urllib) i wstrzykiwanie `fetch` w testach
  zachowane (testy bez sieci).

Adres ffmpeg (johnvansickle) — konfigurowalna stała w jednym miejscu (bywa
nietrwały).

## `updater.py` — asset per platforma

| | Windows | Linux |
|---|---|---|
| Nazwa binarki | `ytdlman.exe` | `ytdlman-linux` |
| Asset w Release | `ytdlman.exe` | `ytdlman-linux` |

- `DOWNLOAD_URL` → funkcja `download_url()` składająca URL do najnowszego
  release'u z nazwą assetu zależną od `target_os()`.
- Po pobraniu i podmianie (`.new` → swap działającej na `.old` → wstawienie
  nowej) na nie-Windows ustawić `chmod +x` na nowej binarce.
- Mechanika podmiany działa na Linuksie tak samo (rename działającego pliku jest
  dozwolony). Sufiksy `.old`/`.new` bez `.exe` na Linuksie wynikają naturalnie z
  `exe.stem`/`exe.suffix`.
- Porównanie wersji, wykrywanie nowszej, komunikaty — bez zmian.

## CI: build Linux + Release z dwoma plikami

`.github/workflows/release.yml` dostaje drugi job `build-linux` obok
windowsowego:
- runner `ubuntu-latest`, te same wyzwalacze (`tag v*` + `workflow_dispatch`),
- kroki: checkout → setup-python 3.12 → instalacja `requirements.txt` +
  pyinstaller + pytest → testy → weryfikacja `tag == APP_VERSION` (tylko na
  tagu) → `pyinstaller --onefile --name ytdlman-linux main.py` → upload
  artefaktu → publikacja do tego samego Release (`softprops/action-gh-release`
  dokleja asset).
- job windowsowy bez zmian (buduje `ytdlman.exe`).

Efekt: jeden Release zawiera `ytdlman.exe` + `ytdlman-linux`. Oba joby publikują
do tego samego tagu; `action-gh-release` dokłada pliki, nie nadpisuje.

## Testy (pytest)

- `platform_target.py` — `target_os()` respektuje `YTDLMAN_PLATFORM` i
  autodetekcję z `sys.platform`; `exe_suffix()` zwraca `.exe`/`""`;
  `is_windows()` spójne z `target_os()`.
- `paths.py` — istniejące testy zaktualizowane na świadome platformy (asercje
  pod `YTDLMAN_PLATFORM=windows` i `=linux`); binarki bez `.exe` na Linuksie.
- `bootstrap.py` — z `YTDLMAN_PLATFORM=linux` (+ zamockowany `fetch`):
  `ensure_ytdlp` zapisuje `yt-dlp` (bez `.exe`) i nadaje bit wykonywalny;
  rozpakowanie `.tar.xz` wyciąga `ffmpeg`/`ffprobe`; deno z linuksowego zipa;
  wybór URL-i wg platformy. Istniejące testy windowsowe pod
  `YTDLMAN_PLATFORM=windows` zostają zielone.
- `updater.py` — `download_url()` zwraca `ytdlman.exe` dla windows i
  `ytdlman-linux` dla linux; po podmianie na nie-Windows binarka jest
  wykonywalna (bit `+x` ustawiony).
- pomocnik `chmod` — na nie-Windows ustawia `0o755`, na Windows no-op (test: na
  Linuksie plik staje się wykonywalny).
- CI/PyInstaller — weryfikowane realnym buildem na `ubuntu-latest` przy
  tagu/dispatchu (nie testem jednostkowym).

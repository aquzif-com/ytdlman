# Tryb serwera WWW + autoryzacja (pod-projekt A)

**Data:** 2026-06-23
**Status:** zatwierdzony
**Repo:** https://github.com/aquzif-com/ytdlman
**Bazuje na:** [2026-06-23-ytdlman-design.md](2026-06-23-ytdlman-design.md)

## Kontekst i podział

Interfejs webowy do obsługi aplikacji to kilka podsystemów; dzielimy na pod-projekty:

- **A (ten spec):** szkielet serwera WWW + autoryzacja + panel operacji „samodzielnych"
  (zależności, sprawdzanie aktualizacji, cookies) + lista playlist tylko do odczytu.
- **B (osobny spec później):** pełne operacje w WWW — dodawanie/usuwanie playlist,
  uruchamianie synchronizacji z paskiem postępu na żywo, ustawienia, podgląd logów,
  pełna samo-aktualizacja serwera z restartem.

## Cel

Uruchomienie aplikacji z argumentem `--serve PORT` startuje serwer WWW na
`0.0.0.0:PORT` (po sprawdzeniu zależności i aktualizacji), z dostępem chronionym
loginem i hasłem. Pierwsze wejście w przeglądarce wymusza utworzenie konta. Bez
argumentu aplikacja działa jak dotąd (tryb konsolowy, nietknięty).

## Architektura i punkt wejścia

`main.py` parsuje argumenty (argparse):
- brak `--serve` → tryb konsolowy (`ytdlman.app.main()`),
- `--serve PORT` → tryb serwera (`ytdlman.webserver.run(port)`).

Walidacja: port to liczba 1–65535; w przeciwnym razie czytelny błąd i wyjście z
kodem ≠ 0. Wiązanie na stałe `0.0.0.0:PORT`.

| Plik | Rola |
|---|---|
| `main.py` | argparse, wybór trybu |
| `ytdlman/webserver.py` | aplikacja Flask (fabryka `create_app`), trasy, start headless |
| `ytdlman/auth.py` | hashowanie/weryfikacja hasła (pbkdf2), model `AuthConfig`, `login_required`, helpery |
| `ytdlman/config.py` | nowa sekcja `auth` w `config.json` |

Tryb konsolowy i pozostałe moduły pozostają bez zmian (poza dodaniem sekcji `auth`
w `config.py` i argparse w `main.py`).

## Autoryzacja

Nowa sekcja w `config.json`:

```json
"auth": {
  "username": null,
  "password_hash": null,
  "salt": null,
  "secret_key": null,
  "iterations": 200000
}
```

- **Brak konta** = `username` jest `null` → pierwszy ekran wymusza utworzenie konta.
- **Hasło**: `hashlib.pbkdf2_hmac("sha256", password_bytes, salt, iterations)`; sól
  losowa (`secrets.token_bytes`), zapis hex. Hasło nigdy nie jest przechowywane jawnie.
- **`secret_key`**: losowy (`secrets.token_hex`), generowany raz przy tworzeniu konta,
  zapisany w configu → sesje przeżywają restart serwera.
- **Sesja Flask**: trwałe ciasteczko, wygaśnięcie po 7 dniach; `HttpOnly`, `SameSite=Lax`.
- Jedno konto (admin). Wielu użytkowników poza zakresem.

`auth.py` — czyste, testowalne funkcje:
- `hash_password(password: str, salt: bytes, iterations: int) -> str`
- `verify_password(password: str, auth_cfg) -> bool`
- `is_configured(auth_cfg) -> bool`
- `create_account(config, username, password) -> None` (ustawia hash+sól+secret_key, zapis configu)
- `login_required` (dekorator tras: brak sesji → redirect na `/login`)

Zgodność wstecz: stary `config.json` bez sekcji `auth` wczytuje się z pustą domyślną
sekcją (jak przy throttlingu/Linuksie — merge nad `asdict(default)`).

## Sekwencja startu serwera (headless)

`webserver.run(port)`:

1. `setup_logging()` — logi do pliku + konsoli startowej.
2. `load_config()`.
3. **Zależności:** `bootstrap.ensure_all(config, save)` — dociąga brakujące
   yt-dlp/ffmpeg/Deno bez pytań. `BootstrapError` → log błędu na konsolę, **start
   kontynuowany** (część funkcji może nie działać).
4. **Aktualizacja aplikacji:** `updater.check_for_update(APP_VERSION)` — **tylko log**
   („dostępna nowsza wersja vX" / „masz najnowszą"), bez podmiany binarki.
5. Wypisanie na konsolę: `Serwer WWW: http://0.0.0.0:PORT` (+ podpowiedź o zakładaniu
   konta przy pierwszym wejściu).
6. `app.run(host="0.0.0.0", port=PORT)`.

Punkty 3–4 wykonują się **przed** wystartowaniem serwera WWW. `Ctrl+C` zatrzymuje
serwer czysto.

## Trasy i ekrany

Szablony renderowane inline (`render_template_string`) z wbudowanym CSS — żeby
`--onefile` PyInstallera nie wymagał pakowania osobnych plików danych. Język polski.

| Trasa | Metoda | Dostęp | Działanie |
|---|---|---|---|
| `/setup` | GET/POST | tylko gdy brak konta | Formularz login + hasło + powtórz; POST tworzy konto, loguje, redirect `/`. Gdy konto istnieje → redirect `/login`. |
| `/login` | GET/POST | publiczna | Logowanie; błędne dane → komunikat; sukces → sesja + redirect `/`. |
| `/logout` | POST | zalogowany | Czyści sesję → `/login`. |
| `/` (dashboard) | GET | zalogowany | Status zależności + przyciski; wersja aplikacji + „Sprawdź aktualizację"; status i formularz cookies; lista playlist (read-only). |
| `/deps/<name>/refresh` | POST | zalogowany | `name ∈ {yt-dlp, ffmpeg, deno}`: usuń plik(i) + `ensure_*` (wymuszone pobranie), blokująco; wynik jako komunikat. |
| `/update/check` | POST | zalogowany | `updater.check_for_update` → komunikat „dostępna vX / masz najnowszą". |
| `/cookies` | POST | zalogowany | Zapis wklejonej/wgranej treści do `cookies.txt` obok aplikacji; akcja „usuń" kasuje plik; po zapisie status z `inspect_cookies`. |

Zasady:
- Każda trasa poza `/setup` i `/login` ma `login_required`.
- Globalny guard: gdy konto nie istnieje, każde wejście przekierowuje na `/setup`.
- Komunikaty sukces/błąd przez `flash`.
- Operacje (`deps refresh`, `cookies`) jako POST→redirect (PRG), by odświeżenie nie
  powtarzało akcji.
- „Sprawdź aktualizację" = wyłącznie informacja (zgodnie z decyzją: bez podmiany w A).
- Dependency refresh blokuje żądanie do zakończenia pobierania (spinner po stronie
  przeglądarki); pasek postępu na żywo jest w zakresie B.

## Pakowanie, zależności, bezpieczeństwo

- **Zależność**: dochodzi `flask` do `requirements.txt`. Reszta to stdlib (`hashlib`,
  `secrets`, `argparse`).
- **PyInstaller**: szablony i CSS inline → brak dodatkowych plików danych; `--onefile`
  bez zmian w komendzie. Oba joby CI (Windows + Linux) budują binarkę obsługującą oba tryby.
- **Bezpieczeństwo** (świadomie zaakceptowane): HTTP na `0.0.0.0` → do zaufanej sieci
  lokalnej, NIE wystawiać portu na internet bez reverse-proxy z HTTPS (TLS poza
  zakresem). Hasło pbkdf2. Ciasteczko sesji `HttpOnly` + `SameSite=Lax`. Własna ochrona
  CSRF na formularzach POST (token w sesji), bez dodatkowej zależności.

## Testy (pytest)

- **`auth.py`** — `hash_password` deterministyczne dla tej samej soli; `verify_password`
  true/false; `is_configured` przed/po; `create_account` ustawia hash+sól+secret_key i
  zapisuje config.
- **`config.py`** — sekcja `auth` round-trip; stary `config.json` bez `auth` → pusta
  domyślna sekcja (wstecz).
- **`main.py`** — argparse: brak `--serve` → tryb konsolowy; `--serve 8080` → tryb
  serwera; zły port (`0`, `99999`, `abc`) → błąd i kod ≠ 0 (`app.main`/`webserver.run`
  zamockowane).
- **`webserver.py`** (Flask `test_client`):
  - brak konta → wejścia przekierowują na `/setup`; POST `/setup` tworzy konto i loguje;
  - po utworzeniu konta `/setup` → redirect `/login`;
  - `/login` błędne/poprawne hasło;
  - trasy chronione bez sesji → redirect `/login`;
  - `/deps/<name>/refresh` woła bootstrap (zamockowany) i pokazuje wynik;
  - `/cookies` zapisuje plik i pokazuje status; „usuń" kasuje;
  - ochrona CSRF: POST bez/with błędnym tokenem odrzucony.
- **Headless start / realny `app.run`** — weryfikowane ręcznie/integracyjnie, nie jednostkowo.

## Poza zakresem (→ pod-projekt B)

- Dodawanie/usuwanie playlist i ustawienia przez WWW.
- Uruchamianie synchronizacji z paskiem postępu na żywo (SSE/polling).
- Pełna samo-aktualizacja serwera z automatycznym restartem.
- HTTPS/TLS, wielu użytkowników.

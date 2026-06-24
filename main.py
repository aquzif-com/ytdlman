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

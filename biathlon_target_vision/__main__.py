"""Serverstart und kleine Verwaltungsbefehle für die systemd-Installation."""

import argparse
from pathlib import Path

from . import __version__


def main():
    parser = argparse.ArgumentParser(description="Biathlon Target Vision starten")
    parser.add_argument("--version", action="version", version=__version__)
    management = parser.add_mutually_exclusive_group()
    management.add_argument("--status", action="store_true")
    management.add_argument("--upgrade", action="store_true")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--lanes", type=int, help="Bahnanzahl beim ersten Start (Standard: 20)")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--simulation", action="store_true")
    args = parser.parse_args()
    if args.status or args.upgrade:
        if args.upgrade:
            from .deployment import upgrade
            raise SystemExit(upgrade())
        from .status import status
        raise SystemExit(status(args.data_dir, args.host, args.port))
    if args.lanes is not None and args.lanes < 1:
        parser.error("--lanes muss größer als null sein")
    from .config import load_settings
    from .app import create_app
    import uvicorn
    settings = load_settings(args.data_dir)
    port = settings.port if args.port is None else args.port
    if not 1 <= port <= 65535:
        parser.error("--port muss zwischen 1 und 65535 liegen")
    uvicorn.run(create_app(args.data_dir, args.lanes, args.simulation),
                host=args.host or settings.host, port=port)


if __name__ == "__main__":
    main()

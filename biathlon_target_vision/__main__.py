"""Lokaler Serverstart mit genau einem gemeinsamen Prozess."""

import argparse
from pathlib import Path

import uvicorn

from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="Biathlon Target Vision starten")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--lanes", type=int, help="Bahnanzahl beim ersten Start (Standard: 20)")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--simulation", action="store_true", help="Simulator und simulierte Zielbedienung freischalten")
    args = parser.parse_args()
    if args.lanes is not None and args.lanes < 1:
        parser.error("--lanes muss größer als null sein")
    uvicorn.run(create_app(args.data_dir, args.lanes, args.simulation), host=args.host, port=args.port)


if __name__ == "__main__":
    main()

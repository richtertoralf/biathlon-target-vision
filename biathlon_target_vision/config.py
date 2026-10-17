"""Kleine JSON-Betriebskonfiguration außerhalb des Programmverzeichnisses."""

import json
import os
from pathlib import Path
import tempfile

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = "127.0.0.1"
    port: int = Field(default=8091, ge=1, le=65535, strict=True)


def load_settings(directory):
    path = Path(directory) / "config.json"
    return Settings.model_validate_json(path.read_text()) if path.exists() else Settings()


def save_settings(directory, settings):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(settings.model_dump(), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(directory / "config.json")
    finally:
        if temporary and temporary.exists():
            temporary.unlink()

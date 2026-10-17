"""Kleine JSON-Betriebskonfiguration außerhalb des Programmverzeichnisses."""

import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CameraSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(repr=False)
    lane_ids: list[int] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def rtsp_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme not in ("rtsp", "rtsps") or not parsed.hostname or any(c.isspace() for c in value):
            raise ValueError("Vollständige RTSP-Adresse erforderlich")
        return value

    @field_validator("lane_ids", mode="before")
    @classmethod
    def valid_lanes(cls, value):
        if not isinstance(value, list) or any(type(n) is not int or n < 1 for n in value) or len(value) != len(set(value)):
            raise ValueError("Bahnnummern müssen eindeutig und positiv sein")
        return sorted(value)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cameras: list[CameraSettings] = Field(default_factory=list)
    host: str = "127.0.0.1"
    port: int = Field(default=8091, ge=1, le=65535, strict=True)


    @model_validator(mode="after")
    def unique_assignments(self):
        ids = [camera.id for camera in self.cameras]
        lanes = [lane for camera in self.cameras for lane in camera.lane_ids]
        if len(ids) != len(set(ids)) or len(lanes) != len(set(lanes)):
            raise ValueError("Kamera oder Bahn mehrfach zugeordnet")
        return self


def load_settings(directory):
    path = Path(directory) / "config.json"
    try:
        return Settings.model_validate_json(path.read_text()) if path.exists() else Settings()
    except ValueError:
        raise ValueError("Ungültige config.json: Betriebsparameter und Kamerazuordnungen prüfen") from None


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

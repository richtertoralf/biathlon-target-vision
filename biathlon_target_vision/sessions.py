"""Aufzeichnungssitzungen: getrennte Journale und ein atomarer aktiver Verweis."""

from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .core import Conflict, EventStore
from .models import ModeChange


class SessionName(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_session_id: UUID
    name: str = Field(min_length=1, max_length=128)


class SessionStart(SessionName):
    session_id: UUID
    confirm_active: bool = False


def sync_directory(path):
    descriptor = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
    sync_directory(path.parent)


class Sessions:
    def __init__(self, directory: Path, lane_count=None):
        self.directory = directory
        self.store = None
        self.failed = False
        directory.mkdir(parents=True, exist_ok=True)
        # Der Journal-Lock allein schützt nicht über einen Sitzungswechsel hinweg.
        self.lock = (directory / "sessions.lock").open("a+b")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.index = directory / "sessions.json"
            (directory / "sessions").mkdir(exist_ok=True)
            if not self.index.exists():
                if (directory / "events.jsonl").exists() or (directory / "corrections").exists():
                    raise ValueError("Alter Testdatenbestand: events.jsonl und corrections vor dem Start manuell archivieren; siehe README, Aufzeichnungssitzungen.")
                if any((directory / "sessions").iterdir()):
                    raise ValueError("Sitzungsindex fehlt bei vorhandenen Sitzungsordnern; Bestand manuell prüfen.")
                session_id = str(uuid4())
                self.store = EventStore(self.session_path(session_id), lane_count)
                sync_directory(directory / "sessions")
                write_json(self.index, {"schema_version": 1, "active_session_id": session_id, "sessions": [{
                    "session_id": session_id, "name": "Erste Sitzung",
                    "started_at": datetime.now(timezone.utc).isoformat(), "ended_at": None,
                }]})
            self.metadata = json.loads(self.index.read_text(encoding="utf-8"))
            if self.metadata["schema_version"] != 1:
                raise ValueError("Unbekannte Sitzungsversion")
            for session in self.metadata["sessions"]:
                UUID(session["session_id"])
            self.path = self.session_path(self.current["session_id"])
            if not (self.path / "events.jsonl").is_file():
                raise ValueError("Journal der aktiven Sitzung fehlt")
            if self.store is None:
                self.store = EventStore(self.path, lane_count)
        except BaseException:
            self.close()
            raise

    @property
    def current(self):
        return next(item for item in self.metadata["sessions"] if item["session_id"] == self.metadata["active_session_id"])

    def session_path(self, session_id):
        return self.directory / "sessions" / str(UUID(session_id))

    def check_session(self, session_id):
        if self.failed:
            raise OSError("Sitzungsspeicher nach Schreibfehler gesperrt; Neustart erforderlich")
        if session_id != self.current["session_id"]:
            raise Conflict("Sitzung wurde gewechselt. Aktuellen Zustand neu laden.")

    def rename(self, command):
        self.check_session(str(command.expected_session_id))
        metadata = deepcopy(self.metadata)
        metadata["sessions"][-1]["name"] = command.name
        try:
            write_json(self.index, metadata)
        except OSError:
            self.failed = True
            raise
        self.metadata = metadata

    def start(self, command):
        if self.failed or self.store.failed:
            raise OSError("Speicherfehler vor Sitzungsabschluss beheben; Neustart erforderlich")
        new_id = str(command.session_id)
        if new_id == self.current["session_id"] and self.current["name"] == command.name:
            return False  # Wiederholung nach verlorener HTTP-Antwort.
        self.check_session(str(command.expected_session_id))
        if any(item["session_id"] == new_id for item in self.metadata["sessions"]) or self.session_path(new_id).exists():
            raise Conflict("Sitzungskennung wurde bereits verwendet.")
        active = [lane["lane_id"] for lane in self.store.state["lanes"].values()
                  if lane["occupied_bout_id"] or lane["current_bout_id"]]
        if active and not command.confirm_active:
            raise Conflict("Belegte Bahnen oder offene Schießeinlagen: " + ", ".join(map(str, active)) + ". Abschluss ausdrücklich bestätigen.")
        now = datetime.now(timezone.utc).isoformat()
        path = self.session_path(new_id)
        new_store = EventStore(path, len(self.store.state["lanes"]))
        try:
            # Quellensperren sind Administration, keine Sportler-/Scheibendaten.
            for lane in self.store.state["lanes"].values():
                if lane["mode"] != "automatic":
                    new_store.apply(ModeChange(lane_id=lane["lane_id"], mode=lane["mode"], expected_control_revision=0))
            sync_directory(path.parent)
            metadata = deepcopy(self.metadata)
            metadata["sessions"][-1]["ended_at"] = now
            metadata["sessions"].append({"session_id": new_id, "name": command.name, "started_at": now, "ended_at": None})
            metadata["active_session_id"] = new_id
            try:
                write_json(self.index, metadata)
            except OSError:
                # Bei unklarem fsync-Ergebnis entscheidet erst der Neustart anhand
                # des gespeicherten Verweises; nie weiter in den alten Stand schreiben.
                self.failed = True
                raise
        except BaseException:
            new_store.close()
            raise
        self.store.close()
        self.store, self.path, self.metadata = new_store, path, metadata
        return True

    def history(self, session_id, after, limit):
        if session_id == self.current["session_id"]:
            return self.store.history(after, limit), self.store.state["sequence"]
        if not any(item["session_id"] == session_id for item in self.metadata["sessions"]):
            raise KeyError(session_id)
        events, sequence = [], 0
        # Archive werden nur gelesen, niemals als aktiver Ereigniskern geöffnet.
        with (self.session_path(session_id) / "events.jsonl").open(encoding="utf-8") as file:
            next(file)
            for line in file:
                event = json.loads(line)
                sequence = event["sequence"]
                if after < sequence <= after + limit:
                    events.append(event)
        return events, sequence

    def close(self):
        if self.store is not None:
            self.store.close()
        self.lock.close()

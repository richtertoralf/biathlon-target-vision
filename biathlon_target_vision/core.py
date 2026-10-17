"""Ein Ereigniskern: Zuordnungen, Zielzustände und dauerhaftes JSONL-Journal."""

from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import threading

from pydantic import TypeAdapter

from .models import EventCommand, Observation


class Conflict(ValueError):
    """Ein gültiger Befehl widerspricht dem bekannten Zustand."""


class EventStore:
    def __init__(self, directory: Path, lane_count: int | None = None):
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.file = (directory / "events.jsonl").open("a+b")
        self.failed = False
        try:
            # Zwei Prozesse dürften getrennte Speicherzustände nicht fortschreiben.
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.file.seek(0)
            lines = self.file.readlines()
            if lines:
                if not lines[0].endswith(b"\n"):
                    raise ValueError("Unvollständiger Journalkopf.")
                header = json.loads(lines[0])
                if header.get("schema_version") != 1:
                    raise ValueError("Unbekannte Journalversion.")
                stored_count = header["lane_count"]
                if lane_count is not None and lane_count != stored_count:
                    raise ValueError("Bahnanzahl passt nicht zum vorhandenen Journal.")
                lane_count = stored_count
            else:
                lane_count = 20 if lane_count is None else lane_count
            if type(lane_count) is not int or lane_count < 1:
                raise ValueError("Bahnanzahl muss eine positive Ganzzahl sein.")
            self.state = {
                "sequence": 0,
                "lanes": {str(i): {
                    "lane_id": i, "revision": 0, "assignment_revision": 0,
                    "targets": ["unknown"] * 5,
                    "last_known_targets": ["unknown"] * 5,
                    "observed_at": [None] * 5,
                    "last_observed_at": None,
                    "current_bout_id": None, "occupied_bout_id": None,
                } for i in range(1, lane_count + 1)},
                "bouts": {},
            }
            self.events = []
            self.by_id = {}
            if not lines:
                self._append({"schema_version": 1, "lane_count": lane_count})
                descriptor = os.open(directory, os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            adapter = TypeAdapter(EventCommand)
            for number, line in enumerate(lines[1:], start=2):
                try:
                    if not line.endswith(b"\n"):
                        raise ValueError("Unvollständige letzte Zeile")
                    event = json.loads(line)
                    command = adapter.validate_python(event["command"])
                    if event["sequence"] != self.state["sequence"] + 1:
                        raise ValueError("Lücke in der Ereignisfolge")
                    if command.event_id in self.by_id:
                        raise ValueError("Doppelte Ereigniskennung")
                    self._reduce(self.state, command)
                    self.state["sequence"] = event["sequence"]
                    self.events.append(event)
                    self.by_id[command.event_id] = event
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f"Journalfehler in Zeile {number}: {exc}") from exc
        except Exception:
            self.file.close()
            raise

    def close(self):
        self.file.close()

    def snapshot(self):
        with self.lock:
            return deepcopy(self.state)

    def history(self, after=0, limit=1000):
        with self.lock:
            return deepcopy(self.events[after:after + limit])

    def _append(self, value):
        data = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        try:
            self.file.write(data)
            self.file.flush()
            os.fsync(self.file.fileno())
        except OSError:
            # Nach einem unklaren Schreibfehler keine weiteren Befehle annehmen.
            self.failed = True
            raise

    def apply(self, command):
        with self.lock:
            if self.failed:
                raise OSError("Ereignisspeicher nach Schreibfehler gesperrt; Neustart erforderlich.")
            payload = command.model_dump(mode="json")
            previous = self.by_id.get(command.event_id)
            if previous:
                # Alte Journale enthalten neue optionale Befehlsfelder noch nicht.
                previous_payload = TypeAdapter(EventCommand).validate_python(previous["command"]).model_dump(mode="json")
                if previous_payload != payload:
                    raise Conflict("Ereigniskennung wurde bereits mit anderem Inhalt verwendet.")
                return deepcopy(previous)
            # Ein abgewiesener oder nicht gespeicherter Befehl verändert nichts.
            candidate = deepcopy(self.state)
            self._reduce(candidate, command)
            sequence = self.state["sequence"] + 1
            event = {"sequence": sequence,
                     "accepted_at": datetime.now(timezone.utc).isoformat(),
                     "command": payload}
            self._append(event)
            candidate["sequence"] = sequence
            self.state = candidate
            self.events.append(event)
            self.by_id[command.event_id] = event
            return deepcopy(event)

    @staticmethod
    def _new_bout(state, lane, command):
        # Vom auslösenden Ereignis abgeleitet: auch beim Replay dieselbe Kennung.
        bout_id = command.event_id
        bout = {"bout_id": bout_id, "lane_id": command.lane_id,
                "started_sequence": state["sequence"] + 1,
                "bib": None, "closed": False, "close_reason": None,
                "observations": []}
        state["bouts"][bout_id] = bout
        lane["current_bout_id"] = bout_id
        return bout

    @staticmethod
    def _close_bout(state, lane, reason):
        bout_id = lane["current_bout_id"]
        if bout_id:
            state["bouts"][bout_id].update(closed=True, close_reason=reason)
            lane["current_bout_id"] = None

    def _reduce(self, state, command):
        lane = state["lanes"].get(str(command.lane_id))
        if lane is None:
            raise Conflict("Schießbahn existiert nicht.")
        if isinstance(command, Observation):
            self._observe(state, lane, command)
        else:
            expected = command.expected_assignment_revision
            changed = (lane["assignment_revision"] != expected if expected is not None
                       else lane["revision"] != command.expected_revision)
            if changed:
                raise Conflict("Bahn wurde zwischenzeitlich geändert. Zustand neu laden.")
            if command.kind == "assign":
                self._assign(state, lane, command)
            else:
                bout = state["bouts"].get(command.bout_id)
                if not bout or bout["lane_id"] != command.lane_id:
                    raise Conflict("Schießeinlage gehört nicht zu dieser Bahn.")
                if lane["occupied_bout_id"] not in (None, command.bout_id):
                    raise Conflict("Eine andere Schießeinlage belegt diese Bahn.")
                if command.bout_id not in (lane["occupied_bout_id"], lane["current_bout_id"]):
                    raise Conflict("Schießeinlage ist bereits freigegeben.")
                lane["occupied_bout_id"] = None
                if lane["current_bout_id"] == command.bout_id:
                    self._close_bout(state, lane, "release")
            lane["assignment_revision"] += 1
        lane["revision"] += 1

    def _assign(self, state, lane, command):
        bout_id = command.bout_id
        if bout_id is None and command.bout_after_sequence is not None:
            if command.bout_after_sequence > state["sequence"]:
                raise Conflict("Eingabebeginn liegt vor keinem bekannten Serverzustand.")
            # Der erste Treffer kann während der Eingabe oder während des HTTP-
            # Transports eintreffen. Auch nach Rückstellung bleibt dieselbe erste
            # Einlage gemeint, niemals automatisch die inzwischen nächste.
            candidates = [b for b in state["bouts"].values()
                          if b["lane_id"] == command.lane_id and b["started_sequence"] > command.bout_after_sequence]
            if candidates:
                bout_id = min(candidates, key=lambda b: b["started_sequence"])["bout_id"]
        if bout_id is None and any(
            b["lane_id"] == command.lane_id and b["closed"] and b["bib"] is None
            for b in state["bouts"].values()
        ):
            raise Conflict("Frühere Einlage ohne Startnummer vorhanden. Schießeinlage ausdrücklich auswählen.")
        bout_id = bout_id or lane["current_bout_id"]
        bout = state["bouts"].get(bout_id) if bout_id else None
        if command.bout_id and (not bout or bout["lane_id"] != command.lane_id):
            raise Conflict("Schießeinlage gehört nicht zu dieser Bahn.")
        if bout and bout["bib"] not in (None, command.bib) and command.bout_id is None:
            raise Conflict("Korrektur benötigt die ausdrückliche Schießeinlagenkennung.")
        active = bout is None or not bout["closed"] or lane["occupied_bout_id"] == bout_id
        if active:
            if lane["occupied_bout_id"] not in (None, bout_id):
                raise Conflict("Vorherige Belegung zuerst ausdrücklich freigeben.")
            for other in state["lanes"].values():
                occupied = other["occupied_bout_id"]
                if other is not lane and occupied and state["bouts"][occupied]["bib"] == command.bib:
                    raise Conflict("Startnummer belegt bereits eine andere Bahn.")
        if bout is None:
            bout = self._new_bout(state, lane, command)
        bout["bib"] = command.bib
        if active:
            lane["occupied_bout_id"] = bout["bout_id"]

    def _observe(self, state, lane, command):
        if command.kind == "target":
            if command.target_id is None or command.state is None:
                raise Conflict("Zielbeobachtung benötigt target_id und state.")
            indexes = [command.target_id - 1]
            new_state = command.state
        else:
            if command.target_id is not None or command.state is not None:
                raise Conflict("Rückstellung gilt für alle Ziele; keine einzelnen Zielwerte angeben.")
            indexes = list(range(5))
            new_state = "standing"
        timestamp = command.observed_at.isoformat()
        if lane["last_observed_at"] and command.observed_at < datetime.fromisoformat(lane["last_observed_at"]):
            raise Conflict("Beobachtung liegt vor dem zuletzt erfassten Bahnzustand.")
        for index in indexes:
            previous_time = lane["observed_at"][index]
            if previous_time and command.observed_at <= datetime.fromisoformat(previous_time):
                raise Conflict("Veraltete oder zeitlich widersprüchliche Zielbeobachtung.")
        # Jede erkannte Rückkehr eines gefallenen Ziels begrenzt die Einlage.
        # Eine noch bestehende Belegung wird niemals auf die nächste übertragen.
        reset = command.kind == "reset" or any(
            lane["last_known_targets"][i] == "fallen" and new_state == "standing" for i in indexes)
        bout_id = lane["current_bout_id"]
        if not reset and new_state == "fallen" and any(lane["last_known_targets"][i] != "fallen" for i in indexes):
            if not bout_id:
                bout_id = self._new_bout(state, lane, command)["bout_id"]
        if bout_id:
            state["bouts"][bout_id]["observations"].append(command.event_id)
        if reset:
            self._close_bout(state, lane, "reset")
        for index in indexes:
            lane["targets"][index] = new_state
            # Eine Verdeckung löscht keine bereits bekannte mechanische Stellung.
            if new_state != "unknown":
                lane["last_known_targets"][index] = new_state
            lane["observed_at"][index] = timestamp
        lane["last_observed_at"] = timestamp

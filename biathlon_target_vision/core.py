"""Ein Ereigniskern: Zuordnungen, Zielzustände und dauerhaftes JSONL-Journal."""

from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import threading

from pydantic import TypeAdapter

from .models import (EventCommand, Observation, LaneControl, ModeChange, ManualTarget,
                     OverrideRelease, ManualReset, Occupy)


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
                    "mode": "automatic", "control_revision": 0,
                    "automatic_generation": 0,
                    "reset_confirmed": False, "automatic_reset_pending": False,
                    "automatic_targets": ["unknown"] * 5,
                    "automatic_last_known": ["unknown"] * 5,
                    "automatic_baseline_pending": [False] * 5,
                    "manual_targets": [None] * 5,
                    "unassigned_manual_target_ids": [],
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
                    command = adapter.validate_python(self._command_data(event))
                    if event["sequence"] != self.state["sequence"] + 1:
                        raise ValueError("Lücke in der Ereignisfolge")
                    if command.event_id in self.by_id:
                        raise ValueError("Doppelte Ereigniskennung")
                    rules = event.get("rules_version", 1)
                    if rules not in (1, 2, 3):
                        raise ValueError("Unbekannte Ereignisregeln")
                    self._reduce(self.state, command, rules)
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
            result = deepcopy(self.state)
            for lane in result["lanes"].values():
                prepared = lane["reset_confirmed"] and lane["targets"] == ["standing"] * 5
                lane["status"] = "occupied" if lane["occupied_bout_id"] else "ready" if prepared else "reset_required"
            return result

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
                previous_payload = TypeAdapter(EventCommand).validate_python(self._command_data(previous)).model_dump(mode="json")
                if previous_payload != payload:
                    raise Conflict("Ereigniskennung wurde bereits mit anderem Inhalt verwendet.")
                return deepcopy(previous)
            # Ein abgewiesener oder nicht gespeicherter Befehl verändert nichts.
            candidate = deepcopy(self.state)
            self._reduce(candidate, command)
            sequence = self.state["sequence"] + 1
            # Baseline bleibt außerhalb des bisherigen Beobachtungsbefehls.
            # Neue Bedienbefehle benötigen hingegen mindestens Version 0.7.
            baseline = payload.pop("baseline", False)
            event = {"sequence": sequence, "rules_version": 3,
                     "accepted_at": datetime.now(timezone.utc).isoformat(),
                     "command": payload}
            if baseline:
                event["baseline"] = True
            lane = self.state["lanes"][str(command.lane_id)]
            if (isinstance(command, Observation) and command.kind == "target"
                    and (command.baseline or lane["automatic_baseline_pending"][command.target_id - 1])):
                event["effective_baseline"] = True
            event["effective_targets"] = list(candidate["lanes"][str(command.lane_id)]["targets"])
            if isinstance(command, ManualTarget):
                index = command.target_id - 1
                event["manual_input"] = {
                    "mode": lane["mode"], "automatic_state": lane["automatic_targets"][index],
                    "automatic_observed_at": lane["observed_at"][index],
                    "previous_effective_state": lane["targets"][index],
                    "manual_state": command.state,
                }
            self._append(event)
            candidate["sequence"] = sequence
            self.state = candidate
            self.events.append(event)
            self.by_id[command.event_id] = event
            return deepcopy(event)

    @staticmethod
    def _command_data(event):
        payload = dict(event["command"])
        if "baseline" in event:
            payload["baseline"] = event["baseline"]
        return payload

    def _new_bout(self, state, lane, command, rules):
        self._clear_manual(lane, rules)
        lane["unassigned_manual_target_ids"] = []
        # Vom auslösenden Ereignis abgeleitet: auch beim Replay dieselbe Kennung.
        bout_id = command.event_id
        bout = {"bout_id": bout_id, "lane_id": command.lane_id,
                "started_sequence": state["sequence"] + 1,
                "bib": None, "closed": False, "close_reason": None,
                "fallen_target_ids": [],
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

    def _reduce(self, state, command, rules=3):
        legacy = rules == 1
        lane = state["lanes"].get(str(command.lane_id))
        if lane is None:
            raise Conflict("Schießbahn existiert nicht.")
        if isinstance(command, Observation):
            self._observe(state, lane, command, rules)
        elif isinstance(command, LaneControl):
            if command.expected_control_revision != lane["control_revision"]:
                raise Conflict("Bedienzustand wurde geändert. Bahn neu prüfen.")
            self._control(state, lane, command, rules)
            lane["control_revision"] += 1
        else:
            expected = command.expected_assignment_revision
            changed = (lane["assignment_revision"] != expected if expected is not None
                       else lane["revision"] != command.expected_revision)
            if changed:
                raise Conflict("Bahn wurde zwischenzeitlich geändert. Zustand neu laden.")
            if command.kind == "assign":
                self._assign(state, lane, command, rules)
            elif isinstance(command, Occupy):
                if lane["occupied_bout_id"]:
                    raise Conflict("Bahn ist bereits belegt.")
                bout = state["bouts"].get(lane["current_bout_id"])
                if bout is None:
                    bout = self._new_bout(state, lane, command, rules)
                lane["occupied_bout_id"] = bout["bout_id"]
                lane["reset_confirmed"] = False
                lane["automatic_reset_pending"] = False
                lane["control_revision"] += 1
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
                    if legacy:
                        lane["control_revision"] += 1
                if not legacy:
                    lane["control_revision"] += 1
            lane["assignment_revision"] += 1
        lane["revision"] += 1

    def _assign(self, state, lane, command, rules):
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
            # Erste Zuordnung darf bereits erfasste, noch ungebundene Werte
            # übernehmen, aber keine Übersteuerungen des Vorgängers.
            lane["control_revision"] += 1
            bout = self._new_bout(state, lane, command, rules)
        bout["bib"] = command.bib
        if active:
            if lane["occupied_bout_id"] != bout["bout_id"]:
                lane["reset_confirmed"] = False
                lane["automatic_reset_pending"] = False
            lane["occupied_bout_id"] = bout["bout_id"]

    def _observe(self, state, lane, command, rules):
        legacy = rules == 1
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
        if command.baseline and command.kind != "target":
            raise Conflict("Eine Grundbeobachtung beschreibt genau ein Ziel")
        timestamp = command.observed_at.isoformat()
        if lane["last_observed_at"] and command.observed_at < datetime.fromisoformat(lane["last_observed_at"]):
            raise Conflict("Beobachtung liegt vor dem zuletzt erfassten Bahnzustand.")
        for index in indexes:
            previous_time = lane["observed_at"][index]
            if previous_time and command.observed_at <= datetime.fromisoformat(previous_time):
                raise Conflict("Veraltete oder zeitlich widersprüchliche Zielbeobachtung.")
        baseline = command.baseline or (command.kind == "target" and any(lane["automatic_baseline_pending"][i] for i in indexes))
        reset = not baseline and (command.kind == "reset" or any(
            lane["automatic_last_known"][i] == "fallen" and new_state == "standing" for i in indexes))
        previous = list(lane["automatic_last_known"])
        if baseline:
            # Eine unterbrochene Beobachtungskette bestätigt keine Rückstellung.
            lane["automatic_reset_pending"] = False
        for index in indexes:
            lane["automatic_targets"][index] = new_state
            if new_state != "unknown":
                lane["automatic_last_known"][index] = new_state
                lane["automatic_baseline_pending"][index] = False
            lane["observed_at"][index] = timestamp
        lane["last_observed_at"] = timestamp
        # Im manuellen Betrieb bleibt die Kamera lediglich eine Vergleichsquelle.
        if lane["mode"] == "manual":
            return
        if legacy and new_state != "standing":
            lane["reset_confirmed"] = False
        if reset:
            lane["automatic_reset_pending"] = True
            if legacy:
                self._close_bout(state, lane, "reset")
                lane["control_revision"] += 1
        if not legacy and new_state != "standing":
            lane["automatic_reset_pending"] = False
        # Erst ein beobachteter Übergang UND fünf verlässlich aufgerichtete
        # Scheiben bestätigen Rückstellung. Ein einzelner Rücksprung reicht nicht.
        if lane["automatic_reset_pending"] and lane["automatic_targets"] == ["standing"] * 5:
            lane["reset_confirmed"] = True
            lane["automatic_reset_pending"] = False
            if legacy:
                self._clear_manual(lane, rules)
            else:
                self._close_bout(state, lane, "reset")
                lane["manual_targets"] = [None] * 5
                indexes = list(range(5))
            lane["unassigned_manual_target_ids"] = []
            lane["control_revision"] += 1
        self._effective(lane, indexes, legacy)
        bout_id = lane["current_bout_id"]
        changed_fall = not baseline and not reset and new_state == "fallen" and any(
            previous[i] != "fallen" and lane["manual_targets"][i] is None for i in indexes)
        if changed_fall and not bout_id:
            bout_id = self._new_bout(state, lane, command, rules)["bout_id"]
            lane["control_revision"] += 1
        if bout_id:
            bout = state["bouts"][bout_id]
            bout["observations"].append(command.event_id)
            if changed_fall:
                for index in indexes:
                    if (previous[index] != "fallen" and lane["manual_targets"][index] is None
                            and index + 1 not in bout["fallen_target_ids"]):
                        bout["fallen_target_ids"].append(index + 1)

    @staticmethod
    def _effective(lane, indexes=range(5), legacy=False):
        if legacy:
            indexes = range(5)
        for index in indexes:
            manual, automatic = lane["manual_targets"][index], lane["automatic_targets"][index]
            # Nach menschlicher Vorbereitung gilt die bestätigte Stellung auch
            # ohne Kamera. Erst eine bekannte Grundbeobachtung übernimmt wieder.
            if manual is not None:
                lane["targets"][index] = manual
            elif legacy or not (lane["automatic_baseline_pending"][index] and automatic == "unknown"):
                lane["targets"][index] = automatic
            value = lane["targets"][index]
            if value != "unknown":
                lane["last_known_targets"][index] = value
            if value == "fallen" or (not legacy and value == "unknown"):
                lane["reset_confirmed"] = False

    def _clear_manual(self, lane, rules):
        if rules == 1:
            # Historische Befehle müssen auch ihre damaligen Revisionen erzeugen.
            if lane["mode"] != "manual":
                lane["manual_targets"] = [None] * 5
                self._effective(lane, legacy=True)
            return
        indexes = [i for i, value in enumerate(lane["manual_targets"])
                   if value is not None and (rules < 3 or i + 1 not in lane["unassigned_manual_target_ids"])]
        if indexes:
            # Eine bestätigte Vorbereitung bleibt gültig, auch aus alten Journalen.
            # Sonst keine Stellungen des Vorgängers oder alte Kamerawerte einsetzen.
            prepared = lane["reset_confirmed"] and lane["targets"] == ["standing"] * 5
            for index in indexes:
                lane["targets"][index] = "standing" if prepared else "unknown"
                lane["manual_targets"][index] = None
            lane["automatic_baseline_pending"] = [True] * 5
            lane["automatic_generation"] += 1

    def _control(self, state, lane, command, rules):
        legacy = rules == 1
        if isinstance(command, ModeChange):
            if command.mode == lane["mode"]:
                return
            if legacy and command.mode == "manual":
                lane["manual_targets"] = list(lane["targets"])
            if lane["mode"] == "manual":
                # Auch REST-Adapter müssen nach Rückwechsel eine neue Grundlage
                # liefern; unbekannte Bilder verbrauchen diese Markierung nicht.
                lane["automatic_baseline_pending"] = [True] * 5
                lane["automatic_generation"] += 1
                lane["automatic_reset_pending"] = False
            lane["mode"] = command.mode
            if not legacy:
                return
        elif isinstance(command, ManualReset):
            lane["unassigned_manual_target_ids"] = []
            self._close_bout(state, lane, "reset")
            lane["reset_confirmed"] = True
            lane["automatic_reset_pending"] = False
            lane["automatic_targets"] = ["unknown"] * 5
            lane["automatic_last_known"] = ["unknown"] * 5
            lane["automatic_baseline_pending"] = [True] * 5
            lane["automatic_generation"] += 1
            lane["manual_targets"] = ["standing"] * 5 if legacy and lane["mode"] == "manual" else [None] * 5
            # Physisch bestätigte Rückstellung gilt unmittelbar. Die erste neue
            # Kameragrundbeobachtung darf anschließend keinen Fall erfinden.
            lane["targets"] = ["standing"] * 5
            lane["last_known_targets"] = ["standing"] * 5
            return
        elif isinstance(command, OverrideRelease):
            if lane["mode"] == "manual":
                raise Conflict("Im manuellen Betrieb gibt es keine automatische Zielsteuerung.")
            index = command.target_id - 1
            lane["manual_targets"][index] = None
            if command.target_id in lane["unassigned_manual_target_ids"]:
                lane["unassigned_manual_target_ids"].remove(command.target_id)
            if not legacy:
                lane["targets"][index] = lane["automatic_targets"][index]
        elif isinstance(command, ManualTarget):
            if command.start_bout and command.state == "fallen" and not lane["current_bout_id"]:
                self._new_bout(state, lane, command, rules)
            lane["manual_targets"][command.target_id - 1] = command.state
            # Ohne aktive Einlage oder Belegung ist dies eine neue Entscheidung,
            # keine Korrektur des Vorgängers. Erst der Einlagenbeginn bindet sie.
            if not lane["current_bout_id"] and not lane["occupied_bout_id"]:
                if command.target_id not in lane["unassigned_manual_target_ids"]:
                    lane["unassigned_manual_target_ids"].append(command.target_id)
            if command.state != "standing":
                lane["reset_confirmed"] = False
            # Eine menschliche Zustandseingabe ist kein beobachteter Schuss und
            # verändert die Liste automatisch beobachteter Fälle nicht.
        indexes = [command.target_id - 1] if isinstance(command, (ManualTarget, OverrideRelease)) else range(5)
        self._effective(lane, indexes, legacy)

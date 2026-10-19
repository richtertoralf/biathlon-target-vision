"""Optional test diagnostics per recording session: system, camera and processing samples.

Stored in `sessions/<id>/diagnostics/` next to the journal, never inside it:
`state.json` (runs with start/stop and a system snapshot), `samples.jsonl` (one
line about every five seconds), `notes.json` (optional manual details) and
generated reports. Errors stop only the diagnostics; the event core, journal and
tablet operation never depend on them.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import time
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .build import commit as build_commit
from .sessions import write_json
from .status import lan_addresses

INTERVAL = 5.0
NOTE_FIELDS = ("camera_distances", "weather", "light", "observations", "recordings_dir")
MEDIAMTX_CONFIGS = (Path("/usr/local/etc/mediamtx.yml"), Path("/etc/mediamtx/mediamtx.yml"), Path("/etc/mediamtx.yml"))


class Notes(BaseModel):
    """Optional manual details; everything else is recorded automatically."""
    model_config = ConfigDict(extra="forbid")
    camera_distances: str = Field(default="", max_length=4000)
    weather: str = Field(default="", max_length=4000)
    light: str = Field(default="", max_length=4000)
    observations: str = Field(default="", max_length=4000)
    recordings_dir: str = Field(default="", max_length=1000)


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def proc_value(path, key):
    """A value in kB from /proc/meminfo or /proc/self/status, in bytes; None if unavailable."""
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith(key + ":"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def cpu_ticks():
    """Total and idle jiffies of all CPUs from /proc/stat; None if unavailable."""
    try:
        values = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        return sum(values), values[3] + (values[4] if len(values) > 4 else 0)
    except (OSError, ValueError, IndexError):
        return None


def system_info(data_dir):
    """One-time snapshot without secrets: program, host, addresses and time."""
    release = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            key, _, value = line.partition("=")
            release[key] = value.strip('"')
    except OSError:
        pass
    model = None
    try:
        model = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                      if line.startswith("model name")), None)
    except OSError:
        pass
    try:
        timezone_name = os.path.realpath("/etc/localtime").split("zoneinfo/", 1)[1]
    except IndexError:
        timezone_name = None
    disk = shutil.disk_usage(data_dir)
    return {"btv_version": __version__, "commit": build_commit(), "os": release.get("PRETTY_NAME") or platform.platform(),
            "kernel": platform.release(), "python": sys.version.split()[0], "cpu_model": model, "cpu_count": os.cpu_count(),
            "memory_total_bytes": proc_value("/proc/meminfo", "MemTotal"), "addresses": [address for address, _ in lan_addresses()],
            "server_time": now(), "timezone": timezone_name or time.tzname[0], "disk_total_bytes": disk.total}


class Diagnostics:
    """Start/stop, sampling and files of the optional session diagnostics."""

    def __init__(self, sessions, data_dir, live):
        # live() returns cameras, lanes, health and processing times of the running app.
        self.sessions, self.data_dir, self.live = sessions, Path(data_dir), live
        self.task = None
        self.session_id = None
        self.error = None
        self.previous = None
        self.counts = {}

    def directory(self, session_id):
        if not any(item["session_id"] == session_id for item in self.sessions.metadata["sessions"]):
            raise KeyError(session_id)
        return self.sessions.session_path(session_id) / "diagnostics"

    def state(self, session_id):
        return read_json(self.directory(session_id) / "state.json", {"runs": []})

    def notes(self, session_id):
        stored = read_json(self.directory(session_id) / "notes.json", {})
        return {field: stored.get(field, "") for field in NOTE_FIELDS} | {"updated_at": stored.get("updated_at")}

    def save_notes(self, session_id, values):
        directory = self.directory(session_id)
        directory.mkdir(exist_ok=True)
        notes = {field: str(values.get(field, ""))[:4000] for field in NOTE_FIELDS} | {"updated_at": now()}
        write_json(directory / "notes.json", notes)
        return notes

    def samples(self, session_id):
        """Stored samples; a line cut off by a crash or power loss is skipped."""
        path = self.directory(session_id) / "samples.jsonl"
        try:
            with path.open(encoding="utf-8") as file:
                for line in file:
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
        except OSError:
            return

    def count(self, session_id):
        """Number of samples; only bytes added since the last call are read."""
        path = self.directory(session_id) / "samples.jsonl"
        try:
            size = path.stat().st_size
        except OSError:
            return 0
        known_size, known_count = self.counts.get(path, (0, 0))
        if size < known_size:
            known_size, known_count = 0, 0
        try:
            with path.open("rb") as file:
                file.seek(known_size)
                known_count += file.read(size - known_size).count(b"\n")
        except OSError:
            return known_count
        self.counts[path] = (size, known_count)
        return known_count

    def reports(self, session_id):
        directory = self.directory(session_id)
        return sorted(path.name for path in directory.glob("testprotokoll-*.md")) if directory.is_dir() else []

    def status(self, session_id):
        state = self.state(session_id)
        runs = state["runs"]
        active = bool(runs) and runs[-1].get("stopped_at") is None
        running = active and self.task is not None and not self.task.done() and self.session_id == session_id
        return {"session_id": session_id, "active": active, "running": running, "runs": [
                    {key: run.get(key) for key in ("started_at", "stopped_at", "stop_reason", "resumed")} for run in runs],
                "samples": self.count(session_id), "reports": self.reports(session_id),
                "error": self.error if self.session_id in (None, session_id) else None, "notes": self.notes(session_id),
                "server_time": now()}

    def write_state(self, session_id, state):
        directory = self.directory(session_id)
        directory.mkdir(exist_ok=True)
        write_json(directory / "state.json", state)

    def start(self, session_id):
        if session_id != self.sessions.current["session_id"]:
            raise ValueError("Testdiagnose ist nur für die aktive Sitzung möglich.")
        state = self.state(session_id)
        if state["runs"] and state["runs"][-1].get("stopped_at") is None and self.task and not self.task.done():
            return self.status(session_id)
        state["runs"].append({"started_at": now(), "stopped_at": None, "stop_reason": None, "resumed": [],
                              "system": system_info(self.data_dir)})
        self.write_state(session_id, state)
        self.launch(session_id)
        return self.status(session_id)

    def stop(self, session_id, reason="beendet"):
        if self.session_id == session_id and self.task:
            self.task.cancel()
            self.task = None
        state = self.state(session_id)
        if state["runs"] and state["runs"][-1].get("stopped_at") is None:
            state["runs"][-1].update(stopped_at=now(), stop_reason=reason)
            self.write_state(session_id, state)
        return self.status(session_id)

    def resume(self):
        """After a restart, continue a diagnosis that the active session had running."""
        session_id = self.sessions.current["session_id"]
        state = self.state(session_id)
        if state["runs"] and state["runs"][-1].get("stopped_at") is None:
            state["runs"][-1].setdefault("resumed", []).append(now())
            self.write_state(session_id, state)
            self.launch(session_id)

    def launch(self, session_id):
        self.session_id, self.error, self.previous = session_id, None, None
        self.task = asyncio.get_running_loop().create_task(self.run(session_id))

    def sample(self):
        """One sample: process/system load and the live state of cameras, lanes and processing."""
        wall, cpu, ticks = time.monotonic(), sum(os.times()[:2]), cpu_ticks()
        process_cpu = system_cpu = None
        if self.previous:
            elapsed = wall - self.previous[0]
            process_cpu = round((cpu - self.previous[1]) / elapsed * 100, 1) if elapsed > 0 else None
            if ticks and self.previous[2] and ticks[0] > self.previous[2][0]:
                total, idle = ticks[0] - self.previous[2][0], ticks[1] - self.previous[2][1]
                system_cpu = round((total - idle) / total * 100, 1)
        self.previous = (wall, cpu, ticks)
        disk = shutil.disk_usage(self.data_dir)
        return {"t": now(), "process": {"cpu_percent": process_cpu, "rss_bytes": proc_value("/proc/self/status", "VmRSS"),
                                        "threads": len(os.listdir("/proc/self/task")) if os.path.isdir("/proc/self/task") else None},
                "system": {"cpu_percent": system_cpu, "memory_total_bytes": proc_value("/proc/meminfo", "MemTotal"),
                           "memory_available_bytes": proc_value("/proc/meminfo", "MemAvailable"),
                           "disk_free_bytes": disk.free, "load1": os.getloadavg()[0]}, **self.live()}

    async def run(self, session_id):
        path = self.directory(session_id) / "samples.jsonl"
        try:
            while True:
                # A session change stops sampling; data never moves to another session.
                if self.sessions.current["session_id"] != session_id:
                    self.stop(session_id, "Sitzung gewechselt")
                    return
                line = json.dumps(self.sample(), ensure_ascii=False, separators=(",", ":")) + "\n"
                with path.open("a", encoding="utf-8") as file:
                    file.write(line)
                    file.flush()
                    os.fsync(file.fileno())
                await asyncio.sleep(INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Diagnostics must never affect operation: record the error and stop sampling.
            logging.exception("Testdiagnose angehalten")
            self.error = f"Testdiagnose angehalten: {error}"
            try:
                self.stop(session_id, f"Fehler: {error}")
            except OSError:
                pass

    def close(self):
        if self.task:
            self.task.cancel()


def mediamtx_roots(notes_dir=""):
    """Recording directories: the one given in the notes, else absolute recordPath roots of MediaMTX."""
    roots, hints = [], []
    if notes_dir.strip():
        roots.append(Path(notes_dir.strip()))
    for config in MEDIAMTX_CONFIGS:
        try:
            text = config.read_text(encoding="utf-8")
        except OSError:
            continue
        for value in re.findall(r"^\s*recordPath:\s*(\S+)", text, re.MULTILINE):
            root = value.split("%", 1)[0].rstrip("/")
            if root.startswith("/"):
                roots.append(Path(root))
            else:
                hints.append(f"{config}: relativer recordPath „{value}“ – Arbeitsverzeichnis von MediaMTX unbekannt")
    unique = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique, hints


def recordings(roots, cameras, since=None, limit=500):
    """Read-only list of recording files per camera; MediaMTX paths are matched by URL path."""
    result, problems = {}, []
    for camera in cameras:
        # Only the path of the camera URL is used; credentials are never read.
        path = urlsplit(camera.url).path.strip("/")
        files = []
        for root in roots:
            folder = root / path if path else None
            if folder is None or not folder.is_dir():
                continue
            try:
                for item in sorted(folder.rglob("*"))[:limit]:
                    if not item.is_file():
                        continue
                    stat = item.stat()
                    modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                    if since and modified < since:
                        continue
                    files.append({"file": str(item), "bytes": stat.st_size, "modified": modified.isoformat()})
            except OSError as error:
                problems.append(f"{folder}: nicht lesbar ({error.strerror})")
        result[camera.id] = {"mediamtx_path": path or None, "files": files}
    for root in roots:
        if not root.is_dir():
            problems.append(f"{root}: Verzeichnis nicht vorhanden oder nicht lesbar")
    return result, problems

"""Operating status for administrators: `biathlon-target-vision --status`.

Collects only values that are actually available: first from the running API,
otherwise from the data directory if it is readable (usually with sudo).
Exit codes (ADR-002): 0 = no technical fault, also for a deliberately stopped
service or a disconnected camera; 1 = technical fault (service failed, API
unreachable while the service runs, API reports a fault); 2 = config.json is
readable but invalid. Missing read permission is a hint, not an error.
Never prints RTSP addresses or secrets.
"""

import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from . import __version__
from .build import commit, describe
from .config import load_settings
from .deployment import SERVICE

DEFAULT_PORT = 8091
UNKNOWN = "unbekannt"


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def config_invalid(directory):
    """True if config.json is readable but invalid; missing or unreadable files are no config error."""
    try:
        load_settings(directory)
    except OSError:
        return False
    except ValueError:
        return True
    return False


def server_address(directory, host=None, port=None, invalid=False):
    """Configured bind address; None if unknown. Arguments override the protected config file."""
    config = read_json(Path(directory) / "config.json")
    if host or port:
        return host or (config or {}).get("host"), port or (config or {}).get("port", DEFAULT_PORT), "aus Aufrufparametern"
    if invalid and config is None:
        return None, DEFAULT_PORT, f"Adresse {UNKNOWN}, Standardport angenommen – {Path(directory) / 'config.json'} ungültig"
    if config is None:
        # Never assume a bind address: the installer writes 0.0.0.0, a local start uses 127.0.0.1.
        return None, DEFAULT_PORT, f"Adresse {UNKNOWN}, Standardport angenommen – Konfiguration nicht lesbar, mit sudo aufrufen"
    return config.get("host", "127.0.0.1"), config.get("port", DEFAULT_PORT), f"aus {Path(directory) / 'config.json'}"


def service_state():
    """systemd ActiveState, "not-found" if the unit is not installed, None without systemd."""
    try:
        output = subprocess.run(["systemctl", "show", "-p", "LoadState", "-p", "ActiveState", SERVICE],
                                capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    if values.get("LoadState") == "not-found":
        return "not-found"  # e.g. a local development start without installation
    return values.get("ActiveState") or None


def lan_addresses():
    """Global IPv4 addresses of this host; the one of the default route first."""
    addresses = []
    try:
        output = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"],
                                capture_output=True, text=True, timeout=5).stdout
        for line in output.splitlines():
            fields = line.split()
            addresses.append((fields[3].split("/")[0], fields[1]))
    except (OSError, subprocess.TimeoutExpired, IndexError):
        pass
    try:
        # Connecting a UDP socket sends nothing; it only selects the outgoing interface.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            primary = probe.getsockname()[0]
    except OSError:
        primary = None
    if primary and not ipaddress.ip_address(primary).is_loopback and primary not in [a for a, _ in addresses]:
        addresses.insert(0, (primary, None))
    addresses.sort(key=lambda item: item[0] != primary)
    return addresses


def is_loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def url_host(host):
    return f"[{host}]" if ":" in host else host


def fetch(base, path, timeout=2):
    """JSON of an API path; HTTP errors still return their JSON body (e.g. health 503)."""
    try:
        with urlopen(base + path, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            return json.load(error)
        except ValueError:
            return None
    except (OSError, URLError, ValueError):
        return None


def reachable_path(base, path):
    try:
        with urlopen(base + path, timeout=2) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def from_api(base):
    """Everything the running server reports; None if the API is not reachable."""
    health = fetch(base, "/api/health")
    if not health:
        return None
    state = fetch(base, "/api/state") or {}
    cameras = (fetch(base, "/api/cameras") or {}).get("cameras")
    sessions = (fetch(base, "/api/sessions") or {}).get("sessions")
    calibration = {}
    for camera in cameras or []:
        for lane in camera["lane_ids"]:
            result = fetch(base, f"/api/lanes/{lane}/calibration")
            calibration[lane] = None if result is None else \
                "missing" if not result.get("calibration") else "valid" if result.get("valid_for_camera") else "invalid"
    return {"source": "API", "health": health.get("status", UNKNOWN), "version": health.get("version"),
            "commit": health.get("commit"),
            "lanes": len(state["lanes"]) if "lanes" in state else None,
            "cameras": [{"id": c["id"], "name": c["name"], "lane_ids": c["lane_ids"], "connected": c["connected"]}
                        for c in cameras] if cameras is not None else None,
            "calibration": calibration if cameras is not None else None,
            "session": state.get("session"), "archived": None if sessions is None else
            sum(1 for item in sessions if item.get("ended_at")),
            "docs": reachable_path(base, "/docs")}


def from_files(directory):
    """Fallback without a running API; only what the readable data directory states."""
    directory = Path(directory)
    config, index = read_json(directory / "config.json"), read_json(directory / "sessions.json")
    if config is None and index is None:
        return None
    session, lanes = None, None
    if index:
        session = next((item for item in index.get("sessions", []) if item["session_id"] == index.get("active_session_id")), None)
        try:
            with (directory / "sessions" / index["active_session_id"] / "events.jsonl").open(encoding="utf-8") as journal:
                lanes = json.loads(journal.readline()).get("lane_count")
        except (OSError, ValueError, KeyError):
            pass
    calibrations = directory / "calibrations"
    return {"source": "Datenverzeichnis", "health": None, "version": None, "commit": None, "lanes": lanes,
            "cameras": [{"id": c["id"], "name": c["name"], "lane_ids": c["lane_ids"], "connected": None}
                        for c in config.get("cameras", [])] if config is not None else None,
            "calibration": {int(path.stem.split("-")[1]): "file" for path in calibrations.glob("lane-*.json")}
            if calibrations.is_dir() else None,
            "session": session, "archived": None if index is None else
            sum(1 for item in index.get("sessions", []) if item.get("ended_at")), "docs": False}


def address_lines(host, port, info, addresses, row):
    """URLs that match the real binding: LAN addresses for 0.0.0.0, otherwise the bind address."""
    note = " im Netzwerk"
    if host in ("0.0.0.0", "::"):
        hosts = [address for address, _ in addresses]
    elif host:
        hosts = [host]
        if is_loopback(host):
            note = " (nur auf diesem Rechner erreichbar)"
    else:
        # Unknown binding: list only LAN addresses that actually answer.
        hosts = [address for address, _ in addresses if fetch(f"http://{url_host(address)}:{port}", "/api/health", timeout=1)]
        note = " im Netzwerk (Erreichbarkeit geprüft)"
    if not hosts:
        reason = "Bind-Adresse unbekannt und keine LAN-Adresse antwortet" if host is None else "keine LAN-Adresse ermittelbar"
        return [f"Adressen: {UNKNOWN} ({reason})"]
    base = f"http://{url_host(hosts[0])}:{port}"
    pages = [("Tablet", "/"), ("Kontrollmonitor", "/monitor"), ("Administration", "/admin"),
             ("Kalibrierung", "/calibration"), ("API (Zustand)", "/api/state"), ("API (WebSocket)", "/ws")]
    if info and info.get("docs"):
        pages.append(("API-Dokumentation", "/docs"))
    if not (info and info["source"] == "API"):
        note += " – laut Konfiguration, API derzeit nicht erreichbar"
    lines = ["Adressen" + note]
    lines += [row(label, (base.replace("http://", "ws://", 1) if path == "/ws" else base) + path) for label, path in pages]
    interfaces = dict(addresses)
    others = [f"{address} ({interfaces[address]})" if interfaces.get(address) else address for address in hosts[1:]]
    if others:
        lines.append(row("Weitere Adressen", ", ".join(others)))
    return lines


def exit_code(service, info, invalid=False):
    if invalid:
        return 2
    if service == "failed":
        return 1
    if info is not None and info["source"] == "API":
        return 0 if info["health"] == "ok" else 1
    # Without an answering API only a deliberately stopped service is in order.
    return 0 if service == "inactive" else 1


def report(directory, host, port, source, service, info, addresses, invalid=False):
    """Human-readable lines; missing values are marked as unknown."""
    row = lambda label, value: f"  {label:<22} {value}"
    lines = ["Biathlon Target Vision – Betriebsstatus", ""]
    running = info.get("version") if info else None
    running_commit = info.get("commit") if info else None
    installed_commit = commit()
    outdated = running and (running != __version__ or
                            (running_commit and installed_commit and running_commit != installed_commit))
    lines.append(row("Version", f"installiert {__version__} · laufend {running or UNKNOWN}"
                     + (f" ({running_commit})" if running_commit else "")
                     + (" – Dienst neu starten?" if outdated else "")))
    lines.append(row("Build", describe()))
    states = {"active": "aktiv", "inactive": "gestoppt", "failed": "fehlgeschlagen", "activating": "startet",
              "not-found": "nicht installiert"}
    lines.append(row("Dienst", f"{states.get(service, service)} ({SERVICE})" if service else f"{UNKNOWN} (systemd nicht verfügbar)"))
    api = "nicht erreichbar" if info is None or info["source"] != "API" else \
        "erreichbar, Zustand ok" if info["health"] == "ok" else f"erreichbar, Störung gemeldet ({info['health']})"
    lines.append(row("API", api))
    lines.append(row("Server", f"{host or UNKNOWN}:{port} ({source})"))
    readable = Path(directory).is_dir() and os.access(directory, os.R_OK | os.X_OK)
    lines.append(row("Datenverzeichnis", f"{Path(directory).resolve()}" + ("" if readable else " (nicht lesbar)")))
    if invalid:
        lines.append(row("Konfiguration", f"ungültig: {Path(directory) / 'config.json'} – Betriebsparameter und "
                                          "Kamerazuordnungen prüfen"))
    lines.append("")
    lines += address_lines(host, port, info, addresses, row)
    lines.append("")

    lines.append("Schießstand" + (f" (aus {info['source']})" if info else ""))
    if info is None:
        lines.append("  Keine Angaben: API nicht erreichbar und " + ("Konfiguration ungültig." if invalid else
                                                                 "Datenverzeichnis nicht lesbar (mit sudo aufrufen)."))
        return lines
    lines.append(row("Schießbahnen", info["lanes"] if info["lanes"] is not None else UNKNOWN))
    cameras = info["cameras"]
    if cameras is None:
        lines.append(row("Kameras", UNKNOWN))
    else:
        connected = sum(1 for camera in cameras if camera["connected"])
        lines.append(row("Kameras", f"{len(cameras)} konfiguriert" +
                         (f", {connected} verbunden" if info["source"] == "API" else ", Verbindung unbekannt")))
        for camera in cameras:
            state = {True: "verbunden", False: "getrennt", None: UNKNOWN}[camera["connected"]]
            lanes = ", ".join(map(str, camera["lane_ids"])) or "keine"
            lines.append(f"    {camera['name']} ({camera['id']}) · Bahnen {lanes} · {state}")
    calibration = info["calibration"]
    if calibration is None:
        lines.append(row("Kalibrierung", UNKNOWN))
    elif info["source"] == "API":
        values = list(calibration.values())
        text = f"{values.count('valid')} von {len(values)} Bahnen mit Kamera kalibriert"
        if values.count("invalid"):
            text += f", {values.count('invalid')} ungültig (Kamera geändert)"
        if values.count(None):
            text += f", {values.count(None)} {UNKNOWN}"
        lines.append(row("Kalibrierung", text))
    else:
        lines.append(row("Kalibrierung", f"{len(calibration)} Kalibrierungsdateien (Gültigkeit {UNKNOWN})"))
    session = info["session"]
    lines.append(row("Aktive Sitzung", f"{session['name']} (ID {session['session_id']})" if session else UNKNOWN))
    lines.append(row("Archivierte Sitzungen", info["archived"] if info["archived"] is not None else UNKNOWN))
    return lines


def status(directory, host=None, port=None):
    invalid = config_invalid(directory)
    host, port, source = server_address(directory, host, port, invalid)
    probe = "127.0.0.1" if host in (None, "0.0.0.0", "::") else host
    info = from_api(f"http://{url_host(probe)}:{port}") or from_files(directory)
    service = service_state()
    code = exit_code(service, info, invalid)
    lines = report(directory, host, port, source, service, info, lan_addresses(), invalid)
    lines += ["", {0: "Ergebnis: kein technischer Fehler (Exitcode 0)",
                   1: "Ergebnis: technischer Fehler – Dienst fehlgeschlagen, API nicht erreichbar oder Störung gemeldet (Exitcode 1)",
                   2: "Ergebnis: Konfiguration ungültig (Exitcode 2)"}[code]]
    print("\n".join(lines))
    return code

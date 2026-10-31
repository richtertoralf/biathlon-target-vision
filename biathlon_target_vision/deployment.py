"""Installation mit Git, venv und systemd; vorbereiten, umschalten, Start prüfen.

The service keeps its systemd state: an upgrade only restarts a service that was
running before and never changes autostart; `enable` happens on first install only.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path("/opt/biathlon-target-vision")
DATA = Path("/var/lib/biathlon-target-vision")
SERVICE = "biathlon-target-vision.service"
REPOSITORY = "https://github.com/richtertoralf/biathlon-target-vision.git"
UNIT = Path("/etc/systemd/system") / SERVICE
LAUNCHER = Path("/usr/local/bin/biathlon-target-vision")
VERSION_PATTERN = re.compile(r'__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"')


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def reachable(directory, expected_version=None, host=None, port=None):
    try:
        try:
            config = json.loads((Path(directory) / "config.json").read_text())
        except (PermissionError, FileNotFoundError):
            # Status darf ohne Leserecht auf spätere Kamera-Zugangsdaten arbeiten.
            config = {}
        host = host or config.get("host", "127.0.0.1")
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        if ":" in host:
            host = f"[{host}]"
        with urlopen(f"http://{host}:{port or config.get('port', 8091)}/api/health", timeout=1) as response:
            health = json.load(response)
        return health.get("status") == "ok" and (expected_version is None or health.get("version") == expected_version)
    except (OSError, URLError, ValueError):
        return False


def service_state():
    """(ActiveState, UnitFileState) of the service, e.g. ("active", "enabled"); read only."""
    states = []
    for query in ("is-active", "is-enabled"):
        try:
            states.append(subprocess.run(["systemctl", query, SERVICE], capture_output=True, text=True).stdout.strip() or "unknown")
        except OSError:
            states.append("unknown")
    return tuple(states)


def release_version(release):
    """Version of an installed release directory; None if it cannot be read."""
    try:
        match = VERSION_PATTERN.search((Path(release) / "biathlon_target_vision" / "__init__.py").read_text())
    except OSError:
        return None
    return match[1] if match else None


def wait_reachable(directory, version):
    for _ in range(30):
        if reachable(directory, version):
            return True
        time.sleep(.5)
    return False


def switch_link(link, target):
    temporary = link.with_name(link.name + ".new")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(link)


def activate(root, directory, release, version, start=None):
    """Switch to the prepared release; on failure switch back. Data is never replaced.

    start=None keeps the previous service state: only a running service is stopped,
    restarted and checked. The installer passes start=True for a first installation.
    """
    link = root / "current"
    previous = link.resolve() if link.exists() else None
    active, enabled = service_state()
    # "activating" includes systemd's automatic restart after a crash: the service is meant to run.
    was_running = active in ("active", "activating", "reloading")
    running = was_running if start is None else start
    print(f"Dienst vorher: {active}, Autostart {enabled} (wird nicht verändert)")
    if was_running:
        run("systemctl", "stop", SERVICE)
    backup = root / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        shutil.copytree(directory, backup)
        switch_link(link, release)
        if not running:
            print(f"Version {version} installiert; Dienst bleibt gestoppt "
                  f"(Start: sudo systemctl start {SERVICE}). Datensicherung: {backup}")
            return
        run("systemctl", "reset-failed", SERVICE)
        run("systemctl", "start", SERVICE)
        if not wait_reachable(directory, version):
            raise RuntimeError("Neue Version ist nicht erreichbar")
        print(f"Version {version} gestartet; Datensicherung: {backup}")
    except Exception:
        rollback(link, directory, previous, running)
        raise


def rollback(link, directory, previous, running):
    """Restore the previous release and its service state; report a failed restore explicitly."""
    try:
        if running:
            run("systemctl", "stop", SERVICE)
        if previous is None:
            return
        switch_link(link, previous)
        old_version = release_version(previous)
        if running:
            run("systemctl", "reset-failed", SERVICE)
            run("systemctl", "start", SERVICE)
            if not wait_reachable(directory, old_version):
                raise RuntimeError(f"vorheriger Programmstand {old_version or previous} ist nicht erreichbar")
            print(f"Bisherigen Programmstand {old_version or previous} wieder gestartet.", file=sys.stderr)
        else:
            print(f"Bisherigen Programmstand {old_version or previous} wiederhergestellt; Dienst bleibt gestoppt.", file=sys.stderr)
    except Exception as error:
        print(f"ROLLBACK FEHLGESCHLAGEN: {error}. Prüfen: systemctl status {SERVICE}, "
              f"Programmlink {link}", file=sys.stderr)


def checkout_origin(source):
    """Origin of an installation from a local checkout: path, branch and an exact version tag."""
    def git(*args):
        result = subprocess.run(["git", "-C", str(source), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    branch = git("symbolic-ref", "--short", "-q", "HEAD")
    return {"source": "checkout", "path": str(source), "branch": branch,
            "tag": git("describe", "--tags", "--exact-match", "--match", "v[0-9]*")}


def prepare(source, root, origin):
    """Nur Git-versionierte Dateien übernehmen, niemals lokale Laufzeitdaten."""
    revision = run("git", "-C", str(source), "rev-parse", "HEAD", capture_output=True, text=True).stdout.strip()
    version_text = run("git", "-C", str(source), "show",
                       f"{revision}:biathlon_target_vision/__init__.py", capture_output=True, text=True).stdout
    version = VERSION_PATTERN.search(version_text)
    if not version:
        raise ValueError("Versionsnummer fehlt")
    root.joinpath("releases").mkdir(parents=True, exist_ok=True)
    root.chmod(0o755)
    root.joinpath("releases").chmod(0o755)
    release = Path(tempfile.mkdtemp(prefix=version[1] + "-", dir=root / "releases"))
    try:
        release.chmod(0o755)
        archive = run("git", "-C", str(source), "archive", revision, capture_output=True).stdout
        run("tar", "-x", "-C", str(release), input=archive)
        run("python3", "-m", "venv", str(release / ".venv"))
        run(str(release / ".venv/bin/python"), "-m", "pip", "install", "-r", str(release / "requirements.txt"))
        run(str(release / ".venv/bin/python"), "-m", "pip", "check")
        # Import vor Dienstunterbrechung: fehlende native Bibliotheken früh erkennen.
        run(str(release / ".venv/bin/python"), "-c", "from biathlon_target_vision.app import create_app", cwd=release)
        # Shown by --version and --status (build.py); the commit itself comes from git archive.
        (release / "installation.json").write_text(json.dumps(
            {**origin, "installed_at": datetime.now().astimezone().isoformat(timespec="seconds")}, indent=2) + "\n")
    except BaseException:
        # An incomplete release is never activated; remove it instead of leaving a half venv behind.
        shutil.rmtree(release, ignore_errors=True)
        raise
    return release, version[1]


def upgrade():
    if os.geteuid() != 0:
        print("Upgrade benötigt root: sudo biathlon-target-vision --upgrade", file=sys.stderr)
        return 1
    os.umask(0o022)
    # Genau ein Upgrade/Installer gleichzeitig, ohne zusätzlichen Verwaltungsdienst.
    import fcntl
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / "install.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix="btv-upgrade-") as temporary:
            source = Path(temporary) / "source"
            run("git", "clone", "--quiet", "--no-checkout", REPOSITORY, str(source))
            tags = run("git", "-C", str(source), "tag", "--list", capture_output=True, text=True).stdout.splitlines()
            versions = [(tuple(map(int, tag[1:].split("."))), tag) for tag in tags
                        if re.fullmatch(r"v\d+\.\d+\.\d+", tag)]
            if not versions:
                raise RuntimeError("Keine veröffentlichte Version gefunden")
            _, tag = max(versions)
            from . import __version__
            if tuple(map(int, tag[1:].split("."))) <= tuple(map(int, __version__.split("."))):
                print(f"Version {__version__} ist aktuell.")
                return 0
            run("git", "-C", str(source), "checkout", "--quiet", tag)
            release, version = prepare(source, ROOT, {"source": "release", "tag": tag})
            activate(ROOT, DATA, release, version)
    return 0


def install(source):
    if os.geteuid() != 0:
        raise RuntimeError("Installation benötigt root")
    os.umask(0o022)
    import fcntl
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / "install.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if subprocess.run(["id", "-u", "btv"], capture_output=True).returncode:
            run("useradd", "--system", "--user-group", "--home-dir", str(DATA), "--shell", "/usr/sbin/nologin", "btv")
        DATA.mkdir(parents=True, exist_ok=True)
        DATA.chmod(0o750)
        config = DATA / "config.json"
        if not config.exists():
            config.write_text(json.dumps({"host": "0.0.0.0", "port": 8091}, indent=2) + "\n")
        config.chmod(0o600)
        run("chown", "-R", "btv:btv", str(DATA))
        release, version = prepare(source, ROOT, checkout_origin(source))
        # Autostart is set once; a repeated ./install.sh keeps the operator's choice.
        first = not UNIT.exists()
        UNIT.write_text((release / "systemd" / SERVICE).read_text())
        LAUNCHER.write_text('#!/bin/sh\ncd /opt/biathlon-target-vision/current || exit 1\nexec .venv/bin/python -m biathlon_target_vision --data-dir /var/lib/biathlon-target-vision "$@"\n')
        LAUNCHER.chmod(0o755)
        run("systemctl", "daemon-reload")
        if first:
            run("systemctl", "enable", SERVICE)
        activate(ROOT, DATA, release, version, start=True if first else None)
        print("Tablet: http://SERVER-IP:8091/  Monitor: http://SERVER-IP:8091/monitor")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    install(parser.parse_args().source.resolve())

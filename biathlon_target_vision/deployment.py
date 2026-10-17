"""Installation mit Git, venv und systemd; vorbereiten, umschalten, Start prüfen."""

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


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def reachable(directory, expected_version=None):
    try:
        config = json.loads((Path(directory) / "config.json").read_text())
        host = config.get("host", "127.0.0.1")
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        if ":" in host:
            host = f"[{host}]"
        with urlopen(f"http://{host}:{config.get('port', 8091)}/api/health", timeout=1) as response:
            health = json.load(response)
        return health.get("status") == "ok" and (expected_version is None or health.get("version") == expected_version)
    except (OSError, URLError, ValueError):
        return False


def status(directory):
    result = subprocess.run(["systemctl", "is-active", SERVICE], capture_output=True, text=True)
    online = reachable(directory)
    print(f"Dienst: {result.stdout.strip() or 'unbekannt'}; API: {'erreichbar' if online else 'nicht erreichbar'}")
    return 0 if result.returncode == 0 and online else 1


def switch_link(link, target):
    temporary = link.with_name(link.name + ".new")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(link)


def activate(root, directory, release, version):
    """Bei fehlgeschlagenem Start Programm zurückschalten; Daten nie ersetzen."""
    link = root / "current"
    previous = link.resolve() if link.exists() else None
    run("systemctl", "stop", SERVICE)
    backup = root / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        shutil.copytree(directory, backup)
        switch_link(link, release)
        run("systemctl", "reset-failed", SERVICE)
        run("systemctl", "start", SERVICE)
        for _ in range(30):
            if reachable(directory, version):
                print(f"Version {version} gestartet; Datensicherung: {backup}")
                return
            time.sleep(.5)
        raise RuntimeError("Neue Version ist nicht erreichbar")
    except Exception:
        run("systemctl", "stop", SERVICE)
        if previous:
            switch_link(link, previous)
            run("systemctl", "reset-failed", SERVICE)
            run("systemctl", "start", SERVICE)
            print("Bisherigen Programmstand wieder gestartet.", file=sys.stderr)
        raise


def prepare(source, root):
    """Nur Git-versionierte Dateien übernehmen, niemals lokale Laufzeitdaten."""
    version_text = (source / "biathlon_target_vision/__init__.py").read_text()
    version = re.search(r'__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"', version_text)
    if not version:
        raise ValueError("Versionsnummer fehlt")
    root.joinpath("releases").mkdir(parents=True, exist_ok=True)
    release = Path(tempfile.mkdtemp(prefix=version[1] + "-", dir=root / "releases"))
    release.chmod(0o755)
    archive = run("git", "-C", str(source), "archive", "HEAD", capture_output=True).stdout
    run("tar", "-x", "-C", str(release), input=archive)
    run("python3", "-m", "venv", str(release / ".venv"))
    run(str(release / ".venv/bin/python"), "-m", "pip", "install", "-r", str(release / "requirements.txt"))
    run(str(release / ".venv/bin/python"), "-m", "pip", "check")
    # Import vor Dienstunterbrechung: fehlende native Bibliotheken früh erkennen.
    run(str(release / ".venv/bin/python"), "-c", "from biathlon_target_vision.app import create_app", cwd=release)
    return release, version[1]


def upgrade():
    if os.geteuid() != 0:
        print("Upgrade benötigt root: sudo biathlon-target-vision --upgrade", file=sys.stderr)
        return 1
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
            release, version = prepare(source, ROOT)
            activate(ROOT, DATA, release, version)
    return 0


def install(source):
    if os.geteuid() != 0:
        raise RuntimeError("Installation benötigt root")
    import fcntl
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / "install.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if subprocess.run(["id", "-u", "btv"], capture_output=True).returncode:
            run("useradd", "--system", "--home-dir", str(DATA), "--shell", "/usr/sbin/nologin", "btv")
        DATA.mkdir(parents=True, exist_ok=True)
        DATA.chmod(0o750)
        config = DATA / "config.json"
        if not config.exists():
            config.write_text(json.dumps({"host": "0.0.0.0", "port": 8091}, indent=2) + "\n")
        config.chmod(0o600)
        run("chown", "-R", "btv:btv", str(DATA))
        release, version = prepare(source, ROOT)
        unit = Path("/etc/systemd/system") / SERVICE
        unit.write_text((release / "systemd" / SERVICE).read_text())
        launcher = Path("/usr/local/bin/biathlon-target-vision")
        launcher.write_text('#!/bin/sh\ncd /opt/biathlon-target-vision/current || exit 1\nexec .venv/bin/python -m biathlon_target_vision --data-dir /var/lib/biathlon-target-vision "$@"\n')
        launcher.chmod(0o755)
        run("systemctl", "daemon-reload")
        run("systemctl", "enable", SERVICE)
        activate(ROOT, DATA, release, version)
        print("Tablet: http://SERVER-IP:8091/  Monitor: http://SERVER-IP:8091/monitor")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    install(parser.parse_args().source.resolve())

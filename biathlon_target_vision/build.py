"""Build information of the installed program: commit, origin and installation time.

Shown in the page footer, by `--version` and by `--status`.
"""

import json
from pathlib import Path
import subprocess

# The installer copies the program with `git archive`; `.gitattributes` marks this
# file for export-subst, so the archive contains the real short commit here.
ARCHIVED_COMMIT = "$Format:%h$"
# Release directory (or development checkout); the installer writes installation.json there.
PROGRAM = Path(__file__).resolve().parents[1]


def commit():
    """Commit of the installed release, of a development checkout, or None if unknown."""
    if not ARCHIVED_COMMIT.startswith("$"):
        return ARCHIVED_COMMIT
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent,
                                capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def installation(program=PROGRAM):
    """Origin and time written by the installer; None for a start without installation."""
    try:
        return json.loads((Path(program) / "installation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def origin(info):
    if info is None:
        return "Start ohne Installation"
    if info.get("source") == "release":
        return f"GitHub-Release {info.get('tag')}"
    ref = f"Branch {info['branch']}" if info.get("branch") else f"Tag {info['tag']}" if info.get("tag") else "ohne Branch"
    return f"lokaler Checkout {info.get('path')} ({ref})"


def describe(program=PROGRAM):
    """Commit, origin and installation time in one line, without the version number."""
    info = installation(program)
    parts = [f"Commit {commit() or 'unbekannt'}", origin(info)]
    if info and info.get("installed_at"):
        parts.append(f"installiert {info['installed_at']}")
    return " · ".join(parts)

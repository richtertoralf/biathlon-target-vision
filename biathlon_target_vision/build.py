"""Short Git commit of the installed program for display in the page footer."""

from pathlib import Path
import subprocess

# The installer copies the program with `git archive`; `.gitattributes` marks this
# file for export-subst, so the archive contains the real short commit here.
ARCHIVED_COMMIT = "$Format:%h$"


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

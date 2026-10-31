"""Version, commit and server time in /api/health for the shared page frame."""

from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from fastapi.testclient import TestClient

from biathlon_target_vision import __version__, build
from biathlon_target_vision.app import create_app

REPOSITORY = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.run(['git', *args], cwd=REPOSITORY, capture_output=True, check=True).stdout


class BuildInfoTests(unittest.TestCase):
    def test_health_reports_version_commit_and_server_time(self):
        with tempfile.TemporaryDirectory() as directory, TestClient(create_app(Path(directory))) as client:
            before = datetime.now(timezone.utc)
            health = client.get('/api/health').json()
            after = datetime.now(timezone.utc)
        self.assertEqual(health['version'], __version__)
        self.assertEqual(health['commit'], git('rev-parse', '--short', 'HEAD').decode().strip())
        # server_time is truncated to milliseconds and may lie up to 1 ms before `before`.
        self.assertTrue(before - timedelta(milliseconds=1) <= datetime.fromisoformat(health['server_time']) <= after)

    def test_installer_archive_contains_the_real_commit(self):
        # deployment.prepare copies the program with `git archive`; export-subst fills in the commit.
        if subprocess.run(['git', 'cat-file', '-e', 'HEAD:biathlon_target_vision/build.py'], cwd=REPOSITORY).returncode:
            self.skipTest('build.py is not committed yet')
        archive = tarfile.open(fileobj=io.BytesIO(git('archive', 'HEAD', 'biathlon_target_vision/build.py')))
        source = archive.extractfile('biathlon_target_vision/build.py').read().decode()
        commit = source.split('ARCHIVED_COMMIT = "', 1)[1].split('"', 1)[0]
        self.assertRegex(commit, r'^[0-9a-f]{7,}$')
        self.assertTrue(git('rev-parse', 'HEAD').decode().startswith(commit))

    def test_describe_release_and_checkout_installations(self):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory)
            self.assertRegex(build.describe(program), r'^Commit [0-9a-f]{7,} · Start ohne Installation$')
            (program / 'installation.json').write_text(
                '{"source": "release", "tag": "v0.8.6", "installed_at": "2026-10-31T18:00:00+01:00"}')
            self.assertRegex(build.describe(program),
                             r'^Commit [0-9a-f]{7,} · GitHub-Release v0\.8\.6 · installiert 2026-10-31T18:00:00\+01:00$')
            (program / 'installation.json').write_text(
                '{"source": "checkout", "path": "/home/op/btv", "branch": "feature/x", "tag": null, "installed_at": "2026-10-31T18:00:00+01:00"}')
            self.assertIn('lokaler Checkout /home/op/btv (Branch feature/x) · installiert', build.describe(program))
            (program / 'installation.json').write_text(
                '{"source": "checkout", "path": "/home/op/btv", "branch": null, "tag": "v0.8.6", "installed_at": "x"}')
            self.assertIn('lokaler Checkout /home/op/btv (Tag v0.8.6)', build.describe(program))


class ReadmeVersionTests(unittest.TestCase):
    """ADR-002: the static README badge and the install example follow __version__."""

    def test_badge_and_install_example_match_version(self):
        readme = (REPOSITORY / 'README.md').read_text(encoding='utf-8')
        self.assertIn(f'https://img.shields.io/badge/version-{__version__}-blue', readme)
        self.assertIn(f'git clone --branch v{__version__} ', readme)
        # A dynamic release badge is allowed only with the label "release".
        self.assertNotIn('label=version', readme)

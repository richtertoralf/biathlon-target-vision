"""Version, commit and server time in /api/health for the shared page frame."""

from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from fastapi.testclient import TestClient

from biathlon_target_vision import __version__
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

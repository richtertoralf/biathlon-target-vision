"""Installationsvorbereitung, Dienststatus und Rollback mit isolierten Dateien."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from biathlon_target_vision import __version__
from biathlon_target_vision.config import Settings, load_settings, save_settings
from biathlon_target_vision import deployment


class DeploymentTests(unittest.TestCase):
    def test_version_without_data_directory(self):
        result = subprocess.run([sys.executable, '-m', 'biathlon_target_vision', '--version'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), __version__)

    def test_settings_roundtrip_and_invalid_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            save_settings(directory, Settings(port=8092))
            self.assertEqual(load_settings(directory).port, 8092)
            self.assertEqual((directory / 'config.json').stat().st_mode & 0o777, 0o600)
            (directory / 'config.json').write_text('{"port": 0}')
            with self.assertRaises(ValueError):
                load_settings(directory)

    def test_successful_activation_preserves_data_and_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = root / 'data'; data.mkdir()
            (data / 'events.jsonl').write_text('journal\n')
            old = root / 'old'; old.mkdir(); new = root / 'new'; new.mkdir()
            (root / 'current').symlink_to(old)
            with patch.object(deployment, 'run') as run, patch.object(deployment, 'reachable', return_value=True):
                deployment.activate(root, data, new, '0.3.0')
            self.assertEqual((root / 'current').resolve(), new)
            self.assertEqual((data / 'events.jsonl').read_text(), 'journal\n')
            self.assertEqual(next((root / 'backups').glob('*/events.jsonl')).read_text(), 'journal\n')
            self.assertEqual(run.call_args_list[0].args, ('systemctl', 'stop', deployment.SERVICE))

    def test_failed_start_rolls_back_without_replacing_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = root / 'data'; data.mkdir()
            (data / 'config.json').write_text('{}')
            old = root / 'old'; old.mkdir(); new = root / 'new'; new.mkdir()
            (root / 'current').symlink_to(old)
            with patch.object(deployment, 'run') as run, patch.object(deployment, 'reachable', return_value=False), patch.object(deployment.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'nicht erreichbar'):
                    deployment.activate(root, data, new, '0.3.0')
            self.assertEqual((root / 'current').resolve(), old)
            self.assertEqual((data / 'config.json').read_text(), '{}')
            self.assertEqual(run.call_args_list[-1].args, ('systemctl', 'start', deployment.SERVICE))

    def test_backup_failure_restarts_previous_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = root / 'data'; data.mkdir()
            old = root / 'old'; old.mkdir(); (root / 'current').symlink_to(old)
            with patch.object(deployment, 'run') as run, patch.object(deployment.shutil, 'copytree', side_effect=OSError('full')):
                with self.assertRaises(OSError):
                    deployment.activate(root, data, root / 'new', '0.3.0')
            self.assertEqual((root / 'current').resolve(), old)
            self.assertEqual(run.call_args_list[-1].args, ('systemctl', 'start', deployment.SERVICE))

    def test_prepare_archives_only_committed_files_and_is_service_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            package = source / 'biathlon_target_vision'; package.mkdir()
            (package / '__init__.py').write_text('__version__ = "0.3.0"\n')
            (source / 'requirements.txt').write_text('')
            subprocess.run(['git','init','-q',str(source)], check=True)
            subprocess.run(['git','-C',str(source),'add','.'], check=True)
            subprocess.run(['git','-C',str(source),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'], check=True)
            (source / 'secret-runtime-data').write_text('must not deploy')
            original = deployment.run
            def prepare_command(*args, **kwargs):
                if args[0] == 'git' or args[0] == 'tar':
                    return original(*args, **kwargs)
                return subprocess.CompletedProcess(args, 0)
            with patch.object(deployment, 'run', side_effect=prepare_command):
                release, version = deployment.prepare(source, root / 'install')
            self.assertEqual(version, '0.3.0')
            self.assertFalse((release / 'secret-runtime-data').exists())
            self.assertTrue((release / 'biathlon_target_vision/__init__.py').exists())
            self.assertEqual(release.stat().st_mode & 0o777, 0o755)

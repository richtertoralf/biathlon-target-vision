"""Installationsvorbereitung, Dienststatus und Rollback mit isolierten Dateien."""

import contextlib
import io
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


def release(root, name, version):
    """Minimal release directory whose version deployment.release_version can read."""
    directory = root / name; (directory / 'biathlon_target_vision').mkdir(parents=True)
    (directory / 'biathlon_target_vision/__init__.py').write_text(f'__version__ = "{version}"\n')
    return directory


def git_fixture(source, version='0.3.0'):
    package = source / 'biathlon_target_vision'; package.mkdir(parents=True)
    (package / '__init__.py').write_text(f'__version__ = "{version}"\n')
    (source / 'requirements.txt').write_text('')
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(source)], check=True)
    subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(source), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '-qm', 'fixture'], check=True)


def systemctl_calls(run):
    return [call.args[1] for call in run.call_args_list if call.args[0] == 'systemctl']


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        # No test may ask the real systemd; each test states the service state it needs.
        self.state = patch.object(deployment, 'service_state', return_value=('active', 'enabled')); self.state.start()
        self.addCleanup(self.state.stop)

    def activate(self, *args, **kwargs):
        """deployment.activate with captured stdout/stderr."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                deployment.activate(*args, **kwargs)
            finally:
                self.out, self.err = out.getvalue(), err.getvalue()

    def test_version_without_data_directory(self):
        result = subprocess.run([sys.executable, '-m', 'biathlon_target_vision', '--version'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout.strip(), rf'^{__version__} · Commit [0-9a-f]{{7,}} · Start ohne Installation$')

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
                self.activate(root, data, new, '0.3.0')
            self.assertEqual((root / 'current').resolve(), new)
            self.assertEqual((data / 'events.jsonl').read_text(), 'journal\n')
            self.assertEqual(next((root / 'backups').glob('*/events.jsonl')).read_text(), 'journal\n')
            self.assertEqual(run.call_args_list[0].args, ('systemctl', 'stop', deployment.SERVICE))
            self.assertEqual(systemctl_calls(run), ['stop', 'reset-failed', 'start'])

    def test_stopped_service_stays_stopped_and_autostart_is_untouched(self):
        for enabled in ('enabled', 'disabled'):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); data = root / 'data'; data.mkdir()
                old = release(root, 'old', '0.2.0'); new = release(root, 'new', '0.3.0'); (root / 'current').symlink_to(old)
                self.state.stop(); self.state = patch.object(deployment, 'service_state', return_value=('inactive', enabled)); self.state.start()
                with patch.object(deployment, 'run') as run, patch.object(deployment, 'reachable') as reachable:
                    self.activate(root, data, new, '0.3.0')
                self.assertEqual((root / 'current').resolve(), new)
                self.assertEqual(systemctl_calls(run), [])
                reachable.assert_not_called()
                self.assertIn('Dienst bleibt gestoppt', self.out); self.assertIn(f'Autostart {enabled}', self.out)
                self.assertEqual(len(list((root / 'backups').iterdir())), 1)

    def test_active_service_never_changes_autostart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = root / 'data'; data.mkdir()
            (root / 'current').symlink_to(release(root, 'old', '0.2.0'))
            self.state.stop(); self.state = patch.object(deployment, 'service_state', return_value=('active', 'disabled')); self.state.start()
            with patch.object(deployment, 'run') as run, patch.object(deployment, 'reachable', return_value=True):
                self.activate(root, data, release(root, 'new', '0.3.0'), '0.3.0')
            self.assertNotIn('enable', systemctl_calls(run)); self.assertNotIn('disable', systemctl_calls(run))

    def test_failed_start_rolls_back_without_replacing_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = root / 'data'; data.mkdir()
            (data / 'config.json').write_text('{}')
            old = root / 'old'; old.mkdir(); new = root / 'new'; new.mkdir()
            (root / 'current').symlink_to(old)
            old = release(root, 'previous', '0.2.0'); (root / 'current').unlink(); (root / 'current').symlink_to(old)
            # Only the previous version answers: the new one never starts, the old one does.
            with patch.object(deployment, 'run') as run, patch.object(deployment, 'reachable', side_effect=lambda _, version=None: version == '0.2.0'), \
                    patch.object(deployment.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'nicht erreichbar'):
                    self.activate(root, data, new, '0.3.0')
            self.assertEqual((root / 'current').resolve(), old)
            self.assertEqual((data / 'config.json').read_text(), '{}')
            self.assertEqual(run.call_args_list[-1].args, ('systemctl', 'start', deployment.SERVICE))
            self.assertIn('Bisherigen Programmstand 0.2.0 wieder gestartet', self.err)
            self.assertNotIn('ROLLBACK FEHLGESCHLAGEN', self.err)

    def test_failed_rollback_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = root / 'data'; data.mkdir()
            old = release(root, 'old', '0.2.0'); (root / 'current').symlink_to(old)
            with patch.object(deployment, 'run'), patch.object(deployment, 'reachable', return_value=False), patch.object(deployment.time, 'sleep'):
                with self.assertRaisesRegex(RuntimeError, 'Neue Version ist nicht erreichbar'):
                    self.activate(root, data, release(root, 'new', '0.3.0'), '0.3.0')
            self.assertEqual((root / 'current').resolve(), old)
            self.assertIn('ROLLBACK FEHLGESCHLAGEN: vorheriger Programmstand 0.2.0 ist nicht erreichbar', self.err)
            self.assertNotIn('wieder gestartet', self.err)

    def test_backup_failure_restarts_previous_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); data = root / 'data'; data.mkdir()
            old = root / 'old'; old.mkdir(); (root / 'current').symlink_to(old)
            with patch.object(deployment, 'run') as run, patch.object(deployment.shutil, 'copytree', side_effect=OSError('full')), \
                    patch.object(deployment, 'reachable', return_value=True):
                with self.assertRaises(OSError):
                    self.activate(root, data, root / 'new', '0.3.0')
            self.assertEqual((root / 'current').resolve(), old)
            self.assertEqual(run.call_args_list[-1].args, ('systemctl', 'start', deployment.SERVICE))
            # A stopped service stays stopped during the rollback as well.
            self.state.stop(); self.state = patch.object(deployment, 'service_state', return_value=('inactive', 'enabled')); self.state.start()
            with patch.object(deployment, 'run') as run, patch.object(deployment.shutil, 'copytree', side_effect=OSError('full')):
                with self.assertRaises(OSError):
                    self.activate(root, data, root / 'new', '0.3.0')
            self.assertEqual((root / 'current').resolve(), old)
            self.assertEqual(systemctl_calls(run), [])
            self.assertIn('Dienst bleibt gestoppt', self.err)

    def test_prepare_archives_only_committed_files_and_is_service_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'
            git_fixture(source); package = source / 'biathlon_target_vision'
            (source / 'secret-runtime-data').write_text('must not deploy')
            (package / '__init__.py').write_text('__version__ = "9.9.9"\n')
            original = deployment.run
            def prepare_command(*args, **kwargs):
                if args[0] == 'git' or args[0] == 'tar':
                    return original(*args, **kwargs)
                return subprocess.CompletedProcess(args, 0)
            with patch.object(deployment, 'run', side_effect=prepare_command):
                prepared, version = deployment.prepare(source, root / 'install', {'source': 'release', 'tag': 'v0.3.0'})
            self.assertEqual(version, '0.3.0')
            self.assertFalse((prepared / 'secret-runtime-data').exists())
            self.assertTrue((prepared / 'biathlon_target_vision/__init__.py').exists())
            self.assertEqual(prepared.stat().st_mode & 0o777, 0o755)
            installation = json.loads((prepared / 'installation.json').read_text())
            self.assertEqual((installation['source'], installation['tag']), ('release', 'v0.3.0'))
            self.assertRegex(installation['installed_at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$')

    def test_failed_prepare_removes_incomplete_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; git_fixture(source)
            original = deployment.run
            def failing_pip(*args, **kwargs):
                if args[0] in ('git', 'tar'):
                    return original(*args, **kwargs)
                if 'pip' in args:
                    raise subprocess.CalledProcessError(1, args)
                return subprocess.CompletedProcess(args, 0)
            with patch.object(deployment, 'run', side_effect=failing_pip):
                with self.assertRaises(subprocess.CalledProcessError):
                    deployment.prepare(source, root / 'install', {'source': 'release', 'tag': 'v0.3.0'})
            self.assertEqual(list((root / 'install/releases').iterdir()), [])

    def test_checkout_origin_names_branch_or_tag(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'; git_fixture(source)
            subprocess.run(['git', '-C', str(source), 'switch', '-q', '-c', 'feature/x'], check=True)
            self.assertEqual(deployment.checkout_origin(source),
                             {'source': 'checkout', 'path': str(source), 'branch': 'feature/x', 'tag': None})
            # `git clone --branch v0.3.0` as in the README: detached HEAD exactly on the tag.
            subprocess.run(['git', '-C', str(source), 'tag', 'v0.3.0'], check=True)
            subprocess.run(['git', '-C', str(source), 'switch', '-q', '--detach', 'v0.3.0'], check=True)
            self.assertEqual(deployment.checkout_origin(source),
                             {'source': 'checkout', 'path': str(source), 'branch': None, 'tag': 'v0.3.0'})


class UpgradeTests(unittest.TestCase):
    """deployment.upgrade with a replaced Git clone: only a newer version tag is deployed."""

    def upgrade(self, tags):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(deployment, 'ROOT', Path(temporary)), patch.object(deployment.os, 'geteuid', return_value=0), \
                patch.object(deployment, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='\n'.join(tags))) as run, \
                patch.object(deployment, 'prepare', return_value=(Path(temporary) / 'release', 'x')) as prepare, \
                patch.object(deployment, 'activate') as activate, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(deployment.upgrade(), 0)
        return run, prepare, activate, output.getvalue()

    def test_same_or_older_version_deploys_nothing(self):
        major, minor, patch_level = map(int, __version__.split('.'))
        run, prepare, activate, output = self.upgrade([f'v{__version__}', f'v{major}.{minor}.{max(patch_level - 1, 0)}', 'v0.1.0-rc1'])
        prepare.assert_not_called(); activate.assert_not_called()
        self.assertNotIn('systemctl', [call.args[0] for call in run.call_args_list])
        self.assertIn(f'Version {__version__} ist aktuell', output)

    def test_newer_tag_is_prepared_as_release(self):
        major, minor, patch_level = map(int, __version__.split('.'))
        newer = f'v{major}.{minor}.{patch_level + 1}'
        run, prepare, activate, _ = self.upgrade([f'v{__version__}', newer])
        self.assertEqual(prepare.call_args.args[2], {'source': 'release', 'tag': newer})
        self.assertIn(('git', '-C', str(prepare.call_args.args[0]), 'checkout', '--quiet', newer), [call.args for call in run.call_args_list])
        activate.assert_called_once()
        # No start parameter: the upgrade keeps the previous service state.
        self.assertEqual(activate.call_args.kwargs, {})


class InstallTests(unittest.TestCase):
    """deployment.install with temporary system paths: autostart is only enabled on first install."""

    def install(self, root):
        with patch.object(deployment, 'ROOT', root / 'opt'), patch.object(deployment, 'DATA', root / 'data'), \
                patch.object(deployment, 'UNIT', root / 'unit.service'), patch.object(deployment, 'LAUNCHER', root / 'launcher'), \
                patch.object(deployment.os, 'geteuid', return_value=0), \
                patch.object(deployment.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(deployment, 'checkout_origin', return_value={'source': 'checkout'}), \
                patch.object(deployment, 'prepare', return_value=(root / 'release', '0.3.0')), \
                patch.object(deployment, 'run') as run, patch.object(deployment, 'activate') as activate, \
                contextlib.redirect_stdout(io.StringIO()):
            deployment.install(root / 'source')
        return systemctl_calls(run), activate.call_args.kwargs

    def test_enable_only_on_first_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'release/systemd').mkdir(parents=True)
            (root / 'release/systemd' / deployment.SERVICE).write_text('[Unit]\n')
            calls, kwargs = self.install(root)
            self.assertEqual(calls, ['daemon-reload', 'enable']); self.assertEqual(kwargs, {'start': True})
            # Repeated ./install.sh: keep autostart and service state as they are.
            calls, kwargs = self.install(root)
            self.assertEqual(calls, ['daemon-reload']); self.assertEqual(kwargs, {'start': None})

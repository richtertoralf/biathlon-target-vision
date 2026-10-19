"""Sitzungsgrenzen über API, Journal, Neustart und laufende Kameraauswertung."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from biathlon_target_vision.app import create_app
from biathlon_target_vision.calibration import CalibrationStore, calibrate
from biathlon_target_vision.cameras import camera_binding
from biathlon_target_vision.config import CameraSettings, Settings, save_settings
from biathlon_target_vision.core import EventStore
from biathlon_target_vision.sessions import Sessions, write_json
from tests.synthetic import scene
from tests.test_cameras import FakeCameras


class SessionApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name)
        self.client = TestClient(create_app(self.path, 2))
        self.client.__enter__()
        self.session_id = self.state()['session_id']
        self.client.headers['X-Session-ID'] = self.session_id

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temporary.cleanup()

    def state(self):
        return self.client.get('/api/state').json()

    def start(self, **changes):
        body = dict(session_id=str(uuid4()), expected_session_id=self.session_id, name='Nachmittag')
        body.update(changes)
        return self.client.post('/api/sessions/start', json=body)

    def input(self, action, **fields):
        lane = self.state()['lanes']['1']
        expected = {'expected_revision': lane['revision']} if action in ('occupy', 'bib') else {'expected_control_revision': lane['control_revision']}
        response = self.client.request('PUT' if action == 'bib' else 'POST', '/api/lanes/1/' + action,
            json={'lane_id': 1, **expected, **fields})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_independent_bibs_archive_and_restart(self):
        renamed = self.client.put('/api/sessions/current', json={'expected_session_id': self.session_id, 'name': 'Vormittag'})
        self.assertEqual(renamed.status_code, 200)
        self.input('reset'); self.input('occupy'); self.input('bib', bib=42)
        self.input('manual-target', target_id=3, state='fallen')
        journal = self.path / 'sessions' / self.session_id / 'events.jsonl'
        before = journal.read_bytes()
        corrections = journal.parent / 'corrections'; corrections.mkdir()
        (corrections / '4.jpg').write_bytes(b'comparison evidence')
        settings = Settings(port=8099); save_settings(self.path, settings)
        image, quad, _, _ = scene(); CalibrationStore(self.path).save(1, calibrate(image, quad))
        shared = {path: path.read_bytes() for path in [self.path/'config.json', *self.path.glob('calibrations/*')]}
        self.assertEqual(self.start().status_code, 409)
        response = self.start(confirm_active=True)
        self.assertEqual(response.status_code, 200, response.text)
        fresh = response.json(); new_id = fresh['session_id']
        self.assertNotEqual(new_id, self.session_id)
        self.assertEqual(fresh['bouts'], {})
        self.assertTrue(all(lane['status'] == 'reset_required' and lane['targets'] == ['unknown'] * 5 for lane in fresh['lanes'].values()))
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual((corrections/'4.jpg').read_bytes(), b'comparison evidence')
        self.assertEqual({path: path.read_bytes() for path in shared}, shared)
        archive = self.client.get('/api/events', params={'session_id': self.session_id}).json()
        self.assertEqual(archive['session_id'], self.session_id)
        self.assertEqual(len(archive['events']), 4)
        self.assertEqual(self.client.get('/api/events').json()['events'], [])
        self.client.headers['X-Session-ID'] = new_id
        self.input('occupy'); self.input('bib', bib=42)
        expected = self.state()
        self.client.__exit__(None, None, None)
        self.client = TestClient(create_app(self.path)); self.client.__enter__()
        restored = self.state()
        self.assertNotEqual(restored.pop('instance_id'), expected.pop('instance_id'))
        self.assertEqual(restored, expected)
        sessions = self.client.get('/api/sessions').json()['sessions']
        self.assertEqual([s['name'] for s in sessions], ['Vormittag', 'Nachmittag'])
        self.assertEqual(sessions[0]['ended_at'], sessions[1]['started_at'])
        self.assertEqual(journal.read_bytes(), before)

    def test_source_exclusion_is_preserved_without_target_history(self):
        self.client.put('/api/lanes/1/mode', json={'lane_id': 1, 'mode': 'manual', 'expected_control_revision': 0})
        self.input('manual-target', target_id=2, state='fallen', start_bout=False)
        fresh = self.start().json()
        self.assertEqual(fresh['lanes']['1']['mode'], 'manual')
        self.assertEqual(fresh['lanes']['1']['manual_targets'], [None]*5)
        self.assertEqual(fresh['lanes']['2']['mode'], 'automatic')
        events = self.client.get('/api/events').json()['events']
        self.assertEqual([e['command']['kind'] for e in events], ['mode'])

    def test_open_bout_without_occupancy_requires_confirmation(self):
        self.input('manual-target', target_id=1, state='fallen')
        lane = self.state()['lanes']['1']
        self.assertIsNone(lane['occupied_bout_id'])
        self.assertIsNotNone(lane['current_bout_id'])
        self.assertEqual(self.start().status_code, 409)
        self.assertEqual(self.start(confirm_active=True).status_code, 200)

    def test_old_and_unscoped_commands_cannot_enter_new_session(self):
        self.start()
        requests = [('/release', {'expected_revision': 0, 'bout_id': 'archived-bout'}),
                    ('/occupy', {'expected_revision': 0}), ('/reset', {'expected_control_revision': 0}),
                    ('/manual-target', {'expected_control_revision': 0, 'target_id': 1, 'state': 'fallen'}),
                    ('/override-release', {'expected_control_revision': 0, 'target_id': 1})]
        for suffix, fields in requests:
            self.assertEqual(self.client.post('/api/lanes/1'+suffix, json={'lane_id': 1, **fields}).status_code, 409)
        self.assertEqual(self.client.put('/api/lanes/1/bib', json={'lane_id': 1, 'bib': 42, 'expected_revision': 0}).status_code, 409)
        self.assertEqual(self.client.put('/api/lanes/1/mode', json={'lane_id': 1, 'mode': 'manual', 'expected_control_revision': 0}).status_code, 409)
        observation = {'lane_id': 1, 'kind': 'target', 'target_id': 1, 'state': 'fallen', 'source': 'test', 'observed_at': datetime.now(timezone.utc).isoformat()}
        self.assertEqual(self.client.post('/api/observations', json=observation).status_code, 409)
        del self.client.headers['X-Session-ID']
        self.assertEqual(self.client.post('/api/observations', json=observation).status_code, 422)
        self.assertEqual(self.state()['sequence'], 0)

    def test_two_tablets_receive_empty_session_and_old_drafts_are_ignored(self):
        with self.client.websocket_connect('/ws') as first, self.client.websocket_connect('/ws') as second:
            first.receive_json(); second.receive_json()
            first.send_json({'type': 'draft', 'session_id': self.session_id, 'lane_id': 1, 'value': '42'})
            self.assertTrue(first.receive_json()['drafts']); self.assertTrue(second.receive_json()['drafts'])
            fresh = self.start().json()
            for socket in (first, second):
                state = socket.receive_json()
                self.assertEqual(state['session_id'], fresh['session_id'])
                self.assertEqual(state['drafts'], [])
            first.send_json({'type': 'draft', 'session_id': self.session_id, 'lane_id': 1, 'value': '43'})
            self.assertEqual(first.receive_json()['drafts'], [])
            self.assertEqual(second.receive_json()['drafts'], [])

    def test_two_administrators_and_retried_switch(self):
        def send(identifier):
            return self.start(session_id=identifier)
        ids = [str(uuid4()), str(uuid4())]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(send, ids))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        winner = next(r.json()['session_id'] for r in responses if r.status_code == 200)
        self.assertEqual(self.start(session_id=winner).status_code, 200)
        self.assertEqual(len(self.client.get('/api/sessions').json()['sessions']), 2)
        self.assertEqual(self.start(session_id=winner, name='Anderer Inhalt').status_code, 409)

    def test_archive_pagination_and_unknown_id(self):
        for _ in range(3): self.input('reset')
        self.start()
        page = self.client.get('/api/events', params={'session_id': self.session_id, 'after': 1, 'limit': 1})
        self.assertEqual([e['sequence'] for e in page.json()['events']], [2])
        self.assertEqual(page.json()['sequence'], 3)
        self.assertEqual(page.headers['cache-control'], 'no-store')
        self.assertEqual(self.client.get('/api/events?session_id=../../outside').status_code, 404)

    def test_index_write_failure_stops_writes_and_restart_uses_committed_pointer(self):
        for committed in (False, True):
            with self.subTest(committed=committed):
                old_id = self.state()['session_id']
                def fail(path, data):
                    if committed: write_json(path, data)
                    raise OSError('test disk error')
                with patch('biathlon_target_vision.sessions.write_json', side_effect=fail), self.assertLogs(level='ERROR'):
                    response = self.start(expected_session_id=old_id)
                    self.assertEqual(response.status_code, 503)
                self.assertEqual(self.client.get('/api/health').status_code, 503)
                with self.assertLogs(level='ERROR'):
                    self.assertEqual(self.client.post('/api/lanes/1/reset', json={'lane_id': 1, 'expected_control_revision': 0}).status_code, 503)
                self.client.__exit__(None, None, None)
                self.client = TestClient(create_app(self.path)); self.client.__enter__()
                new_id = self.state()['session_id']
                self.assertEqual(new_id != old_id, committed)
                self.client.headers['X-Session-ID'] = new_id


class SessionStorageTests(unittest.TestCase):
    def test_old_test_data_requires_manual_archival_and_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            old = EventStore(path, 1); old.close()
            (path/'corrections').mkdir(); (path/'corrections'/'1.jpg').write_bytes(b'evidence')
            before = {p: p.read_bytes() for p in path.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError, 'manuell archivieren'):
                Sessions(path)
            for file, content in before.items(): self.assertEqual(file.read_bytes(), content)
            self.assertFalse((path/'sessions.json').exists())

    def test_directory_lock_and_missing_active_journal(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary); sessions = Sessions(path, 2)
            try:
                with self.assertRaises(BlockingIOError): Sessions(path)
                journal = sessions.path / 'events.jsonl'
            finally: sessions.close()
            journal.unlink()
            with self.assertRaisesRegex(ValueError, 'Journal.*fehlt'): Sessions(path)
            self.assertFalse(journal.exists())

    def test_initial_index_failure_preserves_unreferenced_journal(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            with patch('biathlon_target_vision.sessions.write_json', side_effect=OSError('disk full')):
                with self.assertRaises(OSError): Sessions(path, 2)
            journals = list((path/'sessions').glob('*/events.jsonl'))
            self.assertEqual(len(journals), 1)
            with self.assertRaisesRegex(ValueError, "Sitzungsindex fehlt"):
                Sessions(path, 2)
            self.assertTrue(journals[0].exists())


class SessionVisionTests(unittest.TestCase):
    def test_correction_evidence_with_same_sequence_stays_in_its_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            camera = CameraSettings(id='test', name='Test', url='rtsp://localhost/test', lane_ids=[1])
            save_settings(path, Settings(cameras=[camera]))
            image, quad, _, _ = scene(); calibration = calibrate(image, quad); calibration.update(camera_binding(camera))
            CalibrationStore(path).save(1, calibration)
            capture = {'frame': image, 'connected': True, 'captured_at': datetime.now(timezone.utc), 'frame_number': 1}
            with patch('biathlon_target_vision.app.CameraManager') as manager:
                manager.return_value.snapshot.return_value = capture
                with TestClient(create_app(path, 1)) as client:
                    old_id = client.get('/api/state').json()['session_id']
                    shared = {file: file.read_bytes() for file in [path/'config.json', *path.glob('calibrations/*')]}
                    command = {'lane_id': 1, 'target_id': 3, 'state': 'fallen', 'start_bout': False, 'expected_control_revision': 0}
                    before = client.post('/api/lanes/1/manual-target', json=command, headers={'X-Session-ID': old_id})
                    self.assertEqual(before.status_code, 200, before.text)
                    archive = path/'sessions'/old_id/'corrections'
                    original = {p.name: p.read_bytes() for p in archive.iterdir()}
                    response = client.post('/api/sessions/start', json={'session_id': str(uuid4()), 'expected_session_id': old_id, 'name': 'Neu'})
                    new_id = response.json()['session_id']
                    after = client.post('/api/lanes/1/manual-target', json=command, headers={'X-Session-ID': new_id})
                    self.assertEqual(after.status_code, 200, after.text)
                    self.assertEqual(before.json()['event']['sequence'], after.json()['event']['sequence'])
                    self.assertEqual({p.name: p.read_bytes() for p in archive.iterdir()}, original)
                    evidence = path/'sessions'/new_id/'corrections'/'1.json'
                    self.assertEqual(json.loads(evidence.read_text())['session_id'], new_id)
                    self.assertEqual({file: file.read_bytes() for file in shared}, shared)

    def test_buffered_image_from_previous_session_is_not_classified(self):
        import asyncio
        from biathlon_target_vision.vision import VisionService
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary); store = EventStore(path, 1)
            camera = CameraSettings(id='test', name='Test', url='rtsp://localhost/test', lane_ids=[1])
            cameras = FakeCameras([camera])
            capture = cameras.snapshot('test')
            boundary = datetime.now(timezone.utc).isoformat()
            service = VisionService(lambda: Settings(cameras=[camera]), cameras, CalibrationStore(path), store, store.apply, not_before=boundary)
            try:
                with patch.object(cameras, 'snapshot', return_value=capture), patch('biathlon_target_vision.vision.classify') as classify:
                    asyncio.run(service.step())
                    classify.assert_not_called()
                self.assertEqual(store.events, [])
            finally: store.close()

    def test_switch_discards_running_classification_and_restarts_with_baseline(self):
        entered, unblock = threading.Event(), threading.Event()
        first = True
        def classify(image, calibration):
            nonlocal first
            if first:
                first = False; entered.set()
                if not unblock.wait(5): raise RuntimeError('test did not release classifier')
                return ['fallen']*5
            return ['standing']*5
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            camera = CameraSettings(id='test', name='Test', url='rtsp://localhost/test', lane_ids=[1])
            save_settings(path, Settings(cameras=[camera]))
            image, quad, _, _ = scene(); calibration = calibrate(image, quad); calibration.update(camera_binding(camera))
            CalibrationStore(path).save(1, calibration)
            with patch('biathlon_target_vision.app.CameraManager', FakeCameras), patch('biathlon_target_vision.vision.classify', side_effect=classify):
                try:
                    with TestClient(create_app(path, 1)) as client:
                        self.assertTrue(entered.wait(2))
                        old = client.get('/api/state').json()['session_id']
                        response = client.post('/api/sessions/start', json={'session_id': str(uuid4()), 'expected_session_id': old, 'name': 'Neu'})
                        self.assertEqual(response.status_code, 200, response.text)
                        unblock.set()
                        deadline = time.monotonic()+3
                        while time.monotonic() < deadline:
                            state = client.get('/api/state').json()
                            if state['lanes']['1']['targets'] == ['standing']*5: break
                            time.sleep(.05)
                        self.assertEqual(state['lanes']['1']['targets'], ['standing']*5)
                        self.assertEqual(state['lanes']['1']['status'], 'reset_required')
                        self.assertEqual(state['bouts'], {})
                        events = client.get('/api/events').json()['events']
                        self.assertEqual(len(events), 5)
                        self.assertTrue(all(event['baseline'] and event['command']['state'] == 'standing' for event in events))
                        self.assertEqual(client.get('/api/events', params={'session_id': old}).json()['events'], [])
                finally: unblock.set()

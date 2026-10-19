"""Optional test diagnostics, Markdown test report and PDF field protocol of a session."""

from datetime import datetime, timezone
import asyncio
import json
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from biathlon_target_vision import diagnostics
from biathlon_target_vision.app import create_app
from biathlon_target_vision.calibration import CalibrationStore, calibrate
from biathlon_target_vision.cameras import camera_binding
from biathlon_target_vision.config import CameraSettings, Settings, save_settings
from tests.synthetic import scene

SECRET_URL = 'rtsp://admin:geheim@127.0.0.1:8554/kamera-nord?token=abc'


class Cameras:
    """Synthetic decoder: camera "nord" delivers frames unless switched off, "sued" never does."""
    online = {'nord': True}

    def __init__(self, cameras):
        self.image = scene()[0]

    def configure(self, cameras): pass
    def close(self): pass

    def snapshot(self, camera_id):
        connected = self.online.get(camera_id, False)
        number = int(time.monotonic() * 10)
        return {'connected': connected, 'frame': self.image if connected else None, 'frame_number': number,
                'captured_at': datetime.now(timezone.utc), 'stream_epoch': 1 if connected else 0}


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        Cameras.online = {'nord': True}
        self.temporary = tempfile.TemporaryDirectory(); self.path = Path(self.temporary.name)
        nord = CameraSettings(id='nord', name='Kamera Nord', url=SECRET_URL, lane_ids=[1, 2])
        sued = CameraSettings(id='sued', name='Kamera Süd', url='rtsp://127.0.0.1:8554/kamera-sued', lane_ids=[3])
        save_settings(self.path, Settings(cameras=[nord, sued]))
        image, quad, _, _ = scene(); calibration = calibrate(image, quad); calibration.update(camera_binding(nord))
        CalibrationStore(self.path).save(1, calibration)  # lane 2 and 3 stay uncalibrated
        self.patches = [patch('biathlon_target_vision.app.CameraManager', Cameras), patch.object(diagnostics, 'INTERVAL', .05),
                        patch.object(diagnostics, 'MEDIAMTX_CONFIGS', ())]
        for item in self.patches:
            item.start()
        self.open()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for item in self.patches:
            item.stop()
        self.temporary.cleanup()

    def open(self):
        self.client = TestClient(create_app(self.path, 4)); self.client.__enter__()
        self.session = self.client.get('/api/state').json()['session_id']
        self.base = f'/api/sessions/{self.session}'

    def stop_capture(self):
        """Stop camera processing so that only the tested action could change the journal."""
        async def cancel():
            self.client.app.state.vision_task.cancel()
            await asyncio.gather(self.client.app.state.vision_task, return_exceptions=True)
        self.client.portal.call(cancel)

    def journal(self, session=None):
        return (self.path / 'sessions' / (session or self.session) / 'events.jsonl').read_bytes()

    def wait_samples(self, count, session=None):
        deadline = time.monotonic() + 10
        while self.client.get(f'/api/sessions/{session or self.session}/diagnostics').json()['samples'] < count:
            self.assertLess(time.monotonic(), deadline, 'no diagnostics samples written'); time.sleep(.05)

    def test_start_stop_samples_and_report_without_secrets(self):
        self.assertFalse(self.client.get(f'{self.base}/diagnostics').json()['active'])
        status = self.client.post(f'{self.base}/diagnostics/start').json()
        self.assertTrue(status['active']); self.assertTrue(status['running'])
        self.client.post('/api/lanes/1/occupy', headers={'X-Session-ID': self.session}, json={'lane_id': 1, 'expected_revision': 0})
        self.wait_samples(3)
        Cameras.online = {'nord': False}  # camera failure between samples
        time.sleep(.3)
        Cameras.online = {'nord': True}
        self.wait_samples(10)
        status = self.client.post(f'{self.base}/diagnostics/stop').json()
        self.assertFalse(status['active']); self.assertEqual(status['runs'][-1]['stop_reason'], 'beendet')
        stopped = status['samples']; time.sleep(.2)
        self.assertEqual(self.client.get(f'{self.base}/diagnostics').json()['samples'], stopped, 'sampling continues after stop')
        sample = json.loads((self.path / 'sessions' / self.session / 'diagnostics' / 'samples.jsonl').read_text().splitlines()[-1])
        self.assertEqual(sample['cameras']['nord']['resolution'], [960, 440])
        self.assertIsNotNone(sample['process']['rss_bytes']); self.assertIn('lanes', sample)
        self.client.put(f'{self.base}/diagnostics/notes', json={'weather': 'bedeckt, 6 °C', 'camera_distances': 'Kamera Nord 48 m'})
        self.stop_capture()
        journal = self.journal()
        name = self.client.post(f'{self.base}/diagnostics/report').json()['report']
        response = self.client.get(f'{self.base}/diagnostics/report')
        self.assertEqual(response.status_code, 200); self.assertIn(name, response.headers['content-disposition'])
        report = response.text
        for section in range(1, 18):
            self.assertIn(f'## {section}. ', report)
        self.assertIn('keine physische Ende-zu-Ende-Latenz', report)
        self.assertRegex(report, r'\| nord \| \d+ % der Messungen \| [1-9]')  # the failure appears as a drop
        self.assertIn('| 2 | nord | nicht kalibriert', report); self.assertIn('Kamerabahn ohne Kalibrierung: Bahn 2, 3', report)
        self.assertIn('bedeckt, 6 °C', report); self.assertIn('Bahn belegt | 1', report)
        self.assertNotIn('bestanden |', report)
        measurements = self.client.get(f'{self.base}/diagnostics/measurements.json')
        self.assertEqual(len(measurements.json()['samples']), stopped)
        for text in (report, measurements.text, json.dumps(status), self.client.get(f'{self.base}/field-protocol.pdf').content.decode('latin-1')):
            self.assertNotIn('geheim', text); self.assertNotIn('token=abc', text)
        self.assertEqual(self.journal(), journal, 'report generation changed the journal')

    def test_report_without_diagnostics_names_unmeasured_values(self):
        self.client.post(f'{self.base}/diagnostics/report')
        report = self.client.get(f'{self.base}/diagnostics/report').text
        self.assertIn('Für diese Sitzung wurde keine Testdiagnose gestartet.', report)
        self.assertIn('Keine Testdiagnose aufgezeichnet; Systemangaben nicht gemessen.', report)
        self.assertIn('| CPU BTV-Prozess (% eines Kerns, inkl. RTSP-Dekodierung) | nicht gemessen |', report)
        self.assertEqual(self.client.get('/api/sessions/00000000-0000-4000-8000-000000000000/diagnostics/report').status_code, 404)
        self.assertEqual(self.client.get('/api/sessions/..%2F..%2Fetc/diagnostics').status_code, 404)

    def test_restart_resumes_and_session_change_closes_diagnostics(self):
        self.client.post(f'{self.base}/diagnostics/start'); self.wait_samples(2)
        self.client.__exit__(None, None, None)
        self.open()  # BTV restart while the diagnosis runs
        status = self.client.get(f'{self.base}/diagnostics').json()
        self.assertTrue(status['running']); self.assertEqual(len(status['runs'][-1]['resumed']), 1)
        before = status['samples']; self.wait_samples(before + 2)
        old = self.session
        response = self.client.post('/api/sessions/start', json={'session_id': '5f0c3a1e-7c1b-4d43-9a76-1a2b3c4d5e6f',
                                                                  'expected_session_id': old, 'name': 'Nachmittag'})
        self.assertEqual(response.status_code, 200)
        closed = self.client.get(f'/api/sessions/{old}/diagnostics').json()
        self.assertFalse(closed['active']); self.assertEqual(closed['runs'][-1]['stop_reason'], 'Sitzung abgeschlossen')
        count = closed['samples']; time.sleep(.3)
        self.assertEqual(self.client.get(f'/api/sessions/{old}/diagnostics').json()['samples'], count)
        new = self.client.get('/api/state').json()['session_id']
        self.assertEqual(self.client.get(f'/api/sessions/{new}/diagnostics').json()['samples'], 0, 'samples moved to the new session')
        # Archived session: no new diagnosis, but a report from its stored data.
        self.assertEqual(self.client.post(f'/api/sessions/{old}/diagnostics/start').status_code, 409)
        journal = self.journal(old)  # archived journal: no new events can arrive
        self.assertEqual(self.client.post(f'/api/sessions/{old}/diagnostics/report').status_code, 200)
        report = self.client.get(f'/api/sessions/{old}/diagnostics/report').text
        self.assertIn('| Grund |', report); self.assertIn('Sitzung abgeschlossen', report); self.assertIn('1 Neustarts während der Diagnose', report)
        self.assertEqual(self.journal(old), journal)

    def test_write_error_stops_only_the_diagnostics(self):
        # A real write error on the sample file only (a directory in its place).
        (self.path / 'sessions' / self.session / 'diagnostics' / 'samples.jsonl').mkdir(parents=True)
        self.client.post(f'{self.base}/diagnostics/start')
        deadline = time.monotonic() + 5
        while not self.client.get(f'{self.base}/diagnostics').json()['error']:
            self.assertLess(time.monotonic(), deadline); time.sleep(.05)
        status = self.client.get(f'{self.base}/diagnostics').json()
        self.assertFalse(status['running']); self.assertFalse(status['active']); self.assertIn('Testdiagnose angehalten', status['error'])
        response = self.client.post('/api/lanes/1/occupy', headers={'X-Session-ID': self.session}, json={'lane_id': 1, 'expected_revision': 0})
        self.assertEqual(response.status_code, 200, 'tablet operation blocked by a diagnostics error')
        self.assertEqual(self.client.get('/api/health').json()['status'], 'ok')

    def test_recordings_are_listed_read_only_and_missing_directories_are_named(self):
        recordings = self.path / 'mediamtx'; (recordings / 'kamera-nord').mkdir(parents=True)
        segment = recordings / 'kamera-nord' / '2026-10-21_15-00-00-000000.mp4'; segment.write_bytes(b'x' * 2048)
        self.client.put(f'{self.base}/diagnostics/notes', json={'recordings_dir': str(recordings)})
        self.client.post(f'{self.base}/diagnostics/report')
        report = self.client.get(f'{self.base}/diagnostics/report').text
        self.assertIn('| nord | kamera-nord | 1 | 2.0 KiB |', report); self.assertIn(str(segment), report)
        self.assertEqual(segment.read_bytes(), b'x' * 2048)
        self.client.put(f'{self.base}/diagnostics/notes', json={'recordings_dir': str(self.path / 'fehlt')})
        self.client.post(f'{self.base}/diagnostics/report')
        self.assertIn('Verzeichnis nicht vorhanden oder nicht lesbar', self.client.get(f'{self.base}/diagnostics/report').text)

    def test_field_protocol_pdf_structure_and_prefill(self):
        self.stop_capture()
        journal = self.journal()
        response = self.client.get(f'{self.base}/field-protocol.pdf')
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        pdf = response.content
        self.assertTrue(pdf.startswith(b'%PDF-1.4')); self.assertTrue(pdf.rstrip().endswith(b'%%EOF'))
        # Overview, one sheet per camera, weather, two reference pages, operation.
        self.assertIn(b'/Count 7', pdf)
        offset = int(re.search(rb'startxref\n(\d+)', pdf).group(1))
        self.assertTrue(pdf[offset:].startswith(b'xref'))
        for number, position in enumerate(re.findall(rb'(\d{10}) 00000 n', pdf), start=1):
            self.assertTrue(pdf[int(position):].startswith(b'%d 0 obj' % number))
        text = pdf.decode('cp1252')
        for value in (self.session, 'Kamera Nord', 'Kamera S\xfcd', '1, 2', '960\xd7440', 'Referenzbeobachtungen', 'Wetter und Licht',
                      'Bedienung mit Handschuhen', 'gültig'):
            self.assertIn(value, text)
        self.assertNotIn('geheim', text)
        self.assertEqual(self.journal(), journal)

    def test_field_protocol_without_cameras_has_an_empty_camera_sheet(self):
        self.client.__exit__(None, None, None)
        save_settings(self.path, Settings())
        self.open()
        pdf = self.client.get(f'{self.base}/field-protocol.pdf').content
        self.assertIn(b'/Count 6', pdf); self.assertIn(b'Keine Kamera konfiguriert', pdf)
        self.client.post(f'{self.base}/diagnostics/report')
        self.assertIn('Keine Kamera konfiguriert.', self.client.get(f'{self.base}/diagnostics/report').text)

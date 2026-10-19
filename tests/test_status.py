"""CLI status: real server with several cameras, faults, stopped service and file fallback."""

import contextlib
import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

import uvicorn

from biathlon_target_vision import status as cli
from biathlon_target_vision.app import create_app
from biathlon_target_vision.calibration import CalibrationStore, calibrate
from biathlon_target_vision.cameras import camera_binding
from biathlon_target_vision.config import CameraSettings, Settings, save_settings
from tests.synthetic import scene


class Cameras:
    """Camera "sued" is offline; frames are not needed for the status."""
    def __init__(self, cameras): pass
    def configure(self, cameras): pass
    def close(self): pass
    def snapshot(self, camera_id):
        return {'connected': camera_id != 'sued', 'frame': None, 'frame_number': 0, 'captured_at': None, 'stream_epoch': 0}


def free_port():
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        return reservation.getsockname()[1]


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.data = Path(self.temporary.name); self.port = free_port()
        nord = CameraSettings(id='nord', name='Kamera Nord', url='rtsp://admin:geheim@10.0.0.5/a', lane_ids=[1, 2])
        sued = CameraSettings(id='sued', name='Kamera Süd', url='rtsp://10.0.0.6/b', lane_ids=[3])
        save_settings(self.data, Settings(host='0.0.0.0', port=self.port, cameras=[nord, sued]))
        image, quad, _, _ = scene(); calibrations = CalibrationStore(self.data)
        valid = calibrate(image, quad); valid.update(camera_binding(nord)); calibrations.save(1, valid)
        stale = calibrate(image, quad); stale.update(camera_binding(sued), camera_url_hash='other'); calibrations.save(3, stale)
        self.server = None
        # Cameras are created on server start, so the replacement stays active.
        self.cameras = patch('biathlon_target_vision.app.CameraManager', Cameras); self.cameras.start()

    def tearDown(self):
        if self.server:
            self.server.should_exit = True; self.thread.join(timeout=10)
        self.cameras.stop(); self.temporary.cleanup()

    def start(self, host='127.0.0.1'):
        self.app = create_app(self.data, 6)
        self.server = uvicorn.Server(uvicorn.Config(self.app, host=host, port=self.port, log_level='warning'))
        self.thread = threading.Thread(target=self.server.run, daemon=True); self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            self.assertLess(time.monotonic(), deadline); time.sleep(.05)

    def run_status(self, service='active', addresses=(('192.168.1.10', 'eth0'), ('10.8.0.2', 'wg0')), **kwargs):
        output = io.StringIO()
        with patch.object(cli, 'service_state', return_value=service), patch.object(cli, 'lan_addresses', return_value=list(addresses)), \
                contextlib.redirect_stdout(output):
            code = cli.status(kwargs.get('directory', self.data), kwargs.get('host'), kwargs.get('port'))
        return code, output.getvalue()

    def test_reachable_api_with_several_cameras(self):
        self.start()
        base = f'http://127.0.0.1:{self.port}'
        with urlopen(base + '/api/state') as response:
            session_id = json.load(response)['session_id']
        request = Request(base + '/api/sessions/start', method='POST', headers={'Content-Type': 'application/json'},
                          data=json.dumps({'session_id': '5f0c3a1e-7c1b-4d43-9a76-1a2b3c4d5e6f', 'expected_session_id': session_id,
                                           'name': 'Arber Test'}).encode())
        with urlopen(request) as response:
            self.assertEqual(response.status, 200)
        code, text = self.run_status()
        self.assertEqual(code, 0, text)
        base = f'http://192.168.1.10:{self.port}'
        for line in (f'{base}/', f'{base}/monitor', f'{base}/admin', f'{base}/calibration', f'{base}/api/state', f'{base}/docs',
                     f'ws://192.168.1.10:{self.port}/ws', '10.8.0.2 (wg0)', f'0.0.0.0:{self.port}', 'Schießbahnen           6',
                     '2 konfiguriert, 1 verbunden', 'Kamera Nord (nord) · Bahnen 1, 2 · verbunden', 'Kamera Süd (sued) · Bahnen 3 · getrennt',
                     '1 von 3 Bahnen mit Kamera kalibriert, 1 ungültig', 'Arber Test (ID 5f0c3a1e-7c1b-4d43-9a76-1a2b3c4d5e6f)', 'Archivierte Sitzungen  1',
                     'erreichbar, Zustand ok', 'Exitcode 0'):
            self.assertIn(line, text)
        for secret in ('geheim', 'admin:', '10.0.0.5', 'rtsp://'):
            self.assertNotIn(secret, text)

    def test_reported_fault_and_stopped_service_have_own_exit_codes(self):
        self.start()
        self.app.state.store.failed = True
        code, text = self.run_status()
        self.assertEqual(code, 2, text); self.assertIn('Störung gemeldet (error)', text)
        self.app.state.store.failed = False
        code, text = self.run_status(service='failed')
        self.assertEqual(code, 1, text); self.assertIn('fehlgeschlagen', text)
        # A local start without installed unit is not a service failure.
        self.assertEqual(self.run_status(service='not-found')[0], 0)
        self.assertEqual(self.run_status(service=None)[0], 0)

    def test_unreachable_api_uses_readable_data_directory(self):
        code, text = self.run_status(service='inactive')
        self.assertEqual(code, 1)
        for line in ('API                    nicht erreichbar', 'Schießstand (aus Datenverzeichnis)', '2 konfiguriert, Verbindung unbekannt',
                     '2 Kalibrierungsdateien (Gültigkeit unbekannt)', 'laut Konfiguration, API derzeit nicht erreichbar', 'gestoppt'):
            self.assertIn(line, text)
        self.assertNotIn('geheim', text)
        # Lane count and session come from the journal of a former run.
        self.start(); self.server.should_exit = True; self.thread.join(timeout=10); self.server = None
        code, text = self.run_status(service='inactive')
        self.assertIn('Schießbahnen           6', text); self.assertIn('Erste Sitzung (ID', text)

    def test_unreadable_configuration_never_invents_addresses(self):
        with tempfile.TemporaryDirectory() as empty:
            missing = Path(empty) / 'missing'
            code, text = self.run_status(service='active', directory=missing)
            self.assertEqual(code, 1)
            self.assertIn('Adressen: unbekannt', text); self.assertIn('(nicht lesbar)', text); self.assertIn('Keine Angaben', text)
            self.assertNotIn('http://', text)
            # Unknown binding: only addresses that actually answer are listed.
            self.start()
            code, text = self.run_status(directory=missing, addresses=(('127.0.0.1', 'lo'), ('127.0.0.2', 'test')), port=self.port)
            self.assertEqual(code, 0, text)
            self.assertIn(f'http://127.0.0.1:{self.port}/admin', text); self.assertNotIn('127.0.0.2', text)

    def test_loopback_binding_is_marked_local(self):
        save_settings(self.data, Settings(host='127.0.0.1', port=self.port))
        self.start()
        code, text = self.run_status()
        self.assertEqual(code, 0, text)
        self.assertIn('nur auf diesem Rechner erreichbar', text); self.assertIn(f'http://127.0.0.1:{self.port}/', text)
        self.assertNotIn('192.168.1.10', text)

    def test_service_state_parses_systemd(self):
        def run(output):
            return patch.object(cli.subprocess, 'run', return_value=type('Result', (), {'stdout': output})())
        with run('LoadState=loaded\nActiveState=active\n'):
            self.assertEqual(cli.service_state(), 'active')
        with run('LoadState=not-found\nActiveState=inactive\n'):
            self.assertEqual(cli.service_state(), 'not-found')
        with patch.object(cli.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertIsNone(cli.service_state())

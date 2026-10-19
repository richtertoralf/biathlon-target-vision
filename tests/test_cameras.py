"""Mehrere Kameras, persistente Zuordnung, Geheimnisschutz und echter RTSP-Eingang."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import cv2
from fastapi.testclient import TestClient

from biathlon_target_vision.app import create_app
from biathlon_target_vision.config import CameraSettings, Settings, load_settings, save_settings
from biathlon_target_vision.cameras import CameraManager, camera_binding
from tests.synthetic import scene
from tests.rtsp_support import available, rtsp_stream


class FakeCameras:
    def __init__(self, cameras): self.configure(cameras)
    def configure(self, cameras): self.cameras = cameras
    def close(self): pass
    def snapshot(self, camera_id):
        return {'connected':True,'frame':scene()[0], 'frame_number':1, 'captured_at':datetime.now(timezone.utc)}


class CameraApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.path = Path(self.directory.name)
        self.mock = patch('biathlon_target_vision.app.CameraManager', FakeCameras); self.mock.start()
        self.client = TestClient(create_app(self.path, 3)); self.client.__enter__()
        self.client.headers["X-Session-ID"] = self.client.get("/api/state").json()["session_id"]
    def tearDown(self):
        self.client.__exit__(None,None,None); self.mock.stop(); self.directory.cleanup()
    def camera(self, **changes):
        return dict(id='cam-1',name='Bahnen 1–2',url='rtsp://user:secret@127.0.0.1/test',lane_ids=[1,2],**changes)
    def test_crud_persistence_preview_and_credentials(self):
        response=self.client.post('/api/cameras',json=self.camera())
        self.assertEqual(response.status_code,200,response.text); self.assertNotIn('secret',response.text)
        self.assertNotIn('url',response.json()['cameras'][0])
        self.assertEqual(self.client.get('/api/cameras/cam-1/frame').headers['content-type'],'image/jpeg')
        self.assertEqual(self.client.get('/admin').status_code,200)
        self.assertEqual(load_settings(self.path).cameras[0].url,self.camera()['url'])
        edited=self.camera(); edited.update(url='',name='Neu',lane_ids=[3])
        self.assertEqual(self.client.put('/api/cameras/cam-1',json=edited).status_code,200)
        self.assertEqual(load_settings(self.path).cameras[0].url,self.camera()['url'])
        self.client.__exit__(None,None,None); self.client=TestClient(create_app(self.path)); self.client.__enter__()
        self.client.headers["X-Session-ID"] = self.client.get("/api/state").json()["session_id"]
        self.assertEqual(self.client.get('/api/cameras').json()['cameras'][0]['lane_ids'],[3])
        self.assertEqual(self.client.delete('/api/cameras/cam-1').status_code,200)
        self.assertEqual(self.client.get('/api/cameras').json()['cameras'],[])
        self.assertEqual(self.client.get('/api/cameras/cam-1/frame').status_code,404)
    def test_administration_address_hides_credentials_and_stays_out_of_state(self):
        raw=self.camera();raw['url']='rtsp://user:p%40ss@word@10.0.0.5:554/Streaming/101?user=x&password=secret'
        for response in (self.client.post('/api/cameras',json=raw),self.client.get('/api/cameras')):
            self.assertNotIn('secret',response.text);self.assertNotIn('word',response.text)
            self.assertEqual(response.json()['cameras'][0]['address'],'rtsp://***@10.0.0.5:554/Streaming/101?…')
        raw['url']='rtsp://[fe80::1]:8554/cam';self.assertEqual(self.client.put('/api/cameras/cam-1',json=raw).status_code,200)
        self.assertEqual(self.client.get('/api/cameras').json()['cameras'][0]['address'],'rtsp://[fe80::1]:8554/cam')
        # The shared state for tablets and external clients keeps its previous fields.
        self.assertNotIn('address',self.client.get('/api/state').json()['capture']['cameras'][0])
    def test_invalid_or_conflicting_config_never_echoes_credentials(self):
        self.client.post('/api/cameras',json=self.camera())
        for changes in ({'id':'cam-2'}, {'id':'cam-2','lane_ids':[4]}, {'id':'cam-2','lane_ids':[3],'url':'http://user:secret@localhost/test'}, {'id':'cam-2','lane_ids':[True]}):
            raw=self.camera();raw.update(changes)
            response=self.client.post('/api/cameras',json=raw)
            self.assertEqual(response.status_code,422,response.text);self.assertNotIn('secret',response.text)
        self.assertEqual(len(load_settings(self.path).cameras),1)
    def test_calibration_reuses_detector_and_binds_to_camera(self):
        self.client.post('/api/cameras',json=self.camera())
        image,quad,_,_=scene();_,encoded=cv2.imencode('.png',image)
        response=self.client.post('/api/lanes/1/calibration',files={'image':('frame.png',encoded.tobytes())},data={'quad':json.dumps(quad)})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(response.json()['calibration']['targets']),5)
        self.assertTrue(self.client.get('/api/lanes/1/calibration').json()['valid_for_camera'])
        changed=self.camera();changed['url']='rtsp://localhost/new'
        self.client.put('/api/cameras/cam-1',json=changed)
        self.assertFalse(self.client.get('/api/lanes/1/calibration').json()['valid_for_camera'])
    def test_invalid_saved_configuration_has_no_password_in_error(self):
        (self.path/'config.json').write_text(json.dumps({'cameras':[{'id':'bad','name':'bad','url':'http://secret@host'}]}))
        with self.assertRaises(ValueError) as failure: load_settings(self.path)
        self.assertNotIn('secret',str(failure.exception))


class CameraRuntimeTests(unittest.TestCase):
    def test_one_reader_for_multiple_lanes_and_no_restart_for_metadata(self):
        camera=CameraSettings(id='one',name='one',url='rtsp://localhost/one',lane_ids=[1,2,3])
        with patch('biathlon_target_vision.cameras.CameraReader') as reader:
            reader.return_value.camera = camera
            manager=CameraManager([camera]); first=manager.readers['one']
            manager.configure([camera.model_copy(update={'name':'new','lane_ids':[2]})])
            self.assertIs(manager.readers['one'],first);self.assertEqual(reader.call_count,1)
            manager.configure([]);first.close.assert_called_once()

    def test_native_decoder_errors_do_not_log_credentials(self):
        program = "from biathlon_target_vision.cameras import CameraReader; from biathlon_target_vision.config import CameraSettings; import time; r=CameraReader(CameraSettings(id='test',name='test',url='rtsp://user:UNIQUE_SECRET@127.0.0.1:1/test')); time.sleep(.2); r.close()"
        result = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('UNIQUE_SECRET', result.stderr)
        self.assertNotIn('rtsp://', result.stderr)

    @unittest.skipUnless(available(), 'MediaMTX und FFmpeg optional für lokalen RTSP-Test')
    def test_local_rtsp_disconnect_and_second_camera_independence(self):
        with rtsp_stream(scene(mask=10)[0]) as (url,publisher):
            camera=CameraSettings(id='live',name='live',url=url,lane_ids=[1,2])
            absent=CameraSettings(id='absent',name='absent',url='rtsp://127.0.0.1:1/missing',lane_ids=[3])
            manager=CameraManager([camera,absent])
            try:
                deadline=time.monotonic()+15
                while time.monotonic()<deadline and not manager.snapshot('live')['connected']: time.sleep(.1)
                snapshot=manager.snapshot('live'); self.assertTrue(snapshot['connected'])
                self.assertEqual(snapshot['frame'].shape[:2],(440,960));self.assertFalse(manager.snapshot('absent')['connected'])
                epoch=snapshot['stream_epoch']
                before=snapshot['frame_number'];time.sleep(.4)
                self.assertGreater(manager.snapshot('live')['frame_number'],before)
                publisher.terminate();publisher.wait(timeout=5)
                deadline=time.monotonic()+7
                while time.monotonic()<deadline and manager.snapshot('live')['connected']:time.sleep(.1)
                self.assertIsNone(manager.snapshot('live')['frame'])
                replacement = subprocess.Popen(publisher.args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    deadline=time.monotonic()+10
                    while time.monotonic()<deadline and not manager.snapshot('live')['connected']:time.sleep(.1)
                    self.assertTrue(manager.snapshot('live')['connected'])
                    self.assertGreater(manager.snapshot('live')['stream_epoch'],epoch)
                finally:
                    replacement.terminate(); replacement.wait(timeout=5)
            finally: manager.close()

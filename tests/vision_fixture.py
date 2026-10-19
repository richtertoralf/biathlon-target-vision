"""Synthetische laufende Kamerabilder durch echte API bis zu den Browsern prüfen."""

from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys
import tempfile
from time import monotonic
from unittest.mock import patch

import uvicorn

from biathlon_target_vision.app import create_app
from biathlon_target_vision.calibration import CalibrationStore, calibrate
from biathlon_target_vision.cameras import camera_binding
from biathlon_target_vision.config import CameraSettings, Settings, save_settings
from tests.synthetic import scene


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='btv-vision-browser-') as temporary:
        directory=Path(temporary); control=directory/'frames.json';control.write_text('{}')
        cameras=[] if '--manual-only' in sys.argv else [CameraSettings(id=f'camera{n}',name=f'Kamera {n}',url=f'rtsp://synthetic/{n}',lane_ids=[n]) for n in (1,2)]
        save_settings(directory,Settings(cameras=cameras));calibrations=CalibrationStore(directory)
        for camera in cameras:
            image,quad,_,_=scene();calibration=calibrate(image,quad);calibration.update(camera_binding(camera));calibrations.save(camera.lane_ids[0],calibration)
        class SyntheticCameras:
            def __init__(self,cameras):self.frames={}
            def configure(self,cameras):pass
            def close(self):pass
            def snapshot(self,camera_id):
                controls=json.loads(control.read_text()).get(camera_id,{})
                number=int(monotonic()*10)
                key=(number,controls)
                previous=self.frames.get(camera_id)
                # Match the real decoder: metadata reads reuse the latest frame
                # instead of generating another image for every access.
                if previous and previous[0]==key:
                    return previous[1]
                connected=controls.get('connected',True)
                image=scene(mask=controls.get('mask',0),missing=controls.get('missing'),noise=controls.get('noise',0),brightness=controls.get('brightness',1))[0] if connected else None
                capture={'frame':image,'frame_number':number,'captured_at':datetime.now(timezone.utc),'connected':connected}
                self.frames[camera_id]=(key,capture)
                return capture
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
        with patch('biathlon_target_vision.app.CameraManager',SyntheticCameras):
            print(json.dumps({'url':f'http://127.0.0.1:{port}','control':str(control)}),flush=True)
            uvicorn.run(create_app(directory,3 if '--three-lanes' in sys.argv else 2),host='127.0.0.1',port=port,log_level='warning')

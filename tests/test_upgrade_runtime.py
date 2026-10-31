"""Echte Serverstarts bei Upgrade/Rollback, isolierte Daten und ersetztes systemd."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from biathlon_target_vision import __version__
from biathlon_target_vision import deployment
from biathlon_target_vision.calibration import CalibrationStore, calibrate
from biathlon_target_vision.config import Settings, save_settings
from tests.synthetic import scene


class UpgradeRuntimeTests(unittest.TestCase):
    def test_real_start_upgrade_and_failed_start_rollback_preserve_data(self):
        with tempfile.TemporaryDirectory(prefix='btv-upgrade-test-') as temporary:
            root=Path(temporary);data=root/'data';data.mkdir()
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
            save_settings(data,Settings(port=port))
            image,quad,_,_=scene();CalibrationStore(data).save(1,calibrate(image,quad))
            repository=Path(__file__).resolve().parents[1]
            good='import sys; sys.path.insert(0, '+repr(str(repository))+'); from biathlon_target_vision.__main__ import main; main()\n'
            for name in ('old','new','broken'):
                release=root/name;release.mkdir()
                (release/'start.py').write_text('raise RuntimeError("intentional failed start")\n' if name=='broken' else good)
            (root/'current').symlink_to(root/'old')
            process=None
            with (root/'server.log').open('w') as log:
                def service(*args, **kwargs):
                    nonlocal process
                    self.assertEqual(args[0],'systemctl')
                    if args[1]=='stop' and process is not None:
                        process.terminate();process.wait(timeout=15);process=None
                    if args[1]=='start':
                        process=subprocess.Popen([sys.executable,str((root/'current'/'start.py').resolve()),'--data-dir',str(data),'--lanes','2'],stdout=log,stderr=log)
                def ready():
                    deadline=time.monotonic()+10
                    while time.monotonic()<deadline:
                        if deployment.reachable(data,__version__):return
                        time.sleep(.05)
                    self.fail('isolierter Server nicht erreichbar')
                def state():
                    with urlopen(f'http://127.0.0.1:{port}/api/state',timeout=2) as response:return json.load(response)
                try:
                    service('systemctl','start',deployment.SERVICE);ready()
                    request=Request(f'http://127.0.0.1:{port}/api/observations',data=json.dumps({'lane_id':1,'kind':'target','source':'upgrade-test','target_id':5,'state':'fallen','baseline':True,'observed_at':'2026-10-17T12:00:00Z'}).encode(),headers={'Content-Type':'application/json','X-Session-ID':state()['session_id']},method='POST')
                    with urlopen(request,timeout=2) as response:self.assertEqual(response.status,200)
                    request=Request(f'http://127.0.0.1:{port}/api/sessions/start',data=json.dumps({'session_id':'ba389980-936b-490a-a875-998128bd178a','expected_session_id':state()['session_id'],'name':'Upgrade-Test'}).encode(),headers={'Content-Type':'application/json'},method='POST')
                    with urlopen(request,timeout=2) as response:self.assertEqual(response.status,200)
                    before=state();self.assertEqual(before['session']['name'],'Upgrade-Test');files={path.relative_to(data):path.read_bytes() for path in data.rglob('*') if path.is_file()}
                    with patch.object(deployment,'run',side_effect=service),patch.object(deployment,'service_state',return_value=('active','enabled')):deployment.activate(root,data,root/'new',__version__)
                    after=state();self.assertNotEqual(before.pop('instance_id'),after.pop('instance_id'));self.assertEqual(before,after)
                    self.assertEqual((root/'current').resolve(),root/'new')
                    original_sleep=time.sleep
                    with patch.object(deployment,'run',side_effect=service),patch.object(deployment,'service_state',return_value=('active','enabled')),patch.object(deployment.time,'sleep',side_effect=lambda _:original_sleep(.05)):
                        with self.assertRaisesRegex(RuntimeError,'nicht erreichbar'):deployment.activate(root,data,root/'broken',__version__)
                    ready();restored=state();restored.pop('instance_id');self.assertEqual(restored,before)
                    self.assertEqual((root/'current').resolve(),root/'new')
                    self.assertEqual({path.relative_to(data):path.read_bytes() for path in data.rglob('*') if path.is_file()},files)
                    self.assertEqual(len(list((root/'backups').iterdir())),2)
                finally:service('systemctl','stop',deployment.SERVICE)

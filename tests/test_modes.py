"""Reguläre manuelle Erfassung, Zielpriorität und kompatibles Journal-Replay."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from biathlon_target_vision.app import create_app
from biathlon_target_vision.core import Conflict, EventStore
from biathlon_target_vision.models import (Assignment, Observation, Release, ModeChange,
                                          ManualTarget, OverrideRelease, ManualReset)


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.store = EventStore(self.directory, 3)
        self.at = datetime(2026, 10, 18, tzinfo=timezone.utc)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def lane(self, lane=1):
        return self.store.snapshot()['lanes'][str(lane)]

    def control(self, model, lane=1, **values):
        return self.store.apply(model(lane_id=lane,
            expected_control_revision=self.lane(lane)['control_revision'], **values))

    def observe(self, target=1, value='standing', lane=1, **values):
        self.at += timedelta(seconds=1)
        return self.store.apply(Observation(lane_id=lane, source='camera:test', kind='target',
            target_id=target, state=value, observed_at=self.at, **values))

    def assign(self, bib=42, lane=1):
        return self.store.apply(Assignment(lane_id=lane, bib=bib,
            expected_revision=self.lane(lane)['revision']))

    def test_manual_without_camera_full_bouts_and_replay(self):
        self.control(ModeChange, mode='manual')
        self.control(ManualReset)
        self.assign()
        first = self.lane()['current_bout_id']
        for target in (1, 3, 5):
            self.control(ManualTarget, target_id=target, state='fallen')
        self.assertEqual(self.lane()['targets'], ['fallen','standing','fallen','standing','fallen'])
        self.assertEqual(self.store.state['bouts'][first]['fallen_target_ids'], [])
        self.assertEqual(self.lane()['automatic_targets'], ['unknown']*5)
        self.control(ManualReset)
        self.assertTrue(self.store.state['bouts'][first]['closed'])
        self.assertEqual(self.lane()['occupied_bout_id'], first)
        self.store.apply(Release(lane_id=1, bout_id=first, expected_revision=self.lane()['revision']))
        self.assign(43)
        self.control(ManualTarget, target_id=2, state='fallen')
        self.assertNotEqual(first, self.lane()['current_bout_id'])
        self.assertEqual(self.lane()['targets'], ['standing','fallen','standing','standing','standing'])
        before = self.store.snapshot()
        self.store.close(); self.store = EventStore(self.directory)
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual({event['command']['kind'] for event in self.store.events},
                         {'mode','manual_reset','assign','manual_target','release'})

    def test_mixed_priority_underlying_observations_and_other_targets(self):
        self.control(ModeChange, mode='mixed'); self.assign()
        for target in range(1, 6): self.observe(target)
        self.observe(1, 'fallen'); self.observe(4, 'fallen')
        before_count = list(self.store.state['bouts'][self.lane()['current_bout_id']]['fallen_target_ids'])
        correction = self.control(ManualTarget, target_id=3, state='fallen')
        self.assertEqual(correction['manual_input']['automatic_state'], 'standing')
        self.assertEqual(correction['manual_input']['manual_state'], 'fallen')
        self.assertEqual(correction['manual_input']['mode'], 'mixed')
        for _ in range(4): self.observe(3, 'standing')
        self.observe(5, 'fallen')
        self.assertEqual(self.lane()['targets'], ['fallen','standing','fallen','fallen','fallen'])
        self.assertEqual(self.lane()['automatic_targets'], ['fallen','standing','standing','fallen','fallen'])
        self.assertEqual(before_count, [1,4])
        self.assertEqual(self.store.state['bouts'][self.lane()['current_bout_id']]['fallen_target_ids'], [1,4,5])
        self.control(OverrideRelease, target_id=3)
        self.assertEqual(self.lane()['targets'][2], 'standing')
        self.assertIsNone(self.lane()['manual_targets'][2])

    def test_override_survives_restart_and_duplicate_is_idempotent(self):
        self.control(ModeChange, mode='mixed'); self.assign(); self.observe(3)
        command = ManualTarget(event_id='correction', lane_id=1, target_id=3, state='fallen',
                               expected_control_revision=self.lane()['control_revision'])
        event = self.store.apply(command)
        self.observe(3)
        before = self.store.snapshot()
        self.store.close(); self.store = EventStore(self.directory)
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(self.store.apply(command), event)
        self.observe(3)
        self.assertEqual(self.lane()['targets'][2], 'fallen')
        self.assertEqual(self.lane()['automatic_targets'][2], 'standing')

    def test_outage_manual_continuation_and_return_baseline_preserve_bout(self):
        self.assign(); bout = self.lane()['current_bout_id']
        for target in range(1, 6): self.observe(target)
        self.observe(1,'fallen'); self.observe(1,'unknown',baseline=True)
        self.control(ModeChange, mode='manual')
        self.control(ManualTarget, target_id=1,state='fallen')
        self.control(ManualTarget, target_id=3,state='fallen')
        # Kamera kann während des Ersatzbetriebs zurückkehren und zurückstellen.
        self.observe(1,'standing'); self.observe(4,'fallen')
        self.assertEqual(self.lane()['current_bout_id'], bout)
        self.assertEqual(self.lane()['targets'][2], 'fallen')
        self.control(ModeChange, mode='mixed')
        self.observe(3,'unknown'); event = self.observe(3,'fallen')
        self.assertTrue(event['effective_baseline'])
        self.assertEqual(self.store.state['bouts'][bout]['fallen_target_ids'],[1])
        self.assertEqual(self.lane()['targets'][2], 'fallen')
        self.control(OverrideRelease,target_id=3)
        self.assertEqual(self.lane()['targets'][2], 'fallen')
        self.assertEqual(self.lane()['occupied_bout_id'],bout)
        self.assertEqual(self.store.state['bouts'][bout]['bib'],42)
        self.assertEqual(self.lane(2)['targets'],['unknown']*5)

    def test_automatic_mode_preserves_manual_values_until_explicit_release(self):
        self.control(ModeChange,mode='manual'); self.assign()
        self.control(ManualTarget,target_id=3,state='fallen')
        self.control(ModeChange,mode='automatic'); self.observe(3,'standing')
        self.assertEqual(self.lane()['targets'][2],'fallen')
        self.control(ManualTarget,target_id=3,state='standing')
        self.assertEqual(self.lane()['targets'][2],'standing')
        self.control(OverrideRelease,target_id=3)
        self.assertEqual(self.lane()['targets'][2],'standing')

    def test_reset_and_explicit_new_bout_end_old_overrides(self):
        self.control(ModeChange,mode='mixed');self.assign()
        for target in range(1,6):self.observe(target,'standing')
        self.observe(1,'fallen');self.control(ManualTarget,target_id=3,state='fallen')
        self.observe(1,'standing')
        self.assertEqual(self.lane()['manual_targets'],[None]*5)
        self.control(ManualTarget,target_id=4,state='standing')
        self.control(ManualReset)
        self.assertEqual(self.lane()['targets'],['standing']*5)
        self.assertEqual(self.lane()['manual_targets'],[None]*5)
        self.observe(4,'fallen')
        self.assertIsNone(self.lane()['current_bout_id'])
        self.assertEqual(self.store.events[-1]['effective_baseline'],True)
        old = self.lane()['occupied_bout_id']
        self.store.apply(Release(lane_id=1,bout_id=old,expected_revision=self.lane()['revision']))
        self.assign(43)
        self.assertEqual(self.lane()['manual_targets'],[None]*5)

    def test_pending_control_ignores_frames_but_rejects_other_operator(self):
        self.control(ModeChange,mode='mixed'); self.assign()
        command = ManualTarget(lane_id=1,target_id=2,state='fallen',
                              expected_control_revision=self.lane()['control_revision'])
        self.observe(3,'standing'); self.observe(4,'standing')
        self.store.apply(command)
        with self.assertRaises(Conflict): self.store.apply(command.model_copy(update={'event_id':'other'}))

    def test_automatic_reset_does_not_close_manual_bout(self):
        self.control(ModeChange,mode='manual'); self.assign()
        self.control(ManualTarget,target_id=2,state='fallen'); bout=self.lane()['current_bout_id']
        self.observe(1,'fallen');self.observe(1,'standing')
        self.assertEqual(self.lane()['current_bout_id'],bout)
        self.assertEqual(self.lane()['targets'][1],'fallen')
        with self.assertRaises(Conflict): self.control(OverrideRelease,target_id=2)

    def test_manual_standing_correction_is_not_a_reset(self):
        self.control(ModeChange,mode='mixed'); self.assign(); self.observe(1,'fallen')
        bout=self.lane()['current_bout_id']
        self.control(ManualTarget,target_id=1,state='standing')
        self.assertEqual(self.lane()['current_bout_id'],bout)
        self.assertEqual(self.store.state['bouts'][bout]['fallen_target_ids'],[1])
        self.observe(1,'fallen');self.assertEqual(self.lane()['targets'][0],'standing')
        self.control(ManualTarget,target_id=1,state='unknown')
        self.assertEqual(self.lane()['targets'][0],'unknown')

    def test_release_invalidates_pending_target_correction(self):
        self.control(ModeChange,mode='mixed');self.assign()
        lane=self.lane()
        pending=ManualTarget(lane_id=1,target_id=3,state='fallen',
                             expected_control_revision=lane['control_revision'])
        self.store.apply(Release(lane_id=1,bout_id=lane['current_bout_id'],expected_revision=lane['revision']))
        with self.assertRaises(Conflict): self.store.apply(pending)

    def test_actual_v06_journal_remains_readable(self):
        import json
        import os
        import subprocess
        import sys
        legacy=self.directory/'legacy';package=legacy/'biathlon_target_vision';package.mkdir(parents=True)
        for name in ('__init__.py','models.py','core.py'):
            result=subprocess.run(['git','show',f'v0.6.0:biathlon_target_vision/{name}'],check=True,capture_output=True)
            (package/name).write_bytes(result.stdout)
        data=self.directory/'old-data'
        script="""from pathlib import Path
from datetime import datetime, timezone
import sys, json
from biathlon_target_vision.core import EventStore
from biathlon_target_vision.models import Assignment, Observation
s=EventStore(Path(sys.argv[1]),1)
s.apply(Assignment(lane_id=1,bib=71,expected_revision=0))
s.apply(Observation(lane_id=1,kind='target',target_id=4,state='fallen',source='camera:test',observed_at=datetime.now(timezone.utc)))
print(json.dumps(s.snapshot()))
s.close()
"""
        result=subprocess.run([sys.executable,'-c',script,str(data)],cwd=legacy,
                              env={**os.environ,'PYTHONPATH':str(legacy)},check=True,capture_output=True,text=True)
        old=json.loads(result.stdout)
        with_store=EventStore(data)
        try:
            new=with_store.snapshot()
            self.assertEqual(new['bouts'],old['bouts'])
            for key,value in old['lanes']['1'].items():self.assertEqual(new['lanes']['1'][key],value)
            self.assertEqual(new['lanes']['1']['mode'],'automatic')
            with_store.apply(ModeChange(lane_id=1,mode='mixed',expected_control_revision=new['lanes']['1']['control_revision']))
            self.assertEqual(with_store.state['lanes']['1']['targets'][3],'fallen')
        finally:with_store.close()


class ModeApiTests(unittest.TestCase):
    def test_normal_api_two_sockets_control_revision_and_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            app=create_app(Path(temporary),2)
            with TestClient(app) as client:
                client.headers["X-Session-ID"] = client.get("/api/state").json()["session_id"]
                with client.websocket_connect('/ws') as first, client.websocket_connect('/ws') as second:
                    self.assertFalse(first.receive_json()['simulation']);second.receive_json()
                    result=client.put('/api/lanes/1/mode',json={'lane_id':1,'mode':'manual','expected_control_revision':0})
                    self.assertEqual(result.status_code,200)
                    self.assertEqual(first.receive_json()['lanes']['1']['mode'],'manual')
                    self.assertEqual(second.receive_json()['lanes']['1']['mode'],'manual')
                    body={'lane_id':1,'target_id':3,'state':'fallen','expected_control_revision':1,'event_id':'manual'}
                    result=client.post('/api/lanes/1/manual-target',json=body)
                    self.assertEqual(result.status_code,200)
                    expected=result.json()['state']['lanes']['1']
                    for socket in (first,second):
                        self.assertEqual(socket.receive_json()['lanes']['1'],expected)
                    self.assertEqual(client.post('/api/lanes/1/manual-target',json=body).status_code,200)
                    self.assertEqual(client.post('/api/lanes/2/manual-target',json=body).status_code,422)
                    body['event_id']='other'
                    self.assertEqual(client.post('/api/lanes/1/manual-target',json=body).status_code,409)
                    self.assertEqual(client.get('/api/health').status_code,200)
            with TestClient(create_app(Path(temporary))) as client:
                client.headers["X-Session-ID"] = client.get("/api/state").json()["session_id"]
                self.assertEqual(client.get('/api/state').json()['lanes']['1'],expected)
                self.assertEqual(client.get('/api/events').json()['events'][-1]['manual_input']['manual_state'],'fallen')

    def test_correction_image_and_failed_evidence_never_undo_input(self):
        from biathlon_target_vision.calibration import CalibrationStore, calibrate
        from biathlon_target_vision.cameras import camera_binding
        from biathlon_target_vision.config import CameraSettings, Settings, save_settings
        from tests.synthetic import scene
        camera=CameraSettings(id='test',name='Test',url='rtsp://localhost/test',lane_ids=[1])
        image,quad,_,_=scene()
        capture={'frame':image,'connected':True,'captured_at':datetime.now(timezone.utc),'frame_number':1}
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);save_settings(directory,Settings(cameras=[camera]))
            calibration=calibrate(image,quad);calibration.update(camera_binding(camera))
            CalibrationStore(directory).save(1,calibration)
            with patch('biathlon_target_vision.app.CameraManager') as manager:
                manager.return_value.snapshot.return_value=capture
                with TestClient(create_app(directory,1)) as client:
                    client.headers["X-Session-ID"] = client.get("/api/state").json()["session_id"]
                    state=client.get('/api/state').json()['lanes']['1']
                    result=client.post('/api/lanes/1/manual-target',json={'lane_id':1,'target_id':3,'state':'fallen','expected_control_revision':state['control_revision']})
                    self.assertEqual(result.status_code,200)
                    event=result.json()['event'];stem=directory/'sessions'/result.json()['state']['session_id']/'corrections'/str(event['sequence'])
                    self.assertTrue(stem.with_suffix('.jpg').is_file());self.assertTrue(stem.with_suffix('.json').is_file())
                    with patch('biathlon_target_vision.app.cv2.imencode',side_effect=ValueError('encoder failed')):
                        with self.assertLogs(level='ERROR'):
                            result=client.post('/api/lanes/1/manual-target',json={'lane_id':1,'target_id':4,'state':'fallen','expected_control_revision':result.json()['state']['lanes']['1']['control_revision']})
                    self.assertEqual(result.status_code,200)
                    self.assertEqual(result.json()['state']['lanes']['1']['targets'][3],'fallen')


class ModeVisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_modes_shared_camera_outage_and_return(self):
        import numpy as np
        from biathlon_target_vision.calibration import CalibrationStore, calibrate
        from biathlon_target_vision.cameras import camera_binding
        from biathlon_target_vision.config import CameraSettings, Settings
        from biathlon_target_vision.vision import VisionService
        from tests.synthetic import scene
        from tests.test_vision import SequenceCameras
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);store=EventStore(directory,3)
            cameras=SequenceCameras();calibrations=CalibrationStore(directory)
            first=CameraSettings(id='first',name='First',url='rtsp://localhost/one',lane_ids=[1,2])
            second=CameraSettings(id='second',name='Second',url='rtsp://localhost/two',lane_ids=[3])
            settings=Settings(cameras=[first,second])
            base,quad,_,_=scene();double=np.vstack([base,base]);lower=(np.array(quad)+[0,440]).tolist()
            for lane,image,roi,camera in [(1,double,quad,first),(2,double,lower,first),(3,base,quad,second)]:
                calibration=calibrate(image,roi);calibration.update(camera_binding(camera));calibrations.save(lane,calibration)
            service=VisionService(lambda:settings,cameras,calibrations,store,store.apply)
            number=0
            def lane(n):return store.snapshot()['lanes'][str(n)]
            def control(n,model,**fields):
                return store.apply(model(lane_id=n,expected_control_revision=lane(n)['control_revision'],**fields))
            async def frames(mask=0,other=0,connected=True):
                nonlocal number
                for _ in range(3):
                    number+=1
                    cameras.set('first',np.vstack([scene(mask=mask)[0],scene(mask=mask)[0]]) if connected else None,number)
                    cameras.set('second',scene(mask=other)[0],number)
                    with patch('biathlon_target_vision.vision.monotonic',return_value=number*.2):
                        await service.step()
            try:
                control(1,ModeChange,mode='manual');control(2,ModeChange,mode='mixed')
                await frames()
                self.assertEqual(lane(1)['targets'],['unknown']*5)
                self.assertEqual(lane(2)['targets'],['standing']*5)
                await frames(9,4)
                control(1,ManualTarget,target_id=3,state='fallen')
                control(2,ManualTarget,target_id=3,state='fallen')
                bout=lane(2)['current_bout_id'];observed=list(store.state['bouts'][bout]['fallen_target_ids'])
                await frames(25,12)
                self.assertEqual(lane(2)['targets'],['fallen','standing','fallen','fallen','fallen'])
                self.assertEqual(lane(2)['automatic_targets'][2],'standing')
                self.assertEqual(lane(1)['targets'],['unknown','unknown','fallen','unknown','unknown'])
                self.assertEqual(lane(3)['targets'][3],'fallen')
                await frames(connected=False,other=28)
                self.assertEqual(lane(2)['targets'][2],'fallen')
                control(2,ModeChange,mode='manual');control(2,ManualTarget,target_id=5,state='fallen')
                control(2,ModeChange,mode='mixed')
                await frames(9,28)
                self.assertEqual(lane(2)['targets'][4],'fallen')
                self.assertEqual(lane(2)['automatic_targets'][4],'standing')
                self.assertEqual(lane(2)['current_bout_id'],bout)
                self.assertEqual(store.state['bouts'][bout]['fallen_target_ids'],observed+[5])
                control(2,OverrideRelease,target_id=5)
                self.assertEqual(lane(2)['targets'][4],'standing')
                await frames(0,28)
                self.assertEqual(lane(2)['manual_targets'],[None]*5)
                self.assertEqual(lane(2)['targets'],['standing']*5)
                self.assertEqual(lane(1)['targets'][2],'fallen')
            finally:store.close()

    async def test_reset_during_classification_discards_old_result(self):
        import asyncio
        import threading
        from biathlon_target_vision.calibration import CalibrationStore, calibrate
        from biathlon_target_vision.cameras import camera_binding
        from biathlon_target_vision.config import CameraSettings, Settings
        from biathlon_target_vision.vision import VisionService
        from tests.synthetic import scene
        from tests.test_vision import SequenceCameras
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);store=EventStore(directory,1)
            camera=CameraSettings(id='test',name='Test',url='rtsp://localhost/test',lane_ids=[1])
            cameras=SequenceCameras();image,quad,_,_=scene()
            calibration=calibrate(image,quad);calibration.update(camera_binding(camera))
            calibrations=CalibrationStore(directory);calibrations.save(1,calibration)
            cameras.set('test',image,1)
            service=VisionService(lambda:Settings(cameras=[camera]),cameras,calibrations,store,store.apply)
            started=threading.Event();resume=threading.Event()
            def classify(*args):
                started.set();resume.wait(timeout=5);return ['fallen']*5
            try:
                with patch('biathlon_target_vision.vision.classify',classify):
                    task=asyncio.create_task(service.step())
                    self.assertTrue(await asyncio.to_thread(started.wait,2))
                    store.apply(ManualReset(lane_id=1,expected_control_revision=0))
                    sequence=store.state['sequence'];resume.set();await task
                self.assertEqual(store.state['sequence'],sequence)
                self.assertEqual(store.state['lanes']['1']['targets'],['standing']*5)
            finally:resume.set();store.close()

"""Synthetische Videofolgen: echte Zielpositionen, Verdeckung, Reset und mehrere Quellen."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import subprocess
import os
import sys
import json
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from biathlon_target_vision.calibration import CalibrationError, CalibrationStore, calibrate
from biathlon_target_vision.cameras import camera_binding
from biathlon_target_vision.config import CameraSettings, Settings
from biathlon_target_vision.core import EventStore
from biathlon_target_vision.models import ManualTarget, ModeChange, Observation
from biathlon_target_vision.vision import classify, LaneTracker, VisionService
from tests.synthetic import scene


class SequenceCameras:
    def __init__(self): self.frames = {}
    def set(self, camera_id, image, number):
        self.frames[camera_id] = {'frame':image,'frame_number':number,'connected':image is not None,
                                 'stream_epoch':self.frames.get(camera_id,{}).get('stream_epoch',1),
                                 'captured_at':datetime.now(timezone.utc)}
    def snapshot(self, camera_id): return self.frames[camera_id]


class VisionTests(unittest.TestCase):
    def test_all_masks_perspectives_noise_and_lighting(self):
        for perspective in range(3):
            base, quad, _, _ = scene(perspective=perspective)
            calibration = calibrate(base,quad)
            for brightness in (.6,1.2):
                for mask in range(32):
                    image=scene(mask=mask,perspective=perspective,brightness=brightness,noise=6)[0]
                    self.assertEqual(classify(image,calibration),['fallen' if mask&(1<<i) else 'standing' for i in range(5)],(perspective,brightness,mask))

    def test_partial_occlusion_and_small_motion(self):
        image,quad,_,_=scene();calibration=calibrate(image,quad)
        image=scene(mask=18,missing=2,shift=(7,-3),noise=5,brightness=.8)[0]
        self.assertEqual(classify(image,calibration),['standing','fallen','unknown','standing','fallen'])
        image=scene(mask=18,shift=(60,0))[0]
        with self.assertRaises(CalibrationError): classify(image,calibration)
        image=scene()[0];cv2.rectangle(image,(185,195),(250,250),(140,140,140),-1)
        with self.assertRaises(CalibrationError): classify(image,calibration)
        with self.assertRaises(CalibrationError): classify(scene(shift=(120,0))[0],calibration)

    def test_temporal_confirmation_baseline_disconnect_and_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=EventStore(Path(temporary),1);tracker=LaneTracker(1,'camera:test',['unknown']*5)
            now=0
            def frames(states):
                nonlocal now
                commands=[]
                for _ in range(3):
                    now+=.2
                    commands.extend(tracker.update(states,datetime(2026,10,17,tzinfo=timezone.utc)+timedelta(seconds=now),now))
                for command in commands: store.apply(command)
                return commands
            commands=frames(['standing']*4+['fallen'])
            self.assertTrue(all(c.baseline for c in commands));self.assertIsNone(store.state['lanes']['1']['current_bout_id'])
            frames(['standing']*5);frames(['standing','fallen','standing','standing','standing'])
            bout=store.state['lanes']['1']['current_bout_id'];self.assertEqual(store.state['bouts'][bout]['fallen_target_ids'],[2])
            for command in tracker.disconnected(datetime(2026,10,17,tzinfo=timezone.utc)+timedelta(seconds=now+.1)):store.apply(command)
            frames(['fallen','fallen','standing','standing','standing'])
            self.assertEqual(store.state['bouts'][bout]['fallen_target_ids'],[2])
            state=store.snapshot();store.close();store=EventStore(Path(temporary));self.assertEqual(store.snapshot(),state);store.close()

    def test_single_frame_and_short_flicker_do_not_create_events(self):
        tracker=LaneTracker(1,'camera:test',['standing']*5)
        at=datetime.now(timezone.utc)
        self.assertEqual(tracker.update(['fallen']*5,at,0),[])
        self.assertEqual(tracker.update(['standing']*5,at,.1),[])
        self.assertEqual(tracker.update(['fallen']*5,at,.2),[])

    def test_parallel_lanes_cameras_reset_occlusion_and_failure(self):
        async def scenario(directory):
            store=EventStore(directory,3);calibrations=CalibrationStore(directory);cameras=SequenceCameras()
            first=CameraSettings(id='first',name='first',url='rtsp://localhost/first',lane_ids=[1,2])
            second=CameraSettings(id='second',name='second',url='rtsp://localhost/second',lane_ids=[3])
            settings=Settings(cameras=[first,second])
            base,quad,_,_=scene();double=np.vstack([base,base]);lower=(np.array(quad)+[0,440]).tolist()
            for lane,image,roi,camera in [(1,double,quad,first),(2,double,lower,first),(3,base,quad,second)]:
                saved=calibrate(image,roi);saved.update(camera_binding(camera));calibrations.save(lane,saved)
            service=VisionService(lambda:settings,cameras,calibrations,store,store.apply)
            number=0
            async def frames(one,two,three,missing=None,disconnected=False):
                nonlocal number
                for _ in range(3):
                    number+=1
                    cameras.set('first',None if disconnected else np.vstack([scene(mask=one,missing=missing)[0],scene(mask=two)[0]]),number)
                    cameras.set('second',scene(mask=three)[0],number)
                    with patch('biathlon_target_vision.vision.monotonic',return_value=number*.2):await service.step()
            try:
                cameras.set('first',double,0); cameras.set('second',base,0)
                self.assertEqual(service.capture_status(1), 'uncertain')
                for instant in (0,.3,.6):
                    with patch('biathlon_target_vision.vision.monotonic',return_value=instant): await service.step()
                self.assertEqual(store.events, [], "Dasselbe Bild darf keine zeitliche Bestätigung ergeben")
                await frames(0,0,0)
                self.assertEqual([service.capture_status(n) for n in (1,2,3)], ['active']*3)
                self.assertEqual(store.state['lanes']['1']['targets'],['standing']*5)
                self.assertFalse(store.state['bouts'])
                await frames(16,1,4)
                bouts=[store.state['lanes'][str(n)]['current_bout_id'] for n in (1,2,3)]
                self.assertEqual([store.state['bouts'][b]['fallen_target_ids'] for b in bouts],[[5],[1],[3]])
                await frames(18,9,4,missing=2)
                self.assertEqual(store.state['lanes']['1']['targets'],['standing','fallen','unknown','standing','fallen'])
                self.assertEqual([service.capture_status(n) for n in (1,2,3)], ['uncertain','active','active'])
                cameras.frames['first']['stream_epoch'] += 1
                self.assertEqual(service.capture_status(1), 'uncertain')
                await frames(19,9,4)
                self.assertEqual(store.state['bouts'][bouts[0]]['fallen_target_ids'],[5,2])
                await frames(18,9,12,disconnected=True)
                self.assertEqual([service.capture_status(n) for n in (1,2,3)], ['unavailable','unavailable','active'])
                self.assertEqual(store.state['lanes']['1']['targets'],['unknown']*5)
                self.assertEqual(store.state['bouts'][bouts[2]]['fallen_target_ids'],[3,4])
                await frames(19,9,12)
                self.assertEqual(service.capture_status(1), 'active')
                self.assertEqual(store.state['bouts'][bouts[0]]['fallen_target_ids'],[5,2])
                await frames(0,0,0)
                self.assertTrue(all(store.state['bouts'][b]['closed'] for b in bouts))
                count=len(store.events)
                with patch('biathlon_target_vision.vision.monotonic',return_value=number*.2+1):await service.step()
                self.assertEqual(len(store.events),count)
            finally:store.close()
        with tempfile.TemporaryDirectory() as temporary:asyncio.run(scenario(Path(temporary)))

    def test_capture_status_is_live_not_an_effective_target_or_journal_value(self):
        async def scenario(directory):
            store=EventStore(directory,3);calibrations=CalibrationStore(directory);cameras=SequenceCameras()
            camera=CameraSettings(id='test',name='test',url='rtsp://localhost/test',lane_ids=[1,2])
            settings=Settings(cameras=[camera])
            image,quad,_,_=scene();saved=calibrate(image,quad);saved.update(camera_binding(camera));calibrations.save(1,saved)
            service=VisionService(lambda:settings,cameras,calibrations,store,store.apply)
            try:
                cameras.set('test',image,0)
                self.assertEqual(service.capture_status(3), 'unavailable')
                for number in range(1,4):
                    cameras.set('test',image,number)
                    with patch('biathlon_target_vision.vision.monotonic',return_value=number*.2):await service.step()
                self.assertEqual(service.capture_status(1), 'active')
                self.assertEqual(service.capture_status(2), 'uncertain', 'Eine verbundene Kamera ohne Bahnkalibrierung genügt nicht')
                lane=store.state['lanes']['1']
                store.apply(ManualTarget(lane_id=1,target_id=3,state='fallen',expected_control_revision=lane['control_revision'],start_bout=False))
                lane=store.state['lanes']['1']
                self.assertEqual(service.capture_status(1), 'active', 'Manuelle Priorität ändert nicht die Kameraqualität')
                self.assertEqual(lane['targets'][2], 'fallen')
                self.assertEqual(lane['automatic_targets'][2], 'standing')
                count=len(store.events)
                # Schon die aktuelle unsichere Klassifikation darf kein Erfolg sein,
                # auch wenn die zeitliche Stabilisierung noch den alten Wert hält.
                cameras.set('test',scene(missing=2)[0],4)
                with patch('biathlon_target_vision.vision.monotonic',return_value=.8):await service.step()
                self.assertEqual(lane['automatic_targets'], ['standing']*5)
                self.assertEqual(service.capture_status(1), 'uncertain')
                self.assertEqual(len(store.events), count, 'Status ist kein Journalereignis')
                restarted=VisionService(lambda:settings,cameras,calibrations,store,store.apply)
                self.assertEqual(restarted.capture_status(1), 'uncertain', 'Alte bekannte Werte belegen keine laufende Erkennung')
                store.apply(ModeChange(lane_id=1,mode='manual',expected_control_revision=lane['control_revision']))
                self.assertEqual(service.capture_status(1), 'unavailable')
            finally:store.close()
        with tempfile.TemporaryDirectory() as temporary:asyncio.run(scenario(Path(temporary)))

    def test_run_notifies_transient_uncertainty_but_not_unchanged_frames(self):
        async def scenario(directory):
            store=EventStore(directory,1);calibrations=CalibrationStore(directory);cameras=SequenceCameras()
            camera=CameraSettings(id='test',name='test',url='rtsp://localhost/test',lane_ids=[1])
            image,quad,_,_=scene();saved=calibrate(image,quad);saved.update(camera_binding(camera));calibrations.save(1,saved)
            service=VisionService(lambda:Settings(cameras=[camera]),cameras,calibrations,store,store.apply)
            try:
                for number in range(1,4):
                    cameras.set('test',image,number)
                    with patch('biathlon_target_vision.vision.monotonic',return_value=number*.2):await service.step()
                journal=Path(store.file.name).read_bytes()
                statuses=[];step=service.step;number=3
                async def next_frame():
                    nonlocal number
                    number+=1
                    if number>10:
                        raise asyncio.CancelledError
                    cameras.set('test',scene(missing=2)[0] if number==4 else image,number)
                    await step()
                # One uncertain frame changes status without changing a stabilized
                # target value. Recovery also needs no journal entry.
                with patch.object(service,'step',next_frame), self.assertRaises(asyncio.CancelledError):
                    await service.run(lambda:statuses.append(service.capture_statuses()))
                self.assertEqual(statuses,[{'1':'uncertain'},{'1':'active'}])
                self.assertEqual(Path(store.file.name).read_bytes(),journal)
            finally:store.close()
        with tempfile.TemporaryDirectory() as temporary:asyncio.run(scenario(Path(temporary)))


    def test_baseline_journal_is_readable_by_previous_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); data=root/'data';store=EventStore(data,1)
            command=Observation(lane_id=1,kind='target',source='camera:test',target_id=5,state='fallen',baseline=True,observed_at=datetime.now(timezone.utc))
            event=store.apply(command)
            self.assertTrue(event['baseline']);self.assertNotIn('baseline',event['command'])
            self.assertEqual(store.apply(command),event)
            self.assertIsNone(store.state['lanes']['1']['current_bout_id']);store.close()
            legacy=root/'legacy';package=legacy/'biathlon_target_vision';package.mkdir(parents=True)
            repository=Path(__file__).resolve().parents[1]
            for name in ('__init__.py','models.py','core.py'):
                source=subprocess.run(['git','show',f'v0.4.0:biathlon_target_vision/{name}'],cwd=repository,check=True,capture_output=True).stdout
                (package/name).write_bytes(source)
            env={**os.environ,'PYTHONPATH':str(legacy)}
            result=subprocess.run([sys.executable,'-c',"from pathlib import Path; import sys,json; from biathlon_target_vision.core import EventStore; s=EventStore(Path(sys.argv[1])); print(json.dumps(s.snapshot()['lanes']['1']['targets'])); s.close()",str(data)],cwd=legacy,env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),['unknown']*4+['fallen'])
            store=EventStore(data);self.assertIsNone(store.state['lanes']['1']['current_bout_id']);self.assertEqual(store.apply(command),event);store.close()

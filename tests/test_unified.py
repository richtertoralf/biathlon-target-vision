"""Ein Kampfrichterablauf, menschliche Priorität und unverändertes historisches Replay."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from biathlon_target_vision.core import EventStore, Conflict
from biathlon_target_vision.models import Occupy, Release, ManualReset, ManualTarget, Observation, ModeChange, Assignment


class UnifiedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.store = EventStore(self.directory, 1)
        self.at = datetime(2026, 10, 18, tzinfo=timezone.utc)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def lane(self):
        return self.store.snapshot()['lanes']['1']

    def control(self, model, **fields):
        return self.store.apply(model(lane_id=1, expected_control_revision=self.lane()['control_revision'], **fields))

    def target(self, n, value):
        return self.control(ManualTarget, target_id=n, state=value, start_bout=False)

    def occupy(self):
        return self.store.apply(Occupy(lane_id=1, expected_revision=self.lane()['revision']))

    def leave(self):
        return self.store.apply(Release(lane_id=1, bout_id=self.lane()['occupied_bout_id'],
                                       expected_revision=self.lane()['revision']))

    def observe(self, n, value, baseline=False):
        self.at += timedelta(seconds=1)
        return self.store.apply(Observation(lane_id=1, kind='target', target_id=n, state=value,
            source='camera:test', observed_at=self.at, baseline=baseline))

    def standing(self, baseline=False):
        for n in range(1, 6):
            self.observe(n, 'standing', baseline)

    def test_three_manual_athletes_without_camera_or_source_selection(self):
        for positions in ([], [3], [1, 3, 5]):
            self.control(ManualReset)
            self.assertEqual(self.lane()['status'], 'ready')
            self.occupy()
            bout = self.lane()['current_bout_id']
            for n in positions:
                self.target(n, 'fallen')
                self.target(n, 'standing')
                self.target(n, 'fallen')
            self.assertEqual(self.lane()['current_bout_id'], bout)
            self.assertEqual(self.store.state['bouts'][bout]['fallen_target_ids'], [])
            self.leave()
            self.assertEqual(self.lane()['status'], 'reset_required')
        self.assertEqual(len(self.store.state['bouts']), 3)
        self.assertFalse(any(e['command']['kind'] == 'mode' for e in self.store.events))
        self.control(ManualReset)
        self.assertEqual(self.lane()['manual_targets'], [None]*5)

    def test_partial_return_cannot_split_bout_or_erase_correction(self):
        self.standing(True); self.occupy()
        bout = self.lane()['current_bout_id']
        self.observe(1, 'fallen'); self.observe(4, 'fallen'); self.target(3, 'fallen')
        self.observe(1, 'standing')
        self.assertEqual(self.lane()['current_bout_id'], bout)
        self.assertEqual(self.lane()['targets'][2], 'fallen')
        self.observe(5, 'fallen')
        self.assertEqual(len(self.store.state['bouts']), 1)
        self.observe(4, 'standing'); self.observe(5, 'standing')
        self.assertIsNone(self.lane()['current_bout_id'])
        self.assertEqual(self.lane()['occupied_bout_id'], bout)
        self.assertEqual(self.lane()['manual_targets'], [None]*5)
        self.leave(); self.assertEqual(self.lane()['status'], 'ready')

    def test_manual_preparation_survives_missing_camera_but_uses_known_baseline(self):
        self.control(ManualReset)
        for n in range(1, 6): self.observe(n, 'unknown', True)
        self.assertEqual(self.lane()['status'], 'ready')
        self.assertEqual(self.lane()['targets'], ['standing']*5)
        self.assertEqual(self.lane()['automatic_targets'], ['unknown']*5)
        event = self.observe(3, 'fallen')
        self.assertTrue(event['effective_baseline'])
        self.assertEqual(self.lane()['targets'][2], 'fallen')
        self.assertEqual(self.lane()['status'], 'reset_required')
        self.assertEqual(self.store.state['bouts'], {})

    def test_no_selection_needed_when_camera_disappears_and_returns(self):
        self.standing(True); self.occupy(); bout = self.lane()['current_bout_id']
        self.observe(1, 'fallen'); self.target(3, 'fallen')
        for n in range(1, 6): self.observe(n, 'unknown', True)
        self.target(2, 'standing'); self.target(4, 'fallen')
        self.standing(True)
        self.assertEqual(self.lane()['targets'], ['standing','standing','fallen','fallen','standing'])
        self.assertEqual(self.lane()['current_bout_id'], bout)
        self.assertFalse(self.lane()['reset_confirmed'])
        self.observe(5, 'fallen')
        self.assertEqual(self.store.state['bouts'][bout]['fallen_target_ids'], [1,5])
        self.assertEqual(self.lane()['manual_targets'][2:4], ['fallen','fallen'])
        self.assertFalse(any(e['command']['kind'] == 'mode' for e in self.store.events))

    def test_unknown_can_be_confirmed_both_ways_without_a_bout(self):
        self.target(1, 'standing'); self.target(2, 'fallen')
        self.assertEqual(self.lane()['targets'], ['standing','fallen','unknown','unknown','unknown'])
        self.assertEqual(self.store.state['bouts'], {})
        self.assertEqual(self.lane()['status'], 'reset_required')

    def test_next_athlete_never_inherits_overrides_or_stale_camera_values(self):
        self.standing(True); self.occupy(); self.target(3, 'fallen'); self.leave()
        self.occupy() # Tatsächliches Betreten darf auch ohne Vorbereitung erfasst werden.
        self.assertEqual(self.lane()['manual_targets'], [None]*5)
        self.assertEqual(self.lane()['targets'][2], 'unknown')
        self.observe(1, 'standing', True)
        self.assertEqual(self.lane()['targets'][2], 'unknown')
        self.observe(3, 'standing', True)
        self.assertEqual(self.lane()['targets'][2], 'standing')
        self.assertEqual(len(self.store.state['bouts']), 2)

    def test_release_after_reset_invalidates_other_tablets_target_choice(self):
        self.control(ManualReset); self.occupy(); self.control(ManualReset)
        pending = ManualTarget(lane_id=1, target_id=3, state='fallen', start_bout=False,
                               expected_control_revision=self.lane()['control_revision'])
        self.leave()
        with self.assertRaises(Conflict): self.store.apply(pending)
        self.assertEqual(self.lane()['targets'], ['standing']*5)

    def test_restart_preserves_preparation_and_overrides(self):
        self.control(ManualReset); self.occupy(); self.target(3, 'fallen')
        self.observe(3, 'standing', True)
        before = self.store.snapshot()
        self.store.close(); self.store = EventStore(self.directory)
        self.assertEqual(before, self.store.snapshot())
        self.observe(3, 'standing')
        self.assertEqual(self.lane()['targets'][2], 'fallen')
        self.leave(); self.control(ManualReset)
        before = self.store.snapshot()
        self.store.close(); self.store = EventStore(self.directory)
        self.assertEqual(before, self.store.snapshot())

    def test_five_manual_standing_corrections_are_not_a_full_reset(self):
        self.occupy()
        for n in range(1, 6): self.target(n, 'standing')
        self.leave()
        self.assertEqual(self.lane()['status'], 'reset_required')
        self.control(ManualReset)
        self.assertEqual(self.lane()['status'], 'ready')

    def test_preparation_survives_dead_vision_and_disconnected_assigned_camera(self):
        import asyncio
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from biathlon_target_vision.app import create_app
        from biathlon_target_vision.config import Settings, CameraSettings, save_settings
        from tests.test_cameras import FakeCameras
        async def idle(service): await asyncio.Event().wait()
        directory = self.directory/'api'
        save_settings(directory,Settings(cameras=[CameraSettings(id='test',name='Test',url='rtsp://localhost/test',lane_ids=[1])]))
        with patch('biathlon_target_vision.app.CameraManager',FakeCameras), patch('biathlon_target_vision.vision.VisionService.run',idle):
            with TestClient(create_app(directory,1)) as client:
                async def stop():
                    client.app.state.vision_task.cancel()
                    await asyncio.gather(client.app.state.vision_task,return_exceptions=True)
                client.portal.call(stop)
                result=client.post('/api/lanes/1/reset',json={'lane_id':1,'expected_control_revision':0})
                self.assertEqual(result.status_code,200)
                self.assertEqual(result.json()['state']['lanes']['1']['status'],'ready')
                self.assertEqual(result.json()['state']['health'],'error')
                result=client.post('/api/lanes/1/occupy',json={'lane_id':1,'expected_revision':1})
                self.assertEqual(result.status_code,200)
                self.assertEqual(result.json()['state']['lanes']['1']['status'],'occupied')

    def test_source_switch_does_not_fabricate_manual_overrides(self):
        self.standing(True); self.occupy(); self.target(3, 'fallen')
        self.control(ModeChange, mode='manual')
        self.assertEqual(self.lane()['manual_targets'], [None,None,'fallen',None,None])
        self.observe(1, 'fallen')
        self.assertEqual(self.lane()['targets'][0], 'standing')
        self.control(ModeChange, mode='automatic')
        event = self.observe(1, 'fallen')
        self.assertTrue(event['effective_baseline'])
        self.assertEqual(self.lane()['targets'][0], 'fallen')
        self.observe(3, 'standing')
        self.assertEqual(self.lane()['targets'][2], 'fallen')
        self.assertEqual(self.lane()['automatic_targets'][2], 'standing')

    def test_actual_pr9_journal_retains_bouts_revisions_and_idempotence(self):
        legacy = self.directory/'legacy'; package = legacy/'biathlon_target_vision'; package.mkdir(parents=True)
        for name in ('__init__.py','core.py','models.py'):
            content = subprocess.run(['git','show',f'39674032:biathlon_target_vision/{name}'],
                                     check=True, capture_output=True).stdout
            (package/name).write_bytes(content)
        script = '''from pathlib import Path
from datetime import datetime, timedelta, timezone
import sys,json
from biathlon_target_vision.core import EventStore
from biathlon_target_vision.models import *
s=EventStore(Path(sys.argv[1]),1)
def lane(): return s.state['lanes']['1']
def control(cls,**values):s.apply(cls(lane_id=1,expected_control_revision=lane()['control_revision'],**values))
control(ModeChange,mode='mixed')
s.apply(Occupy(lane_id=1,expected_revision=lane()['revision']))
for n,value in enumerate(['fallen','fallen','standing','standing','standing'],1):
 s.apply(Observation(lane_id=1,kind='target',target_id=n,state=value,source='old',observed_at=datetime(2026,1,1,tzinfo=timezone.utc)))
s.apply(Observation(lane_id=1,kind='target',target_id=1,state='standing',source='old',observed_at=datetime(2026,1,2,tzinfo=timezone.utc)))
control(ManualTarget,target_id=3,state='fallen',start_bout=False)
control(ManualReset)
s.apply(Release(lane_id=1,bout_id=lane()['occupied_bout_id'],expected_revision=lane()['revision']))
control(ModeChange,mode='manual')
control(ManualReset)
s.apply(Occupy(lane_id=1,expected_revision=lane()['revision']))
control(ManualTarget,target_id=5,state='fallen',start_bout=False)
control(ManualReset)
s.apply(Release(lane_id=1,bout_id=lane()['occupied_bout_id'],expected_revision=lane()['revision']))
print(json.dumps(s.state));s.close()
'''
        directory = self.directory/'old-data'
        result = subprocess.run([sys.executable,'-c',script,str(directory)],cwd=legacy,
            env={**os.environ,'PYTHONPATH':str(legacy)},check=True,capture_output=True,text=True)
        old = json.loads(result.stdout)
        original = (directory/'events.jsonl').read_bytes()
        store = EventStore(directory)
        try:
            old['lanes']['1']['unassigned_manual_target_ids'] = []
            self.assertEqual(store.state, old)
            self.assertEqual((directory/'events.jsonl').read_bytes(), original)
            command = Release.model_validate(store.events[-1]['command'])
            self.assertEqual(store.apply(command), store.events[-1])
            store.apply(Occupy(lane_id=1,expected_revision=store.state['lanes']['1']['revision']))
            self.assertEqual(store.state['lanes']['1']['targets'], ['standing']*5)
            self.assertEqual(store.state['lanes']['1']['manual_targets'], [None]*5)
            self.assertEqual(store.events[-1]['rules_version'], 3)
            expected = store.snapshot()
        finally: store.close()
        store = EventStore(directory)
        try: self.assertEqual(store.snapshot(), expected)
        finally: store.close()

    def test_actual_rules2_journal_keeps_history_and_preserves_unassigned_inputs_after_upgrade(self):
        legacy = self.directory/'rules2'; package = legacy/'biathlon_target_vision'; package.mkdir(parents=True)
        for name in ('__init__.py', 'core.py', 'models.py'):
            (package/name).write_bytes(subprocess.run(
                ['git', 'show', f'0921a98:biathlon_target_vision/{name}'],
                check=True, capture_output=True).stdout)
        script = '''from pathlib import Path
import sys,json
from biathlon_target_vision.core import EventStore
from biathlon_target_vision.models import Assignment, ManualReset, ManualTarget, Occupy, Release
s=EventStore(Path(sys.argv[1]),2)
def lane(n):return s.state['lanes'][str(n)]
def control(n,cls,**fields):s.apply(cls(lane_id=n,expected_control_revision=lane(n)['control_revision'],**fields))
for n in (1,2):control(n,ManualReset)
control(1,ManualTarget,target_id=1,state='fallen',start_bout=False)
s.apply(Assignment(lane_id=1,bib=41,expected_revision=lane(1)['revision']))
assert lane(1)['targets'][0]=='unknown' # Tatsächlich gespeicherter alter Fehler bleibt historisch erhalten.
s.apply(Release(lane_id=1,bout_id=lane(1)['occupied_bout_id'],expected_revision=lane(1)['revision']))
control(1,ManualTarget,target_id=3,state='fallen',start_bout=False)
control(2,ManualTarget,target_id=2,state='fallen',start_bout=False)
print(json.dumps(s.state));s.close()
'''
        directory = self.directory/'rules2-data'
        result = subprocess.run([sys.executable, '-c', script, str(directory)], cwd=legacy,
            env={**os.environ, 'PYTHONPATH':str(legacy)}, check=True, capture_output=True, text=True)
        old = json.loads(result.stdout)
        original = (directory/'events.jsonl').read_bytes()
        store = EventStore(directory)
        try:
            old['lanes']['1']['unassigned_manual_target_ids'] = [3]
            old['lanes']['2']['unassigned_manual_target_ids'] = [2]
            self.assertEqual(store.state, old)
            self.assertEqual((directory/'events.jsonl').read_bytes(), original)
            last = ManualTarget.model_validate(store.events[-1]['command'])
            self.assertEqual(store.apply(last), store.events[-1])
            for n in (1, 2):
                lane = store.state['lanes'][str(n)]
                before = list(lane['targets'])
                command = Assignment(lane_id=n, bib=50+n, expected_revision=lane['revision'])
                event = store.apply(command)
                self.assertEqual(event['rules_version'], 3)
                self.assertEqual(store.state['lanes'][str(n)]['targets'], before)
                self.assertEqual(store.apply(command), event)
            expected = store.snapshot()
        finally:
            store.close()
        store = EventStore(directory)
        try:
            self.assertEqual(store.snapshot(), expected)
            self.assertTrue((directory/'events.jsonl').read_bytes().startswith(original))
        finally:
            store.close()

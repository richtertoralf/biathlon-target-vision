"""Belegung ohne BIB und bestätigte Vorbereitung unabhängig von Schießeinlagen."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from biathlon_target_vision.app import create_app
from biathlon_target_vision.core import EventStore, Conflict
from biathlon_target_vision.models import (Occupy, Assignment, Release, Observation, ModeChange,
                                          ManualTarget, ManualReset)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)
        self.store=EventStore(self.directory,2);self.at=datetime(2026,10,18,tzinfo=timezone.utc)

    def tearDown(self):self.store.close();self.temp.cleanup()
    def lane(self):return self.store.snapshot()['lanes']['1']
    def control(self,model,**fields):
        return self.store.apply(model(lane_id=1,expected_control_revision=self.lane()['control_revision'],**fields))
    def occupy(self):
        return self.store.apply(Occupy(lane_id=1,expected_revision=self.lane()['revision'],
                                      expected_assignment_revision=self.lane()['assignment_revision']))
    def leave(self):
        lane=self.lane()
        return self.store.apply(Release(lane_id=1,bout_id=lane['occupied_bout_id'],
            expected_revision=lane['revision'],expected_assignment_revision=lane['assignment_revision']))
    def observe(self,target,state='standing',baseline=False):
        self.at+=timedelta(seconds=1)
        return self.store.apply(Observation(lane_id=1,kind='target',source='camera:test',target_id=target,
                                           state=state,observed_at=self.at,baseline=baseline))
    def standing(self,baseline=False):
        for target in range(1,6):self.observe(target,baseline=baseline)
    def assign(self,bib,bout=None):
        return self.store.apply(Assignment(lane_id=1,bib=bib,bout_id=bout,expected_revision=self.lane()['revision']))
    def manual(self,target,state):
        return self.control(ManualTarget,target_id=target,state=state,start_bout=False)

    def test_complete_manual_flow_without_bib_then_late_correction(self):
        self.control(ModeChange,mode='manual')
        self.assertEqual(self.lane()['status'],'reset_required')
        self.control(ManualReset);self.assertEqual(self.lane()['status'],'ready')
        self.occupy();bout=self.lane()['occupied_bout_id']
        self.assertEqual(self.lane()['status'],'occupied')
        self.assertIsNone(self.store.state['bouts'][bout]['bib'])
        self.manual(3,'fallen');self.manual(3,'standing');self.manual(3,'fallen')
        self.assertEqual(self.lane()['current_bout_id'],bout)
        self.assign(42,bout);self.assign(43,bout)
        self.assertEqual(self.store.state['bouts'][bout]['bib'],43)
        self.leave();self.assertEqual(self.lane()['status'],'reset_required')
        # Korrektur einer einzelnen Scheibe ist keine bestätigte Rückstellung.
        self.manual(3,'standing');self.assertEqual(self.lane()['status'],'reset_required')
        self.assertIsNone(self.lane()['current_bout_id']);self.assertEqual(len(self.store.state['bouts']),1)
        self.control(ManualReset);self.assertEqual(self.lane()['status'],'ready')
        self.occupy();self.assertNotEqual(self.lane()['occupied_bout_id'],bout)

    def test_late_bib_preserves_manual_values_with_and_without_occupancy(self):
        for occupied_first in (False, True, False):
            with self.subTest(occupied_first=occupied_first):
                self.control(ManualReset)
                if occupied_first:
                    self.occupy()
                self.manual(1, 'fallen'); self.manual(3, 'fallen')
                before = self.lane()
                count = len(self.store.state['bouts'])
                self.assign(42, before['current_bout_id'])
                bout = self.lane()['current_bout_id']
                self.assertEqual(len(self.store.state['bouts']), count + (not occupied_first))
                if occupied_first:
                    self.assertEqual(bout, before['current_bout_id'])
                for bib in (43, 44):
                    self.assign(bib, bout)
                    self.assertEqual(self.lane()['targets'], before['targets'])
                    self.assertEqual(self.lane()['manual_targets'], before['manual_targets'])
                    self.assertEqual(self.lane()['current_bout_id'], bout)
                    self.assertEqual(self.store.state['bouts'][bout]['fallen_target_ids'], [])
                expected = self.store.snapshot()
                self.store.close(); self.store = EventStore(self.directory)
                self.assertEqual(self.store.snapshot(), expected)
                self.leave()

    def test_new_bib_preserves_fresh_corrections_but_not_previous_athletes(self):
        self.control(ManualReset); self.occupy(); self.assign(41)
        old_bout = self.lane()['current_bout_id']
        self.manual(1, 'fallen'); self.manual(3, 'fallen'); self.leave()
        # Neue Entscheidungen auf freier Bahn gehören nicht zum Vorgänger.
        self.manual(3, 'standing'); self.manual(4, 'fallen')
        self.assign(42)
        self.assertNotEqual(self.lane()['current_bout_id'], old_bout)
        self.assertEqual(self.lane()['targets'], ['unknown', 'standing', 'standing', 'fallen', 'standing'])
        self.assertEqual(self.lane()['manual_targets'], [None, None, 'standing', 'fallen', None])
        self.assertEqual(len(self.store.state['bouts']), 2)
        before = self.store.snapshot()
        self.store.close(); self.store = EventStore(self.directory)
        self.assertEqual(self.store.snapshot(), before)

    def test_automatic_bout_start_preserves_unassigned_manual_decisions(self):
        self.standing(baseline=True)
        self.manual(3, 'fallen')
        self.assertIsNone(self.lane()['current_bout_id'])
        self.observe(1, 'fallen')
        bout = self.lane()['current_bout_id']
        self.assign(42, bout)
        self.standing(baseline=True)
        self.assertEqual(self.lane()['targets'][2], 'fallen')
        self.assertEqual(self.store.state['bouts'][bout]['fallen_target_ids'], [1])
        self.assertEqual(len(self.store.state['bouts']), 1)

    def test_correction_after_reset_on_occupied_lane_still_belongs_to_previous_athlete(self):
        self.occupy(); self.assign(41); self.control(ManualReset)
        self.manual(3, 'fallen'); self.leave(); self.assign(42)
        self.assertEqual(self.lane()['manual_targets'], [None] * 5)
        self.assertEqual(self.lane()['targets'][2], 'unknown')

    def test_leaving_after_manual_reset_stays_occupied_until_departure(self):
        self.control(ModeChange,mode='manual');self.control(ManualReset);self.occupy()
        bout=self.lane()['occupied_bout_id'];self.manual(2,'fallen')
        self.control(ManualReset)
        self.assertEqual(self.lane()['status'],'occupied')
        self.assertEqual(self.lane()['occupied_bout_id'],bout)
        self.assertIsNone(self.lane()['current_bout_id'])
        self.leave();self.assertEqual(self.lane()['status'],'ready')

    def test_all_standing_unchanged_after_occupancy_does_not_prove_reset(self):
        self.standing(baseline=True);self.assertEqual(self.lane()['status'],'reset_required')
        self.control(ManualReset);self.standing(baseline=True)
        self.assertEqual(self.lane()['status'],'ready')
        self.occupy();self.standing();self.leave()
        self.assertEqual(self.lane()['targets'],['standing']*5)
        self.assertFalse(self.lane()['reset_confirmed'])
        self.assertEqual(self.lane()['status'],'reset_required')
        self.standing(baseline=True);self.assertEqual(self.lane()['status'],'reset_required')

    def test_automatic_full_reset_prepares_lane_after_departure(self):
        self.standing(baseline=True);self.occupy();bout=self.lane()['occupied_bout_id']
        self.observe(1,'fallen');self.observe(4,'fallen');self.leave()
        self.observe(1)
        self.assertEqual(self.lane()['status'],'reset_required')
        self.assertTrue(self.store.state['bouts'][bout]['closed'])
        self.observe(4);self.assertEqual(self.lane()['status'],'ready')
        self.assertEqual(self.store.state['bouts'][bout]['fallen_target_ids'],[1,4])

    def test_automatic_reset_before_leaving_does_not_change_occupancy(self):
        self.standing(baseline=True);self.occupy();bout=self.lane()['occupied_bout_id']
        self.observe(2,'fallen');self.observe(2)
        self.assertEqual(self.lane()['status'],'occupied');self.assertTrue(self.lane()['reset_confirmed'])
        self.assign(52,bout) # Auch nach Rückstellung verspätet derselben Belegung zuordnen.
        self.leave();self.assertEqual(self.lane()['status'],'ready')
        self.assertEqual(self.store.state['bouts'][bout]['bib'],52)

    def test_baseline_after_outage_cannot_complete_partial_reset(self):
        self.standing(baseline=True);self.occupy();self.observe(1,'fallen');self.observe(2,'fallen');self.leave()
        self.observe(1)
        self.observe(2,'unknown',baseline=True);self.standing(baseline=True)
        self.assertEqual(self.lane()['status'],'reset_required')
        self.assertFalse(self.lane()['automatic_reset_pending'])

    def test_mixed_unchanged_standing_does_not_erase_manual_correction(self):
        self.control(ModeChange,mode='mixed');self.standing(baseline=True);self.occupy()
        self.manual(3,'fallen')
        for _ in range(2):self.standing()
        self.assertEqual(self.lane()['targets'][2],'fallen')
        self.assertEqual(self.lane()['automatic_targets'][2],'standing')
        self.observe(1,'fallen');self.observe(2,'fallen');self.observe(1)
        self.assertEqual(self.lane()['targets'][2],'fallen') # Teilrückstellung reicht nicht.
        self.observe(2)
        self.assertEqual(self.lane()['manual_targets'],[None]*5)
        self.assertEqual(self.lane()['status'],'occupied')
        self.leave();self.assertEqual(self.lane()['status'],'ready')

    def test_target_correction_never_starts_new_bout_even_after_reset(self):
        self.control(ModeChange,mode='manual');self.manual(1,'fallen')
        self.assertEqual(len(self.store.state['bouts']),0)
        self.control(ManualReset);self.occupy();bout=self.lane()['occupied_bout_id']
        self.control(ManualReset);self.manual(1,'fallen');self.manual(1,'standing')
        self.assertEqual(len(self.store.state['bouts']),1)
        self.assertEqual(self.lane()['occupied_bout_id'],bout)
        self.assertIsNone(self.lane()['current_bout_id'])
        self.assertFalse(self.lane()['reset_confirmed'])

    def test_unknown_or_camera_loss_cannot_be_ready_and_manual_continuation_keeps_bout(self):
        self.standing(baseline=True);self.control(ManualReset);self.standing(baseline=True)
        self.assertEqual(self.lane()['status'],'ready')
        self.observe(1,'unknown',baseline=True);self.assertEqual(self.lane()['status'],'reset_required')
        self.occupy();bout=self.lane()['occupied_bout_id'];self.assign(42,bout)
        self.control(ModeChange,mode='manual');self.manual(3,'fallen')
        self.assertEqual(self.lane()['occupied_bout_id'],bout)
        self.assertEqual(self.lane()['current_bout_id'],bout)
        self.assertEqual(self.store.state['bouts'][bout]['bib'],42)

    def test_occupancy_conflict_idempotence_and_pending_bib_remains_bound(self):
        lane=self.lane();command=Occupy(lane_id=1,expected_revision=lane['revision'],
                                      expected_assignment_revision=lane['assignment_revision'])
        event=self.store.apply(command);self.assertEqual(self.store.apply(command),event)
        with self.assertRaises(Conflict):self.store.apply(command.model_copy(update={'event_id':'competitor'}))
        bout=self.lane()['occupied_bout_id'];pending=Assignment(lane_id=1,bib=62,bout_id=bout,
            expected_revision=self.lane()['revision'],expected_assignment_revision=self.lane()['assignment_revision'])
        self.observe(3,'fallen');self.observe(3)
        self.store.apply(pending);self.assertEqual(self.store.state['bouts'][bout]['bib'],62)
        self.assertEqual(self.lane()['occupied_bout_id'],bout)

    def test_replay_persists_pending_reset_and_full_workflow(self):
        self.standing(baseline=True);self.occupy();self.observe(1,'fallen');self.observe(4,'fallen');self.leave()
        self.observe(1);before=self.store.snapshot()
        self.store.close();self.store=EventStore(self.directory)
        self.assertEqual(self.store.snapshot(),before)
        self.observe(4);self.assertEqual(self.lane()['status'],'ready')
        before=self.store.snapshot();self.store.close();self.store=EventStore(self.directory)
        self.assertEqual(self.store.snapshot(),before)


class WorkflowApiTests(unittest.TestCase):
    def test_late_bib_two_tablets_conflict_idempotence_and_restart_preserve_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with TestClient(create_app(directory, 1)) as client:
                client.headers["X-Session-ID"] = client.get("/api/state").json()["session_id"]
                with client.websocket_connect('/ws') as first, client.websocket_connect('/ws') as second:
                    first.receive_json(); second.receive_json()
                    # BIB-Eingabe beginnt vor den manuellen Zuständen auf dem zweiten Tablet.
                    pending = {'lane_id':1, 'bib':42, 'expected_revision':0,
                               'expected_assignment_revision':0, 'bout_after_sequence':0, 'event_id':'bib-first'}
                    competing = {**pending, 'bib':43, 'event_id':'bib-other'}
                    for revision, target in enumerate((1, 3)):
                        response = client.post('/api/lanes/1/manual-target', json={
                            'lane_id':1, 'target_id':target, 'state':'fallen', 'start_bout':False,
                            'expected_control_revision':revision})
                        self.assertEqual(response.status_code, 200)
                        for socket in (first, second): socket.receive_json()
                    response = client.put('/api/lanes/1/bib', json=pending)
                    self.assertEqual(response.status_code, 200)
                    state = response.json()['state']; lane = state['lanes']['1']
                    expected = ['fallen', 'unknown', 'fallen', 'unknown', 'unknown']
                    self.assertEqual(lane['targets'], expected)
                    for socket in (first, second):
                        self.assertEqual(socket.receive_json()['lanes']['1'], lane)
                    self.assertEqual(client.put('/api/lanes/1/bib', json=competing).status_code, 409)
                    self.assertEqual(client.put('/api/lanes/1/bib', json=pending).json()['event'], response.json()['event'])
                    self.assertEqual(client.get('/api/state').json()['sequence'], state['sequence'])
            with TestClient(create_app(directory)) as client:
                client.headers["X-Session-ID"] = client.get("/api/state").json()["session_id"]
                restored = client.get('/api/state').json()
                self.assertEqual(restored['lanes']['1'], lane)
                self.assertEqual(len(restored['bouts']), 1)
                self.assertEqual(restored['bouts'][lane['occupied_bout_id']]['bib'], 42)

    def test_occupy_without_bib_two_tablets_and_existing_bib_release_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            with TestClient(create_app(directory,2)) as client:
                client.headers["X-Session-ID"] = client.get("/api/state").json()["session_id"]
                with client.websocket_connect('/ws') as first,client.websocket_connect('/ws') as second:
                    first.receive_json();second.receive_json()
                    response=client.post('/api/lanes/1/occupy',json={'lane_id':1,'expected_revision':0})
                    self.assertEqual(response.status_code,200);expected=response.json()['state']['lanes']['1']
                    self.assertEqual(expected['status'],'occupied')
                    for socket in (first,second):self.assertEqual(socket.receive_json()['lanes']['1'],expected)
                    bout=expected['occupied_bout_id']
                    response=client.put('/api/lanes/1/bib',json={'lane_id':1,'bib':82,'bout_id':bout,
                        'expected_revision':expected['revision'],'expected_assignment_revision':expected['assignment_revision']})
                    self.assertEqual(response.status_code,200)
                    lane=response.json()['state']['lanes']['1']
                    response=client.post('/api/lanes/1/release',json={'lane_id':1,'bout_id':bout,'expected_revision':lane['revision']})
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.json()['state']['lanes']['1']['status'],'reset_required')
            with TestClient(create_app(directory)) as client:
                client.headers["X-Session-ID"] = client.get("/api/state").json()["session_id"]
                state=client.get('/api/state').json();self.assertIsNone(state['lanes']['1']['occupied_bout_id'])
                self.assertEqual(state['bouts'][bout]['bib'],82)
                self.assertEqual(client.get('/api/health').status_code,200)

    def test_disconnected_camera_and_stopped_capture_hide_stale_readiness(self):
        import asyncio
        from unittest.mock import patch
        from biathlon_target_vision.config import CameraSettings, Settings, save_settings
        from tests.test_cameras import FakeCameras
        class SwitchCamera(FakeCameras):
            connected=True
            def snapshot(self,camera_id):
                return {**super().snapshot(camera_id),'connected':self.connected}
        async def idle(service, status_changed):await asyncio.Event().wait()
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            save_settings(directory,Settings(cameras=[CameraSettings(id='test',name='Test',url='rtsp://localhost/test',lane_ids=[1])]))
            with patch('biathlon_target_vision.app.CameraManager',SwitchCamera),patch('biathlon_target_vision.vision.VisionService.run',idle):
                with TestClient(create_app(directory,1)) as client:
                    client.headers["X-Session-ID"] = client.get("/api/state").json()["session_id"]
                    result=client.post('/api/lanes/1/reset',json={'lane_id':1,'expected_control_revision':0})
                    self.assertEqual(result.status_code,200)
                    at=datetime.now(timezone.utc)
                    for target in range(1,6):
                        result=client.post('/api/observations',json={'lane_id':1,'kind':'target','target_id':target,'state':'standing',
                            'source':'camera:test','observed_at':(at+timedelta(seconds=target)).isoformat(),'baseline':True})
                        self.assertEqual(result.status_code,200)
                    before=client.get('/api/state').json()
                    self.assertEqual(before['lanes']['1']['status'],'ready')
                    client.app.state.cameras.connected=False
                    after=client.get('/api/state').json()
                    self.assertEqual(after['sequence'],before['sequence'])
                    self.assertEqual(after['lanes']['1']['targets'],['standing']*5)
                    self.assertEqual(after['lanes']['1']['status'],'reset_required')
                    client.app.state.cameras.connected=True
                    async def stop():
                        client.app.state.vision_task.cancel()
                        await asyncio.gather(client.app.state.vision_task,return_exceptions=True)
                    client.portal.call(stop)
                    self.assertEqual(client.get('/api/state').json()['lanes']['1']['status'],'reset_required')
                    self.assertEqual(client.get('/api/health').status_code,503)
                    lane=client.get('/api/state').json()['lanes']['1']
                    result=client.put('/api/lanes/1/mode',json={'lane_id':1,'mode':'manual','expected_control_revision':lane['control_revision']})
                    self.assertEqual(result.json()['state']['lanes']['1']['status'],'ready')

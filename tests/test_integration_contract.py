"""Öffentlichen BTV-Vertrag als externe lesende Anwendung und bei Ausfällen prüfen."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocket

from biathlon_target_vision import API_VERSION
from biathlon_target_vision.app import create_app
from tests.test_cameras import FakeCameras


class IntegrationContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(); self.path=Path(self.temporary.name)
        self.client=TestClient(create_app(self.path,2));self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None);self.temporary.cleanup()
    def observe(self, target, state, number, baseline=False):
        return self.client.post('/api/observations',json={'lane_id':1,'kind':'target','target_id':target,'state':state,'source':'external-test','observed_at':(datetime(2026,10,17,tzinfo=timezone.utc)+timedelta(seconds=number)).isoformat(),'baseline':baseline})

    def test_complete_states_are_independent_of_registered_shots(self):
        with self.client.websocket_connect('/ws') as socket:
            initial=socket.receive_json();self.assertEqual(initial['api_version'],API_VERSION)
            self.assertEqual(initial['health'],'ok');self.assertTrue(initial['capture']['running'])
            self.assertEqual(self.observe(5,'fallen',1,baseline=True).status_code,200)
            state=socket.receive_json();lane=state['lanes']['1']
            self.assertEqual(lane['targets'],['unknown']*4+['fallen'])
            self.assertIsNone(lane['current_bout_id'])
            self.assertNotIn('shots',state)
            assignment=self.client.put('/api/lanes/1/bib',json={'lane_id':1,'bib':42,'expected_revision':lane['revision'],'expected_assignment_revision':lane['assignment_revision']})
            self.assertEqual(assignment.status_code,200)
            state=socket.receive_json();lane=state['lanes']['1'];bout=state['bouts'][lane['current_bout_id']]
            self.assertEqual(bout['bib'],42);self.assertEqual(bout['fallen_target_ids'],[])
            self.assertEqual(lane['targets'][4],'fallen')
            self.observe(2,'fallen',2);state=socket.receive_json()
            self.assertEqual(state['lanes']['1']['targets'],['unknown','fallen','unknown','unknown','fallen'])
            self.assertEqual(state['bouts'][bout['bout_id']]['fallen_target_ids'],[2])
        page=self.client.get('/api/events?after=0&limit=2')
        self.assertEqual(page.headers['cache-control'],'no-store')
        self.assertEqual(page.json()['instance_id'],initial['instance_id'])
        self.assertEqual([event['sequence'] for event in page.json()['events']],[1,2])
        self.assertTrue(page.json()['events'][0]['baseline'])
        later=self.client.get('/api/events?after=2&limit=2').json()
        self.assertEqual([event['sequence'] for event in later['events']],[3])
        self.assertEqual(later['sequence'],3)

    def test_slow_socket_does_not_block_another_client_or_journal(self):
        gate=asyncio.Event();blocked=threading.Event();original=WebSocket.send_json
        async def slow_send(socket, message, *args, **kwargs):
            if message.get('editor_id')==1 and message.get('sequence',0)>0 and not gate.is_set():
                blocked.set();await gate.wait()
            return await original(socket,message,*args,**kwargs)
        with patch.object(WebSocket,'send_json',slow_send):
            with self.client.websocket_connect('/ws') as slow, self.client.websocket_connect('/ws') as fast:
                slow.receive_json();fast.receive_json()
                for number in range(1,13):
                    response=self.observe(5,'fallen' if number%2 else 'standing',number)
                    self.assertEqual(response.status_code,200)
                    if number == 1:
                        self.assertTrue(blocked.wait(timeout=2))
                    self.assertEqual(fast.receive_json()['sequence'],number)
                self.assertTrue(blocked.wait(timeout=2))
                self.assertEqual(len(self.client.get('/api/events').json()['events']),12)
                self.client.portal.call(gate.set)
                self.assertEqual(slow.receive_json()['sequence'],1)
                self.assertEqual(slow.receive_json()['sequence'],12)

    def test_capture_task_failure_is_explicit_without_invented_events(self):
        async def stop_capture():
            self.client.app.state.vision_task.cancel()
            await asyncio.gather(self.client.app.state.vision_task,return_exceptions=True)
        self.client.portal.call(stop_capture)
        self.assertEqual(self.client.get('/api/health').status_code,503)
        with self.client.websocket_connect('/ws') as socket:
            state=socket.receive_json();self.assertEqual(state['health'],'error')
            self.assertFalse(state['capture']['running']);self.assertEqual(state['sequence'],0)

    def test_storage_failure_is_explicit_in_state(self):
        self.client.app.state.store.failed=True
        self.assertEqual(self.client.get('/api/health').status_code,503)
        self.assertEqual(self.client.get('/api/state').json()['health'],'error')

    def test_capture_metadata_contains_no_camera_credentials(self):
        self.client.__exit__(None,None,None)
        with patch('biathlon_target_vision.app.CameraManager',FakeCameras):
            self.client=TestClient(create_app(self.path));self.client.__enter__()
            response=self.client.post('/api/cameras',json={'id':'test','name':'Test','url':'rtsp://user:PRIVATE_PASSWORD@localhost/test','lane_ids':[1,2]})
            self.assertEqual(response.status_code,200)
            with self.client.websocket_connect('/ws') as socket:
                state=socket.receive_json();self.assertNotIn('PRIVATE_PASSWORD',json.dumps(state))
                self.assertEqual(state['capture']['cameras'][0]['lane_ids'],[1,2])
                self.assertTrue(state['capture']['cameras'][0]['connected'])

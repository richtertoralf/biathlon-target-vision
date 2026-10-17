"""Beobachtete Zielanzahl bleibt einlagenbezogen und über Neustarts korrekt."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from biathlon_target_vision.app import create_app
from biathlon_target_vision.core import EventStore
from biathlon_target_vision.models import Assignment, Observation, Release


class MonitorTests(unittest.TestCase):
    def test_count_tracks_positions_and_survives_unknown_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            store = EventStore(directory, 1)
            start = datetime.now(timezone.utc)
            for i, (target, value) in enumerate([(5,'fallen'), (2,'fallen'), (5,'unknown'), (5,'fallen')]):
                store.apply(Observation(lane_id=1, kind='target', source='test', observed_at=start+timedelta(seconds=i), target_id=target, state=value))
            before = store.snapshot(); bout = before['lanes']['1']['current_bout_id']
            self.assertEqual(before['bouts'][bout]['fallen_target_ids'], [5,2])
            store.close(); store = EventStore(directory)
            self.assertEqual(store.snapshot(), before)
            store.apply(Observation(lane_id=1, kind='reset', source='test', observed_at=start+timedelta(seconds=5)))
            self.assertIsNone(store.snapshot()['lanes']['1']['current_bout_id'])
            store.close()

    def test_new_bout_does_not_count_old_fallen_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            with TestClient(create_app(Path(temporary), 1)) as client:
                self.assertEqual(client.get('/monitor').status_code, 200)
                self.assertEqual(client.get('/api/health').json()['status'], 'ok')
                first = client.post('/api/observations', json={'lane_id':1,'kind':'target','target_id':5,'state':'fallen','source':'test','observed_at':'2026-10-17T12:00:00Z'}).json()['state']
                bout = first['lanes']['1']['current_bout_id']
                client.put('/api/lanes/1/bib', json={'lane_id':1,'bib':41,'bout_id':bout,'expected_revision':1})
                client.post('/api/lanes/1/release', json={'lane_id':1,'bout_id':bout,'expected_revision':2})
                state = client.put('/api/lanes/1/bib', json={'lane_id':1,'bib':42,'expected_revision':3}).json()['state']
                current = state['lanes']['1']['current_bout_id']
                self.assertEqual(state['bouts'][current]['fallen_target_ids'], [])

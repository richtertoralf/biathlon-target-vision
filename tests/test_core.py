"""Zuordnungsgrenzen, konkurrierende Bedienung und dauerhafte Wiederherstellung."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from biathlon_target_vision.core import Conflict, EventStore
from biathlon_target_vision.models import Assignment, Observation, Release


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.store = EventStore(self.directory, 3)
        self.time = datetime(2026, 10, 17, tzinfo=timezone.utc)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def lane(self, number=1):
        return self.store.snapshot()["lanes"][str(number)]

    def observe(self, state="fallen", target=1, lane=1, kind="target"):
        self.time += timedelta(seconds=1)
        command = Observation(kind=kind, lane_id=lane, source="test", observed_at=self.time,
                              target_id=target if kind == "target" else None,
                              state=state if kind == "target" else None)
        return self.store.apply(command)

    def assign(self, bib, lane=1, bout=None):
        return self.store.apply(Assignment(lane_id=lane, bib=bib, bout_id=bout,
                                          expected_revision=self.lane(lane)["revision"]))

    def release(self, bout, lane=1):
        return self.store.apply(Release(lane_id=lane, bout_id=bout, expected_revision=self.lane(lane)["revision"]))

    def test_normal_flow_independent_targets_and_correction(self):
        self.observe(kind="reset")
        self.assign(42)
        bout = self.lane()["current_bout_id"]
        for target in (1, 3, 5):
            self.observe(target=target)
        self.assertEqual(self.lane()["targets"], ["fallen", "standing", "fallen", "standing", "fallen"])
        self.assign(43, bout=bout)
        self.assertEqual(self.store.state["bouts"][bout]["bib"], 43)
        self.release(bout)
        self.assertIsNone(self.lane()["occupied_bout_id"])
        self.assertEqual(self.lane()["targets"][0], "fallen")
        self.assertEqual(self.store.state["bouts"][bout]["close_reason"], "release")
        self.assertEqual({e["command"]["kind"] for e in self.store.events}, {"reset", "assign", "target", "release"})

    def test_pending_release_survives_hits_and_reset(self):
        self.assign(22)
        pending = Release(lane_id=1, bout_id=self.lane()["current_bout_id"],
                          expected_revision=self.lane()["revision"],
                          expected_assignment_revision=self.lane()["assignment_revision"])
        self.observe()
        self.observe(kind="reset")
        self.observe(target=3)
        new_bout = self.lane()["current_bout_id"]
        self.store.apply(pending)
        self.assertIsNone(self.lane()["occupied_bout_id"])
        self.assertEqual(self.lane()["current_bout_id"], new_bout)
        before = self.store.snapshot()
        self.store.close()
        self.store = EventStore(self.directory)
        self.assertEqual(before, self.store.snapshot())

    def test_late_bib_preserves_observations(self):
        first = self.observe()
        second = self.observe(target=4)
        bout = self.lane()["current_bout_id"]
        self.assign(101)
        self.assertEqual(self.store.state["bouts"][bout]["observations"], [first["command"]["event_id"], second["command"]["event_id"]])
        self.assertEqual(self.store.state["bouts"][bout]["bib"], 101)

    def test_late_release_never_assigns_next_bout_to_previous_athlete(self):
        self.assign(7)
        old = self.lane()["current_bout_id"]
        self.observe()
        self.observe(kind="reset")
        self.observe(target=2)
        new = self.lane()["current_bout_id"]
        self.assertNotEqual(old, new)
        self.assertIsNone(self.store.state["bouts"][new]["bib"])
        with self.assertRaises(Conflict):
            self.assign(8)
        self.release(old)
        self.assertEqual(self.lane()["current_bout_id"], new)
        self.assign(8, bout=new)
        self.assertEqual(self.store.state["bouts"][old]["bib"], 7)
        self.assertEqual(self.store.state["bouts"][new]["bib"], 8)

    def test_assign_closed_unassigned_bout_explicitly(self):
        self.observe()
        old = self.lane()["current_bout_id"]
        self.observe(kind="reset")
        self.observe(target=2)
        new = self.lane()["current_bout_id"]
        with self.assertRaises(Conflict):
            self.assign(55)
        self.assign(55, bout=old)
        self.assertEqual(self.store.state["bouts"][old]["bib"], 55)
        self.assertIsNone(self.store.state["bouts"][new]["bib"])
        self.assertIsNone(self.lane()["occupied_bout_id"])

    def test_late_bib_after_reset_requires_explicit_bout(self):
        self.observe()
        old = self.lane()["current_bout_id"]
        self.observe(kind="reset")
        with self.assertRaises(Conflict):
            self.assign(12)
        self.assign(12, bout=old)
        self.assertIsNone(self.lane()["occupied_bout_id"])
        self.assertEqual(len(self.store.state["bouts"]), 1)

    def test_conflicting_assignments_are_atomic(self):
        self.assign(1)
        before = self.store.snapshot()
        with self.assertRaises(Conflict):
            self.assign(1, lane=2)
        with self.assertRaises(Conflict):
            self.assign(2)
        with self.assertRaises(Conflict):
            self.assign(2, lane=2, bout=self.lane()["current_bout_id"])
        self.assertEqual(before, self.store.snapshot())

    def test_stale_operator_revision_and_wrong_release(self):
        self.assign(10)
        old = self.lane()["current_bout_id"]
        revision = self.lane()["revision"]
        self.observe()
        with self.assertRaises(Conflict):
            self.store.apply(Release(lane_id=1, bout_id=old, expected_revision=revision))
        self.release(old)
        self.assign(11)
        with self.assertRaises(Conflict):
            self.release(old)

    def test_simultaneous_bib_conflict(self):
        commands = [Assignment(lane_id=i, bib=20, expected_revision=0) for i in (1, 2)]
        def apply(command):
            try:
                self.store.apply(command)
                return True
            except Conflict:
                return False
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(apply, commands)), [False, True])

    def test_idempotence_and_conflicting_id(self):
        event = self.observe()
        command = Observation.model_validate(event["command"])
        self.assertEqual(self.store.apply(command), event)
        self.assertEqual(self.store.state["sequence"], 1)
        with self.assertRaises(Conflict):
            self.store.apply(command.model_copy(update={"state": "standing"}))

    def test_old_target_observation_rejected_across_targets(self):
        self.observe()
        command = Observation(kind="target", lane_id=1, source="camera", observed_at=self.time - timedelta(seconds=1), target_id=3, state="fallen")
        with self.assertRaises(Conflict):
            self.store.apply(command)

    def test_duplicate_state_does_not_create_new_bout(self):
        self.observe()
        bout = self.lane()["current_bout_id"]
        self.release(bout)
        self.observe()
        self.assertIsNone(self.lane()["current_bout_id"])
        self.assertEqual(len(self.store.state["bouts"]), 1)

    def test_partial_reset_closes_bout_without_transferring_bib(self):
        self.assign(11)
        bout = self.lane()["current_bout_id"]
        self.observe()
        self.observe(target=2)
        self.observe(state="standing", target=1)
        self.assertTrue(self.store.state["bouts"][bout]["closed"])
        self.assertEqual(self.lane()["targets"][1], "fallen")
        self.assertEqual(self.lane()["occupied_bout_id"], bout)

    def test_unknown_does_not_invent_shots(self):
        self.observe(state="unknown")
        self.assertEqual(len(self.store.state["bouts"]), 0)
        self.observe()
        self.observe(state="unknown")
        self.assertEqual(self.lane()["targets"][0], "unknown")
        self.assertTrue(all(e["command"]["kind"] == "target" for e in self.store.events))

    def test_unknown_between_fallen_and_standing_still_closes_bout(self):
        self.observe()
        bout = self.lane()["current_bout_id"]
        self.observe(state="unknown")
        self.observe(state="standing")
        self.assertTrue(self.store.state["bouts"][bout]["closed"])

    def test_reappearing_fallen_target_does_not_start_new_bout(self):
        self.observe()
        self.release(self.lane()["current_bout_id"])
        self.observe(state="unknown")
        self.observe()
        self.assertIsNone(self.lane()["current_bout_id"])
        self.assertEqual(len(self.store.state["bouts"]), 1)

    def test_restart_replays_exactly_and_remembers_ids(self):
        event = self.observe()
        self.assign(3)
        self.observe(kind="reset")
        self.observe(target=3)
        before = self.store.snapshot()
        self.store.close()
        self.store = EventStore(self.directory)
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(self.store.apply(Observation.model_validate(event["command"])), event)
        with self.assertRaisesRegex(ValueError, "Bahnanzahl"):
            self.store.close()
            EventStore(self.directory, 4)
        self.store = EventStore(self.directory)

    def test_corrupt_journal_fails_visibly(self):
        self.observe()
        self.store.close()
        with (self.directory / "events.jsonl").open("ab") as file:
            file.write(b'{"sequence":')
        with self.assertRaisesRegex(ValueError, "Journalfehler in Zeile 3"):
            EventStore(self.directory)

    def test_storage_failure_does_not_publish(self):
        before = self.store.snapshot()
        with patch("biathlon_target_vision.core.os.fsync", side_effect=OSError("full")):
            with self.assertRaises(OSError):
                self.observe()
        self.assertEqual(before, self.store.snapshot())
        with self.assertRaises(OSError):
            self.observe()

    def test_second_process_cannot_open_same_journal(self):
        with self.assertRaises(BlockingIOError):
            EventStore(self.directory)

    def test_default_lane_count(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory))
            try:
                self.assertEqual(len(store.state["lanes"]), 20)
            finally:
                store.close()

    def test_multiple_hits_do_not_conflict_with_pending_bib(self):
        pending = Assignment(lane_id=1, bib=99, expected_revision=0,
                             expected_assignment_revision=0, bout_after_sequence=0)
        for number in (1, 2, 4):
            self.observe(target=number)
        bout = self.lane()["current_bout_id"]
        self.assertEqual(self.lane()["assignment_revision"], 0)
        self.store.apply(pending)
        self.assertEqual(self.store.state["bouts"][bout]["bib"], 99)
        self.assertEqual(self.lane()["assignment_revision"], 1)
        self.assertEqual(self.lane()["targets"], ["fallen", "fallen", "unknown", "fallen", "unknown"])

    def test_reset_and_next_bout_do_not_redirect_pending_bib(self):
        pending = Assignment(lane_id=1, bib=99, expected_revision=0,
                             expected_assignment_revision=0, bout_after_sequence=0)
        self.observe()
        old = self.lane()["current_bout_id"]
        self.observe(kind="reset")
        self.observe(target=3)
        new = self.lane()["current_bout_id"]
        self.store.apply(pending)
        self.assertEqual(self.store.state["bouts"][old]["bib"], 99)
        self.assertIsNone(self.store.state["bouts"][new]["bib"])
        self.assertIsNone(self.lane()["occupied_bout_id"])

    def test_assignment_revision_rejects_competing_confirmations(self):
        first = Assignment(lane_id=1, bib=11, expected_revision=0, expected_assignment_revision=0)
        second = Assignment(lane_id=1, bib=12, expected_revision=0, expected_assignment_revision=0)
        self.store.apply(first)
        self.observe()
        with self.assertRaises(Conflict):
            self.store.apply(second)

    def test_legacy_journal_replay_and_retry(self):
        import json
        event = self.assign(9)
        self.store.close()
        path = self.directory / "events.jsonl"
        lines = path.read_text().splitlines()
        stored = json.loads(lines[1])
        stored["command"].pop("expected_assignment_revision")
        stored["command"].pop("bout_after_sequence")
        lines[1] = json.dumps(stored)
        path.write_text("\n".join(lines) + "\n")
        self.store = EventStore(self.directory)
        self.assertEqual(self.lane()["assignment_revision"], 1)
        self.store.apply(Assignment.model_validate(event["command"]))
        self.assertEqual(self.store.state["sequence"], 1)

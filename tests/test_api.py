"""REST, mehrere WebSocket-Bedienplätze und persistente Bildkalibrierung prüfen."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
from fastapi.testclient import TestClient

from biathlon_target_vision.app import create_app
from tests.synthetic import scene


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.client = TestClient(create_app(self.directory, 2))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def observation(self, **changes):
        value = {"event_id": "obs-1", "lane_id": 1, "kind": "target", "source": "camera-1",
                 "observed_at": "2026-10-17T12:00:00Z", "target_id": 2, "state": "fallen"}
        value.update(changes)
        return value

    def test_full_flow_broadcasts_and_reconnects(self):
        with self.client.websocket_connect("/ws") as first, self.client.websocket_connect("/ws") as second:
            for socket in (first, second):
                self.assertEqual(socket.receive_json()["sequence"], 0)
            response = self.client.post("/api/observations", json=self.observation())
            self.assertEqual(response.status_code, 200, response.text)
            one, two = first.receive_json(), second.receive_json()
            self.assertNotEqual(one.pop("editor_id"), two.pop("editor_id"))
            self.assertEqual(one, two)
            self.assertEqual(one["lanes"]["1"]["targets"][1], "fallen")
            assignment = {"lane_id": 1, "bib": 42, "expected_revision": 1}
            self.assertEqual(self.client.put("/api/lanes/1/bib", json=assignment).status_code, 200)
            for socket in (first, second):
                self.assertEqual(socket.receive_json()["bouts"]["obs-1"]["bib"], 42)
            assignment.update(bib=43, bout_id="obs-1", expected_revision=2)
            self.assertEqual(self.client.put("/api/lanes/1/bib", json=assignment).status_code, 200)
            for socket in (first, second):
                self.assertEqual(socket.receive_json()["bouts"]["obs-1"]["bib"], 43)
            self.assertEqual(self.client.post("/api/lanes/1/release", json={"lane_id": 1, "bout_id": "obs-1", "expected_revision": 3}).status_code, 200)
            for socket in (first, second):
                self.assertIsNone(socket.receive_json()["lanes"]["1"]["occupied_bout_id"])
        with self.client.websocket_connect("/ws") as socket:
            self.assertEqual(socket.receive_json()["sequence"], 4)
        page = self.client.get("/api/events?after=1&limit=2").json()
        self.assertEqual([e["sequence"] for e in page["events"]], [2, 3])
        self.assertEqual(page["sequence"], 4)

    def test_repeated_parallel_socket_disconnect_cleans_up(self):
        for _ in range(30):
            with self.client.websocket_connect("/ws") as first, self.client.websocket_connect("/ws") as second:
                self.assertEqual(first.receive_json()["sequence"], 0)
                self.assertEqual(second.receive_json()["sequence"], 0)
        self.assertEqual(self.client.get("/api/state").json()["sequence"], 0)

    def test_repeated_observation_and_validation(self):
        command = self.observation()
        first = self.client.post("/api/observations", json=command)
        self.assertEqual(first.status_code, 200)
        again = self.client.post("/api/observations", json=command)
        self.assertEqual(again.json()["event"], first.json()["event"])
        self.assertEqual(self.client.get("/api/state").json()["sequence"], 1)
        for invalid in ({"target_id": 6}, {"lane_id": "1"}, {"observed_at": "2026-10-17T12:00:00"}, {"state": "miss"}):
            self.assertEqual(self.client.post("/api/observations", json=self.observation(**invalid)).status_code, 422)
        self.assertEqual(self.client.post("/api/observations", json=self.observation(event_id="other", lane_id=99)).status_code, 409)
        self.assertEqual(self.client.post("/api/observations", json=self.observation(state="standing")).status_code, 409)
        self.assertEqual(self.client.post("/api/observations", json=self.observation(event_id="reset", kind="reset")).status_code, 409)
        self.assertEqual(self.client.get("/api/events?after=-1").status_code, 422)

    def test_conflicts_leave_state_unchanged(self):
        self.client.put("/api/lanes/1/bib", json={"lane_id": 1, "bib": 10, "expected_revision": 0})
        before = self.client.get("/api/state").json()
        for url, data, expected in (
            ("/api/lanes/2/bib", {"lane_id": 2, "bib": 10, "expected_revision": 0}, 409),
            ("/api/lanes/1/bib", {"lane_id": 1, "bib": 11, "expected_revision": 0}, 409),
            ("/api/lanes/2/bib", {"lane_id": 1, "bib": 11, "expected_revision": 1}, 422),
        ):
            self.assertEqual(self.client.put(url, json=data).status_code, expected)
        self.assertEqual(self.client.get("/api/state").json(), before)
        self.assertEqual(self.client.put("/api/lanes/1/bib", json={"lane_id": 1, "bib": 11, "bout_id": "", "expected_revision": 1}).status_code, 422)

    def test_api_restart(self):
        self.client.post("/api/observations", json=self.observation())
        before = self.client.get("/api/state").json()
        self.client.__exit__(None, None, None)
        self.client = TestClient(create_app(self.directory))
        self.client.__enter__()
        self.assertEqual(self.client.get("/api/state").json(), before)

    def upload(self, image, quad=None, path="/api/lanes/1/calibration"):
        _, data = cv2.imencode(".png", image)
        return self.client.post(path, files={"image": ("test.png", data.tobytes(), "image/png")},
                                data={"quad": json.dumps(quad)} if quad is not None else {})

    def test_calibration_persistence_alignment_and_failure(self):
        image, quad, _, _ = scene(mask=10)
        response = self.upload(image, quad)
        self.assertEqual(response.status_code, 200, response.text)
        saved = response.json()
        self.assertEqual(self.client.get("/api/lanes/1/calibration").json(), saved)
        moved, _, _, _ = scene(mask=31, shift=(5, 3))
        response = self.upload(moved, path="/api/lanes/1/calibration/align")
        self.assertEqual(response.status_code, 200, response.text)
        invisible, _, _, _ = scene(mask=31, rim=False)
        self.assertEqual(self.upload(invisible, quad).status_code, 422)
        self.assertEqual(self.client.get("/api/lanes/1/calibration").json(), saved)
        self.assertEqual(self.client.get("/api/state").json()["sequence"], 0)
        self.client.__exit__(None, None, None)
        self.client = TestClient(create_app(self.directory))
        self.client.__enter__()
        self.assertEqual(self.client.get("/api/lanes/1/calibration").json(), saved)

    def test_invalid_images_and_roi(self):
        image, quad, _, _ = scene()
        for invalid in ([], {}, "wrong", None, [[0, 1]] * 4):
            _, data = cv2.imencode(".png", image)
            response = self.client.post("/api/lanes/1/calibration", files={"image": ("test.png", data.tobytes())}, data={"quad": json.dumps(invalid)})
            self.assertEqual(response.status_code, 422, response.text)
        response = self.client.post("/api/lanes/1/calibration", files={"image": ("test.png", b"garbage")}, data={"quad": json.dumps(quad)})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.upload(image, quad, "/api/lanes/99/calibration").status_code, 404)
        self.assertEqual(self.upload(image, path="/api/lanes/2/calibration/align").status_code, 422)

    def test_browser_assets_and_openapi(self):
        for path in ("/", "/static/tablet.js", "/static/translations.js", "/static/tablet.css", "/calibration", "/static/calibration.js", "/static/calibration.css", "/openapi.json"):
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_simulation_disabled_by_default(self):
        self.assertFalse(self.client.get("/api/state").json()["simulation"])
        before = self.client.get("/api/state").json()
        response = self.client.post("/api/observations", json=self.observation(source="simulator"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/state").json(), before)
        self.assertEqual(self.client.post("/api/observations", json=self.observation()).status_code, 200)

    def test_simulation_uses_same_journal_with_revision_guard(self):
        self.client.__exit__(None, None, None)
        self.client = TestClient(create_app(self.directory, simulation=True))
        self.client.__enter__()
        self.assertTrue(self.client.get("/api/state").json()["simulation"])
        command = self.observation(source="simulator")
        headers = {"X-Lane-Revision": "0"}
        response = self.client.post("/api/observations", json=command, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post("/api/observations", json=command, headers=headers).status_code, 200)
        reset = self.observation(source="simulator", event_id="reset", kind="reset", target_id=None, state=None, observed_at="2026-10-17T12:00:01Z")
        self.assertEqual(self.client.post("/api/observations", json=reset, headers=headers).status_code, 409)
        self.assertEqual(self.client.post("/api/observations", json=reset, headers={"X-Lane-Revision": "1"}).status_code, 200)
        journal = self.client.get("/api/events").json()["events"]
        self.assertEqual([e["command"]["kind"] for e in journal], ["target", "reset"])
        self.assertTrue(all(e["command"]["source"] == "simulator" for e in journal))

    def test_websocket_heartbeat_does_not_create_events(self):
        with self.client.websocket_connect("/ws") as socket:
            initial = socket.receive_json()
            self.assertEqual(socket.receive_json(), initial)
        self.assertEqual(self.client.get("/api/events").json()["events"], [])

    def test_live_drafts_are_separate_and_never_change_official_state(self):
        before = self.client.get("/api/state").json()
        with self.client.websocket_connect("/ws") as first, self.client.websocket_connect("/ws") as second:
            first_id = first.receive_json()["editor_id"]
            second_id = second.receive_json()["editor_id"]
            first.send_json({"type": "draft", "lane_id": 1, "value": "12"})
            for connection in (first, second):
                message = connection.receive_json()
                self.assertEqual(message["drafts"], [{"editor_id": first_id, "lane_id": 1, "bout_id": None, "value": "12"}])
            second.send_json({"type": "draft", "lane_id": 1, "value": "34", "editor_id": first_id})
            for connection in (first, second):
                by_editor = {draft["editor_id"]: draft["value"] for draft in connection.receive_json()["drafts"]}
                self.assertEqual(by_editor, {first_id: "12", second_id: "34"})
            self.assertEqual(self.client.get("/api/state").json(), before)
            self.assertEqual(self.client.get("/api/events").json()["events"], [])
            # Ein dritter Bedienplatz darf trotz zweier Entwürfe sofort bestätigen.
            response = self.client.put("/api/lanes/1/bib", json={"lane_id": 1, "bib": 56, "expected_revision": 0})
            self.assertEqual(response.status_code, 200)
            for connection in (first, second):
                self.assertEqual(connection.receive_json()["sequence"], 1)
            first.send_json({"type": "draft_clear"})
            for connection in (first, second):
                remaining = connection.receive_json()["drafts"]
                self.assertEqual([draft["editor_id"] for draft in remaining], [second_id])
            second.close()
            self.assertEqual(first.receive_json()["drafts"], [])
        with self.client.websocket_connect("/ws") as restarted:
            self.assertEqual(restarted.receive_json()["drafts"], [])
        self.assertEqual(len(self.client.get("/api/events").json()["events"]), 1)

    def test_abandoned_draft_expires_without_journal_event(self):
        with self.client.websocket_connect("/ws") as socket:
            socket.receive_json()
            socket.send_json({"type": "draft", "lane_id": 1, "value": "77"})
            self.assertEqual(len(socket.receive_json()["drafts"]), 1)
            with patch("biathlon_target_vision.app.monotonic", return_value=10**20):
                self.assertEqual(socket.receive_json()["drafts"], [])
        self.assertEqual(self.client.get("/api/events").json()["events"], [])

    def test_invalid_draft_is_rejected_without_event(self):
        with self.client.websocket_connect("/ws") as socket:
            socket.receive_json()
            socket.send_json({"type": "draft", "lane_id": 1, "value": "not-a-number"})
            self.assertEqual(socket.receive()["code"], 1008)
        self.assertEqual(self.client.get("/api/state").json()["sequence"], 0)

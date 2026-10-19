"""Measure optical capture timing through the real app with synthetic 1080p frames.

Not part of the unit test suite. Run manually, for example on the target server:

    .venv/bin/python -m tests.benchmark_vision --lanes 4 8 12 16 20

Four synthetic cameras deliver 25 frames per second; their lanes sit side by side
in one frame. Measured: classification per lane, one full capture cycle,
stabilisation and the time from a frame change to the WebSocket state.
Not included: camera exposure/encoding, network, MediaMTX relay, RTSP decoding
and browser rendering. These must be measured with real cameras.
"""

import argparse
import json
import random
import resource
import socket
import statistics
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import uvicorn
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from biathlon_target_vision import vision
from biathlon_target_vision.app import create_app
from biathlon_target_vision.calibration import CalibrationStore, calibrate
from biathlon_target_vision.cameras import camera_binding
from biathlon_target_vision.config import CameraSettings, Settings, save_settings
from tests.synthetic import scene

CAMERAS, FPS, WIDTH, HEIGHT = 4, 25, 1920, 1080


class SyntheticCameras:
    """Replace CameraManager: one cached frame per camera and 40 ms frame slot."""
    images = {}

    def __init__(self, cameras):
        self.cache = {}

    def configure(self, cameras):
        pass

    def close(self):
        pass

    def snapshot(self, camera_id):
        number = int(time.monotonic() * FPS)
        cached = self.cache.get(camera_id)
        if cached and cached["frame_number"] == number:
            return cached
        # A changed image becomes visible with the next frame, like a real camera.
        cached = {"frame": self.images[camera_id], "frame_number": number, "connected": True,
                  "stream_epoch": 1, "captured_at": datetime.now(timezone.utc)}
        self.cache[camera_id] = cached
        return cached


class Layout:
    """Lanes of one camera side by side; tiles are prepared outside the measurement."""

    def __init__(self, lane_count):
        self.per_camera = -(-lane_count // CAMERAS)
        self.scale = min(1.0, (WIDTH - 20) / (self.per_camera * 960))
        self.tiles = [scene(mask=0 if k < 0 else 1 << k, scale=self.scale, noise=3) for k in range(-1, 5)]
        self.lane_count = lane_count

    def camera(self, lane_id):
        return f"camera{(lane_id - 1) // self.per_camera + 1}"

    def origin(self, lane_id):
        height = self.tiles[0][0].shape[0]
        return 10 + ((lane_id - 1) % self.per_camera) * int(960 * self.scale), (HEIGHT - height) // 2

    def image(self, camera_id, fallen):
        """fallen maps lane_id to a fallen target index (0-4)."""
        image = np.full((HEIGHT, WIDTH, 3), 60, np.uint8)
        for lane_id in range(1, self.lane_count + 1):
            if self.camera(lane_id) != camera_id:
                continue
            tile = self.tiles[fallen.get(lane_id, -1) + 1][0]
            x, y = self.origin(lane_id)
            image[y:y + tile.shape[0], x:x + tile.shape[1]] = tile
        return image

    def quad(self, lane_id):
        x, y = self.origin(lane_id)
        return (np.array(self.tiles[0][1]) + [x, y]).tolist()


class Recorder:
    """Wrap existing functions without changing them."""

    def __init__(self):
        self.classify, self.steps, self.step_starts = [], [], []
        self.first_seen, self.emitted, self.published = {}, {}, {}

    def patches(self):
        classify, step = vision.classify, vision.VisionService.step
        update, emit = vision.LaneTracker.update, vision.VisionService.emit
        recorder = self

        def timed_classify(image, calibration):
            start = time.perf_counter()
            try:
                return classify(image, calibration)
            finally:
                recorder.classify.append(time.perf_counter() - start)

        async def timed_step(service):
            start = time.monotonic()
            recorder.step_starts.append(start)
            await step(service)
            recorder.steps.append(time.monotonic() - start)

        def timed_update(tracker, states, observed_at, now):
            commands = update(tracker, states, observed_at, now)
            for command in commands:
                key = (command.lane_id, command.target_id, command.state)
                recorder.first_seen[key], recorder.emitted[key] = tracker.since[command.target_id - 1], now
            return commands

        def timed_emit(service, commands):
            emit(service, commands)
            now = time.monotonic()
            for command in commands:
                recorder.published[(command.lane_id, command.target_id, command.state)] = now

        return [patch.object(vision, "classify", timed_classify),
                patch.object(vision.VisionService, "step", timed_step),
                patch.object(vision.LaneTracker, "update", timed_update),
                patch.object(vision.VisionService, "emit", timed_emit),
                patch("biathlon_target_vision.app.CameraManager", SyntheticCameras)]


class StateClient(threading.Thread):
    """Record the receive time of every WebSocket state before parsing it."""

    def __init__(self, url):
        super().__init__(daemon=True)
        self.url, self.condition, self.states = url, threading.Condition(), []

    def run(self):
        with connect(self.url, max_size=None) as websocket:
            while True:
                try:
                    raw = websocket.recv()
                except ConnectionClosed:
                    return  # server shutdown after the measurement
                received = time.monotonic()
                message = json.loads(raw)
                if message.get("type") == "state":
                    with self.condition:
                        self.states.append((received, message))
                        self.condition.notify_all()

    def wait(self, predicate, after, timeout=15):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                for received, message in self.states:
                    if received >= after and predicate(message):
                        return received
                self.states = self.states[-1:]
                if not self.condition.wait(deadline - time.monotonic()):
                    raise TimeoutError("Expected state not received")


def percentiles(values):
    values = sorted(values)
    if not values:
        return "-"
    p95 = values[min(len(values) - 1, int(round(.95 * (len(values) - 1))))]
    return f"median {statistics.median(values) * 1000:.0f} / p95 {p95 * 1000:.0f} / max {values[-1] * 1000:.0f} ms"


def measure(lane_count, trials):
    layout = Layout(lane_count)
    recorder = Recorder()
    with tempfile.TemporaryDirectory(prefix="btv-benchmark-") as temporary:
        directory = Path(temporary)
        cameras = [CameraSettings(id=f"camera{n}", name=f"Camera {n}", url=f"rtsp://synthetic/{n}",
                                  lane_ids=[lane for lane in range(1, lane_count + 1) if layout.camera(lane) == f"camera{n}"])
                   for n in range(1, CAMERAS + 1)]
        save_settings(directory, Settings(cameras=[camera for camera in cameras if camera.lane_ids]))
        store = CalibrationStore(directory)
        SyntheticCameras.images = {camera.id: layout.image(camera.id, {}) for camera in cameras}
        for camera in cameras:
            for lane_id in camera.lane_ids:
                calibration = calibrate(SyntheticCameras.images[camera.id], layout.quad(lane_id))
                calibration.update(camera_binding(camera))
                store.save(lane_id, calibration)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        patches = recorder.patches()
        for item in patches:
            item.start()
        try:
            server = uvicorn.Server(uvicorn.Config(create_app(directory, lane_count), host="127.0.0.1",
                                                   port=port, log_level="warning"))
            server_thread = threading.Thread(target=server.run, daemon=True)
            server_thread.start()
            while not server.started:
                time.sleep(.05)
            client = StateClient(f"ws://127.0.0.1:{port}/ws")
            client.start()
            client.wait(lambda m: all(v == "active" for v in m["capture"]["lanes"].values()), 0, timeout=60)
            # Continuous load without changes; trials below add client and frame building work.
            cpu_start, wall_start = resource.getrusage(resource.RUSAGE_SELF), time.monotonic()
            time.sleep(10)
            cpu_end, wall_end = resource.getrusage(resource.RUSAGE_SELF), time.monotonic()
            recorder.classify.clear(), recorder.steps.clear(), recorder.step_starts.clear()

            single, simultaneous = [], []
            for trial in range(trials):
                lane_id, target = trial % lane_count + 1, trial % 5
                camera_id = layout.camera(lane_id)
                for fallen, state in (({lane_id: target}, "fallen"), ({}, "standing")):
                    time.sleep(random.uniform(.2, .5))  # random phase against the capture cycle
                    image = layout.image(camera_id, fallen)
                    changed = time.monotonic()
                    SyntheticCameras.images[camera_id] = image
                    received = client.wait(lambda m: m["lanes"][str(lane_id)]["targets"][target] == state, changed)
                    key = (lane_id, target + 1, state)
                    single.append({"first_seen": recorder.first_seen[key] - changed,
                                   "stabilize": recorder.emitted[key] - recorder.first_seen[key],
                                   "publish": recorder.published[key] - recorder.emitted[key],
                                   "websocket": received - recorder.published[key],
                                   "total": received - changed})
            # Worst case: every lane changes in the same frame.
            for trial in range(3):
                for fallen, state in (({lane: trial for lane in range(1, lane_count + 1)}, "fallen"), ({}, "standing")):
                    time.sleep(random.uniform(.2, .5))
                    images = {camera.id: layout.image(camera.id, fallen) for camera in cameras}
                    changed = time.monotonic()
                    SyntheticCameras.images.update(images)
                    received = client.wait(lambda m: all(lane["targets"][trial] == state for lane in m["lanes"].values()), changed)
                    simultaneous.append(received - changed)
            # A still running capture loop would distort the next lane count.
            server.should_exit = True
            server_thread.join(timeout=30)
        finally:
            for item in patches:
                item.stop()
    cycles = [b - a for a, b in zip(recorder.step_starts, recorder.step_starts[1:])]
    cpu = (cpu_end.ru_utime + cpu_end.ru_stime - cpu_start.ru_utime - cpu_start.ru_stime) / (wall_end - wall_start)
    print(f"\n{lane_count} lanes ({layout.per_camera} per camera, target diameter about {64 * layout.scale:.0f} px), "
          f"{len(single)} single changes, {len(simultaneous)} all-lane changes, steady process CPU {cpu * 100:.0f} % of one core")
    print(f"  classification per lane:   {percentiles(recorder.classify)}")
    print(f"  step (all lanes):          {percentiles(recorder.steps)}")
    print(f"  cycle incl. 100 ms pause:  {percentiles(cycles)}")
    for name in ("first_seen", "stabilize", "publish", "websocket", "total"):
        print(f"  {name + ':':26} {percentiles([sample[name] for sample in single])}")
    print(f"  all lanes changed, last:   {percentiles(simultaneous)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lanes", type=int, nargs="+", default=[4, 8, 12, 16, 20])
    parser.add_argument("--trials", type=int, default=20)
    arguments = parser.parse_args()
    random.seed(1)
    for count in arguments.lanes:
        measure(count, arguments.trials)

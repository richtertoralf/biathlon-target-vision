"""Optische Zielzustände bestätigen und geordnet an den vorhandenen Kern übergeben."""

import asyncio
from datetime import datetime, timezone
import logging
from time import monotonic

import cv2
import numpy as np

from .calibration import CalibrationError, align_visible
from .cameras import camera_binding
from .core import Conflict
from .models import Observation


def classify(image, calibration):
    """Dunkle Öffnung/helle Klappe relativ zum lokalen Scheibenhintergrund prüfen."""
    aligned, visible = align_visible(image, calibration)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    states = []
    for target in aligned["targets"]:
        if target["target_id"] not in visible:
            states.append("unknown")
            continue
        center = np.array(target["center"])
        polygon = np.array(target["polygon"])
        outer = center + (polygon - center) * 1.45
        x, y, w, h = cv2.boundingRect(outer.astype(np.float32))
        if x < 0 or y < 0 or x + w > gray.shape[1] or y + h > gray.shape[0]:
            states.append("unknown")
            continue
        crop = gray[y:y+h, x:x+w]
        inner = np.zeros(crop.shape, np.uint8)
        background = np.zeros(crop.shape, np.uint8)
        origin = [x, y]
        cv2.fillPoly(inner, [np.int32(center + (polygon-center)*.6-origin)], 1)
        cv2.fillPoly(background, [np.int32(outer-origin)], 1)
        cv2.fillPoly(background, [np.int32(center+(polygon-center)*1.12-origin)], 0)
        inside, outside = crop[inner > 0], crop[background > 0]
        if not len(inside) or not len(outside):
            states.append("unknown")
            continue
        reference = float(np.median(outside))
        level = float(np.median(inside))
        spread = float(np.quantile(inside,.9)-np.quantile(inside,.1))
        if reference < 40 or spread > max(25, reference*.3):
            states.append("unknown")
        elif level / reference < .5:
            states.append("standing")
        elif .78 < level / reference < 1.25:
            states.append("fallen")
        else:
            states.append("unknown")
    return states


class LaneTracker:
    """Drei unabhängige Bilder und mindestens 250 ms je Änderung verlangen."""
    def __init__(self, lane_id, source, initial):
        self.lane_id, self.source = lane_id, source
        self.states = list(initial)
        self.continuous = [False]*5
        self.pending = [None]*5
        self.since = [0.0]*5
        self.counts = [0]*5

    def update(self, states, observed_at, now):
        commands = []
        for index, state in enumerate(states):
            if self.pending[index] != state:
                self.pending[index], self.since[index], self.counts[index] = state, now, 1
            else:
                self.counts[index] += 1
            if self.counts[index] < 3 or now-self.since[index] < .25:
                continue
            baseline = not self.continuous[index]
            if state != "unknown":
                self.continuous[index] = True
            if self.states[index] == state:
                continue
            self.states[index] = state
            commands.append(Observation(lane_id=self.lane_id, kind="target", source=self.source,
                target_id=index+1, state=state, observed_at=observed_at, baseline=baseline))
        return commands

    def disconnected(self, observed_at):
        self.continuous = [False]*5
        self.pending = [None]*5
        self.counts = [0]*5
        commands = []
        for index, state in enumerate(self.states):
            if state != "unknown":
                self.states[index] = "unknown"
                commands.append(Observation(lane_id=self.lane_id,kind="target",source=self.source,
                    target_id=index+1,state="unknown",observed_at=observed_at,baseline=True))
        return commands


class VisionService:
    def __init__(self, settings, cameras, calibrations, store, publish):
        self.settings, self.cameras, self.calibrations = settings, cameras, calibrations
        self.store, self.publish = store, publish
        self.trackers = {}
        self.frames = {}
        self.errors = {}

    def emit(self, commands):
        for command in commands:
            try:
                self.publish(command)
            except Conflict:
                # Ein anderer Beobachter kann eine spätere Zeit geliefert haben.
                logging.warning("Veraltete Kamerabeobachtung für Bahn %s verworfen", command.lane_id)
                self.trackers[command.lane_id][1].states = list(self.store.state["lanes"][str(command.lane_id)]["automatic_targets"])

    def calibration(self, lane_id):
        try:
            calibration = self.calibrations.load(lane_id)
            self.errors.pop(lane_id, None)
            return calibration
        except CalibrationError as error:
            if self.errors.get(lane_id) != str(error):
                logging.error("Kalibrierung Bahn %s: %s", lane_id, error)
            self.errors[lane_id] = str(error)
            return None

    async def step(self):
        configured = set()
        for camera in list(self.settings().cameras):
            capture = self.cameras.snapshot(camera.id)
            for lane_id in camera.lane_ids:
                configured.add(lane_id)
                calibration = self.calibration(lane_id)
                key = (camera.id, camera.url, calibration["created_at"] if calibration else None, capture.get("stream_epoch", 0),
                       self.store.state["lanes"][str(lane_id)]["automatic_generation"])
                if lane_id not in self.trackers or self.trackers[lane_id][0] != key:
                    initial = self.store.state["lanes"][str(lane_id)]["automatic_targets"]
                    self.trackers[lane_id] = (key, LaneTracker(lane_id, f"camera:{camera.id}", initial))
                    self.frames.pop(lane_id, None)
                    self.emit(self.trackers[lane_id][1].disconnected(datetime.now(timezone.utc)))
                tracker = self.trackers[lane_id][1]
                if capture["frame"] is None or not calibration or any(calibration.get(k) != v for k,v in camera_binding(camera).items()):
                    self.emit(tracker.disconnected(datetime.now(timezone.utc)))
                    continue
                frame_key = (capture["captured_at"], capture["frame_number"])
                if self.frames.get(lane_id) == frame_key:
                    continue
                self.frames[lane_id] = frame_key
                try:
                    states = await asyncio.to_thread(classify, capture["frame"], calibration)
                except CalibrationError:
                    states = ["unknown"]*5
                # Kamera oder Kalibrierung kann während der CPU-Arbeit geändert werden.
                current = next((c for c in self.settings().cameras if lane_id in c.lane_ids), None)
                saved = self.calibration(lane_id)
                if (current != camera or saved != calibration or
                        self.store.state["lanes"][str(lane_id)]["automatic_generation"] != key[-1]):
                    continue
                latest = self.cameras.snapshot(camera.id)
                # Auch eine zwischen zwei Auswertungen erfolgte Wiederverbindung
                # unterbricht die Beobachtungskette; der Ausfall muss nicht sichtbar gewesen sein.
                if not latest["connected"] or latest.get("stream_epoch", 0) != capture.get("stream_epoch", 0):
                    self.emit(tracker.disconnected(datetime.now(timezone.utc)))
                    continue
                self.emit(tracker.update(states, capture["captured_at"], monotonic()))
        for lane_id in set(self.trackers)-configured:
            self.emit(self.trackers[lane_id][1].disconnected(datetime.now(timezone.utc)))
            del self.trackers[lane_id]
            self.frames.pop(lane_id, None)

    async def run(self):
        try:
            while True:
                await self.step()
                await asyncio.sleep(.1)
        except Exception:
            logging.exception("Optische Erfassung wurde durch einen Fehler gestoppt")
            raise

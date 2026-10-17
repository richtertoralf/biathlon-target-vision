"""Ein RTSP-Decoder je Kamera; nur das neueste Bild im gemeinsamen Prozess halten."""

from datetime import datetime, timezone
from hashlib import sha256
import os
import threading
from time import monotonic

# Native Decoder dürfen vollständige RTSP-Adressen mit Zugangsdaten nicht loggen.
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
import cv2


def camera_binding(camera):
    return {"camera_id": camera.id, "camera_url_hash": sha256(camera.url.encode()).hexdigest()}


class CameraReader:
    def __init__(self, camera):
        self.camera = camera
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.frame = None
        self.frame_number = 0
        self.captured_at = None
        self.updated = 0.0
        self.connected = False
        self.thread = threading.Thread(target=self._read, name=f"camera-{camera.id}", daemon=True)
        self.thread.start()

    def _read(self):
        while not self.stop.is_set():
            capture = None
            try:
                capture = cv2.VideoCapture(self.camera.url, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2000,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000])
                while not self.stop.is_set() and capture.isOpened():
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        break
                    with self.lock:
                        self.frame = frame
                        self.frame_number += 1
                        self.captured_at = datetime.now(timezone.utc)
                        self.updated = monotonic()
                        self.connected = True
            except (cv2.error, OSError):
                # Status zeigt den Ausfall; native Fehlermeldungen könnten Secrets enthalten.
                pass
            finally:
                if capture is not None:
                    capture.release()
                with self.lock:
                    self.connected = False
                    self.frame = None
            self.stop.wait(1)

    def snapshot(self):
        with self.lock:
            fresh = self.connected and monotonic() - self.updated < 3
            return {"connected": fresh, "frame_number": self.frame_number,
                    "captured_at": self.captured_at, "frame": self.frame if fresh else None}

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError(f"Kameratreiber {self.camera.id} beendet sich nicht innerhalb des Lesezeitlimits")


class CameraManager:
    def __init__(self, cameras):
        self.readers = {}
        self.configure(cameras)

    def configure(self, cameras):
        wanted = {camera.id: camera for camera in cameras}
        for camera_id, reader in list(self.readers.items()):
            if camera_id not in wanted or wanted[camera_id].url != reader.camera.url:
                reader.close()
                del self.readers[camera_id]
        for camera in cameras:
            if camera.id not in self.readers:
                self.readers[camera.id] = CameraReader(camera)

    def close(self):
        for reader in self.readers.values():
            reader.close()

    def snapshot(self, camera_id):
        reader = self.readers.get(camera_id)
        return reader.snapshot() if reader else {"connected": False, "frame": None, "frame_number": 0, "captured_at": None}

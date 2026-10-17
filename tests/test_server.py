"""Echten Uvicorn-Prozess mit Simulator, HTTP/WebSocket und Neustart prüfen."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import urlopen

from websockets.sync.client import connect


class ServerTests(unittest.TestCase):
    def test_simulator_and_restart_over_network(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as socket_handle:
                socket_handle.bind(("127.0.0.1", 0))
                port = socket_handle.getsockname()[1]
            url = f"http://127.0.0.1:{port}"
            command = [sys.executable, "-m", "biathlon_target_vision", "--port", str(port),
                       "--data-dir", directory, "--lanes", "4", "--simulation"]
            process = None
            with (Path(directory) / "server.log").open("w+") as log:
                def start():
                    child = subprocess.Popen(command, stdout=log, stderr=log)
                    try:
                        for _ in range(100):
                            if child.poll() is not None:
                                break
                            try:
                                with urlopen(url + "/api/state", timeout=.2) as response:
                                    return child, json.load(response)
                            except (URLError, TimeoutError):
                                time.sleep(.05)
                        log.seek(0)
                        self.fail(f"Serverstart fehlgeschlagen: {log.read()}")
                    except BaseException:
                        child.terminate()
                        child.wait(timeout=10)
                        raise

                try:
                    process, initial = start()
                    self.assertEqual(len(initial["lanes"]), 4)
                    with connect(f"ws://127.0.0.1:{port}/ws") as websocket:
                        self.assertEqual(json.loads(websocket.recv(timeout=3))["sequence"], 0)
                        for args in (("reset", "1"), ("hit", "1", "2"), ("hit", "1", "4")):
                            result = subprocess.run([sys.executable, "-m", "biathlon_target_vision.simulator", *args, "--url", url],
                                                    text=True, capture_output=True, timeout=10)
                            self.assertEqual(result.returncode, 0, result.stderr)
                            state = json.loads(result.stdout)["state"]
                            self.assertEqual(json.loads(websocket.recv(timeout=3))["sequence"], state["sequence"])
                    self.assertEqual(state["lanes"]["1"]["targets"], ["standing", "fallen", "standing", "fallen", "standing"])
                    process.terminate()
                    process.wait(timeout=10)
                    process, restored = start()
                    state.pop("type")
                    self.assertNotEqual(restored.pop("instance_id"), state.pop("instance_id"))
                    self.assertEqual(restored, state)
                finally:
                    if process is not None and process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)

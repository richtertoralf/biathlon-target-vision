"""Isolierte Kamera und BTV-Server für den Browser-Integrationstest bereitstellen."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

from tests.rtsp_support import rtsp_stream
from tests.synthetic import scene

if __name__ == '__main__':
    image, quad, _, _ = scene(mask=10)
    with rtsp_stream(image) as (rtsp, publisher), tempfile.TemporaryDirectory(prefix='btv-camera-browser-') as temporary:
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0)); port=reservation.getsockname()[1]
        with (Path(temporary)/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','biathlon_target_vision','--port',str(port),'--data-dir',temporary,'--lanes','3'],stdout=log,stderr=log)
            try:
                print(json.dumps({'url':f'http://127.0.0.1:{port}','rtsp':rtsp,'quad':quad}),flush=True)
                sys.stdin.readline()
            finally:
                server.terminate()
                try:server.wait(timeout=15)
                except subprocess.TimeoutExpired:server.kill();server.wait()

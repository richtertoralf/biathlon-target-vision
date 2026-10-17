"""Lokaler RTSP-Teststream mit extern bereitgestelltem MediaMTX und FFmpeg."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

import cv2


def available():
    return bool(shutil.which('ffmpeg') and shutil.which('mediamtx'))


@contextmanager
def rtsp_stream(image):
    with tempfile.TemporaryDirectory(prefix='btv-rtsp-') as temporary:
        directory = Path(temporary)
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
        config = directory / 'mediamtx.yml'
        config.write_text(f'''logLevel: error
rtspAddress: 127.0.0.1:{port}
rtspTransports: [tcp]
rtmp: no
hls: no
webrtc: no
srt: no
moq: no
playback: no
paths:
  test:
    source: publisher
''')
        cv2.imwrite(str(directory / 'frame.png'), image)
        publisher = None
        with (directory/'media.log').open('w+') as log:
            media = subprocess.Popen(['mediamtx', str(config)], stdout=log, stderr=log, cwd=directory)
            try:
                for _ in range(100):
                    if media.poll() is not None:
                        log.seek(0); raise RuntimeError(log.read())
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.1): break
                    except OSError: time.sleep(.05)
                url = f'rtsp://127.0.0.1:{port}/test'
                publisher = subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-re','-loop','1','-i',str(directory/'frame.png'),'-c:v','libx264','-threads','1','-preset','ultrafast','-tune','zerolatency','-pix_fmt','yuv420p','-r','10','-g','10','-f','rtsp','-rtsp_transport','tcp',url],stdout=log,stderr=log)
                time.sleep(.5)
                yield url, publisher
            finally:
                for process in (publisher, media):
                    if process is not None:
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: process.kill(); process.wait()

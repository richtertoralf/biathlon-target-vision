"""Zentrale Bahnverwaltung und Kalibrierung mechanischer Biathlonziele."""

import os

# OpenCV vor dem ersten Import konfigurieren: RTSP-Zugangsdaten nicht loggen.
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"

__version__ = "0.6.0"

API_VERSION = 1

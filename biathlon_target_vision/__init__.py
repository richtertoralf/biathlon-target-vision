"""Zentrale Bahnverwaltung und Kalibrierung mechanischer Biathlonziele."""

import os

# OpenCV vor dem ersten Import konfigurieren: RTSP-Zugangsdaten nicht loggen.
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"

__version__ = "0.8.5"

API_VERSION = 2

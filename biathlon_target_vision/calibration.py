"""Fünf sichtbare Scheibenkonturen in einer Gesamt-ROI finden und begrenzt nachführen."""

from datetime import datetime, timezone
from itertools import combinations
import json
import os
from pathlib import Path
import tempfile

import cv2
import numpy as np


class CalibrationError(ValueError):
    pass


def validate_quad(image, quad):
    try:
        points = np.asarray(quad, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise CalibrationError("ROI benötigt vier numerische Bildpunkte.") from exc
    h, w = image.shape[:2]
    if points.shape != (4, 2) or not np.isfinite(points).all():
        raise CalibrationError("ROI benötigt vier endliche Bildpunkte: oben links, oben rechts, unten rechts, unten links.")
    if (points < 0).any() or (points[:, 0] >= w).any() or (points[:, 1] >= h).any():
        raise CalibrationError("ROI liegt außerhalb des Bildes.")
    if not cv2.isContourConvex(points) or cv2.contourArea(points, oriented=True) < 200:
        raise CalibrationError("ROI muss ein ausreichend großes, nicht gekreuztes Viereck sein.")
    if points[0, 0] >= points[1, 0] or points[3, 0] >= points[2, 0] or points[:2, 1].mean() >= points[2:, 1].mean():
        raise CalibrationError("ROI-Ecken in der Reihenfolge oben links, oben rechts, unten rechts, unten links markieren.")
    return points


def _rectify(image, quad):
    points = validate_quad(image, quad)
    width = (np.linalg.norm(points[1] - points[0]) + np.linalg.norm(points[2] - points[3])) / 2
    height = (np.linalg.norm(points[3] - points[0]) + np.linalg.norm(points[2] - points[1])) / 2
    if width < 100 or height < 24 or not 2 < width / height < 15:
        raise CalibrationError("Scheibenbereich zu klein oder ungeeignetes Seitenverhältnis.")
    # Begrenzte Arbeitsauflösung hält Aufwand unabhängig von der Kameragröße.
    size = (1000, int(np.clip(1000 * height / width, 100, 500)))
    destination = np.float32([[0, 0], [size[0] - 1, 0], [size[0] - 1, size[1] - 1], [0, size[1] - 1]])
    matrix = cv2.getPerspectiveTransform(points, destination)
    return cv2.warpPerspective(image, matrix, size), matrix


def _candidates(gray):
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    # Lokaler Kontrast erfasst dunkle Öffnungen und helle Klappen mit dunklem
    # Rand auch bei einem Helligkeitsverlauf über die gesamte Zielreihe.
    binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 51, 5)
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    h, w = gray.shape
    candidates = []
    for contour in contours:
        if len(contour) < 20:
            continue
        (x, y), (a, b), angle = cv2.fitEllipse(contour)
        if not (w * .025 < min(a, b) <= max(a, b) < min(w * .19, h * .92)):
            continue
        if min(a, b) / max(a, b) < .5:
            continue
        # Kleine Kontrastlücken dürfen die Kontur öffnen. Die Hülle und die
        # Winkelabdeckung müssen dennoch eine fast vollständige Ellipse belegen.
        area_ratio = cv2.contourArea(cv2.convexHull(contour)) / (np.pi * a * b / 4)
        if not .85 < area_ratio < 1.12:
            continue
        xy = contour.reshape(-1, 2) - [x, y]
        theta = np.deg2rad(angle)
        rotation = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
        unit = (xy @ rotation) / [a / 2, b / 2]
        residual = np.abs(np.linalg.norm(unit, axis=1) - 1)
        # The median tolerates a few frayed spots: on 4K overview cameras holes have
        # only ~18 px and JPEG noise and colour fringes fray the upscaled outline.
        # Squares still deviate along the whole outline (median > .08).
        if np.median(residual) > .06:
            continue
        angles = np.arctan2(unit[:, 1], unit[:, 0])
        if np.count_nonzero(np.histogram(angles, bins=24, range=(-np.pi, np.pi))[0]) < 22:
            continue
        if x - max(a, b) / 2 < 2 or x + max(a, b) / 2 >= w - 2:
            continue
        if y - max(a, b) / 2 < 2 or y + max(a, b) / 2 >= h - 2:
            continue
        candidates.append((float(x), float(y), float(a), float(b), float(angle)))
    # Ränder erzeugen Innen-/Außenkonturen. Pro Zentrum bleibt der äußere Rand.
    unique = []
    for candidate in sorted(candidates, key=lambda c: c[2] * c[3], reverse=True):
        if not any(np.linalg.norm(np.array(candidate[:2]) - other[:2]) < min(other[2:4]) * .3 for other in unique):
            unique.append(candidate)
    if len(unique) > 25:
        raise CalibrationError("Zu viele mögliche Scheiben. ROI enger um eine einzelne Bahn markieren.")
    return sorted(unique, key=lambda c: c[0])


def _select_row(candidates):
    plausible = []
    for row in combinations(candidates, 5):
        centers = np.array([c[:2] for c in row])
        diameters = np.array([np.sqrt(c[2] * c[3]) for c in row])
        steps = np.diff(centers[:, 0])
        spacing = steps.mean()
        if spacing <= 0:
            continue
        spacing_error = np.max(np.abs(steps / spacing - 1))
        size_error = np.max(np.abs(diameters / np.median(diameters) - 1))
        line = np.polyfit(centers[:, 0], centers[:, 1], 1)
        line_error = np.max(np.abs(np.polyval(line, centers[:, 0]) - centers[:, 1])) / spacing
        if spacing_error > .16 or size_error > .23 or line_error > .07 or abs(line[0]) > .25:
            continue
        if not 1.2 < spacing / diameters.mean() < 4:
            continue
        score = float(spacing_error + size_error + line_error)
        plausible.append((score, row))
    if not plausible:
        raise CalibrationError("Keine eindeutige Reihe aus fünf sichtbaren Scheiben erkannt. ROI, Schärfe, Kontrast und freie Sicht prüfen.")
    plausible.sort(key=lambda item: item[0])
    # Auch eine etwas schlechtere zweite vollständige Reihe ist mehrdeutig.
    if len(plausible) > 1:
        raise CalibrationError("Mehrere plausible Scheibenreihen erkannt. ROI auf genau eine Schießbahn begrenzen.")
    return plausible[0]


def calibrate(image, quad):
    rectified, matrix = _rectify(image, quad)
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY)
    score, row = _select_row(_candidates(gray))
    inverse = np.linalg.inv(matrix)
    targets = []
    for number, (x, y, a, b, angle) in enumerate(row, start=1):
        theta = np.deg2rad(angle)
        angles = np.linspace(0, 2 * np.pi, 32, endpoint=False)
        ellipse = np.column_stack((np.cos(angles) * a / 2, np.sin(angles) * b / 2))
        rotation = np.array([[np.cos(theta), np.sin(theta)], [-np.sin(theta), np.cos(theta)]])
        outline = ellipse @ rotation + [x, y]
        polygon = cv2.perspectiveTransform(outline.astype(np.float32).reshape(1, -1, 2), inverse)[0]
        center = cv2.perspectiveTransform(np.float32([[[x, y]]]), inverse)[0, 0]
        targets.append({"target_id": number, "center": center.tolist(), "polygon": polygon.tolist()})
    return {"schema_version": 1, "image_size": [image.shape[1], image.shape[0]],
            "quad": np.asarray(quad).tolist(), "targets": targets,
            "geometry_error": score, "offset": [0.0, 0.0],
            "created_at": datetime.now(timezone.utc).isoformat()}


def align(image, calibration):
    if calibration["image_size"] != [image.shape[1], image.shape[0]]:
        raise CalibrationError("Bildgröße hat sich geändert. Neu kalibrieren.")
    detected = calibrate(image, calibration["quad"])
    original = np.array([t["center"] for t in calibration["targets"]])
    current = np.array([t["center"] for t in detected["targets"]])
    shifts = current - original
    shift = np.median(shifts, axis=0)
    spacing = np.linalg.norm(np.diff(original, axis=0), axis=1).mean()
    # Immer gegen die gespeicherte Grundkalibrierung: keine schleichende Drift.
    if np.linalg.norm(shift) > min(24, spacing * .2) or np.max(np.linalg.norm(shifts - shift, axis=1)) > max(2, spacing * .04):
        raise CalibrationError("Bildbewegung zu groß oder uneinheitlich. Neu kalibrieren.")
    detected["offset"] = shift.tolist()
    return detected


class CalibrationStore:
    def __init__(self, directory: Path):
        self.directory = directory / "calibrations"
        self.directory.mkdir(parents=True, exist_ok=True)

    def load(self, lane_id):
        path = self.directory / f"lane-{lane_id}.json"
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text())
            if value["schema_version"] != 1 or len(value["targets"]) != 5:
                raise ValueError("Falsches Format")
            size = value["image_size"]
            if len(size) != 2 or any(type(n) is not int or n <= 0 for n in size):
                raise ValueError("Ungültige Bildgröße")
            arrays = [(value["quad"], (4, 2)), (value["offset"], (2,))]
            for number, target in enumerate(value["targets"], start=1):
                if target["target_id"] != number:
                    raise ValueError("Ungültige Scheibenreihenfolge")
                arrays.extend([(target["center"], (2,)), (target["polygon"], (32, 2))])
            for coordinates, shape in arrays:
                array = np.asarray(coordinates, dtype=float)
                if array.shape != shape or not np.isfinite(array).all():
                    raise ValueError("Ungültige Scheibenkoordinaten")
            if not isinstance(value["created_at"], str):
                raise ValueError("Ungültige Speicherzeit")
            return value
        except (ValueError, KeyError, TypeError) as exc:
            raise CalibrationError(f"Gespeicherte Kalibrierung für Bahn {lane_id} ist beschädigt: {exc}") from exc

    def save(self, lane_id, value):
        # Eine fehlgeschlagene Erkennung erreicht diese Methode nicht.
        path = self.directory / f"lane-{lane_id}.json"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.directory, delete=False) as file:
                temporary = Path(file.name)
                json.dump(value, file, ensure_ascii=False, allow_nan=False)
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(path)
            descriptor = os.open(self.directory, os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary and temporary.exists():
                temporary.unlink()


def align_visible(image, calibration):
    """Vorhandene Nachführung nutzen, bei Verdeckung mindestens drei Anker prüfen."""
    try:
        return align(image, calibration), set(range(1, 6))
    except CalibrationError:
        pass
    if calibration["image_size"] != [image.shape[1], image.shape[0]]:
        raise CalibrationError("Bildgröße geändert")
    rectified, matrix = _rectify(image, calibration["quad"])
    candidates = _candidates(cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY))
    original = np.array([target["center"] for target in calibration["targets"]])
    spacing = np.linalg.norm(np.diff(original, axis=0), axis=1).mean()
    limit = min(24, spacing * .2)
    inverse = np.linalg.inv(matrix)
    matched = {}
    for candidate in candidates:
        center = cv2.perspectiveTransform(np.float32([[[candidate[0], candidate[1]]]]), inverse)[0, 0]
        distances = np.linalg.norm(original - center, axis=1)
        index = int(np.argmin(distances))
        if distances[index] <= limit:
            if index in matched:
                raise CalibrationError("Mehrdeutige Scheibenkonturen")
            matched[index] = center - original[index]
    if len(matched) < 3:
        raise CalibrationError("Weniger als drei sichtbare Geometrieanker")
    shift = np.median(list(matched.values()), axis=0)
    visible = {index + 1 for index, value in matched.items()
               if np.linalg.norm(value - shift) <= max(2, spacing * .04)}
    if len(visible) < 3:
        raise CalibrationError("Uneinheitliche Bildbewegung")
    if not {1, 5}.issubset(visible):
        # Ohne beide Endanker könnte eine Verschiebung um einen Zielabstand
        # dieselben Innenpositionen als vermeintlich gültige Nachbarn liefern.
        raise CalibrationError("Bei Teilverdeckung müssen beide äußeren Scheiben sichtbar sein")
    # Nur eine begrenzte Translation von der festen Basis, keine fortgesetzte Drift.
    from copy import deepcopy
    result = deepcopy(calibration)
    result["offset"] = shift.tolist()
    for target in result["targets"]:
        target["center"] = (np.array(target["center"]) + shift).tolist()
        target["polygon"] = (np.array(target["polygon"]) + shift).tolist()
    return result, visible

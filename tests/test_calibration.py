"""Automatische Genauigkeits- und Ablehnungstests mit bekannten Bildkoordinaten."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from biathlon_target_vision.calibration import CalibrationError, CalibrationStore, align, calibrate
from tests.synthetic import scene


class CalibrationTests(unittest.TestCase):
    def test_accuracy_all_states_perspectives_scales_and_lighting(self):
        errors, overlaps = [], []
        count = 0
        for perspective in range(3):
            for scale, brightness in ((.65, .45), (1, .85), (1.35, 1.15)):
                for mask in range(32):
                    with self.subTest(perspective=perspective, scale=scale, mask=mask):
                        image, quad, expected, polygons = scene(mask, scale, perspective, brightness, noise=2)
                        result = calibrate(image, quad)
                        centers = np.array([target["center"] for target in result["targets"]])
                        distance = np.linalg.norm(centers - expected, axis=1)
                        errors.extend(distance.tolist())
                        self.assertLess(float(distance.max()), 2.5)
                        self.assertEqual([t["target_id"] for t in result["targets"]], [1, 2, 3, 4, 5])
                        self.assertTrue(np.all(np.diff(centers[:, 0]) > 0))
                        for target, polygon in zip(result["targets"], polygons):
                            truth = np.zeros(image.shape[:2], np.uint8)
                            actual = truth.copy()
                            cv2.fillPoly(truth, [np.round(polygon).astype(np.int32)], 1)
                            cv2.fillPoly(actual, [np.round(target["polygon"]).astype(np.int32)], 1)
                            iou = np.count_nonzero(truth & actual) / np.count_nonzero(truth | actual)
                            overlaps.append(iou)
                            self.assertGreater(iou, .78)
                        count += 1
        print(f"\nKalibrierung: {count} Bilder, {len(errors)} Ziele; "
              f"Zentrumsfehler Mittel={np.mean(errors):.3f}px, Maximum={max(errors):.3f}px; "
              f"Flächen-IoU Mittel={np.mean(overlaps):.3f}, Minimum={min(overlaps):.3f}")

    def test_missing_or_invisible_target_is_not_invented(self):
        for kwargs in ({"missing": 2}, {"mask": 31, "rim": False}):
            image, quad, _, _ = scene(**kwargs)
            with self.assertRaises(CalibrationError):
                calibrate(image, quad)

    def test_blank_noisy_and_rectangular_images_rejected(self):
        image, quad, _, _ = scene()
        blank = np.full_like(image, 150)
        noise = np.random.default_rng(4).integers(0, 255, image.shape, dtype=np.uint8)
        rectangles = blank.copy()
        for x in range(210, 700, 120):
            cv2.rectangle(rectangles, (x - 25, 205), (x + 25, 255), (0, 0, 0), -1)
        for frame in (blank, noise, rectangles):
            with self.assertRaises(CalibrationError):
                calibrate(frame, quad)

    def test_ambiguous_rows_rejected(self):
        image = np.full((360, 800, 3), 220, np.uint8)
        for y in (100, 250):
            for x in (120, 260, 400, 540, 680):
                cv2.circle(image, (x, y), 30, (25, 25, 25), -1)
        with self.assertRaisesRegex(CalibrationError, "Mehrere"):
            calibrate(image, [[20, 20], [780, 20], [780, 340], [20, 340]])

    def test_invalid_quad_rejected(self):
        image, quad, _, _ = scene()
        for bad in (quad[:3], [[-1, 0], *quad[1:]], [quad[0], quad[2], quad[1], quad[3]], [[float("nan"), 0]] * 4):
            with self.assertRaises(CalibrationError):
                calibrate(image, bad)

    def test_small_translation_with_changed_target_states(self):
        image, quad, _, _ = scene(mask=0)
        base = calibrate(image, quad)
        moved, _, expected, _ = scene(mask=21, shift=(7, -4))
        result = align(moved, base)
        self.assertTrue(np.allclose(result["offset"], [7, -4], atol=1))
        self.assertLess(float(np.linalg.norm(np.array([t["center"] for t in result["targets"]]) - expected, axis=1).max()), 2.5)
        self.assertEqual(base["offset"], [0, 0])

    def test_large_movement_and_changed_resolution_rejected(self):
        image, quad, _, _ = scene()
        base = calibrate(image, quad)
        moved, _, _, _ = scene(shift=(35, 0))
        with self.assertRaises(CalibrationError):
            align(moved, base)
        with self.assertRaises(CalibrationError):
            align(image[::2, ::2], base)

    def test_persist_and_reload(self):
        image, quad, _, _ = scene()
        calibration = calibrate(image, quad)
        with tempfile.TemporaryDirectory() as directory:
            store = CalibrationStore(Path(directory))
            store.save(1, calibration)
            self.assertEqual(CalibrationStore(Path(directory)).load(1), calibration)
            self.assertIsNone(store.load(2))

    def test_corrupt_calibration_fails_visibly(self):
        image, quad, _, _ = scene()
        calibration = calibrate(image, quad)
        with tempfile.TemporaryDirectory() as directory:
            store = CalibrationStore(Path(directory))
            calibration["targets"][0]["center"] = ["invalid", 1]
            store.save(1, calibration)
            with self.assertRaisesRegex(CalibrationError, "beschädigt"):
                store.load(1)

    def test_failed_save_preserves_previous_calibration(self):
        image, quad, _, _ = scene()
        calibration = calibrate(image, quad)
        with tempfile.TemporaryDirectory() as directory:
            store = CalibrationStore(Path(directory))
            store.save(1, calibration)
            with patch("biathlon_target_vision.calibration.os.fsync", side_effect=OSError("full")):
                with self.assertRaises(OSError):
                    store.save(1, {**calibration, "offset": [3, 4]})
            self.assertEqual(store.load(1), calibration)
            self.assertEqual(len(list(store.directory.iterdir())), 1)

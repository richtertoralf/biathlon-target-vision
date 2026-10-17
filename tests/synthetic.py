"""Deterministische Scheibenbilder mit Referenzgeometrie, ohne Kameramaterial."""

import cv2
import numpy as np


def scene(mask=0, scale=1.0, perspective=0, brightness=1.0, noise=0, shift=(0, 0), missing=None, rim=True):
    board = np.full((180, 640, 3), 218, np.uint8)
    centers = np.float32([[80 + i * 120, 90] for i in range(5)])
    for i, (x, y) in enumerate(centers.astype(int)):
        if i == missing:
            continue
        color = (218,) * 3 if mask & (1 << i) else (25,) * 3
        cv2.circle(board, (x, y), 32, color, -1, cv2.LINE_AA)
        if rim:
            cv2.circle(board, (x, y), 32, (90,) * 3, 2, cv2.LINE_AA)
    destinations = [
        [[140, 140], [780, 140], [780, 320], [140, 320]],
        [[130, 110], [800, 160], [750, 335], [160, 290]],
        [[140, 150], [820, 90], [750, 340], [200, 300]],
    ]
    quad = np.float32(destinations[perspective]) * scale + np.float32(shift)
    matrix = cv2.getPerspectiveTransform(np.float32([[0, 0], [639, 0], [639, 179], [0, 179]]), quad)
    image = cv2.warpPerspective(board, matrix, (int(960 * scale), int(440 * scale)), borderValue=(55, 65, 75))
    h, w = image.shape[:2]
    gradient = np.linspace(.75, 1.1, w)[None, :, None]
    pixels = image.astype(float) * brightness * gradient
    pixels += np.random.default_rng(42).normal(0, noise, (h, w, 1))
    image = np.clip(pixels, 0, 255).astype(np.uint8)
    image = cv2.GaussianBlur(image, (3, 3), .6)
    expected = cv2.perspectiveTransform(centers.reshape(1, -1, 2), matrix)[0]
    polygons = []
    for center in centers:
        theta = np.linspace(0, 2 * np.pi, 64, endpoint=False)
        circle = center + np.column_stack((32 * np.cos(theta), 32 * np.sin(theta)))
        polygons.append(cv2.perspectiveTransform(circle.astype(np.float32).reshape(1, -1, 2), matrix)[0])
    return image, quad.tolist(), expected, polygons


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Synthetisches Kalibrierungsbild erzeugen")
    parser.add_argument("--output", type=Path, default=Path(".test-artifacts/calibration.png"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image, quad, _, _ = scene(mask=10, perspective=1)
    if not cv2.imwrite(str(args.output), image):
        raise OSError("Testbild konnte nicht geschrieben werden.")
    print(json.dumps({"image": str(args.output), "quad": quad}, ensure_ascii=False))

#!/usr/bin/env python3
"""Turn the segmented face crop into a compact ASCII portrait with eye sockets."""

import json
import math
import sys
from pathlib import Path

from PIL import Image


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: make_face_art.py <face-crop.png> <face-meta.json> <face-art.js>")

    image_path = Path(sys.argv[1])
    meta_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])

    image = Image.open(image_path).convert("RGBA")
    meta = json.loads(meta_path.read_text())

    width, height = image.size
    cols = 52
    rows = max(2, round(cols * height / width * 0.5))

    # Keep the head centered but force a little margin around the artwork.
    grid = [[" " for _ in range(cols)] for _ in range(rows)]
    ramp = "@%#*+=-:. "

    for row in range(rows):
        for col in range(cols):
            src_x = min(width - 1, int(col * width / cols))
            src_y = min(height - 1, int(row * height / rows))
            r, g, b, a = image.getpixel((src_x, src_y))
            if a < 90:
                continue
            luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
            contrast = 255.0 * ((luminance / 255.0) ** 1.12)
            index = min(len(ramp) - 1, int((255.0 - contrast) * len(ramp) / 256.0))
            grid[row][col] = ramp[index]

    # Blank the eye areas; the page script draws moving pupils there.
    eye_centers = []
    image_w, image_h = meta["image"]["width"], meta["image"]["height"]
    for eye in meta["eyes"]:
        col = round(eye["x"] / image_w * (cols - 1))
        row = round(eye["y"] / image_h * (rows - 1))
        col = max(2, min(cols - 3, col))
        row = max(1, min(rows - 2, row))
        for dy in (-1, 0, 1):
            for dx in (-2, -1, 0, 1, 2):
                if 0 <= row + dy < rows and 0 <= col + dx < cols:
                    grid[row + dy][col + dx] = " "
        eye_centers.append({"x": col, "y": row})

    lines = ["".join(row).rstrip() for row in grid]
    payload = {
        "lines": lines,
        "eyes": eye_centers,
    }
    output_path.write_text("window.FACE_ART = " + json.dumps(payload) + ";\n", encoding="utf-8")
    print(f"art={cols}x{rows} eyes={eye_centers}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render a segmented face photo as a simple, readable ASCII portrait.

The source photo is reduced to a small monospace grid, then the detected face
contour is used as a mask. Skin keeps only a few luminance levels, hair is
quantized into a dark cap, and the eye sockets are reserved for the tracking
pupils drawn by app.js.
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageFilter


def downsample(image, cols, rows):
    gray = image.convert("L").filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(1.1))
    alpha = image.getchannel("A")
    gray_small = gray.resize((cols, rows), Image.Resampling.LANCZOS)
    alpha_small = alpha.resize((cols, rows), Image.Resampling.LANCZOS)
    return [
        [gray_small.getpixel((x, y)) for x in range(cols)]
        for y in range(rows)
    ], [
        [alpha_small.getpixel((x, y)) for x in range(cols)]
        for y in range(rows)
    ]


def point_in_polygon(px, py, polygon):
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > py) != (yj > py):
            x_cross = xj + (py - yj) * (xi - xj) / (yi - yj)
            if px < x_cross:
                inside = not inside
        j = i
    return inside


def to_grid(point, image_width, image_height, cols, rows):
    x = round(point["x"] / image_width * (cols - 1))
    y = round(point["y"] / image_height * (rows - 1))
    return x, y


def clean_grid(grid, rows, cols):
    """Remove isolated specks and fill small holes for a calmer portrait."""
    for _ in range(2):
        snapshot = [row[:] for row in grid]
        for y in range(rows):
            for x in range(cols):
                if snapshot[y][x] == " ":
                    continue
                count = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < rows and 0 <= nx < cols and snapshot[ny][nx] != " ":
                            count += 1
                if count < 2:
                    grid[y][x] = " "
    return grid


def render_stylized(image, meta, cols, rows, symmetric):
    image_width, image_height = image.size
    gray, alpha = downsample(image, cols, rows)

    if symmetric:
        for y in range(rows):
            for x in range(cols // 2):
                mx = cols - 1 - x
                g = (gray[y][x] + gray[y][mx]) // 2
                a = (alpha[y][x] + alpha[y][mx]) // 2
                gray[y][x] = gray[y][mx] = g
                alpha[y][x] = alpha[y][mx] = a

    landmarks = meta["landmarks"]
    contour = [to_grid(p, image_width, image_height, cols, rows) for p in landmarks["faceContour"]]
    face_top = min(y for _, y in contour)
    face_bottom = max(y for _, y in contour)
    face_left = min(x for x, _ in contour)
    face_right = max(x for x, _ in contour)
    face_polygon = contour + [(face_right, face_top), (face_left, face_top)]

    left_eye = to_grid(meta["eyes"][0], image_width, image_height, cols, rows)
    right_eye = to_grid(meta["eyes"][1], image_width, image_height, cols, rows)
    nose = to_grid(landmarks["nose"], image_width, image_height, cols, rows)
    mouth = to_grid(landmarks["mouth"], image_width, image_height, cols, rows)
    hair_bottom = max(0, face_top - 1)

    grid = [[" " for _ in range(cols)] for _ in range(rows)]

    for y in range(rows):
        for x in range(cols):
            if alpha[y][x] < 96:
                continue
            lum = gray[y][x]
            inside_face = point_in_polygon(x + 0.5, y + 0.5, face_polygon)

            if y <= hair_bottom and face_left - 2 <= x <= face_right + 2:
                if lum < 170:
                    grid[y][x] = "#"
                continue

            if inside_face:
                if lum < 95:
                    grid[y][x] = "+"
                elif lum < 155:
                    grid[y][x] = "="
                elif lum < 220:
                    grid[y][x] = "."
                continue

    grid = clean_grid(grid, rows, cols)

    def put(y, x, s):
        if not (0 <= y < rows):
            return
        row = grid[y]
        for i, ch in enumerate(s):
            col = x + i
            if 0 <= col < cols:
                row[col] = ch

    def put_box(y, x, lines):
        for dy, line in enumerate(lines):
            put(y + dy, x, line)

    # Brows sit just above the eye sockets.
    put_box(left_eye[1] - 3, left_eye[0] - 2, ["___"])
    put_box(right_eye[1] - 3, right_eye[0] - 2, ["___"])

    # Sockets are blank; app.js inserts the moving pupils.
    for eye in (left_eye, right_eye):
        put_box(eye[1] - 1, eye[0] - 2, ["(   )", "(   )", "(   )"])

    # Nose ridge and a soft smile.
    put(nose[1] - 1, nose[0], "|")
    put(nose[1], nose[0], "|")
    put(nose[1] + 1, nose[0] - 1, "~")
    put_box(mouth[1], mouth[0] - 3, ["\\____/"])

    lines = ["".join(row).rstrip() for row in grid]
    return lines, [{"x": eye[0], "y": eye[1]} for eye in (left_eye, right_eye)]


def render_photo(image, meta, cols, rows, symmetric):
    image_width, image_height = image.size
    gray, alpha = downsample(image, cols, rows)

    if symmetric:
        for y in range(rows):
            for x in range(cols // 2):
                mx = cols - 1 - x
                gray[y][x] = gray[y][mx] = (gray[y][x] + gray[y][mx]) // 2
                alpha[y][x] = alpha[y][mx] = (alpha[y][x] + alpha[y][mx]) // 2

    ramp = "@%#*+=-:. "
    grid = [[" " for _ in range(cols)] for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            if alpha[y][x] < 96:
                continue
            contrast = 255.0 * ((gray[y][x] / 255.0) ** 1.05)
            index = min(len(ramp) - 1, int((255.0 - contrast) * len(ramp) / 256.0))
            grid[y][x] = ramp[index]

    grid = clean_grid(grid, rows, cols)
    left_eye = to_grid(meta["eyes"][0], image_width, image_height, cols, rows)
    right_eye = to_grid(meta["eyes"][1], image_width, image_height, cols, rows)

    def put_box(y, x, lines):
        for dy, line in enumerate(lines):
            row = grid[y + dy]
            for i, ch in enumerate(line):
                if 0 <= x + i < cols:
                    row[x + i] = ch

    for eye in (left_eye, right_eye):
        put_box(eye[1] - 1, eye[0] - 2, ["(   )", "(   )", "(   )"])

    lines = ["".join(row).rstrip() for row in grid]
    return lines, [{"x": eye[0], "y": eye[1]} for eye in (left_eye, right_eye)]


def draw_line(grid, x0, y0, x1, y1, char):
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if 0 <= y0 < len(grid) and 0 <= x0 < len(grid[0]):
            grid[y0][x0] = char
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def render_outline(image, meta, cols, rows, symmetric, outline_char="#"):
    image_width, image_height = image.size
    gray, alpha = downsample(image, cols, rows)

    landmarks = meta["landmarks"]
    contour = [to_grid(p, image_width, image_height, cols, rows) for p in landmarks["faceContour"]]
    face_top = min(y for _, y in contour)
    face_bottom = max(y for _, y in contour)
    face_left = min(x for x, _ in contour)
    face_right = max(x for x, _ in contour)
    face_center_x = round((face_left + face_right) / 2)
    hair_bottom = max(0, face_top - 5)

    left_eye = to_grid(meta["eyes"][0], image_width, image_height, cols, rows)
    right_eye = to_grid(meta["eyes"][1], image_width, image_height, cols, rows)
    nose = to_grid(landmarks["nose"], image_width, image_height, cols, rows)
    mouth = to_grid(landmarks["mouth"], image_width, image_height, cols, rows)
    eye_row = round((left_eye[1] + right_eye[1]) / 2)
    feature_center_x = round((left_eye[0] + right_eye[0]) / 2)

    grid = [[" " for _ in range(cols)] for _ in range(rows)]

    # Hair cap: solid across the top, ending in a light fringe row.
    for y in range(rows):
        if y > hair_bottom:
            break
        for x in range(cols):
            if alpha[y][x] < 96:
                continue
            if x < face_left - 2 or x > face_right + 2:
                continue
            if y < hair_bottom or (gray[y][x] < 160 and (x <= face_left + 4 or x >= face_right - 4)):
                grid[y][x] = "#"

    # Collect the photo contour, then mirror it so the face reads as a clean oval.
    scratch = [[" " for _ in range(cols)] for _ in range(rows)]
    for i in range(len(contour) - 1):
        x0, y0 = contour[i]
        x1, y1 = contour[i + 1]
        if y0 > hair_bottom or y1 > hair_bottom:
            draw_line(scratch, x0, y0, x1, y1, outline_char)

    for y in range(rows):
        for x in range(cols):
            if scratch[y][x] != " ":
                grid[y][x] = outline_char
                if symmetric:
                    mirror = face_center_x + (face_center_x - x)
                    if 0 <= mirror < cols:
                        grid[y][mirror] = outline_char

    def put(y, x, s):
        if not (0 <= y < rows):
            return
        row = grid[y]
        for i, ch in enumerate(s):
            col = x + i
            if 0 <= col < cols:
                row[col] = ch

    def put_box(y, x, lines):
        for dy, line in enumerate(lines):
            put(y + dy, x, line)

    put_box(eye_row - 3, left_eye[0] - 2, ["___"])
    put_box(eye_row - 3, right_eye[0] - 2, ["___"])
    for eye_x in (left_eye[0], right_eye[0]):
        put_box(eye_row - 1, eye_x - 2, ["(   )", "(   )", "(   )"])
    put(eye_row + 3, feature_center_x, "|")
    put(eye_row + 4, feature_center_x, "|")
    put(eye_row + 5, feature_center_x - 1, "~")
    put_box(eye_row + 7, feature_center_x - 3, ["\\____/"])

    lines = ["".join(row).rstrip() for row in grid]
    return lines, [{"x": left_eye[0], "y": eye_row}, {"x": right_eye[0], "y": eye_row}]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("meta")
    parser.add_argument("output")
    parser.add_argument("--cols", type=int, default=52)
    parser.add_argument("--style", choices=["stylized", "photo", "outline"], default="stylized")
    parser.add_argument("--outline", choices=["#", "+", "="], default="#")
    parser.add_argument("--sym", action="store_true")
    args = parser.parse_args()

    image = Image.open(args.image).convert("RGBA")
    meta = json.loads(Path(args.meta).read_text())
    image_width, image_height = image.size
    cols = args.cols
    rows = max(2, round(cols * image_height / image_width * 0.5))

    if args.style == "photo":
        lines, eyes = render_photo(image, meta, cols, rows, args.sym)
    elif args.style == "outline":
        lines, eyes = render_outline(image, meta, cols, rows, args.sym, args.outline)
    else:
        lines, eyes = render_stylized(image, meta, cols, rows, args.sym)

    payload = {"lines": lines, "eyes": eyes}
    Path(args.output).write_text("window.FACE_ART = " + json.dumps(payload) + ";\n", encoding="utf-8")
    print(f"art={cols}x{rows} eyes={eyes} style={args.style} sym={args.sym}")


if __name__ == "__main__":
    main()

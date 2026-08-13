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

from PIL import Image, ImageDraw, ImageFilter, ImageOps


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


def render_refined(image, meta, cols, rows, symmetric):
    image_width, image_height = image.size
    gray, alpha = downsample(image, cols, rows)

    if symmetric:
        for y in range(rows):
            for x in range(cols // 2):
                mx = cols - 1 - x
                gray[y][x] = gray[y][mx] = (gray[y][x] + gray[y][mx]) // 2
                alpha[y][x] = alpha[y][mx] = (alpha[y][x] + alpha[y][mx]) // 2

    landmarks = meta["landmarks"]
    contour = [to_grid(p, image_width, image_height, cols, rows) for p in landmarks["faceContour"]]
    face_top = min(y for _, y in contour)
    face_bottom = max(y for _, y in contour)
    face_left = min(x for x, _ in contour)
    face_right = max(x for x, _ in contour)
    face_center_x = round((face_left + face_right) / 2)
    face_polygon = contour + [(face_right, face_top), (face_left, face_top)]

    left_eye = to_grid(meta["eyes"][0], image_width, image_height, cols, rows)
    right_eye = to_grid(meta["eyes"][1], image_width, image_height, cols, rows)
    nose = to_grid(landmarks["nose"], image_width, image_height, cols, rows)
    mouth = to_grid(landmarks["mouth"], image_width, image_height, cols, rows)
    eye_row = round((left_eye[1] + right_eye[1]) / 2)
    feature_center_x = round((left_eye[0] + right_eye[0]) / 2)
    hairline = max(0, eye_row - 6)

    grid = [[" " for _ in range(cols)] for _ in range(rows)]

    # Hair from the actual luminance: dark short cap with an uneven fringe.
    for y in range(hairline + 1):
        for x in range(cols):
            if alpha[y][x] < 96:
                continue
            if gray[y][x] < 125:
                grid[y][x] = "#"
            elif y < hairline and gray[y][x] < 165:
                grid[y][x] = "="
            elif y == hairline and gray[y][x] < 190:
                grid[y][x] = "="

    # Soft skin and stubble shading inside the face.
    for y in range(rows):
        for x in range(cols):
            if not point_in_polygon(x + 0.5, y + 0.5, face_polygon):
                continue
            if alpha[y][x] < 96:
                continue
            if abs(y - eye_row) <= 2:
                continue
            if abs(y - mouth[1]) <= 1:
                continue
            if abs(y - nose[1]) <= 1:
                continue
            lum = gray[y][x]
            if lum < 95:
                grid[y][x] = "+"
            elif lum < 150:
                grid[y][x] = "="
            elif lum < 215:
                grid[y][x] = "."

    # Face contour: light line around the cheeks and jaw, mirrored.
    scratch = [[" " for _ in range(cols)] for _ in range(rows)]
    for i in range(len(contour) - 1):
        x0, y0 = contour[i]
        x1, y1 = contour[i + 1]
        if y0 >= hairline and y1 >= hairline:
            draw_line(scratch, x0, y0, x1, y1, "#")

    for y in range(rows):
        for x in range(cols):
            if scratch[y][x] == " ":
                continue
            grid[y][x] = "#"
            if symmetric:
                mirror = face_center_x + (face_center_x - x)
                if 0 <= mirror < cols:
                    grid[y][mirror] = "#"

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


def render_portrait(image, meta, cols, rows, symmetric):
    image_width, image_height = image.size
    gray, alpha = downsample(image, cols, rows)

    if symmetric:
        for y in range(rows):
            for x in range(cols // 2):
                mx = cols - 1 - x
                gray[y][x] = gray[y][mx] = (gray[y][x] + gray[y][mx]) // 2
                alpha[y][x] = alpha[y][mx] = (alpha[y][x] + alpha[y][mx]) // 2

    landmarks = meta["landmarks"]
    contour = [to_grid(p, image_width, image_height, cols, rows) for p in landmarks["faceContour"]]
    face_top = min(y for _, y in contour)
    face_bottom = max(y for _, y in contour)
    face_left = min(x for x, _ in contour)
    face_right = max(x for x, _ in contour)
    face_center_x = round((face_left + face_right) / 2)

    left_eye = to_grid(meta["eyes"][0], image_width, image_height, cols, rows)
    right_eye = to_grid(meta["eyes"][1], image_width, image_height, cols, rows)
    nose = to_grid(landmarks["nose"], image_width, image_height, cols, rows)
    mouth = to_grid(landmarks["mouth"], image_width, image_height, cols, rows)
    eye_row = round((left_eye[1] + right_eye[1]) / 2)
    feature_center_x = round((left_eye[0] + right_eye[0]) / 2)
    hair_bottom = max(0, eye_row - 8)

    grid = [[" " for _ in range(cols)] for _ in range(rows)]

    # Rounded hair cap with a lighter fringe, shaped by the photo luminance.
    base_half = max(6, round((face_right - face_left) / 2) + 2)
    for y in range(hair_bottom + 1):
        taper = 1 - (y / max(1, hair_bottom + 1)) * 0.14
        half = max(3, round(base_half * taper))
        for x in range(face_center_x - half, face_center_x + half + 1):
            if 0 <= x < cols and alpha[y][x] >= 96:
                grid[y][x] = "#" if y < hair_bottom else "="

    # Face outline in lighter line-art characters.
    jaw_squeeze = 0.08
    for y in range(hair_bottom + 1, face_bottom + 1):
        progress = (y - hair_bottom) / max(1, face_bottom - hair_bottom)
        squeeze = round(progress * progress * (face_right - face_left) * jaw_squeeze)
        left_x = max(0, face_left + squeeze)
        right_x = min(cols - 1, face_right - squeeze)
        if y < eye_row - 1:
            ch_l = "/"
            ch_r = "\\"
        elif y < eye_row + 4:
            ch_l = "|"
            ch_r = "|"
        else:
            ch_l = "\\"
            ch_r = "/"
        if 0 <= left_x < cols:
            grid[y][left_x] = ch_l
        if 0 <= right_x < cols:
            grid[y][right_x] = ch_r

    # Light stubble along the jaw and cheeks.
    for y in range(eye_row + 5, face_bottom - 1):
        for x in range(face_left + 2, face_right - 1):
            if grid[y][x] != " ":
                continue
            lum = gray[y][x]
            if lum < 120:
                grid[y][x] = ","
            elif lum < 175:
                grid[y][x] = "."

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


def render_equalized(image, meta, cols, rows, symmetric):
    image_width, image_height = image.size

    # Mask the head/hair, so the dark shirt does not distort the face contrast.
    landmarks = meta["landmarks"]
    contour = [(p["x"], p["y"]) for p in landmarks["faceContour"]]
    face_top = min(y for _, y in contour)
    face_bottom = max(y for _, y in contour)
    face_left = min(x for x, _ in contour)
    face_right = max(x for x, _ in contour)
    head_polygon = contour + [(face_right, 0), (face_left, 0)]

    head_mask = Image.new("L", (image_width, image_height), 0)
    ImageDraw.Draw(head_mask).polygon([(x, y) for x, y in head_polygon], fill=255)

    canvas = Image.new("RGBA", image.size, (246, 240, 228, 255))
    canvas.alpha_composite(image)
    canvas.putalpha(head_mask)
    composite = Image.new("RGBA", image.size, (246, 240, 228, 255))
    composite.alpha_composite(canvas)

    gray = composite.convert("L").filter(ImageFilter.MedianFilter(3))
    equalized = ImageOps.equalize(gray).filter(ImageFilter.GaussianBlur(0.8))
    small = equalized.resize((cols, rows), Image.Resampling.LANCZOS)
    alpha = head_mask.resize((cols, rows), Image.Resampling.LANCZOS)

    ramp = " .:-=+*#%@"
    grid = [[" " for _ in range(cols)] for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            if alpha.getpixel((x, y)) < 96:
                continue
            lum = small.getpixel((x, y))
            grid[y][x] = ramp[min(len(ramp) - 1, lum * len(ramp) // 256)]

    if symmetric:
        for y in range(rows):
            for x in range(cols // 2):
                mx = cols - 1 - x
                if grid[y][x] != " " and grid[y][mx] != " ":
                    grid[y][x] = grid[y][mx] = (
                        grid[y][x] if ramp.index(grid[y][x]) <= ramp.index(grid[y][mx]) else grid[y][mx]
                    )

    left_eye = to_grid(meta["eyes"][0], image.size[0], image.size[1], cols, rows)
    right_eye = to_grid(meta["eyes"][1], image.size[0], image.size[1], cols, rows)

    for eye in (left_eye, right_eye):
        for dy in range(-1, 2):
            for dx in range(-2, 3):
                y = eye[1] + dy
                x = eye[0] + dx
                if 0 <= y < rows and 0 <= x < cols:
                    grid[y][x] = " "
        for dy, line in enumerate(["(   )", "(   )", "(   )"]):
            for i, ch in enumerate(line):
                y = eye[1] - 1 + dy
                x = eye[0] - 2 + i
                if 0 <= y < rows and 0 <= x < cols:
                    grid[y][x] = ch

    lines = ["".join(row).rstrip() for row in grid]
    return lines, [{"x": eye[0], "y": eye[1]} for eye in (left_eye, right_eye)]


def render_hybrid(image, meta, cols, rows, symmetric):
    image_width, image_height = image.size
    landmarks = meta["landmarks"]
    contour = [(p["x"], p["y"]) for p in landmarks["faceContour"]]
    face_top = min(y for _, y in contour)
    face_bottom = max(y for _, y in contour)
    face_left = min(x for x, _ in contour)
    face_right = max(x for x, _ in contour)
    head_polygon = contour + [(face_right, 0), (face_left, 0)]

    head_mask = Image.new("L", (image_width, image_height), 0)
    ImageDraw.Draw(head_mask).polygon([(x, y) for x, y in head_polygon], fill=255)
    canvas = Image.new("RGBA", image.size, (246, 240, 228, 255))
    canvas.alpha_composite(image)
    canvas.putalpha(head_mask)
    composite = Image.new("RGBA", image.size, (246, 240, 228, 255))
    composite.alpha_composite(canvas)
    gray = composite.convert("L").filter(ImageFilter.MedianFilter(3))
    equalized = ImageOps.equalize(gray).filter(ImageFilter.GaussianBlur(0.8))
    small = equalized.resize((cols, rows), Image.Resampling.LANCZOS)
    alpha = head_mask.resize((cols, rows), Image.Resampling.LANCZOS)

    left_eye = to_grid(meta["eyes"][0], image_width, image_height, cols, rows)
    right_eye = to_grid(meta["eyes"][1], image_width, image_height, cols, rows)
    eye_row = round((left_eye[1] + right_eye[1]) / 2)
    face_left_g = min(x for x, _ in [to_grid(p, image_width, image_height, cols, rows) for p in landmarks["faceContour"]])
    face_right_g = max(x for x, _ in [to_grid(p, image_width, image_height, cols, rows) for p in landmarks["faceContour"]])
    face_center_g = round((face_left_g + face_right_g) / 2)
    hair_bottom = max(0, eye_row - 6)

    ramp = " .:-=+*#%@"
    grid = [[" " for _ in range(cols)] for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            if alpha.getpixel((x, y)) < 96:
                continue
            lum = small.getpixel((x, y))
            grid[y][x] = ramp[min(len(ramp) - 1, lum * len(ramp) // 256)]

    if symmetric:
        for y in range(rows):
            for x in range(cols // 2):
                mx = cols - 1 - x
                if grid[y][x] != " " and grid[y][mx] != " ":
                    grid[y][x] = grid[y][mx] = (
                        grid[y][x] if ramp.index(grid[y][x]) <= ramp.index(grid[y][mx]) else grid[y][mx]
                    )

    # Rounded hair cap so the portrait reads as a human head.
    for y in range(hair_bottom + 1):
        taper = 1 - y / max(1, hair_bottom + 1) * 0.22
        half = max(2, round((face_right_g - face_left_g) / 2 * taper))
        for x in range(face_center_g - half, face_center_g + half + 1):
            if 0 <= x < cols and alpha.getpixel((x, y)) >= 96:
                grid[y][x] = "#"

    # Face contour below the hairline, mirrored for symmetry.
    scratch = [[" " for _ in range(cols)] for _ in range(rows)]
    contour_g = [to_grid(p, image_width, image_height, cols, rows) for p in landmarks["faceContour"]]
    for i in range(len(contour_g) - 1):
        x0, y0 = contour_g[i]
        x1, y1 = contour_g[i + 1]
        if y0 >= hair_bottom and y1 >= hair_bottom:
            draw_line(scratch, x0, y0, x1, y1, "#")
    for y in range(rows):
        for x in range(cols):
            if scratch[y][x] == " ":
                continue
            grid[y][x] = "#"
            if symmetric:
                mirror = face_center_g + (face_center_g - x)
                if 0 <= mirror < cols:
                    grid[y][mirror] = "#"

    for eye in (left_eye, right_eye):
        for dy in range(-1, 2):
            for dx in range(-2, 3):
                y = eye[1] + dy
                x = eye[0] + dx
                if 0 <= y < rows and 0 <= x < cols:
                    grid[y][x] = " "
        for dy, line in enumerate(["(   )", "(   )", "(   )"]):
            for i, ch in enumerate(line):
                y = eye[1] - 1 + dy
                x = eye[0] - 2 + i
                if 0 <= y < rows and 0 <= x < cols:
                    grid[y][x] = ch

    lines = ["".join(row).rstrip() for row in grid]
    return lines, [{"x": left_eye[0], "y": eye_row}, {"x": right_eye[0], "y": eye_row}]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("meta")
    parser.add_argument("output")
    parser.add_argument("--cols", type=int, default=52)
    parser.add_argument(
        "--style",
        choices=["stylized", "photo", "outline", "refined", "portrait", "equalized", "hybrid"],
        default="stylized",
    )
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
    elif args.style == "refined":
        lines, eyes = render_refined(image, meta, cols, rows, args.sym)
    elif args.style == "portrait":
        lines, eyes = render_portrait(image, meta, cols, rows, args.sym)
    elif args.style == "equalized":
        lines, eyes = render_equalized(image, meta, cols, rows, args.sym)
    elif args.style == "hybrid":
        lines, eyes = render_hybrid(image, meta, cols, rows, args.sym)
    else:
        lines, eyes = render_stylized(image, meta, cols, rows, args.sym)

    payload = {"lines": lines, "eyes": eyes}
    Path(args.output).write_text("window.FACE_ART = " + json.dumps(payload) + ";\n", encoding="utf-8")
    print(f"art={cols}x{rows} eyes={eyes} style={args.style} sym={args.sym}")


if __name__ == "__main__":
    main()

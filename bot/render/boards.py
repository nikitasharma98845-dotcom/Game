from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

BG = (18, 20, 32)
INK = (235, 238, 248)
MUTED = (120, 128, 150)
ACCENT = (255, 196, 61)
GREEN = (60, 200, 120)
RED = (230, 70, 80)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def plinko_board(table: list[float], slot: int) -> bytes:
    width = 720
    height = 320
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    n = len(table)
    pad = 40
    gap = (width - pad * 2) / max(1, n - 1)
    top = 40
    row_gap = 16
    for row in range(max(1, n - 1)):
        y = top + row * row_gap
        count = row + 1
        for i in range(count):
            x = width / 2 - (count - 1) * 8 + i * 16
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=MUTED)
    font = _font(15)
    for i, value in enumerate(table):
        x = pad + i * gap
        y = height - 70
        box = 30 if i == slot else 24
        colour = ACCENT if i == slot else (45, 50, 70)
        draw.rounded_rectangle((x - box / 2, y - 18, x + box / 2, y + 18), radius=6, fill=colour)
        label = f"{value:g}x"
        tw = draw.textlength(label, font=font)
        draw.text((x - tw / 2, y - 8), label, fill=BG if i == slot else INK, font=font)
    return _png(image)


def wheel_image(values: list[float], index: int) -> bytes:
    size = 520
    image = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(image)
    n = len(values)
    box = (30, 30, size - 30, size - 30)
    start: float = -90
    span = 360 / n
    for i in range(n):
        end = start + span
        fill = (40, 44, 64) if i % 2 == 0 else (50, 56, 78)
        if i == index:
            fill = ACCENT
        draw.pieslice(box, start=start, end=end, fill=fill, outline=BG, width=2)
        start = end
    draw.ellipse((size / 2 - 70, size / 2 - 70, size / 2 + 70, size / 2 + 70), fill=BG)
    font = _font(34)
    label = f"{values[index]:g}x"
    tw = draw.textlength(label, font=font)
    draw.text((size / 2 - tw / 2, size / 2 - 18), label, fill=ACCENT, font=font)
    return _png(image)


def roulette_image(number: int, color: str) -> bytes:
    size = 420
    image = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 20, size - 20, size - 20), fill=(35, 38, 55), outline=(70, 76, 96), width=6)
    fill = GREEN if color == "green" else (RED if color == "red" else (30, 30, 34))
    draw.ellipse((size / 2 - 110, size / 2 - 110, size / 2 + 110, size / 2 + 110), fill=fill)
    font = _font(96)
    label = str(number)
    tw = draw.textlength(label, font=font)
    draw.text((size / 2 - tw / 2, size / 2 - 58), label, fill=INK, font=font)
    small = _font(22)
    tw = draw.textlength(color.upper(), font=small)
    draw.text((size / 2 - tw / 2, size / 2 + 60), color.upper(), fill=INK, font=small)
    return _png(image)


def mines_board(revealed: list[int], mines: list[int], reveal: bool = False) -> bytes:
    cell = 74
    pad = 18
    size = cell * 5 + pad * 2
    image = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(image)
    font = _font(34)
    for idx in range(25):
        r, c = divmod(idx, 5)
        x = pad + c * cell
        y = pad + r * cell
        if idx in revealed:
            fill, mark = (30, 110, 80), "💎"
        elif reveal and idx in mines:
            fill, mark = (120, 35, 45), "💣"
        else:
            fill, mark = (38, 42, 60), ""
        draw.rounded_rectangle((x + 3, y + 3, x + cell - 3, y + cell - 3), radius=10, fill=fill)
        if mark:
            tw = draw.textlength(mark, font=font)
            draw.text((x + cell / 2 - tw / 2, y + cell / 2 - 20), mark, fill=INK, font=font)
    return _png(image)


def crash_chart(crash: float) -> bytes:
    width, height = 640, 300
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.line((40, height - 40, width - 20, height - 40), fill=MUTED, width=2)
    steps = 60
    peak = math.log(max(1.0, crash))
    points = []
    for i in range(steps + 1):
        x = 40 + i * (width - 70) / steps
        y = height - 40 - (math.log(1 + i / steps * max(1.0, crash - 1)) / max(0.001, peak)) * (height - 90)
        points.append((x, y))
    draw.line(points, fill=ACCENT, width=4)
    font = _font(26)
    draw.text((50, 20), f"{crash:.2f}x", fill=ACCENT, font=font)
    return _png(image)

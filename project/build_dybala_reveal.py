#!/usr/bin/env python3
"""
Build ~7s Dybala Napoli reveal: back (DYBALA 10) -> turn -> front + wink.
Uses portrait + project/02_assets/kits/napoli.png — stylized compositing, not 3D.

  python build_dybala_reveal.py
  python build_dybala_reveal.py --face /path/to/dybala.png
"""

import argparse
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# MoviePy
from moviepy.video.VideoClip import VideoClip

PROJECT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FACE = os.path.join(
    os.path.dirname(PROJECT),
    ".cursor", "projects", "home-anibalgalindro-SQLiteMigration", "assets",
    "player_2620-cebabbaf-4158-4ce2-93fe-ddca443216d9.png",
)
# Also check workspace-relative path from repo root
ALT_FACE = "/home/anibalgalindro/.cursor/projects/home-anibalgalindro-SQLiteMigration/assets/player_2620-cebabbaf-4158-4ce2-93fe-ddca443216d9.png"
KIT_PATH = os.path.join(PROJECT, "02_assets", "kits", "napoli.png")
OUT_PATH = os.path.join(PROJECT, "03_output", "dybala_napoli_reveal.mp4")

W, H = 1920, 1080
FPS = 30
DURATION = 7.0
BACK_HOLD = 2.8
TURN_DUR = 0.9
NAPOLI_BLUE = (0, 146, 199)
NAPOLI_DARK = (0, 55, 100)


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/google-carlito-fonts/Carlito-Bold.ttf",
    ]
    if not bold:
        paths = [p.replace("Bold", "") for p in paths] + [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for p in paths:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def _remove_light_background(im: Image.Image, thresh: int = 210) -> Image.Image:
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r >= thresh and g >= thresh and b >= thresh:
                px[x, y] = (r, g, b, 0)
    return im


def _gradient_bg() -> Image.Image:
    img = Image.new("RGB", (W, H), NAPOLI_DARK)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(NAPOLI_DARK[0] + (NAPOLI_BLUE[0] - NAPOLI_DARK[0]) * t * 0.5)
        g = int(NAPOLI_DARK[1] + (NAPOLI_BLUE[1] - NAPOLI_DARK[1]) * t * 0.5)
        b = int(NAPOLI_DARK[2] + (NAPOLI_BLUE[2] - NAPOLI_DARK[2]) * t * 0.5)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    return img.convert("RGBA")


def _paste_contain(base: Image.Image, overlay: Image.Image, box: tuple) -> None:
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    ow, oh = overlay.size
    s = min(tw / ow, th / oh)
    nw, nh = max(1, int(ow * s)), max(1, int(oh * s))
    o = overlay.resize((nw, nh), Image.Resampling.LANCZOS)
    px = x0 + (tw - nw) // 2
    py = y0 + (th - nh) // 2
    base.paste(o, (px, py), o)


def build_back_frame(kit: Image.Image, zoom: float = 1.0) -> Image.Image:
    frame = _gradient_bg()
    # Back: mirrored kit + name/number
    back_kit = kit.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    box = (560, 120, 1360, 920)
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    tw, th = int((x1 - x0) * zoom), int((y1 - y0) * zoom)
    _paste_contain(frame, back_kit, (cx - tw // 2, cy - th // 2, cx + tw // 2, cy + th // 2))

    draw = ImageDraw.Draw(frame)
    font_name = _load_font(96)
    font_num = _load_font(220)

    name = "DYBALA"
    nb = draw.textbbox((0, 0), name, font=font_name)
    nw = nb[2] - nb[0]
    draw.text((cx - nw // 2, cy - 80), name, fill=(255, 255, 255), font=font_name, stroke_width=4, stroke_fill=(0, 40, 80))

    num = "10"
    nb2 = draw.textbbox((0, 0), num, font=font_num)
    nw2 = nb2[2] - nb2[0]
    draw.text((cx - nw2 // 2, cy + 20), num, fill=(255, 255, 255), font=font_num, stroke_width=5, stroke_fill=(0, 40, 80))

    return frame


def build_front_frame(kit: Image.Image, face: Image.Image, zoom: float = 1.0, wink: bool = False) -> Image.Image:
    frame = _gradient_bg()
    box = (560, 100, 1360, 940)
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    tw, th = int((x1 - x0) * zoom), int((y1 - y0) * zoom)
    cy = (y0 + y1) // 2
    _paste_contain(frame, kit, (cx - tw // 2, cy - th // 2, cx + tw // 2, cy + th // 2))

    face = face.copy()
    fw, fh = face.size
    face_h = int(th * 0.42)
    face_w = int(face_h * (fw / fh))
    face = face.resize((face_w, face_h), Image.Resampling.LANCZOS)
    fx = cx - face_w // 2
    fy = y0 + int(th * 0.08)
    frame.paste(face, (fx, fy), face)

    if wink:
        draw = ImageDraw.Draw(frame)
        # Viewer-right eye (Dybala's left) — approximate from portrait layout
        eye_cx = fx + int(face_w * 0.62)
        eye_cy = fy + int(face_h * 0.38)
        draw.arc(
            [eye_cx - 28, eye_cy - 8, eye_cx + 28, eye_cy + 18],
            start=0,
            end=180,
            fill=(40, 30, 25),
            width=5,
        )
        draw.line(
            [(eye_cx - 26, eye_cy + 4), (eye_cx + 26, eye_cy + 4)],
            fill=(60, 45, 35),
            width=4,
        )

    return frame


def _blend(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    t = max(0.0, min(1.0, t))
    return Image.blend(a.convert("RGBA"), b.convert("RGBA"), t)


def resolve_face_path(cli_path: str | None) -> str:
    if cli_path and os.path.isfile(cli_path):
        return cli_path
    for p in (
        os.path.join(PROJECT, "02_assets", "players", "dybala.png"),
        ALT_FACE,
        DEFAULT_FACE,
    ):
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("Player face image not found. Use --face /path/to/image.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--face", help="Path to player portrait PNG/JPG")
    parser.add_argument("-o", "--output", default=OUT_PATH)
    args = parser.parse_args()

    face_path = resolve_face_path(args.face)
    if not os.path.isfile(KIT_PATH):
        print(f"Missing kit: {KIT_PATH}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    kit = Image.open(KIT_PATH).convert("RGBA")
    face = _remove_light_background(Image.open(face_path))

    # Cache static bases
    back_base = build_back_frame(kit, 1.0)
    front_base = build_front_frame(kit, face, 1.0, wink=False)
    front_wink = build_front_frame(kit, face, 1.0, wink=True)

    turn_start = BACK_HOLD
    turn_end = BACK_HOLD + TURN_DUR
    wink_start = 5.15
    wink_end = 5.55

    def make_frame(t: float) -> np.ndarray:
        # Gentle zoom pulse
        zoom = 1.0 + 0.04 * math.sin(t * 1.2)

        if t < turn_start:
            img = build_back_frame(kit, zoom)
        elif t < turn_end:
            u = (t - turn_start) / TURN_DUR
            # Ease in-out
            u = u * u * (3 - 2 * u)
            img = _blend(build_back_frame(kit, zoom), build_front_frame(kit, face, zoom, False), u)
        else:
            wink = wink_start <= t < wink_end or (t >= wink_end and (int((t - wink_start) * 8) % 2 == 1 and t < wink_end + 0.15))
            # Single wink pulse
            if wink_start <= t <= wink_end:
                img = build_front_frame(kit, face, zoom, wink=True)
            else:
                img = build_front_frame(kit, face, zoom, wink=False)

        return np.array(img.convert("RGB"))

    print(f"Face: {face_path}")
    print(f"Rendering {DURATION}s @ {W}x{H} ...")
    clip = VideoClip(make_frame, duration=DURATION).set_fps(FPS)
    clip.write_videofile(
        args.output,
        fps=FPS,
        codec="libx264",
        audio=False,
        preset="medium",
        logger=None,
    )
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()

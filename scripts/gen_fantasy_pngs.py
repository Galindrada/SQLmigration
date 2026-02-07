#!/usr/bin/env python3
"""Generate placeholder PNGs for Fantasy (booster pack, card background). Stdlib only."""

import struct
import zlib
import os

def write_png(buf, width, height, path):
    """Write RGBA buffer to PNG. buf: bytes, length = width * height * 4."""
    assert len(buf) == width * height * 4
    raw = b""
    for y in range(height - 1, -1, -1):
        raw += b'\x00'
        raw += buf[y * width * 4 : (y + 1) * width * 4]

    def png_chunk(tag, data):
        chunk = tag + data
        return struct.pack("!I", len(data)) + chunk + struct.pack("!I", 0xFFFFFFFF & zlib.crc32(chunk))

    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 6, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(raw, 9))
    png += png_chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(png)


def mk_buf(w, h, fn):
    """Fill RGBA buffer using fn(x, y) -> (r,g,b,a)."""
    out = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            r, g, b, a = fn(x, y)
            i = (y * w + x) * 4
            out[i : i + 4] = (r, g, b, a)
    return bytes(out)


def main():
    base = os.path.join(os.path.dirname(__file__), "..", "static", "fantasy")
    os.makedirs(base, exist_ok=True)

    # Card background: 400x300, warm beige gradient (#f5f5f0 -> #ebe8e0 -> #e0ddd5)
    def card_bg(x, y):
        t = (x / 400 + y / 300) / 2
        t = max(0, min(1, t))
        r = int(0xf5 + t * (0xeb - 0xf5) + (1 - t) * (0xe0 - 0xf5))
        g = int(0xf5 + t * (0xe8 - 0xf5) + (1 - t) * (0xdd - 0xf5))
        b = int(0xf0 + t * (0xe0 - 0xf0) + (1 - t) * (0xd5 - 0xf0))
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        return (r, g, b, 255)

    w, h = 400, 300
    buf = mk_buf(w, h, card_bg)
    write_png(buf, w, h, os.path.join(base, "card_bg.png"))
    print("Wrote static/fantasy/card_bg.png")

    # Booster pack: 256x256, brown/gold pack-style (#8b4513 -> #a0522d -> #654321), gold ribbon
    def booster(x, y):
        # Simple pack shape: rounded rect with vertical/horizontal gold bands
        cx, cy = 128, 128
        # Gold ribbon vertical (center) and horizontal
        if abs(x - cx) <= 8 or abs(y - cy) <= 8:
            return (0xd4, 0xaf, 0x37, 255)
        # Gradient
        t = (x / 256 + y / 256) / 2
        t = max(0, min(1, t))
        r = int(0x8b + t * (0xa0 - 0x8b) + (1 - t) * (0x65 - 0x8b))
        g = int(0x45 + t * (0x52 - 0x45) + (1 - t) * (0x43 - 0x45))
        b = int(0x13 + t * (0x2d - 0x13) + (1 - t) * (0x21 - 0x13))
        r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
        return (r, g, b, 255)

    w, h = 256, 256
    buf = mk_buf(w, h, booster)
    write_png(buf, w, h, os.path.join(base, "booster_pack.png"))
    print("Wrote static/fantasy/booster_pack.png")


if __name__ == "__main__":
    main()

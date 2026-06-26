"""Generate JobRadar PNG app icons with zero dependencies (stdlib only).
Run:  python tools/gen_icons.py
Draws a dark rounded tile with concentric 'radar' rings, a sweep, and a blip.
"""
import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web"

BG = (11, 17, 32)        # slate-950
RING = (37, 99, 235)     # blue-600
RING2 = (59, 130, 246)   # blue-500
BLIP = (52, 211, 153)    # emerald-400


def _png(size: int, pixels: bytes) -> bytes:
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # RGBA, 8-bit
    raw = bytearray()
    stride = size * 4
    for y in range(size):
        raw.append(0)  # no filter
        raw += pixels[y * stride:(y + 1) * stride]
    idat = zlib.compress(bytes(raw), 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def make(size: int) -> bytes:
    cx = cy = (size - 1) / 2
    corner = size * 0.18          # rounded-tile radius
    rings = [0.40, 0.28, 0.16]    # ring radii (fraction of size)
    buf = bytearray()
    for y in range(size):
        for x in range(size):
            # rounded-square mask -> transparent outside
            dx = max(abs(x - cx) - (size / 2 - corner), 0)
            dy = max(abs(y - cy) - (size / 2 - corner), 0)
            if math.hypot(dx, dy) > corner:
                buf += b"\x00\x00\x00\x00"
                continue
            r = math.hypot(x - cx, y - cy) / size
            ang = math.atan2(y - cy, x - cx)
            R, G, B = BG
            # radar sweep wedge (a soft pie slice)
            if -0.35 < ang < 0.45 and r < 0.42:
                f = 0.10 + 0.18 * (0.45 - ang) / 0.8
                R = int(R + (RING2[0] - R) * f)
                G = int(G + (RING2[1] - G) * f)
                B = int(B + (RING2[2] - B) * f)
            # concentric rings
            for rad in rings:
                if abs(r - rad) < 0.018:
                    R, G, B = RING
            # center blip + crosshair
            if r < 0.05:
                R, G, B = BLIP
            buf += bytes((R, G, B, 255))
    return _png(size, bytes(buf))


if __name__ == "__main__":
    for s in (192, 512):
        (OUT / f"icon-{s}.png").write_bytes(make(s))
        print(f"wrote web/icon-{s}.png")

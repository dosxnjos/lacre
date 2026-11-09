"""Draw the 1024px placeholder app icon (a wax-seal / stamp shape with a check mark).

Regenerate the platform icon set afterwards:
    uv run --python 3.12 --with pillow python src-tauri/icons/make_icon.py
    npx @tauri-apps/cli@2 icon src-tauri/icons/app-icon.png -o src-tauri/icons
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
SCALE = 4  # supersample for smooth edges
S = SIZE * SCALE
C = S / 2

SEAL = (176, 38, 46, 255)  # deep wax red
RING = (236, 214, 200, 255)  # light ring / check colour


def scalloped(radius: float, depth: float, lobes: int, steps: int = 2048):
    """Points of a circle with a wavy (scalloped) edge."""
    pts = []
    for i in range(steps):
        a = 2 * math.pi * i / steps
        r = radius + depth * math.cos(lobes * a)
        pts.append((C + r * math.cos(a), C + r * math.sin(a)))
    return pts


def main() -> None:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # outer scalloped seal
    d.polygon(scalloped(0.44 * S, 0.025 * S, 24), fill=SEAL)

    # inner ring
    r_out, w = 0.33 * S, 0.022 * S
    d.ellipse((C - r_out, C - r_out, C + r_out, C + r_out), outline=RING, width=int(w))

    # check mark
    pts = [(C - 0.15 * S, C + 0.005 * S), (C - 0.04 * S, C + 0.115 * S), (C + 0.165 * S, C - 0.115 * S)]
    d.line(pts, fill=RING, width=int(0.06 * S), joint="curve")
    for x, y in (pts[0], pts[-1]):
        r = 0.03 * S
        d.ellipse((x - r, y - r, x + r, y + r), fill=RING)

    out = Path(__file__).with_name("app-icon.png")
    img.resize((SIZE, SIZE), Image.LANCZOS).save(out)
    print(out)


if __name__ == "__main__":
    main()

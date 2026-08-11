"""
AirOS — Generate application and tray icons
Creates the PNG/ICO assets referenced by electron/main.js:
  public/icon.png      (256x256 window/app icon)
  public/icon16.png    (16x16 tray icon)
  public/icon.ico      (multi-size .ico for packaging)

Run: python scripts/generate_icons.py
"""

import os
from PIL import Image, ImageDraw

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(PROJECT_ROOT, "apps", "desktop", "public")


def draw_icon(size: int) -> Image.Image:
    """Draw the AirOS logo: dark rounded square, gradient ring, pointer glyph."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background rounded square
    pad = int(size * 0.08)
    bg = (15, 17, 23, 255)
    d.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=int(size * 0.22),
        fill=bg,
    )

    # Ring (drawn in segments for a subtle gradient feel)
    cx, cy = size / 2, size / 2
    r_outer = size * 0.34
    r_inner = size * 0.26
    top_color = (99, 179, 237, 255)     # #63b3ed
    bot_color = (183, 148, 244, 255)    # #b794f4

    steps = 40
    for i in range(steps):
        a0 = 360.0 * i / steps
        a1 = 360.0 * (i + 1) / steps
        t = i / steps
        color = tuple(
            int(top_color[k] + (bot_color[k] - top_color[k]) * t)
            for k in range(3)
        ) + (255,)
        d.arc(
            [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
            start=a0, end=a1, fill=color, width=max(2, int(size * 0.045)),
        )

    # Pointer: dot + stem
    dot_r = size * 0.10
    stem = max(2, int(size * 0.055))
    # Stem from center-top to dot
    stem_top = cy - r_inner * 0.6
    dot_cx, dot_cy = cx + r_inner * 0.45, cy + r_inner * 0.45
    d.line([cx, stem_top, dot_cx, dot_cy], fill=(99, 179, 237, 255), width=stem)
    d.ellipse(
        [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
        fill=(99, 179, 237, 255),
    )

    return img


def main():
    os.makedirs(PUBLIC_DIR, exist_ok=True)

    icon = draw_icon(256)
    icon.save(os.path.join(PUBLIC_DIR, "icon.png"))

    tray = draw_icon(16)
    tray.save(os.path.join(PUBLIC_DIR, "icon16.png"))

    # Multi-size .ico for packaging
    ico_path = os.path.join(PUBLIC_DIR, "icon.ico")
    icon.save(ico_path, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])

    print(f"Icons written to {PUBLIC_DIR}")
    for f in ("icon.png", "icon16.png", "icon.ico"):
        p = os.path.join(PUBLIC_DIR, f)
        print(f"  {f}: {os.path.getsize(p)} bytes")


if __name__ == "__main__":
    main()

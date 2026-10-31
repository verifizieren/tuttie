"""Draw the Tuttie app icons (the agent's eyes on the dark card) for the wallet PWA.

Writes apps/wallet/icons/{icon-192,icon-512,icon-maskable-512,apple-touch-icon}.png.
Pillow is only needed for this one-off script, not by the app:
    uv run --no-project --with pillow python scripts/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "apps" / "wallet" / "icons"
BACKGROUND = (8, 8, 11)
EYE = (255, 209, 187)
GLOW = (217, 119, 87)


def draw_icon(size: int, padding: float) -> Image.Image:
    """Two rounded eyes, like the neutral face, inside `padding` (share of the size) of margin."""
    icon = Image.new("RGB", (size, size), BACKGROUND)
    inner = size * (1 - 2 * padding)
    eye_w, eye_h = inner * 0.22, inner * 0.36
    gap = inner * 0.16
    radius = eye_w * 0.45
    cx, cy = size / 2, size / 2
    boxes = [(cx - gap / 2 - eye_w, cy - eye_h / 2, cx - gap / 2, cy + eye_h / 2),
             (cx + gap / 2, cy - eye_h / 2, cx + gap / 2 + eye_w, cy + eye_h / 2)]

    glow = Image.new("RGB", (size, size), BACKGROUND)
    glow_draw = ImageDraw.Draw(glow)
    for box in boxes:
        glow_draw.rounded_rectangle(box, radius=radius, fill=GLOW)
    icon = Image.blend(icon, glow.filter(ImageFilter.GaussianBlur(size * 0.04)), 0.8)

    draw = ImageDraw.Draw(icon)
    for box in boxes:
        draw.rounded_rectangle(box, radius=radius, fill=EYE)
    return icon


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size, padding in [("icon-192", 192, 0.12), ("icon-512", 512, 0.12),
                                ("icon-maskable-512", 512, 0.22), ("apple-touch-icon", 180, 0.12)]:
        draw_icon(size, padding).save(OUT / f"{name}.png", optimize=True)
        print("written:", (OUT / f"{name}.png").relative_to(OUT.parent.parent.parent))


if __name__ == "__main__":
    main()

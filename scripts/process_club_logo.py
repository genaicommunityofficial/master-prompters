"""Tight-crop ClubIcon.png: drop padding and the corner sparkle, keep the black field."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "asset" / "ClubIcon.png"
PUBLIC = ROOT / "frontend" / "public"


def content_mask(im: Image.Image) -> Image.Image:
    gray = im.convert("L")
    # Anything above near-black is logo paint.
    return gray.point(lambda v: 255 if v > 18 else 0, mode="L")


def remove_sparkle(mask: Image.Image) -> Image.Image:
    """Drop isolated specks in the lower-right (decorative star)."""
    w, h = mask.size
    px = mask.load()
    for y in range(int(h * 0.82), h):
        for x in range(int(w * 0.82), w):
            px[x, y] = 0
    return mask


def tight_crop(im: Image.Image, mask: Image.Image, pad: int = 10) -> Image.Image:
    bbox = mask.getbbox()
    if bbox is None:
        raise SystemExit("Logo content not found")
    left = max(0, bbox[0] - pad)
    top = max(0, bbox[1] - pad)
    right = min(im.width, bbox[2] + pad)
    bottom = min(im.height, bbox[3] + pad)
    cropped = im.crop((left, top, right, bottom)).convert("RGB")
    # Flatten any leftover transparency onto black.
    canvas = Image.new("RGB", cropped.size, (8, 8, 8))
    if im.mode == "RGBA":
        canvas.paste(cropped, mask=im.crop((left, top, right, bottom)).split()[-1])
        return canvas
    return cropped


def content_bbox(im: Image.Image, threshold: int = 40) -> tuple[int, int, int, int]:
    px = im.load()
    w, h = im.size
    xs: list[int] = []
    ys: list[int] = []
    for y in range(h):
        for x in range(w):
            if sum(px[x, y][:3]) > threshold:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise SystemExit("Logo content not found")
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def center_on_square(im: Image.Image, pad_ratio: float = 0.14) -> Image.Image:
    left, top, right, bottom = content_bbox(im)
    cropped = im.crop((left, top, right, bottom))
    cw, ch = cropped.size
    inner = max(cw, ch)
    pad = max(8, int(inner * pad_ratio))
    side = inner + pad * 2
    canvas = Image.new("RGB", (side, side), (8, 8, 8))
    canvas.paste(cropped, ((side - cw) // 2, (side - ch) // 2))
    return canvas


def round_corners(im: Image.Image, radius: int) -> Image.Image:
    im = im.convert("RGBA")
    mask = Image.new("L", im.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, im.width, im.height), radius=radius, fill=255)
    im.putalpha(mask.filter(ImageFilter.SMOOTH))
    return im


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    src = Image.open(SRC).convert("RGBA")
    mask = remove_sparkle(content_mask(src))
    lockup = tight_crop(src, mask, pad=8)
    lockup.save(PUBLIC / "club-logo.png", optimize=True)

    # GAi mark only: crop at the first sparse row after the letters.
    px = lockup.load()
    w, h = lockup.size
    cut_y = h
    for y in range(int(h * 0.45), h):
        lit = sum(1 for x in range(w) if sum(px[x, y][:3]) > 40)
        if lit < w * 0.06:
            cut_y = y
            break
    mark_rgb = lockup.crop((0, 0, lockup.width, cut_y))
    mark = center_on_square(mark_rgb, pad_ratio=0.16)
    mark.save(PUBLIC / "club-mark.png", optimize=True)

    fav = mark.resize((32, 32), Image.Resampling.LANCZOS)
    fav.save(PUBLIC / "favicon.png", optimize=True)
    apple = mark.resize((180, 180), Image.Resampling.LANCZOS)
    round_corners(apple, radius=36).save(PUBLIC / "apple-touch-icon.png", optimize=True)

    print("source", src.size)
    print("lockup", lockup.size)
    print("mark", mark.size)


if __name__ == "__main__":
    main()

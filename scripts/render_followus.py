"""Final 'follow us' slide: white background, logo on top, CTA paragraphs below (text from content/cta.json)."""
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
ROOT = os.path.join(os.path.dirname(__file__), "..")
FONTS_DIR = os.path.join(ROOT, "fonts")


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def load_cta():
    with open(os.path.join(ROOT, "content", "cta.json")) as f:
        return json.load(f)["paragraphs"]


def _trim(logo):
    """Crop away the empty padding around the wordmark."""
    arr = np.array(logo.convert("RGBA"))
    ink = (arr[..., 3] > 10) & (arr[..., :3].min(axis=2) < 235)
    ys, xs = np.nonzero(ink)
    return logo.crop((xs.min() - 6, ys.min() - 6, xs.max() + 7, ys.max() + 7))


def render_followus_slide(out_path, logo_path, paragraphs):
    img = Image.new("RGB", (W, H), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    logo = None
    if logo_path and os.path.exists(logo_path):
        logo = _trim(Image.open(logo_path).convert("RGBA"))
        lw = 420
        logo = logo.resize((lw, int(logo.height * lw / logo.width)))
    logo_h = logo.height if logo else 0
    logo_gap, gap, max_w = 90, 34, W - 200
    avail = H - 2 * 150 - logo_h - logo_gap
    reg, bold = os.path.join(FONTS_DIR, "Ubuntu-Regular.ttf"), os.path.join(FONTS_DIR, "Ubuntu-Bold.ttf")
    for fs in range(46, 27, -2):
        fonts = {False: ImageFont.truetype(reg, fs), True: ImageFont.truetype(bold, fs)}
        pitch = int(fs * 1.4)
        blocks = [(_wrap(draw, p["text"], fonts[p.get("bold", False)], max_w), p.get("bold", False)) for p in paragraphs]
        total = sum(len(b) * pitch for b, _ in blocks) + gap * (len(blocks) - 1)
        if total <= avail:
            break
    # centre logo + text as one block so the spacing is balanced
    y = (H - (logo_h + logo_gap + total)) // 2
    if logo:
        img.paste(logo, ((W - logo.width) // 2, y), logo)
        y += logo_h + logo_gap
    for lines, is_bold in blocks:
        for line in lines:
            w = draw.textlength(line, font=fonts[is_bold])
            draw.text(((W - w) / 2, y), line, font=fonts[is_bold], fill="#111111" if is_bold else "#444444")
            y += pitch
        y += gap
    img.save(out_path)

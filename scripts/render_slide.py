"""
Renders a single Instagram carousel slide for rlxed.

Design system:
- Main body/headline font: DejaVu Sans Bold (bundled directly in fonts/ —
  not a system fallback, so it renders identically everywhere).
- Label font: Quicksand Bold.
- Background: a solid base color plus an angled color "band" behind the
  text (the signature two-tone look), sized dynamically so the band
  always fully covers whatever text sits on it, however many lines.
- Each carousel draws from one 4-color palette: base, band, body text,
  label text. Palettes are hand-picked so contrast is always safe.
"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350  # 4:5 portrait — Instagram's recommended carousel ratio

FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "fonts")


def _font(filename, size):
    path = os.path.join(FONTS_DIR, filename)
    return ImageFont.truetype(path, size)


def body_bold(size):
    return _font("DejaVuSans-Bold.ttf", size)


def body_regular(size):
    return _font("DejaVuSans.ttf", size)


def label_font(size):
    return _font("Quicksand-Bold.ttf", size)


def ubuntu_regular(size):
    return _font("Ubuntu-Regular.ttf", size)


# ---- Color palettes -------------------------------------------------
# Each palette: base (fills most of canvas), band (the angled accent
# shape behind the text), body (main text color), label (label color).
# Picked so body text always has strong contrast against "band", and
# label text always has strong contrast against "base".
PALETTES = {
    "classic_dark": {"base": "#000000", "band": "#252424", "body": "#FFFFFF", "label": "#4169E1"},
    "charcoal_pop": {"base": "#252424", "band": "#000000", "body": "#E7E9EB", "label": "#4169E1"},
    "steel_light": {"base": "#A2A1A9", "band": "#000000", "body": "#FFFFFF", "label": "#000000"},
    "pure_contrast": {"base": "#FFFFFF", "band": "#000000", "body": "#FFFFFF", "label": "#000000"},
}
PALETTE_ORDER = ["classic_dark", "charcoal_pop", "steel_light", "pure_contrast"]


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = (current + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_centered_block(draw, lines, font, color, top_y, line_spacing=1.25):
    align_x = W // 2
    ascent, descent = font.getmetrics()
    line_height = int((ascent + descent) * line_spacing)
    y = top_y
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text((align_x - w / 2, y), line, font=font, fill=color)
        y += line_height
    return y


def _draw_angled_band(draw, top_y, bottom_y, color, tilt=40):
    """
    An angled parallelogram band spanning the full width, slanted by
    `tilt` pixels, guaranteed to fully cover [top_y, bottom_y] edge to edge.
    """
    draw.polygon(
        [(0, top_y + tilt), (W, top_y - tilt), (W, bottom_y - tilt), (0, bottom_y + tilt)],
        fill=color,
    )


def render_text_slide(label, body, out_path, palette_name="classic_dark", tilt=40):
    palette = PALETTES[palette_name]
    img = Image.new("RGB", (W, H), color=palette["base"])
    draw = ImageDraw.Draw(img)
    margin = 90

    # measure the body text block first so the band can fully contain it
    body_font = body_bold(66)
    lines = wrap_text(draw, body, body_font, W - 2 * margin)
    ascent, descent = body_font.getmetrics()
    line_spacing = 1.25
    line_height = int((ascent + descent) * line_spacing)
    block_height = len(lines) * line_height
    top_y = (H - block_height) // 2

    band_padding = 70
    band_top = max(top_y - band_padding, 260)  # keep clear of the label area
    band_bottom = min(top_y + block_height + band_padding, H - 60)
    _draw_angled_band(draw, band_top, band_bottom, palette["band"], tilt=tilt)

    if label:
        draw.text((margin, 90), label.upper(), font=label_font(32), fill=palette["label"])

    draw_centered_block(draw, lines, body_font, palette["body"], top_y, line_spacing=line_spacing)

    img.save(out_path)


def render_followus_slide(out_path, logo_path, tagline, palette_name="classic_dark"):
    palette = PALETTES[palette_name]
    img = Image.new("RGB", (W, H), color="#FFFFFF")
    draw = ImageDraw.Draw(img)

    if logo_path and os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        logo_w = 420
        ratio = logo_w / logo.width
        logo = logo.resize((logo_w, int(logo.height * ratio)))
        img.paste(logo, ((W - logo.width) // 2, 420), logo)
        tagline_top = 420 + logo.height + 60
    else:
        tagline_top = 500

    tagline_font = ubuntu_regular(40)
    lines = wrap_text(draw, tagline, tagline_font, W - 240)
    draw_centered_block(draw, lines, tagline_font, "#333333", tagline_top, line_spacing=1.4)

    img.save(out_path)

"""
Renders carousel slides from hand-made templates (see build_templates.py).

Design rules this enforces:
- text block is vertically centred on the SAME centre AE's placeholder text had
  (so the balance between shape and text is exactly as designed)
- text uses AE's own text colour for that design, left-aligned like the placeholder
- text never leaves the measured safe zone; font shrinks (down to MIN_FONT) to fit,
  and if even MIN_FONT can't fit, fit_text returns None so the caller can pick
  a different template instead of cramming
- rotated designs get rotated text at the same angle
"""
import json
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
ROOT = os.path.join(os.path.dirname(__file__), "..")
TEMPLATES_DIR = os.path.join(ROOT, "templates")
FONTS_DIR = os.path.join(ROOT, "fonts")
BODY_FONT = os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf")
LABEL_FONT = os.path.join(FONTS_DIR, "Quicksand-Bold.ttf")
MIN_FONT = 34
MAX_FONT = 64
LABEL_ACCENT = "#4169E1"


def load_templates():
    with open(os.path.join(TEMPLATES_DIR, "templates.json")) as f:
        return json.load(f)


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rotation(t):
    return cv2.getRotationMatrix2D(tuple(t["pivot"]), t["angle"], 1.0)


def zone_polygon(t):
    """Safe zone corners in the ORIGINAL image frame (for debugging overlays)."""
    (cx, cy), (hw, hh) = t["center"], t["zone_half"]
    pts = np.array([[cx - hw, cy - hh], [cx + hw, cy - hh], [cx + hw, cy + hh], [cx - hw, cy + hh]], np.float32)
    inv = cv2.invertAffineTransform(_rotation(t))
    return (pts @ inv[:, :2].T + inv[:, 2]).astype(int)


def wrap(draw, text, font, max_w):
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


def fit_text(text, t, has_label=False, min_font=MIN_FONT):
    """Largest font (and narrowest column) that fits the zone. None if even min_font can't."""
    (cx, cy), (hw, hh) = t["center"], t["zone_half"]
    if has_label and t["angle"] == 0:
        hh = min(hh, cy - 190)  # keep clear of the label at the top
    zone_w, zone_h = 2 * hw, 2 * hh
    if zone_h <= 0:
        return None
    ph_w = t["placeholder_box"][2] - t["placeholder_box"][0]
    lo = min(zone_w, ph_w)
    widths = sorted({round(lo + (zone_w - lo) * i / 6) for i in range(7)})
    d = ImageDraw.Draw(Image.new("L", (8, 8)))

    def is_widow(lines, font):
        if len(lines) < 2:
            return False
        last = lines[-1]
        longest = max(d.textlength(l, font=font) for l in lines)
        return len(last.split()) == 1 and d.textlength(last, font=font) < 0.4 * longest

    best_fallback = None  # first fit found, used only if no widow-free fit exists nearby
    top_fs = min(MAX_FONT, int(t["ref_font"] * 1.15))
    for fs in range(top_fs, min_font - 1, -2):
        font = ImageFont.truetype(BODY_FONT, fs)
        asc, desc = font.getmetrics()
        pitch = int((asc + desc) * 1.25)
        for wrap_w in widths:
            lines = wrap(d, text, font, wrap_w)
            bh = (len(lines) - 1) * pitch + asc + desc
            bw = max(d.textlength(l, font=font) for l in lines)
            if bh <= zone_h and bw <= zone_w:
                cand = {"fs": fs, "font": font, "lines": lines, "pitch": pitch, "bh": bh, "bw": bw}
                if not is_widow(lines, font):
                    return cand
                if best_fallback is None:
                    best_fallback = cand
        if best_fallback is not None and fs <= best_fallback["fs"] - 6:
            return best_fallback  # no widow-free layout within 6px of the best size
    return best_fallback


def _luminance(rgb):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _label_color(region_pixels):
    """Brand blue if it reads on whatever is behind the label, else white/black — contrast wins."""
    vals, counts = np.unique(region_pixels, axis=0, return_counts=True)
    behind = [tuple(int(x) for x in v) for v, c in zip(vals, counts) if c > 0.03 * len(region_pixels)] or [tuple(int(x) for x in vals[0])]
    options = [LABEL_ACCENT, "#FFFFFF", "#000000"]
    scored = [(min(_contrast(hex2rgb(o), b) for b in behind), o) for o in options]
    if scored[0][0] >= 3.0:
        return LABEL_ACCENT
    return max(scored[1:])[1]


def place_label(img_rgb, text, font):
    """Try the four corners; use the one whose background is cleanest (top-left preferred)."""
    lw = ImageDraw.Draw(img_rgb).textlength(text, font=font)
    corners = [(90, 90), (W - 90 - lw, 90), (90, H - 130), (W - 90 - lw, H - 130)]
    scored = []
    for x, y in corners:
        rect = (int(x) - 8, int(y) - 8, int(x + lw) + 8, int(y) + 48)
        region = np.array(img_rgb.crop(rect)).reshape(-1, 3)
        _, counts = np.unique(region, axis=0, return_counts=True)
        scored.append((counts.max() / len(region), (x, y), region))
    best = max(u for u, _, _ in scored)
    for u, pos, region in scored:
        if u >= best - 0.01:
            return pos, _label_color(region)


def render_slide(template_id, text, out_path, label=None, templates=None, fit=None):
    templates = templates or load_templates()
    t = templates[template_id]
    bg = Image.open(os.path.join(TEMPLATES_DIR, "clean", f"{template_id}.png")).convert("RGBA")
    fit = fit or fit_text(text, t, has_label=bool(label))
    if fit is None:
        raise ValueError(f"template {template_id} cannot fit this text at >= {MIN_FONT}px")

    # draw the text axis-aligned in the "deskewed" frame, then rotate the layer back
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = t["center"]
    left = cx - fit["bw"] / 2
    top = cy - fit["bh"] / 2
    if t["align"] == "center":
        for i, line in enumerate(fit["lines"]):
            lw = d.textlength(line, font=fit["font"])
            d.text((cx - lw / 2, top + i * fit["pitch"]), line, font=fit["font"], fill=hex2rgb(t["text_color"]))
    else:
        for i, line in enumerate(fit["lines"]):
            d.text((left, top + i * fit["pitch"]), line, font=fit["font"], fill=hex2rgb(t["text_color"]))
    if t["angle"] != 0:
        inv = cv2.invertAffineTransform(_rotation(t))
        arr = cv2.warpAffine(np.array(layer), inv, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        layer = Image.fromarray(arr)
    out = Image.alpha_composite(bg, layer)

    if label:
        lf = ImageFont.truetype(LABEL_FONT, 32)
        text_up = label.upper()
        pos, color = place_label(out.convert("RGB"), text_up, lf)
        ImageDraw.Draw(out).text(pos, text_up, font=lf, fill=color)
    out.convert("RGB").save(out_path)
    return fit["fs"]


# ---------------------------------------------------------------------------
# Template selection
# ---------------------------------------------------------------------------
SLOTS = [("hook", False), ("mid", True), ("why", True), ("closure", False)]  # (field, has_label)


def load_runs():
    with open(os.path.join(TEMPLATES_DIR, "families.json")) as f:
        return json.load(f)["runs"]


def load_excluded():
    path = os.path.join(TEMPLATES_DIR, "excluded.json")
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        return set(json.load(f).get("excluded_ids", []))


_EXCLUDED = None


def _usable(tid, T):
    global _EXCLUDED
    if _EXCLUDED is None:
        _EXCLUDED = load_excluded()
    return tid in T and tid not in _EXCLUDED


def select_templates(item, T, posts_published, runs=None):
    """
    Pick one design per slide for this carousel.
    Normal case: 4 consecutive designs from one run (= consecutive 15-degree variations
    of one shape). Runs take turns; each time a run comes round again it continues where
    it left off. Every candidate must fit ALL four texts at >= MIN_FONT, otherwise the next
    start position / next run is tried. Last resort: best individually-fitting designs.
    Returns (template_ids, fits, run_name).
    """
    runs = runs or load_runs()
    n = len(runs)
    for attempt in range(n):
        run = runs[(posts_published + attempt) % n]
        ids = [i for i in run["ids"] if _usable(i, T)]
        if not ids:
            continue
        if len(ids) < 4 and not run.get("allow_repeat"):
            continue
        base = ((posts_published // n) * 4) % len(ids)
        for shift in range(len(ids)):
            start = (base + shift) % len(ids)
            chosen = [ids[0]] * 4 if len(ids) < 4 else [ids[(start + i) % len(ids)] for i in range(4)]
            fits = [fit_text(item[f], T[tid], has_label=lab) for (f, lab), tid in zip(SLOTS, chosen)]
            if all(fits):
                return chosen, fits, run["name"]

    # last resort: any usable design that fits each slide on its own
    chosen, fits = [], []
    pool = [k for k in T if _usable(k, T)]
    for (f, lab) in SLOTS:
        for tid in pool:
            r = fit_text(item[f], T[tid], has_label=lab)
            if r:
                chosen.append(tid)
                fits.append(r)
                break
        else:
            raise ValueError(f"no template can fit {f!r} text at >= {MIN_FONT}px")
    return chosen, fits, "fallback"

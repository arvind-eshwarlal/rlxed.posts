"""
One-time tool: turns hand-made design PNGs (with placeholder text baked in)
into reusable templates.

For each design it:
  1. finds the placeholder text (the colour whose pixels form many letter-sized blobs)
  2. measures where that text sits, its rotation angle, alignment and size
  3. erases the text (fills with the nearest surrounding colour) -> clean background
  4. grows the text zone outward (symmetrically around the placeholder's centre, so
     the text keeps the original vertical/horizontal balance) until it would touch
     the edge of the shape, so longer real text has room

Usage:  python scripts/build_templates.py <input_dir> <output_dir>
Writes: <output_dir>/clean/<id>.png and <output_dir>/templates.json
"""
import glob
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

REF_FONT_RATIO = 1.455  # line pitch / font size for DejaVu Sans Bold at 1.25 spacing


def top_colors(arr, n=6):
    flat = (arr[..., 0].astype(np.int32) << 16) | (arr[..., 1].astype(np.int32) << 8) | arr[..., 2]
    vals, counts = np.unique(flat, return_counts=True)
    order = np.argsort(-counts)[:n]
    return [(((int(v) >> 16) & 255, (int(v) >> 8) & 255, int(v) & 255), int(c)) for v, c in zip(vals[order], counts[order])]


def find_text_mask(arr):
    """Return (text_color, mask_of_small_text_blobs) or None."""
    H, W, _ = arr.shape
    best = None
    for color, count in top_colors(arr, 6):
        if count < 0.002 * H * W:
            continue
        m = np.all(np.abs(arr.astype(int) - np.array(color)) <= 10, axis=2)
        lab, n = ndi.label(m)
        if n == 0:
            continue
        areas = ndi.sum(m, lab, index=np.arange(1, n + 1))
        keep = [i + 1 for i, a in enumerate(areas) if 30 <= a <= 6000]
        if len(keep) >= 20 and (best is None or len(keep) > best[0]):
            best = (len(keep), color, np.isin(lab, keep))
    if best is None:
        return None
    return best[1], best[2]


def main_block(mask):
    """Group blobs into blocks; return mask of the biggest block (the text) and group count."""
    grown = cv2.dilate(mask.astype(np.uint8), np.ones((61, 61), np.uint8))
    lab, n = ndi.label(grown)
    if n == 0:
        return None, 0
    sizes = ndi.sum(mask, lab, index=np.arange(1, n + 1))
    k = int(np.argmax(sizes)) + 1
    return (lab == k) & mask, n


def estimate_deskew(block_mask):
    ys, xs = np.nonzero(block_mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    crop = block_mask[y0:y1, x0:x1].astype(np.uint8) * 255
    size = int(np.hypot(*crop.shape)) + 8
    canvas = np.zeros((size, size), np.uint8)
    oy, ox = (size - crop.shape[0]) // 2, (size - crop.shape[1]) // 2
    canvas[oy:oy + crop.shape[0], ox:ox + crop.shape[1]] = crop

    def score(a):
        M = cv2.getRotationMatrix2D((size / 2, size / 2), a, 1.0)
        r = cv2.warpAffine(canvas, M, (size, size), flags=cv2.INTER_NEAREST)
        return float(np.var((r > 127).sum(axis=1)))

    coarse = max(np.arange(-60, 60.1, 3.0), key=score)
    fine = max(np.arange(coarse - 3, coarse + 3.01, 0.5), key=score)
    return 0.0 if abs(fine) < 1.5 else float(fine)


def line_info(block_d):
    """Lines (row runs) of the deskewed text block -> (lefts, rights, tops, bottoms)."""
    rows = block_d.any(axis=1)
    lines, start = [], None
    for y, v in enumerate(rows):
        if v and start is None:
            start = y
        if not v and start is not None:
            lines.append((start, y))
            start = None
    if start is not None:
        lines.append((start, len(rows)))
    lefts, rights = [], []
    for a, b in lines:
        cols = np.nonzero(block_d[a:b].any(axis=0))[0]
        lefts.append(int(cols.min()))
        rights.append(int(cols.max()))
    return lines, lefts, rights


def hexcolor(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


def process(path, out_clean):
    arr = np.array(Image.open(path).convert("RGB"))
    H, W, _ = arr.shape
    found = find_text_mask(arr)
    if found is None:
        return None
    text_color, small = found
    block, ngroups = main_block(small)
    if block is None or block.sum() < 500:
        return None

    # erase text: dilate to catch anti-aliasing, fill from nearest untouched pixel
    erase = cv2.dilate(block.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=3).astype(bool)
    _, (iy, ix) = ndi.distance_transform_edt(erase, return_indices=True)
    clean = arr[iy, ix]
    Image.fromarray(clean).save(out_clean)

    ys, xs = np.nonzero(block)
    pivot = (float((xs.min() + xs.max()) / 2), float((ys.min() + ys.max()) / 2))
    angle = estimate_deskew(block)
    M = cv2.getRotationMatrix2D(pivot, angle, 1.0)
    block_d = cv2.warpAffine(block.astype(np.uint8), M, (W, H), flags=cv2.INTER_NEAREST).astype(bool)
    ys, xs = np.nonzero(block_d)
    bx0, bx1, by0, by1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2

    lines, lefts, rights = line_info(block_d)
    if len(lines) >= 2:
        pitch = float(np.median([lines[i + 1][0] - lines[i][0] for i in range(len(lines) - 1)]))
    else:
        pitch = (by1 - by0) * 1.3
    if len(lefts) >= 2 and max(lefts) - min(lefts) <= 12:
        align = "left"
    elif len(rights) >= 2 and max(rights) - min(rights) <= 12:
        align = "right"
    elif len(lefts) >= 2:
        align = "center"
    else:
        align = "left"

    # shape colour = most common colour inside the placeholder bbox of the clean image
    box_pixels = clean[max(0, int(pivot[1]) - 150):int(pivot[1]) + 150, max(0, int(pivot[0]) - 150):int(pivot[0]) + 150]
    shape_color = top_colors(box_pixels, 1)[0][0]
    shape_mask = np.all(np.abs(clean.astype(int) - np.array(shape_color)) <= 22, axis=2).astype(np.uint8)
    shape_mask_d = cv2.warpAffine(shape_mask, M, (W, H), flags=cv2.INTER_NEAREST, borderValue=0)

    # margin the placeholder itself keeps from the shape edge (so we never demand more than AE chose)
    dist = cv2.distanceTransform(shape_mask_d, cv2.DIST_L2, 5)
    per = np.concatenate([dist[by0, bx0:bx1], dist[by1 - 1, bx0:bx1], dist[by0:by1, bx0], dist[by0:by1, bx1 - 1]])
    margin = int(np.clip(np.percentile(per, 5), 26, 40))
    eroded = (dist >= margin).astype(np.uint8)
    ii = cv2.integral(eroded)

    def inside(x0, y0, x1, y1):
        if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
            return False
        s = ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]
        return s == (x1 - x0) * (y1 - y0)

    hw, hh = (bx1 - bx0) / 2, (by1 - by0) / 2
    grow_x = grow_y = True
    while grow_x or grow_y:
        if grow_y and inside(int(cx - hw), int(cy - hh - 6), int(cx + hw), int(cy + hh + 6)):
            hh += 6
        else:
            grow_y = False
        if grow_x and inside(int(cx - hw - 6), int(cy - hh), int(cx + hw + 6), int(cy + hh)):
            hw += 6
        else:
            grow_x = False

    return {
        "text_color": hexcolor(text_color),
        "shape_color": hexcolor(shape_color),
        "base_color": hexcolor(top_colors(clean, 1)[0][0]),
        "angle": angle,
        "pivot": pivot,
        "center": [cx, cy],
        "placeholder_box": [bx0, by0, bx1, by1],
        "zone_half": [hw, hh],
        "align": align,
        "ref_font": round(pitch / REF_FONT_RATIO, 1),
        "line_count": len(lines),
        "groups": ngroups,
        "margin": margin,
    }


def main(in_dir, out_dir):
    os.makedirs(os.path.join(out_dir, "clean"), exist_ok=True)
    result, failed = {}, []
    for path in sorted(glob.glob(os.path.join(in_dir, "*.png")), key=lambda p: int(os.path.basename(p).split(".")[0])):
        tid = os.path.basename(path).split(".")[0]
        info = process(path, os.path.join(out_dir, "clean", f"{tid}.png"))
        if info is None:
            failed.append(tid)
        else:
            result[tid] = info
    with open(os.path.join(out_dir, "templates.json"), "w") as f:
        json.dump(result, f, indent=1)
    print(f"ok={len(result)} failed={failed}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

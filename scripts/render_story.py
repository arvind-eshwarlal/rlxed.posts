"""
STEP 1 of the story pipeline: build a DRAFT carousel from content/stories.json.
Nothing is posted anywhere. The draft is saved in content/drafts/<post_id>/ so you can look at it.

Usage:  python scripts/render_story.py <story_id | next>

Slide rules (checked automatically, the draft is refused if any fails):
  - 3 to 8 story slides (+ the automatic 'send this' slide + the closing brand slide = max 10, Instagram's limit)
  - hook: max 14 words; other slides: max 22 words
  - text must fit the slide at a readable size (hook >= 76px, other slides >= 54px)
  - the story must list at least one source
  - the caption text (with sources) must fit Threads' 500-character limit
Write [square brackets] around words you want shown in blue.
"""
import datetime
import json
import os
import re
import shutil
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STORIES = os.path.join(ROOT, "content", "stories.json")
SETTINGS = os.path.join(ROOT, "content", "story_settings.json")
STATE = os.path.join(ROOT, "state", "story_state.json")
DRAFTS = os.path.join(ROOT, "content", "drafts")
FONT_BOLD = os.path.join(ROOT, "fonts", "DejaVuSans-Bold.ttf")
LOGO = os.path.join(ROOT, "assets", "rlxed-logo.png")
CTA_JSON = os.path.join(ROOT, "content", "cta.json")
UBUNTU_REG = os.path.join(ROOT, "fonts", "Ubuntu-Regular.ttf")
UBUNTU_BOLD = os.path.join(ROOT, "fonts", "Ubuntu-Bold.ttf")

W, H, M = 1080, 1350, 90
BG, WHITE, GREY, BLUE = (14, 15, 18), (246, 246, 246), (130, 133, 142), (88, 128, 240)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def font(size):
    return ImageFont.truetype(FONT_BOLD, size)


def fail(messages):
    """Print every problem, put them in the run summary, and stop."""
    if isinstance(messages, str):
        messages = [messages]
    print("CANNOT CREATE THE DRAFT:", *messages, sep="\n  - ")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## ❌ The draft was not created\n\n" + "\n".join(f"- {m}" for m in messages) + "\n")
    sys.exit(1)


# ----------------------------------------------------------------------------- choosing the story
def published_ids():
    state = load_json(STATE, {"published": []})
    return {p["story_id"] for p in state.get("published", [])}


def pick_story(story_id):
    data = load_json(STORIES)
    if not data:
        fail("content/stories.json is missing")
    stories = data["stories"]
    done = published_ids()
    if story_id == "next":
        for s in stories:
            if s.get("status", "ready") == "ready" and s["id"] not in done:
                return s
        fail("No unpublished story with status 'ready' is left in content/stories.json - add more stories.")
    for s in stories:
        if s["id"] == story_id:
            if s["id"] in done:
                fail(f"Story '{story_id}' was already published. (Duplicates are blocked on purpose.)")
            if s.get("status", "ready") != "ready":
                fail(f"Story '{story_id}' has status '{s.get('status')}', not 'ready'.")
            return s
    ids = ", ".join(s["id"] for s in stories)
    fail(f"No story with id '{story_id}'. Available ids: {ids}")


# ----------------------------------------------------------------------------- text layout
def parse(text):
    """'plain [blue words] plain' -> list of (word, colour)."""
    out = []
    for m in re.finditer(r"\[([^\]]+)\]|(\S+)", text):
        if m.group(1):
            out.extend((w, BLUE) for w in m.group(1).split())
        else:
            out.append((m.group(2), WHITE))
    return out


def plain(text):
    return re.sub(r"[\[\]]", "", text)


def layout(draw, tokens, size, max_width):
    f = font(size)
    lines, cur = [], []
    for tok, col in tokens:
        trial = cur + [(tok, col)]
        if sum(draw.textlength(t + " ", font=f) for t, _ in trial) > max_width and cur:
            lines.append(cur)
            cur = [(tok, col)]
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines, int(size * 1.28)


def fit_text(draw, text, start, minimum, max_width, max_height):
    tokens = parse(text)
    size = start
    while size >= minimum:
        lines, lh = layout(draw, tokens, size, max_width)
        widest_word = max(draw.textlength(t, font=font(size)) for t, _ in tokens)
        if lh * len(lines) <= max_height and widest_word <= max_width:
            return size, lines, lh
        size -= 2
    return None


def render_slide(text, idx, total, is_hook, settings, out_path, last=False, sources_note=False):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    start, minimum = (92, 76) if is_hook else (64, 54)
    fitted = fit_text(d, text, start, minimum, W - 2 * M, H - 2 * 230)
    if not fitted:
        raise ValueError(f"Slide {idx} text is too long to show at a readable size (min {minimum}px): {plain(text)[:60]}...")
    size, lines, lh = fitted
    d.text((M, M), settings["series_label"], font=font(30), fill=BLUE)
    ctr = f"{idx}/{total}"
    d.text((W - M - d.textlength(ctr, font=font(30)), M + 2), ctr, font=font(30), fill=GREY)
    y = (H - lh * len(lines)) // 2 - 20
    for line in lines:
        x = M
        for tok, col in line:
            d.text((x, y), tok, font=font(size), fill=col)
            x += d.textlength(tok + " ", font=font(size))
        y += lh
    d.text((M, H - M - 34), settings["logo_text"], font=font(34), fill=GREY)
    if not last:
        d.text((W - M - d.textlength("→", font=font(56)), H - M - 52), "→", font=font(56), fill=WHITE)
    if sources_note:
        d.text((M, H - M - 100), "Sources in the caption", font=font(26), fill=GREY)
    img.save(out_path, "JPEG", quality=95, subsampling=0)
    return size


# ----------------------------------------------------------------------------- closing brand slide
def _wrap_words(draw, text, f, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=f) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _trim_logo(logo):
    """Crop the empty padding around the wordmark (same result as render_followus, without numpy)."""
    r, g, b, a = logo.convert("RGBA").split()
    darkish = ImageChops.darker(ImageChops.darker(r, g), b).point(lambda v: 255 if v < 235 else 0)
    solid = a.point(lambda v: 255 if v > 10 else 0)
    x0, y0, x1, y1 = ImageChops.multiply(darkish, solid).getbbox()
    return logo.crop((x0 - 6, y0 - 6, x1 + 6, y1 + 6))


def _logo_for_dark(logo):
    """Black wordmark -> white, keep the blue dot."""
    r, g, b, a = logo.split()
    blue = ImageChops.subtract(b, r).point(lambda v: 255 if v > 60 else 0)
    rgb = Image.composite(logo.convert("RGB"), Image.new("RGB", logo.size, (255, 255, 255)), blue)
    out = rgb.convert("RGBA")
    out.putalpha(a)
    return out


def brand_image(style):
    """The closing 'follow us' slide. style 'light' = your existing white slide; 'dark' = same words on the dark design.
    The words come from content/cta.json (the file you already edit)."""
    paragraphs = (load_json(CTA_JSON, {}) or {}).get("paragraphs", [])
    if not paragraphs:
        raise ValueError("content/cta.json has no paragraphs for the closing brand slide")
    dark = style == "dark"
    img = Image.new("RGB", (W, H), BG if dark else "#FFFFFF")
    draw = ImageDraw.Draw(img)
    logo = None
    if os.path.exists(LOGO):
        logo = _trim_logo(Image.open(LOGO).convert("RGBA"))
        if dark:
            logo = _logo_for_dark(logo)
        lw = 420
        logo = logo.resize((lw, int(logo.height * lw / logo.width)))
    logo_h = logo.height if logo else 0
    logo_gap, gap, max_w = 90, 34, W - 200
    avail = H - 2 * 150 - logo_h - logo_gap
    for fs in range(46, 27, -2):
        fonts = {False: ImageFont.truetype(UBUNTU_REG, fs), True: ImageFont.truetype(UBUNTU_BOLD, fs)}
        pitch = int(fs * 1.4)
        blocks = [(_wrap_words(draw, p["text"], fonts[p.get("bold", False)], max_w), p.get("bold", False)) for p in paragraphs]
        total = sum(len(b) * pitch for b, _ in blocks) + gap * (len(blocks) - 1)
        if total <= avail:
            break
    y = (H - (logo_h + logo_gap + total)) // 2
    if logo:
        img.paste(logo, ((W - logo.width) // 2, y), logo)
        y += logo_h + logo_gap
    reg_col, bold_col = ((200, 203, 210), (246, 246, 246)) if dark else ("#444444", "#111111")
    for lines, is_bold in blocks:
        for line in lines:
            w = draw.textlength(line, font=fonts[is_bold])
            draw.text(((W - w) / 2, y), line, font=fonts[is_bold], fill=bold_col if is_bold else reg_col)
            y += pitch
        y += gap
    return img


# ----------------------------------------------------------------------------- checks
def validate(story, settings):
    problems = []
    for key in ("id", "slides", "caption", "hashtags", "sources"):
        if not story.get(key):
            problems.append(f"story is missing '{key}'")
    if problems:
        return problems
    slides = story["slides"]
    extra = 1 if settings.get("brand_slide", "light") == "off" else 2
    if not 3 <= len(slides) <= settings["max_slides"] - extra:
        problems.append(f"needs 3 to {settings['max_slides'] - extra} story slides (plus the automatic closing slides); found {len(slides)}")
    for i, s in enumerate(slides, 1):
        words = len(plain(s).split())
        limit = settings["max_words_hook"] if i == 1 else settings["max_words_slide"]
        if words > limit:
            problems.append(f"slide {i} has {words} words (max {limit}): {plain(s)[:50]}...")
    if "[" in story["caption"] or "]" in story["caption"]:
        problems.append("the caption must not contain [square brackets]")
    text = caption_text(story)
    if len(text) > settings["threads_text_limit"]:
        problems.append(f"caption + sources is {len(text)} characters; Threads allows {settings['threads_text_limit']} - shorten it")
    if not all(h.startswith("#") and " " not in h for h in story["hashtags"]):
        problems.append("every hashtag must start with # and contain no spaces")
    return problems


def caption_text(story):
    return story["caption"].strip() + "\n\nSources: " + ", ".join(story["sources"])


# ----------------------------------------------------------------------------- contact sheet + summary
def contact_sheet(files, out_path):
    cols = 5 if len(files) > 8 else 4
    rows = (len(files) + cols - 1) // cols
    tw, th, gap = 360, 450, 10
    sheet = Image.new("RGB", (cols * (tw + gap) + gap, rows * (th + gap) + gap), (60, 60, 64))
    for k, f in enumerate(files):
        im = Image.open(f).resize((tw, th), Image.LANCZOS)
        sheet.paste(im, (gap + (k % cols) * (tw + gap), gap + (k // cols) * (th + gap)))
    sheet.save(out_path)


def write_summary(story, meta, post_dir_rel, sizes, settings):
    repo = os.environ.get("GITHUB_REPOSITORY", "OWNER/REPO")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    base = f"https://raw.githubusercontent.com/{repo}/{branch}/{post_dir_rel}"
    text = caption_text(story)
    lines = [
        f"## ✅ Draft ready: {story.get('person', story['id'])}",
        "",
        f"**Story id:** `{story['id']}`  |  **Slides:** {len(meta['slide_files'])}  |  **Closing brand slide:** {settings.get('brand_slide', 'light')}  |  **Nothing has been posted yet.**",
        "",
        f"![preview]({base}/preview.png)",
        "",
        "<details><summary>Open the slides one by one</summary>",
        "",
    ]
    for n, f in enumerate(meta["slide_files"], 1):
        lines.append(f"[Slide {n}]({base}/{f})  ")
    lines += [
        "",
        "</details>",
        "",
        "### Read it as one story (check the flow: does every slide make sense after the ones before it?)",
        "",
    ] + [f"{n}. {plain(t)}" for n, t in enumerate(story["slides"] + [story.get("cta") or settings["cta_text"]], 1)] + [
        "",
        "### Caption (Instagram and Facebook)",
        "",
        "```",
        meta["caption"],
        "```",
        "",
        f"### Threads text ({len(text)} of {settings['threads_text_limit']} characters)",
        "",
        "```",
        text,
        "```",
        "",
        "### Automatic checks passed",
        f"- slide count, word counts and text fit (smallest text used: {min(sizes)}px)",
        "- caption fits Threads; sources listed; nothing already published under this id",
        "",
        "### To approve and post it",
        "1. Open the **Actions** tab, choose **Step 2 - Approve and publish**, click **Run workflow**.",
        f"2. Type exactly: `{story['id']}`  then click the green **Run workflow** button.",
        "",
        "To change something instead: edit the story in `content/stories.json`, then run Step 1 again. A new draft replaces this one.",
    ]
    with open(os.path.join(DRAFTS, "SUMMARY.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ----------------------------------------------------------------------------- main
def main():
    if len(sys.argv) != 2:
        fail("Usage: render_story.py <story_id | next>")
    settings = load_json(SETTINGS, {})
    for k, v in {"series_label": "REAL STORIES", "cta_text": "Send this to someone who needs it. [Share the story.]",
                 "logo_text": ".rlxed", "brand_slide": "light", "max_slides": 10, "max_words_hook": 14, "max_words_slide": 22,
                 "threads_text_limit": 500}.items():
        settings.setdefault(k, v)
    story = pick_story(sys.argv[1].strip())
    problems = validate(story, settings)
    if problems:
        fail(problems)

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    post_id = f"{today}-{story['id']}-run{os.environ.get('GITHUB_RUN_NUMBER', 'local')}"

    # only one draft at a time: remove whatever was there before
    if os.path.isdir(DRAFTS):
        shutil.rmtree(DRAFTS)
    post_dir = os.path.join(DRAFTS, post_id)
    os.makedirs(post_dir)

    all_slides = list(story["slides"]) + [story.get("cta") or settings["cta_text"]]
    brand = settings.get("brand_slide", "light")
    if brand not in ("light", "dark", "off"):
        fail("brand_slide in content/story_settings.json must be 'light', 'dark' or 'off'")
    total = len(all_slides) + (0 if brand == "off" else 1)
    files, sizes = [], []
    try:
        for n, text in enumerate(all_slides, 1):
            name = f"slide_{n}.jpg"
            sizes.append(render_slide(text, n, total, n == 1, settings, os.path.join(post_dir, name),
                                      last=(n == total), sources_note=(n == len(all_slides))))
            files.append(name)
        if brand != "off":
            name = f"slide_{total}.jpg"
            brand_image(brand).save(os.path.join(post_dir, name), "JPEG", quality=95, subsampling=0)
            files.append(name)
    except ValueError as e:
        shutil.rmtree(DRAFTS, ignore_errors=True)
        fail(str(e))

    contact_sheet([os.path.join(post_dir, f) for f in files], os.path.join(post_dir, "preview.png"))
    caption = caption_text(story) + "\n\n" + " ".join(story["hashtags"])
    meta = {"post_id": post_id, "story_id": story["id"], "person": story.get("person"), "formats": ["carousel"],
            "slide_files": files, "caption": caption}
    with open(os.path.join(post_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    rel = f"content/drafts/{post_id}"
    write_summary(story, meta, rel, sizes, settings)

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"post_id={post_id}\nstory_id={story['id']}\npost_dir={rel}\n")
    print(json.dumps({"post_dir": rel, "post_id": post_id, "story_id": story["id"], "slides": total}))


if __name__ == "__main__":
    main()

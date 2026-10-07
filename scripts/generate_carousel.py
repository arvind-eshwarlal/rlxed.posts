"""
Picks the next content item in the theme rotation, renders all 5 slides
(hook, mid, why, closure, follow-us), and updates state.json.

Run from the repo root:
    python scripts/generate_carousel.py

Prints the generated post's folder path and caption as JSON on the last
line, which the GitHub Actions workflow captures and passes to the
publish script.
"""
import json
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(__file__))
from render_slide import render_text_slide, render_followus_slide, PALETTE_ORDER

ROOT = os.path.join(os.path.dirname(__file__), "..")
QUEUE_PATH = os.path.join(ROOT, "content", "queue.json")
STATE_PATH = os.path.join(ROOT, "state", "state.json")
GENERATED_DIR = os.path.join(ROOT, "content", "generated")
LOGO_PATH = os.path.join(ROOT, "assets", "rlxed-logo.png")

FOLLOWUS_TAGLINE = "App for the work you put in. Content to keep you in play. Follow us for more."

# slide-2 label per theme, so every "mid" slide is labeled, not just science
MID_LABELS = {
    "science": "The Science",
    "tag": "Tag Them",
    "confessional": "Real Talk",
}


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def main():
    queue = load_json(QUEUE_PATH)
    state = load_json(STATE_PATH)

    rotation = queue["rotation_order"]
    theme = rotation[state["theme_pointer"] % len(rotation)]

    items = queue["items"][theme]
    item_ptr = state["theme_item_pointers"][theme]
    looped = item_ptr >= len(items)
    item_index = item_ptr % len(items)
    item = items[item_index]

    if looped:
        print(f"WARNING: {theme} queue has looped back to item {item_index + 1} "
              f"— all {len(items)} items already used. Send more content soon.",
              file=sys.stderr)

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "local")
    post_id = f"{today}-{item['id']}-run{run_number}"
    post_dir = os.path.join(GENERATED_DIR, post_id)
    os.makedirs(post_dir, exist_ok=True)

    # cycle the palette by total posts published so consecutive carousels
    # don't all look identical, while each single carousel stays consistent
    palette_name = PALETTE_ORDER[state.get("posts_published", 0) % len(PALETTE_ORDER)]

    slide_files = []

    hook_path = os.path.join(post_dir, "1_hook.png")
    render_text_slide(None, item["hook"], hook_path, palette_name=palette_name)
    slide_files.append("1_hook.png")

    mid_path = os.path.join(post_dir, "2_mid.png")
    render_text_slide(MID_LABELS[theme], item["mid"], mid_path, palette_name=palette_name)
    slide_files.append("2_mid.png")

    why_path = os.path.join(post_dir, "3_why.png")
    render_text_slide("Why It Matters", item["why"], why_path, palette_name=palette_name)
    slide_files.append("3_why.png")

    closure_path = os.path.join(post_dir, "4_closure.png")
    render_text_slide(None, item["closure"], closure_path, palette_name=palette_name)
    slide_files.append("4_closure.png")

    followus_path = os.path.join(post_dir, "5_followus.png")
    render_followus_slide(followus_path, LOGO_PATH, FOLLOWUS_TAGLINE, palette_name=palette_name)
    slide_files.append("5_followus.png")

    full_caption = item["caption"] + "\n\n" + " ".join(item["hashtags"])

    meta = {
        "post_id": post_id,
        "theme": theme,
        "item_id": item["id"],
        "slide_files": slide_files,
        "caption": full_caption,
    }
    save_json(os.path.join(post_dir, "meta.json"), meta)

    # advance state
    state["theme_pointer"] = (state["theme_pointer"] + 1) % len(rotation)
    state["theme_item_pointers"][theme] = item_ptr + 1
    state["last_post_id"] = post_id
    state["posts_published"] = state.get("posts_published", 0) + 1
    save_json(STATE_PATH, state)

    # last line: machine-readable output for the workflow to pick up
    print(json.dumps({"post_dir": f"content/generated/{post_id}", "post_id": post_id}))


if __name__ == "__main__":
    main()

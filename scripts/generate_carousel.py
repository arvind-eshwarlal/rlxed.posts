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
from template_render import load_templates, render_slide, select_templates, SLOTS
from render_followus import render_followus_slide, load_cta
from make_reel import build_reel

ROOT = os.path.join(os.path.dirname(__file__), "..")
QUEUE_PATH = os.path.join(ROOT, "content", "queue.json")
STATE_PATH = os.path.join(ROOT, "state", "state.json")
GENERATED_DIR = os.path.join(ROOT, "content", "generated")
LOGO_PATH = os.path.join(ROOT, "assets", "rlxed-logo.png")
SETTINGS_PATH = os.path.join(ROOT, "content", "settings.json")
MUSIC_DIR = os.path.join(ROOT, "music")


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

    # pick designs: 4 consecutive 15-degree variations of one shape, all verified to fit the text
    posts_so_far = state.get("posts_published", 0)
    settings = load_json(SETTINGS_PATH) if os.path.exists(SETTINGS_PATH) else {}
    fmt = settings.get("format", "carousel")
    if fmt == "alternate":
        formats = ["reel"] if posts_so_far % 2 == 1 else ["carousel"]
    elif fmt == "both":
        formats = ["carousel", "reel"]
    else:
        formats = [fmt]
    templates = load_templates()
    template_ids, fits, run_name = select_templates(item, templates, posts_so_far)

    labels = {"hook": None, "mid": MID_LABELS[theme], "why": "Why It Matters", "closure": None}
    slide_files = []
    for n, ((field, _), tid, fit) in enumerate(zip(SLOTS, template_ids, fits), start=1):
        name = f"{n}_{field}.png"
        render_slide(tid, item[field], os.path.join(post_dir, name), label=labels[field], templates=templates, fit=fit)
        slide_files.append(name)

    followus_name = "5_followus.png"
    render_followus_slide(os.path.join(post_dir, followus_name), LOGO_PATH, load_cta())
    slide_files.append(followus_name)

    video_file, music_info = None, None
    if "reel" in formats:
        tracks = load_json(os.path.join(MUSIC_DIR, "music.json")) if os.path.exists(os.path.join(MUSIC_DIR, "music.json")) else []
        if not tracks:
            raise RuntimeError("Reel requested but music/music.json is missing or empty - upload the music folder")
        music_info = tracks[state.get("reels_made", 0) % len(tracks)]
        cta_text = " ".join(p["text"] for p in load_cta())
        texts = [item["hook"], item["mid"], item["why"], item["closure"], cta_text]
        video_file = "reel.mp4"
        build_reel([os.path.join(post_dir, f) for f in slide_files], texts,
                   os.path.join(MUSIC_DIR, music_info["file"]), os.path.join(post_dir, video_file))
        state["reels_made"] = state.get("reels_made", 0) + 1

    full_caption = item["caption"] + "\n\n" + " ".join(item["hashtags"])

    meta = {
        "post_id": post_id,
        "theme": theme,
        "item_id": item["id"],
        "slide_files": slide_files,
        "templates": template_ids,
        "run": run_name,
        "formats": formats,
        "video_file": video_file,
        "music": music_info,
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

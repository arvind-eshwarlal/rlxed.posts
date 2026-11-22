"""
Helpers for STEP 2 of the story pipeline (approve and publish).

  check   <story_id>            the single saved draft must be this story, and not already published
  promote <story_id>            move the approved draft from content/drafts to content/generated
  publish <post_dir> [--dry-run]  post to Instagram, then Threads and Facebook (reuses publish_carousel.py)
  list                          show every story and whether it is published
"""
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DRAFTS = os.path.join(ROOT, "content", "drafts")
GENERATED = os.path.join(ROOT, "content", "generated")
STATE = os.path.join(ROOT, "state", "story_state.json")
STORIES = os.path.join(ROOT, "content", "stories.json")


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def stop(msg):
    print(f"STOPPED: {msg}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## ❌ Stopped - nothing was posted\n\n{msg}\n")
    sys.exit(1)


def find_draft():
    metas = glob.glob(os.path.join(DRAFTS, "*", "meta.json"))
    if not metas:
        stop("There is no saved draft. Run 'Step 1 - Create story carousel' first.")
    if len(metas) > 1:
        stop("More than one draft is saved. Run Step 1 again to create a single fresh draft.")
    return os.path.dirname(metas[0]), load_json(metas[0])


def already_published(story_id):
    state = load_json(STATE, {"published": []})
    return [p for p in state.get("published", []) if p["story_id"] == story_id]


def cmd_check(story_id):
    folder, meta = find_draft()
    if meta.get("story_id") != story_id:
        stop(f"You typed '{story_id}' but the saved draft is for '{meta.get('story_id')}'. "
             f"Type exactly '{meta.get('story_id')}' to approve that draft, or run Step 1 again for the one you want.")
    if already_published(story_id):
        stop(f"Story '{story_id}' is already published, so it was not posted again. "
             "To fix a missing platform use the 'Cross-post an existing post' workflow.")
    print(f"OK: draft '{meta['post_id']}' matches '{story_id}' and has not been published.")
    print(json.dumps({"post_id": meta["post_id"], "slides": len(meta["slide_files"])}))


def cmd_promote(story_id):
    folder, meta = find_draft()
    if meta.get("story_id") != story_id:
        stop("Draft does not match the story id.")
    target = os.path.join(GENERATED, meta["post_id"])
    os.makedirs(GENERATED, exist_ok=True)
    if os.path.exists(target):
        stop(f"{target} already exists.")
    shutil.move(folder, target)
    summary = os.path.join(DRAFTS, "SUMMARY.md")
    if os.path.exists(summary):
        os.remove(summary)
    rel = f"content/generated/{meta['post_id']}"
    print(json.dumps({"post_dir": rel, "post_id": meta["post_id"]}))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"post_dir={rel}\npost_id={meta['post_id']}\n")


def cmd_publish(post_dir, dry_run=False):
    meta = load_json(os.path.join(ROOT, post_dir, "meta.json"))
    if not meta:
        stop(f"No meta.json in {post_dir}")
    if dry_run:
        print("DRY RUN - nothing is sent to any platform.")
        print(f"Would post {len(meta['slide_files'])} slides from {post_dir} to Instagram, Threads and Facebook.")
        print("Caption:\n" + meta["caption"])
        return 0
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "scripts", "publish_carousel.py"), post_dir],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
    instagram_done, ig_info = False, None
    for line in proc.stdout:
        print(line, end="")
        s = line.strip()
        if s.startswith("{") and '"published"' in s:
            try:
                ig_info = json.loads(s)
                instagram_done = bool(ig_info.get("published"))
            except json.JSONDecodeError:
                pass
    rc = proc.wait()
    if instagram_done:
        state = load_json(STATE, {"published": []})
        state["published"].append({
            "story_id": meta["story_id"], "post_id": meta["post_id"],
            "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "status": "published" if rc == 0 else "instagram-published-but-another-platform-failed",
            "instagram": ig_info["published"]})
        save_json(STATE, state)
        print(f"Recorded '{meta['story_id']}' as published in state/story_state.json")
    else:
        print("Instagram did not publish, so the story was NOT recorded as published.")
    return rc


def cmd_list():
    data = load_json(STORIES, {"stories": []})
    done = {p["story_id"]: p for p in load_json(STATE, {"published": []}).get("published", [])}
    for s in data["stories"]:
        mark = "PUBLISHED " + done[s["id"]]["date"] if s["id"] in done else s.get("status", "ready")
        print(f"{s['id']:<28} {mark}")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    if a[0] == "check" and len(a) == 2:
        cmd_check(a[1].strip())
    elif a[0] == "promote" and len(a) == 2:
        cmd_promote(a[1].strip())
    elif a[0] == "publish" and len(a) >= 2:
        sys.exit(cmd_publish(a[1], dry_run="--dry-run" in a))
    elif a[0] == "list":
        cmd_list()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

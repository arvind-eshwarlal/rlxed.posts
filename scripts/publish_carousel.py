"""
Publishes one already-generated carousel to Instagram.

Usage:
    python scripts/publish_carousel.py content/generated/2026-10-06-science-01-run12

Requires environment variables:
    IG_USER_ID       - e.g. 38924023033908560
    IG_ACCESS_TOKEN  - the long-lived access token
    GITHUB_REPOSITORY - "owner/repo" (GitHub Actions sets this automatically)
    GITHUB_REF_NAME   - branch name, usually "main" (set automatically)

The images in the post folder MUST already be pushed to GitHub and
publicly fetchable at their raw.githubusercontent.com URL before this
script runs — Instagram's API fetches the image from that URL.
"""
import json
import os
import sys
import time
import urllib.parse
import requests

ROOT = os.path.join(os.path.dirname(__file__), "..")

GRAPH = "https://graph.instagram.com/v21.0"


def raw_url(repo, branch, relative_path):
    encoded = "/".join(urllib.parse.quote(part) for part in relative_path.split("/"))
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{encoded}"


def create_item_container(ig_user_id, token, image_url):
    resp = requests.post(f"{GRAPH}/{ig_user_id}/media", data={
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": token,
    })
    resp.raise_for_status()
    return resp.json()["id"]


def create_carousel_container(ig_user_id, token, children_ids, caption):
    resp = requests.post(f"{GRAPH}/{ig_user_id}/media", data={
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": token,
    })
    resp.raise_for_status()
    return resp.json()["id"]


def publish_container(ig_user_id, token, creation_id):
    resp = requests.post(f"{GRAPH}/{ig_user_id}/media_publish", data={
        "creation_id": creation_id,
        "access_token": token,
    })
    resp.raise_for_status()
    return resp.json()["id"]


def load_settings():
    path = os.path.join(ROOT, "content", "settings.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def wait_until_ready(token, container_id, timeout=300, every=6):
    """Videos are processed by Instagram after upload; wait until FINISHED."""
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{GRAPH}/{container_id}", params={"fields": "status_code,status", "access_token": token})
        r.raise_for_status()
        data = r.json()
        code = data.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"video container {code}: {data.get('status')}")
        time.sleep(every)
    raise RuntimeError("timed out waiting for Instagram to process the video")


def create_reel_container(ig_user_id, token, caption, video_url=None):
    data = {"media_type": "REELS", "caption": caption, "share_to_feed": "true", "access_token": token}
    if video_url:
        data["video_url"] = video_url
    else:
        data["upload_type"] = "resumable"
    resp = requests.post(f"{GRAPH}/{ig_user_id}/media", data=data)
    resp.raise_for_status()
    return resp.json()


def upload_resumable(uri, token, path):
    with open(path, "rb") as fh:
        resp = requests.post(uri, headers={"Authorization": f"OAuth {token}", "offset": "0",
                                           "file_size": str(os.path.getsize(path))}, data=fh)
    resp.raise_for_status()


def publish_reel(ig_user_id, token, post_dir, meta, repo, branch, mode):
    video_path = os.path.join(post_dir, meta["video_file"])
    last_err = None
    for attempt in range(3):
        try:
            if mode == "resumable":
                created = create_reel_container(ig_user_id, token, meta["caption"])
                upload_resumable(created["uri"], token, video_path)
            else:
                url = raw_url(repo, branch, f"{post_dir}/{meta['video_file']}")
                print(f"Creating Reel container from {url}")
                created = create_reel_container(ig_user_id, token, meta["caption"], video_url=url)
            wait_until_ready(token, created["id"])
            return publish_container(ig_user_id, token, created["id"])
        except (requests.HTTPError, RuntimeError) as e:
            last_err = e
            detail = e.response.text if isinstance(e, requests.HTTPError) and e.response is not None else str(e)
            print(f"  Reel attempt {attempt + 1} failed: {detail}")
            time.sleep(30)
    raise last_err


def main():
    if len(sys.argv) != 2:
        print("Usage: publish_carousel.py <post_dir>", file=sys.stderr)
        sys.exit(1)

    post_dir = sys.argv[1]
    meta_path = os.path.join(post_dir, "meta.json")
    with open(meta_path) as f:
        meta = json.load(f)

    ig_user_id = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("GITHUB_REF_NAME", "main")

    settings = load_settings()
    formats = meta.get("formats", ["carousel"])
    published = {}

    if "carousel" in formats:
        child_ids = []
        for slide_file in meta["slide_files"]:
            rel_path = f"{post_dir}/{slide_file}"
            url = raw_url(repo, branch, rel_path)
            print(f"Creating item container for {url}")
            # small retry loop in case GitHub's raw CDN hasn't caught up yet
            last_err = None
            for attempt in range(5):
                try:
                    cid = create_item_container(ig_user_id, token, url)
                    child_ids.append(cid)
                    last_err = None
                    break
                except requests.HTTPError as e:
                    last_err = e
                    print(f"  attempt {attempt + 1} failed, retrying in 10s: {e.response.text}")
                    time.sleep(10)
            if last_err:
                raise last_err

        print(f"Created {len(child_ids)} item containers. Creating carousel container...")
        carousel_id = create_carousel_container(ig_user_id, token, child_ids, meta["caption"])
        print(f"Publishing carousel {carousel_id}...")
        time.sleep(5)  # the parent container sometimes needs a moment to finish processing
        published["carousel"] = publish_container(ig_user_id, token, carousel_id)

    if "reel" in formats:
        print("Publishing Reel...")
        published["reel"] = publish_reel(ig_user_id, token, post_dir, meta, repo, branch,
                                         settings.get("video_upload", "url"))

    print(json.dumps({"published": published, "post_id": meta["post_id"]}))

    # same content to Threads / Facebook Page (each switched on in content/crosspost.json)
    from crosspost import crosspost_all
    errors = crosspost_all(meta, post_dir, repo, branch)
    if errors:
        print("CROSSPOST PROBLEMS:", *errors, sep="\n  ")
        sys.exit(1)  # Instagram already published; this just makes the run show red so you notice


if __name__ == "__main__":
    main()

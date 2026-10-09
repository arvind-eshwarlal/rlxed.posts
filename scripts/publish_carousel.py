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
    # the parent container sometimes needs a moment to finish processing
    time.sleep(5)
    media_id = publish_container(ig_user_id, token, carousel_id)

    print(json.dumps({"published_media_id": media_id, "post_id": meta["post_id"]}))


if __name__ == "__main__":
    main()

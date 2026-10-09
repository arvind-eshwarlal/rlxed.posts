"""
Posts the same content to Threads and to the Facebook Page, right after Instagram.

Each platform is optional and independent: it only runs if switched on in content/crosspost.json
AND its token secret exists. One platform failing never stops the others (or undoes Instagram).

Threads : carousel -> Threads carousel of the slides ; reel -> Threads video
Facebook: carousel -> multi-photo Page post          ; reel -> Page Reel
Facebook GROUPS are not possible: Meta removed the Groups API in 2024.
"""
import json
import os
import time
import urllib.parse

import requests

THREADS_HOSTS = ["https://graph.threads.net/v1.0", "https://graph.threads.com/v1.0"]
FB_GRAPH = "https://graph.facebook.com/v25.0"
ROOT = os.path.join(os.path.dirname(__file__), "..")


def raw_url(repo, branch, rel):
    return f"https://raw.githubusercontent.com/{repo}/{branch}/" + "/".join(urllib.parse.quote(p) for p in rel.split("/"))


def split_caption(full):
    """The saved caption is 'text\\n\\n#tag #tag #tag' -> (text, [tags])."""
    text, _, tags = full.partition("\n\n#")
    return text.strip(), (("#" + tags).split() if tags else [])


def _check(resp):
    if not resp.ok:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
    return resp.json()


# ----------------------------------------------------------------------------- Threads
def _threads_base(token):
    last = None
    for base in THREADS_HOSTS:
        try:
            r = requests.get(f"{base}/me", params={"fields": "id", "access_token": token}, timeout=30)
            if r.status_code == 200:
                return base, r.json()["id"]
            last = r.text
        except requests.ConnectionError as e:
            last = str(e)
    raise RuntimeError(f"Threads rejected the token or could not be reached: {last}")


def _threads_wait(base, token, cid, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        d = _check(requests.get(f"{base}/{cid}", params={"fields": "status,error_message", "access_token": token}))
        if d.get("status") in ("FINISHED", "PUBLISHED"):
            return
        if d.get("status") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Threads container {d['status']}: {d.get('error_message')}")
        time.sleep(5)
    raise RuntimeError("timed out waiting for Threads to process the media")


def post_threads(token, meta, post_dir, repo, branch, fmt):
    base, uid = _threads_base(token)
    text, tags = split_caption(meta["caption"])
    text = text if len(text) <= 500 else text[:497] + "..."
    extra = {"topic_tag": tags[0].lstrip("#")} if tags else {}
    last = None
    for attempt in range(3):
        try:
            if fmt == "carousel":
                kids = []
                for f in meta["slide_files"]:
                    r = requests.post(f"{base}/{uid}/threads", data={
                        "media_type": "IMAGE", "image_url": raw_url(repo, branch, f"{post_dir}/{f}"),
                        "is_carousel_item": "true", "access_token": token})
                    kids.append(_check(r)["id"])
                for k in kids:
                    _threads_wait(base, token, k)
                r = requests.post(f"{base}/{uid}/threads", data={
                    "media_type": "CAROUSEL", "children": ",".join(kids), "text": text, "access_token": token, **extra})
            else:
                r = requests.post(f"{base}/{uid}/threads", data={
                    "media_type": "VIDEO", "video_url": raw_url(repo, branch, f"{post_dir}/{meta['video_file']}"),
                    "text": text, "access_token": token, **extra})
            container = _check(r)["id"]
            _threads_wait(base, token, container)
            return _check(requests.post(f"{base}/{uid}/threads_publish", data={"creation_id": container, "access_token": token}))["id"]
        except RuntimeError as e:
            last = e
            print(f"  Threads attempt {attempt + 1} failed: {e}")
            time.sleep(20)
    raise last


# ----------------------------------------------------------------------------- Facebook Page
def _fb_post_photos(token, page, meta, post_dir, repo, branch, count):
    ids = []
    for f in meta["slide_files"][:count]:
        r = requests.post(f"{FB_GRAPH}/{page}/photos", data={
            "url": raw_url(repo, branch, f"{post_dir}/{f}"), "published": "false", "access_token": token})
        ids.append(_check(r)["id"])
    data = {"message": meta["caption"], "access_token": token}
    for i, pid in enumerate(ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    return _check(requests.post(f"{FB_GRAPH}/{page}/feed", data=data))["id"]


def _fb_post_reel(token, page, meta, post_dir):
    path = os.path.join(post_dir, meta["video_file"])
    start = _check(requests.post(f"{FB_GRAPH}/{page}/video_reels", data={"upload_phase": "start", "access_token": token}))
    video_id = start["video_id"]
    url = start.get("upload_url") or f"https://rupload.facebook.com/video-upload/v25.0/{video_id}"
    with open(path, "rb") as fh:
        _check(requests.post(url, headers={"Authorization": f"OAuth {token}", "offset": "0",
                                           "file_size": str(os.path.getsize(path))}, data=fh))
    last = None
    for _ in range(5):
        try:
            return _check(requests.post(f"{FB_GRAPH}/{page}/video_reels", data={
                "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
                "description": meta["caption"], "access_token": token}))
        except RuntimeError as e:
            last = e
            print(f"  Facebook Reel not ready yet, retrying: {e}")
            time.sleep(15)
    raise last


def post_facebook(token, meta, post_dir, repo, branch, fmt):
    page = _check(requests.get(f"{FB_GRAPH}/me", params={"fields": "id,name", "access_token": token}))["id"]
    if fmt == "reel":
        return _fb_post_reel(token, page, meta, post_dir)
    try:
        return _fb_post_photos(token, page, meta, post_dir, repo, branch, len(meta["slide_files"]))
    except RuntimeError as e:  # some accounts cap multi-photo posts; retry with the first 4 slides
        print(f"  Facebook rejected {len(meta['slide_files'])} photos ({e}); retrying with 4")
        return _fb_post_photos(token, page, meta, post_dir, repo, branch, 4)


# ----------------------------------------------------------------------------- orchestration
def crosspost_all(meta, post_dir, repo, branch):
    path = os.path.join(ROOT, "content", "crosspost.json")
    cfg = json.load(open(path)) if os.path.exists(path) else {}
    jobs = [("threads", "THREADS_ACCESS_TOKEN", post_threads), ("facebook", "FB_PAGE_ACCESS_TOKEN", post_facebook)]
    errors = []
    for name, env, fn in jobs:
        if not cfg.get(name):
            continue
        token = os.environ.get(env)
        if not token:
            print(f"{name}: switched on but secret {env} is missing - skipped")
            errors.append(f"{name}: missing secret {env}")
            continue
        for fmt in meta.get("formats", ["carousel"]):
            try:
                print(f"{name}: posting {fmt}...")
                print(f"{name} {fmt} published:", fn(token, meta, post_dir, repo, branch, fmt))
            except Exception as e:  # noqa: BLE001 - one platform must never stop the others
                print(f"{name} {fmt} FAILED: {e}")
                errors.append(f"{name} {fmt}: {e}")
    return errors

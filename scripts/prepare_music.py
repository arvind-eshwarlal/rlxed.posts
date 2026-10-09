"""
One-time tool: turn a folder of music files into small, evenly-loud clips for the Reels.

For each track it skips leading silence, keeps up to CLIP_SECONDS, normalises loudness
to about -16 LUFS (so no track is much louder than another), and saves a 128 kbps MP3.

Usage:  python scripts/prepare_music.py <folder_with_mp3s> music
Writes: music/01.mp3, music/02.mp3 ... and music/music.json (which clip came from which file)
"""
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from media_tools import ffmpeg_path

CLIP_SECONDS = 60


def pretty(name):
    base = os.path.splitext(os.path.basename(name))[0]
    return re.sub(r"[-_]+", " ", re.sub(r"[-_]?\d{4,}$", "", base)).strip()


def main(src, dst):
    os.makedirs(dst, exist_ok=True)
    files = sorted(glob.glob(os.path.join(src, "*.mp3")))
    meta = []
    for i, f in enumerate(files, start=1):
        out = os.path.join(dst, f"{i:02d}.mp3")
        af = ("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.1,"
              "loudnorm=I=-16:TP=-1.5:LRA=11")
        cmd = [ffmpeg_path(), "-y", "-v", "error", "-i", f, "-af", af, "-t", str(CLIP_SECONDS),
               "-ar", "44100", "-ac", "2", "-b:a", "128k", out]
        subprocess.run(cmd, check=True)
        meta.append({"file": f"{i:02d}.mp3", "title": pretty(f), "source_file": os.path.basename(f)})
        print(f"{i:02d}.mp3  <-  {os.path.basename(f)}")
    with open(os.path.join(dst, "music.json"), "w") as fh:
        json.dump(meta, fh, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

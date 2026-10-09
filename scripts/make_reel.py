"""
Builds a Reel (vertical 1080x1920 MP4) from a carousel's slide images plus a music clip.

- each slide stays on screen long enough to read (about 0.26s per word, between 3.2s and 8s)
- soft crossfades between slides; slide 1 is the very first frame, so it is also the cover
- the 4:5 slides sit in the middle of the 9:16 frame over a blurred, dimmed copy of themselves
- music is faded in/out and cut to the video length (looped if the clip were ever shorter)
- encoded to Instagram's Reels spec: H.264 + AAC 128 kbps / 44.1 kHz, 30 fps, faststart,
  closed GOP, no edit list
"""
import os
import subprocess
import tempfile

from PIL import Image, ImageEnhance, ImageFilter

from media_tools import ffmpeg_path

RW, RH = 1080, 1920
FPS = 30
FADE = 0.5


def reading_seconds(text):
    return min(8.0, max(3.2, 2.0 + 0.26 * len(text.split())))


def _frame(slide_path, out_path):
    s = Image.open(slide_path).convert("RGB")
    scale = max(RW / s.width, RH / s.height)
    bg = s.resize((int(s.width * scale) + 1, int(s.height * scale) + 1))
    left, top = (bg.width - RW) // 2, (bg.height - RH) // 2
    bg = bg.crop((left, top, left + RW, top + RH)).filter(ImageFilter.GaussianBlur(40))
    bg = ImageEnhance.Brightness(bg).enhance(0.45)
    bg.paste(s, (0, (RH - s.height) // 2))
    bg.save(out_path)


def build_reel(slide_paths, texts, music_path, out_path):
    """Returns the video length in seconds."""
    n = len(slide_paths)
    durations = [reading_seconds(t) for t in texts]
    total = sum(durations) - (n - 1) * FADE
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [ffmpeg_path(), "-y", "-v", "error"]
        for i, (p, d) in enumerate(zip(slide_paths, durations)):
            fp = os.path.join(tmp, f"f{i}.png")
            _frame(p, fp)
            cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", fp]
        cmd += ["-stream_loop", "-1", "-i", music_path]

        parts, prev, acc = [], "[0:v]", durations[0]
        for k in range(1, n):
            parts.append(f"{prev}[{k}:v]xfade=transition=fade:duration={FADE}:offset={acc - FADE:.2f}[v{k}]")
            prev, acc = f"[v{k}]", acc + durations[k] - FADE
        parts.append(f"{prev}format=yuv420p,fade=t=out:st={total - 0.6:.2f}:d=0.6[vout]")
        parts.append(f"[{n}:a]afade=t=in:st=0:d=0.5,afade=t=out:st={total - 1.5:.2f}:d=1.5[aout]")

        cmd += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-profile:v", "high",
                "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", "60", "-x264-params", "open-gop=0",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                "-movflags", "+faststart", "-use_editlist", "0", "-t", f"{total:.2f}", out_path]
        subprocess.run(cmd, check=True)
    return total

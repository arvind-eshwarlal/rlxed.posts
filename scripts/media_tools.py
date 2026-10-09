"""Shared helper: locate an ffmpeg binary (bundled via imageio-ffmpeg, else system ffmpeg)."""
import shutil


def ffmpeg_path():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        found = shutil.which("ffmpeg")
        if not found:
            raise RuntimeError("ffmpeg not found: run  pip install imageio-ffmpeg")
        return found

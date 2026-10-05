"""Locate the bundled sound library, unpacking it on first use.

The sounds ship as ONE archive (assets/sound_library.tar.gz) because Claude.ai rejects skill uploads with more than 200 files.
First use extracts it next to the skill (assets/sfx, assets/music); if that folder is read-only (some hosted skill sandboxes),
it extracts to a temp/cache folder instead. Importing this module is cheap once the files exist.
"""
import os, tarfile, tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
PACK = os.path.join(ROOT, "sound_library.tar.gz")


def _has_sounds(base): return os.path.isdir(os.path.join(base, "sfx")) and any(f.endswith(".mp3") for f in os.listdir(os.path.join(base, "sfx")))


def assets_dir():
    if _has_sounds(ROOT) or not os.path.isfile(PACK):
        return ROOT
    for base in (ROOT, os.path.join(tempfile.gettempdir(), "reels_video_editor_assets")):
        try:
            os.makedirs(base, exist_ok=True)
            if not _has_sounds(base):
                with tarfile.open(PACK) as t:
                    t.extractall(base)
            return base
        except OSError:
            continue
    return ROOT


BASE = assets_dir()
SFX_DIR = os.path.join(BASE, "sfx")
MUSIC_DIR = os.path.join(BASE, "music")

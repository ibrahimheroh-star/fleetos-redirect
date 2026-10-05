#!/usr/bin/env python3
"""Turn any audio/video file (voice note, mp4, mov, opus, m4a, ogg...) into
speech-friendly mono 16 kHz audio, split into chunks when it is long.

Usage: prepare_audio.py INPUT [--out DIR] [--chunk-min 10] [--format wav|mp3]

Prints a JSON summary (duration, chunk paths) on stdout so the caller can
feed each chunk to a transcription backend in order.
Why 16 kHz mono: that is what Whisper-class models use internally, and it
keeps files small enough for API upload limits.
"""
import argparse, json, os, subprocess, sys, tempfile


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{p.stderr[-800:]}")
    return p.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default=None)
    ap.add_argument("--chunk-min", type=float, default=10.0)
    ap.add_argument("--format", choices=["wav", "mp3"], default="wav")
    a = ap.parse_args()

    if not os.path.exists(a.input):
        sys.exit(f"file not found: {a.input}")
    out = a.out or tempfile.mkdtemp(prefix="audio_")
    os.makedirs(out, exist_ok=True)

    probe = json.loads(run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration:stream=codec_type",
                            "-of", "json", a.input]))
    has_audio = any(s.get("codec_type") == "audio" for s in probe.get("streams", []))
    if not has_audio:
        sys.exit("no audio stream in this file (silent video?)")
    duration = float(probe["format"].get("duration", 0))

    codec = ["-c:a", "pcm_s16le"] if a.format == "wav" else ["-c:a", "libmp3lame", "-b:a", "64k"]
    base = ["ffmpeg", "-y", "-v", "error", "-i", a.input, "-vn", "-ac", "1", "-ar", "16000"] + codec
    seg = int(a.chunk_min * 60)
    if duration <= seg * 1.2:
        path = os.path.join(out, f"chunk_000.{a.format}")
        run(base + [path])
        chunks = [path]
    else:
        run(base + ["-f", "segment", "-segment_time", str(seg), "-reset_timestamps", "1",
                    os.path.join(out, f"chunk_%03d.{a.format}")])
        chunks = sorted(os.path.join(out, f) for f in os.listdir(out) if f.startswith("chunk_"))

    print(json.dumps({"input": a.input, "duration_sec": round(duration, 1),
                      "chunk_seconds": seg, "chunks": chunks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

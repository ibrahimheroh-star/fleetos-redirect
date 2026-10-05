#!/usr/bin/env python3
"""Offline transcription with faster-whisper (no API key needed).

Usage: transcribe_local.py AUDIO [--model small] [--lang ar] [--offset SEC]
                           [--json] [--translate]

Setup (once): pip install faster-whisper   (model downloads on first run)
Model guide: base/small = fast, fine for clear speech; medium/large-v3 =
noticeably better for Arabic dialects and noisy audio, but slower.
--offset shifts timestamps so chunks of a long file line up.
"""
import argparse, json, sys


def ts(t):
    t = int(t)
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--model", default="small")
    ap.add_argument("--lang", default=None, help="ISO code, e.g. ar, en. Omit to auto-detect")
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--translate", action="store_true", help="translate speech to English")
    a = ap.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper missing: pip install faster-whisper")

    model = WhisperModel(a.model, device="auto", compute_type="int8")
    segs, info = model.transcribe(a.audio, language=a.lang, vad_filter=True,
                                  task="translate" if a.translate else "transcribe")
    rows = [{"start": round(s.start + a.offset, 2), "end": round(s.end + a.offset, 2),
             "text": s.text.strip()} for s in segs]
    if a.json:
        print(json.dumps({"language": info.language, "probability": round(info.language_probability, 2),
                          "segments": rows}, ensure_ascii=False, indent=2))
    else:
        print(f"# language: {info.language} ({info.language_probability:.0%})")
        for r in rows:
            print(f"[{ts(r['start'])}] {r['text']}")


if __name__ == "__main__":
    main()

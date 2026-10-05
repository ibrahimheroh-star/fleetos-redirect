#!/usr/bin/env python3
"""Describe non-speech audio (music, ambience, sound effects) as measurable facts.

Usage: analyze_music.py AUDIO [--sections 8]

Setup (once): pip install librosa
Prints JSON: duration, tempo (BPM), estimated key/mode, loudness, brightness,
percussive-vs-harmonic balance, a per-section energy timeline, and a rough
"speech likelihood" so the caller can tell music from talking.
These are estimates from signal analysis, not human-style listening: tempo can
be off by 2x/0.5x, and key detection is unreliable on atonal/non-Western music
(e.g. maqam-based music with quarter tones).
"""
import argparse, json, sys

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Krumhansl-Schmuckler key profiles
MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def estimate_key(chroma_mean, np):
    best = (-2, None)
    for i in range(12):
        for name, prof in (("major", MAJOR), ("minor", MINOR)):
            c = np.corrcoef(chroma_mean, np.roll(prof, i))[0, 1]
            if c > best[0]:
                best = (c, f"{NOTES[i]} {name}")
    return best[1], round(float(best[0]), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--sections", type=int, default=8)
    a = ap.parse_args()
    try:
        import numpy as np
        import librosa
    except ImportError:
        sys.exit("librosa missing: pip install librosa")

    y, sr = librosa.load(a.audio, sr=22050, mono=True)
    dur = len(y) / sr
    if dur < 1:
        sys.exit("audio shorter than 1 second")

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    harm, perc = librosa.effects.hpss(y)
    chroma = librosa.feature.chroma_cqt(y=harm, sr=sr).mean(axis=1)
    key, key_conf = estimate_key(chroma, np)

    rms = librosa.feature.rms(y=y)[0]
    cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    zcr = librosa.feature.zero_crossing_rate(y)[0]
    flat = librosa.feature.spectral_flatness(y=y)[0]
    db = librosa.amplitude_to_db(rms + 1e-9, ref=1.0)

    n = max(1, min(a.sections, int(dur // 3) or 1))
    edges = np.linspace(0, len(rms), n + 1, dtype=int)
    timeline = []
    for i in range(n):
        s, e = edges[i], max(edges[i] + 1, edges[i + 1])
        timeline.append({
            "from_sec": round(dur * i / n, 1), "to_sec": round(dur * (i + 1) / n, 1),
            "loudness_db": round(float(db[s:e].mean()), 1),
            "brightness_hz": int(cent[s:e].mean()),
        })

    # Speech tends to have many short silences/syllable-rate energy dips and
    # moderate ZCR; sustained music has steadier energy. Crude heuristic only.
    energy_var = float(np.std(rms) / (np.mean(rms) + 1e-9))
    pause_ratio = float(np.mean(db < db.max() - 35))
    speech_score = round(min(1.0, 0.5 * min(energy_var / 1.2, 1) + 0.5 * min(pause_ratio / 0.25, 1)), 2)

    print(json.dumps({
        "duration_sec": round(dur, 1),
        "tempo_bpm": round(tempo, 1),
        "tempo_note": "may be double/half the felt tempo",
        "key_estimate": key, "key_confidence": key_conf,
        "avg_loudness_db": round(float(db.mean()), 1),
        "dynamic_range_db": round(float(np.percentile(db, 95) - np.percentile(db, 5)), 1),
        "brightness_hz": int(cent.mean()),
        "noisiness": round(float(flat.mean()), 3),
        "percussive_share": round(float(np.sum(perc ** 2) / (np.sum(y ** 2) + 1e-9)), 2),
        "speech_likelihood_0_1": speech_score,
        "timeline": timeline,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

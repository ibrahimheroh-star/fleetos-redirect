#!/usr/bin/env python3
"""Library v2: ~90 more synthesised sound effects + 7 loopable music beds (numpy synth, no downloads, no copyright).

Categories land in subfolders of assets/: sfx/ (effects, shared with make_sfx.py) and music/ (beds).
Usage: python make_sfx2.py [--only NAME_SUBSTRING] [--no-music]
Requires numpy + ffmpeg. Deterministic (seeded) so reruns reproduce the same files.
"""
import argparse, os, subprocess, sys
import numpy as np

SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
SFX = os.path.join(HERE, "..", "assets", "sfx")
MUSIC = os.path.join(HERE, "..", "assets", "music")
rng = np.random.default_rng(7)
TAU = 2 * np.pi

# ------------------------------------------------------------------ synth helpers
def T(d): return np.arange(int(SR * d)) / SR
def noise(d): return rng.uniform(-1, 1, int(SR * d))
def ph(f):  # phase from instantaneous frequency array
    return TAU * np.cumsum(f) / SR
def sine(f, d=None):
    f = np.full(int(SR * d), float(f)) if np.isscalar(f) else f
    return np.sin(ph(f))
def saw(f, d=None):
    f = np.full(int(SR * d), float(f)) if np.isscalar(f) else f
    p = (np.cumsum(f) / SR) % 1.0
    return 2 * p - 1
def square(f, d=None, duty=0.5):
    f = np.full(int(SR * d), float(f)) if np.isscalar(f) else f
    return np.where((np.cumsum(f) / SR) % 1.0 < duty, 1.0, -1.0)
def tri(f, d=None):
    return 2 * np.abs(saw(f, d)) - 1
def chirp(f0, f1, d, exp=True):
    t = T(d)
    return (f0 * (f1 / f0) ** (t / d)) if exp else (f0 + (f1 - f0) * t / d)
def env(d, a=0.005, k=6.0):  # fast attack, exponential decay
    t = T(d); return np.minimum(t / max(a, 1e-4), 1) * np.exp(-k * t)
def swell(d, p=1.6, peak=0.5):
    x = np.clip(T(d) / d, 0, 1); x = x ** (np.log(0.5) / np.log(peak)); return np.sin(np.pi * x) ** p
def ramp_up(d, p=2.0): return np.clip(T(d) / d, 0, 1) ** p
def ramp_dn(d, p=2.0): return (1 - np.clip(T(d) / d, 0, 1)) ** p
def fade(x, a=0.003, r=0.01):
    n = len(x); y = x.copy(); na, nr = int(SR * a), int(SR * r)
    if na: y[:na] *= np.linspace(0, 1, na)
    if nr: y[-nr:] *= np.linspace(1, 0, nr)
    return y
def fl(x, lo=None, hi=None):  # FFT band filter (brick-wall, fine for sfx)
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
    m = np.ones_like(f)
    if lo: m *= 1 / (1 + (lo / np.maximum(f, 1e-3)) ** 4)
    if hi: m *= 1 / (1 + (f / hi) ** 4)
    return np.fft.irfft(X * m, len(x))
def echo(x, delay=0.12, fb=0.35, n=4):
    pad_n = int(SR * delay); y = np.concatenate([x, np.zeros(pad_n * n)])
    for i in range(1, n + 1): y[i * pad_n:i * pad_n + len(x)] += x * fb ** i
    return y
def reverb(x, d=1.2, wet=0.35):
    ir = noise(d) * np.exp(-3.5 * T(d)); ir = fl(ir, 200, 6000); ir /= np.abs(ir).sum() ** 0.5 + 1e-9
    n = len(x) + len(ir); y = np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)
    y = y / (np.abs(y).max() + 1e-9) * np.abs(x).max()
    x2 = np.concatenate([x, np.zeros(n - len(x))]); return x2 * (1 - wet) + y * wet
def clip(x, g=2.0): return np.tanh(x * g) / np.tanh(g)
def put(out, x, at):  # add x into out at time `at`
    i = int(SR * at); n = min(len(x), len(out) - i)
    if n > 0 and i >= 0: out[i:i + n] += x[:n]
    return out
def blank(d): return np.zeros(int(SR * d))
def vib(f, depth=0.02, rate=6, d=None):
    f = np.full(int(SR * d), float(f)) if np.isscalar(f) else f
    return f * (1 + depth * np.sin(TAU * rate * T(len(f) / SR)))
def bell(f, d, k=3.0):  # inharmonic partials
    t = T(d); y = 0
    for r, a in [(1, 1), (2.76, 0.6), (5.4, 0.4), (8.93, 0.25)]:
        y = y + a * np.sin(TAU * f * r * t) * np.exp(-k * r ** 0.5 * t)
    return y

def write(path, x, peak_db=-3.0, stereo=True):
    x = np.nan_to_num(x.astype(np.float64)); x -= x.mean()
    m = np.abs(x).max()
    if m < 1e-6: sys.exit(f"{path}: silent")
    x = x / m * 10 ** (peak_db / 20)
    af = "aformat=channel_layouts=stereo" if stereo else "anull"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                        "-af", af, "-c:a", "libmp3lame", "-b:a", "192k", path],
                       input=x.astype(np.float32).tobytes(), capture_output=True)
    if r.returncode: sys.exit(r.stderr.decode()[-500:])

SFX_FUNCS = {}
def sfx(fn):
    SFX_FUNCS[fn.__name__] = fn; return fn

# ================================================================== CARTOON / FUN
@sfx
def boing():
    d = 0.7; t = T(d); f = 180 + 420 * np.exp(-6 * t) * (1 + 0.5 * np.sin(TAU * 9 * t))
    return sine(f) * env(d, 0.003, 4) + 0.3 * sine(2 * f) * env(d, 0.003, 5)
@sfx
def slide_whistle_up(): d = 0.8; return sine(chirp(300, 2400, d)) * swell(d, 0.5, 0.8) * 0.8
@sfx
def slide_whistle_down(): d = 0.8; return sine(chirp(2400, 300, d)) * swell(d, 0.5, 0.2) * 0.8
@sfx
def bonk(): d = 0.35; return (sine(chirp(420, 120, d)) * env(d, 0.002, 12) + 0.4 * noise(d) * env(d, 0.001, 60))
@sfx
def squeak(): d = 0.25; return sine(chirp(1500, 2600, d) * (1 + 0.04 * np.sin(TAU * 40 * T(d)))) * swell(d, 0.7)
@sfx
def pop_cork(): return np.concatenate([sine(chirp(220, 700, 0.09)) * env(0.09, 0.001, 18), blank(0.21)])
@sfx
def bubble_pop(): d = 0.15; return sine(chirp(600, 1800, d)) * env(d, 0.002, 28)
@sfx
def bubble_rise(): d = 0.6; return sine(chirp(300, 1400, d) * (1 + 0.1 * np.sin(TAU * 14 * T(d)))) * swell(d, 1, 0.7) * 0.7
@sfx
def splat(): d = 0.4; return fl(noise(d), 80, 2200) * env(d, 0.002, 10) + sine(chirp(200, 60, d)) * env(d, 0.002, 9) * 0.8
@sfx
def spring(): d = 0.9; t = T(d); f = 250 + 120 * np.sin(TAU * 11 * t) * np.exp(-3 * t); return sine(f) * env(d, 0.003, 3.5)
@sfx
def wobble(): d = 0.8; f = 320 + 180 * np.sin(TAU * 6 * T(d)); return square(f, duty=0.35) * 0.4 * swell(d, 0.6)
@sfx
def cartoon_fall(): d = 1.0; return sine(chirp(1800, 120, d, exp=True)) * np.minimum(T(d) / 0.02, 1) * ramp_dn(d, 0.4)
@sfx
def cartoon_run(): return _stepper(1.0, 0.11)
def _stepper(d, gap):
    out = blank(d)
    for i in range(int(d / gap)):
        put(out, fl(noise(0.07), 500, 3500) * env(0.07, 0.001, 45) * (0.7 + 0.3 * (i % 2)), i * gap)
    return out
@sfx
def boing_double(): return np.concatenate([boing()[:int(SR*0.35)], boing()])

# ================================================================== GAME / 8-BIT
@sfx
def blip(): d = 0.1; return square(900, d) * env(d, 0.001, 20)
@sfx
def blip_up(): d = 0.18; return square(chirp(500, 1500, d, False), duty=0.5) * env(d, 0.001, 8) * 0.8
@sfx
def blip_down(): d = 0.18; return square(chirp(1500, 500, d, False)) * env(d, 0.001, 8) * 0.8
@sfx
def jump_8bit(): d = 0.25; return square(chirp(250, 900, d, False), duty=0.25) * env(d, 0.001, 6)
@sfx
def coin():
    out = blank(0.55); put(out, square(988, 0.08) * env(0.08, 0.001, 10), 0); put(out, square(1319, 0.5) * env(0.5, 0.001, 7), 0.08); return out
@sfx
def power_up():
    d = 0.8; f = np.repeat(np.array([392, 494, 587, 784, 988, 1175, 1568, 1975]), int(SR * d / 8))
    return square(f, duty=0.4) * env(d, 0.001, 1.2) * 0.8
@sfx
def power_down():
    d = 0.9; f = np.repeat(np.array([1568, 1319, 1047, 880, 659, 523, 392, 330]), int(SR * d / 8)); return square(f, duty=0.4) * env(d, 0.001, 1.5) * 0.8
@sfx
def level_up():
    out = blank(1.1)
    for i, f in enumerate([523, 659, 784, 1047, 1319, 1568]): put(out, (square(f, 0.2, 0.4) + 0.5 * sine(f, 0.2)) * env(0.2, 0.002, 4), i * 0.1)
    return out
@sfx
def game_over():
    out = blank(1.4)
    for i, f in enumerate([523, 494, 466, 440]): put(out, square(f, 0.34, 0.5) * env(0.34, 0.003, 3), i * 0.3)
    return out
@sfx
def laser_shot(): d = 0.3; return square(chirp(2400, 200, d), duty=0.5) * env(d, 0.001, 8) * 0.7
@sfx
def explosion_8bit(): d = 0.9; return fl(noise(d), 40, 3500) * env(d, 0.003, 3.5) + sine(chirp(120, 35, d)) * env(d, 0.003, 4)
@sfx
def select_blip(): d = 0.12; return square(1200, d, 0.25) * env(d, 0.001, 14)
@sfx
def error_8bit(): d = 0.35; return square(np.where(T(d) % 0.1 < 0.05, 200, 150), duty=0.5) * env(d, 0.001, 3)
@sfx
def pickup_sparkle():
    out = blank(0.6)
    for i, f in enumerate([1568, 1976, 2349, 2794, 3136]): put(out, sine(f, 0.25) * env(0.25, 0.001, 9), i * 0.05)
    return out

# ================================================================== UI / INTERFACE
@sfx
def swipe(): d = 0.25; return fl(noise(d), 800, 9000) * swell(d, 1.2, 0.4) * 0.8
@sfx
def swipe_up(): d = 0.3; return fl(noise(d), 600, 9000) * ramp_up(d, 1.3) * ramp_dn(d, 0.15) * 0.8
@sfx
def toggle_on(): d = 0.12; return np.concatenate([sine(1000, 0.04) * env(0.04, 0.001, 30), sine(1500, 0.08) * env(0.08, 0.001, 24)])
@sfx
def toggle_off(): d = 0.12; return np.concatenate([sine(1500, 0.04) * env(0.04, 0.001, 30), sine(900, 0.08) * env(0.08, 0.001, 24)])
@sfx
def ui_tap(): d = 0.07; return sine(chirp(1800, 900, d)) * env(d, 0.001, 55)
@sfx
def ui_open(): d = 0.35; return sine(chirp(500, 1400, d)) * swell(d, 0.9, 0.7) * 0.5 + fl(noise(d), 1500, 8000) * swell(d) * 0.15
@sfx
def ui_close(): d = 0.3; return sine(chirp(1400, 500, d)) * swell(d, 0.9, 0.3) * 0.5
@sfx
def confirm(): out = blank(0.5); put(out, bell(1320, 0.5, 6), 0); put(out, bell(1760, 0.4, 7), 0.09); return out
@sfx
def cancel(): out = blank(0.4); put(out, sine(500, 0.15) * env(0.15, 0.002, 14), 0); put(out, sine(380, 0.25) * env(0.25, 0.002, 12), 0.1); return out
@sfx
def notification_soft(): out = blank(0.8); put(out, bell(1046, 0.8, 4), 0); put(out, bell(1568, 0.6, 5), 0.12); return out
@sfx
def typing_burst():
    out = blank(0.9)
    for i in range(9): put(out, (fl(noise(0.05), 900, 6000) * env(0.05, 0.001, 70)) * rng.uniform(0.6, 1), i * rng.uniform(0.07, 0.11) + i * 0.02)
    return out
@sfx
def send_message(): d = 0.3; return fl(noise(d), 2000, 10000) * swell(d, 1, 0.3) * 0.5 + sine(chirp(700, 1900, d)) * swell(d, 1, 0.5) * 0.4
@sfx
def like_pop(): out = blank(0.35); put(out, sine(chirp(500, 1100, 0.08)) * env(0.08, 0.001, 20), 0); put(out, bell(1760, 0.3, 8), 0.07); return out
@sfx
def message_ping(): return bell(1568, 0.7, 5)
@sfx
def scroll_tick(): d = 0.03; return sine(2200, d) * env(d, 0.0005, 150)
@sfx
def camera_flash():
    d = 0.9; t = T(d); out = sine(chirp(1500, 5000, 0.5)) * ramp_up(0.5, 2) * 0.2; out = np.concatenate([out, blank(0.4)])
    put(out, fl(noise(0.08), 1500, 12000) * env(0.08, 0.001, 60), 0.5); return out

# ================================================================== DRUMS / PERCUSSION
def _kick(d=0.4, f0=140, f1=42, k=9): return sine(chirp(f0, f1, d)) * env(d, 0.001, k) + 0.2 * noise(d) * env(d, 0.0005, 150)
def _snare(d=0.3): return fl(noise(d), 1200, 9000) * env(d, 0.001, 18) * 0.8 + sine(chirp(220, 160, d)) * env(d, 0.001, 20) * 0.5
def _hat(d=0.06, k=70): return fl(noise(d), 7000, 15000) * env(d, 0.0005, k)
def _clap(d=0.3):
    out = blank(d)
    for i in range(4): put(out, fl(noise(0.04), 900, 6000) * env(0.04, 0.001, 70) * 0.6, i * 0.012)
    put(out, fl(noise(0.25), 900, 5000) * env(0.25, 0.002, 18), 0.036); return out
def _tom(f, d=0.4): return sine(chirp(f * 1.6, f, d)) * env(d, 0.001, 9)
@sfx
def kick(): return _kick()
@sfx
def kick_808(): d = 1.2; return sine(chirp(120, 38, d)) * env(d, 0.002, 2.4)
@sfx
def snare(): return _snare()
@sfx
def clap(): return _clap()
@sfx
def hihat_closed(): return _hat()
@sfx
def hihat_open(): return _hat(0.35, 10)
@sfx
def tom_low(): return _tom(90)
@sfx
def tom_high(): return _tom(180)
@sfx
def rimshot(): d = 0.15; return sine(1700, d) * env(d, 0.0005, 60) + fl(noise(d), 1500, 8000) * env(d, 0.0005, 60) * 0.5
@sfx
def crash_cymbal(): d = 2.2; return fl(noise(d), 3000, 16000) * env(d, 0.002, 2.2) + fl(noise(d), 5000, 14000) * env(d, 0.002, 1.2) * 0.5
@sfx
def ride_ping(): return bell(5200, 1.2, 3) * 0.7
@sfx
def snare_roll():
    d = 1.4; out = blank(d); n = 28
    for i in range(n): put(out, _snare(0.12) * (0.25 + 0.75 * (i / n) ** 1.5), i * (d / n) * 0.98)
    return out
@sfx
def drum_fill():
    out = blank(1.4); hits = [(0, _snare), (0.18, _snare), (0.35, lambda: _tom(200)), (0.53, lambda: _tom(150)), (0.7, lambda: _tom(110)), (0.88, lambda: _tom(80)), (1.05, _kick)]
    for t0, fnx in hits: put(out, fnx(), t0)
    put(out, crash_cymbal()[:int(SR * 0.4)], 1.05); return out
@sfx
def cymbal_swell(): d = 2.2; return fl(noise(d), 3000, 14000) * ramp_up(d, 2.2) * np.minimum((d - T(d)) / 0.05, 1)
@sfx
def darbuka_dum(): d = 0.4; return sine(chirp(190, 95, d)) * env(d, 0.001, 9) + 0.15 * noise(d) * env(d, 0.001, 80)
@sfx
def darbuka_tek(): d = 0.15; return fl(noise(d), 1800, 9000) * env(d, 0.0008, 40) + sine(900, d) * env(d, 0.0008, 40) * 0.3
@sfx
def darbuka_ka(): d = 0.12; return fl(noise(d), 1200, 7000) * env(d, 0.0008, 50) * 0.7
@sfx
def tabla_tin(): return bell(420, 0.5, 5) * 0.8
@sfx
def cowbell(): d = 0.5; return (square(560, d) + square(845, d)) * 0.3 * env(d, 0.001, 9)

# ================================================================== CINEMATIC
@sfx
def braam():
    d = 3.0; t = T(d); f = 55 * (1 + 0.003 * np.sin(TAU * 5 * t))
    y = sum(saw(f * k) * (1 / k) for k in (1, 2, 3, 4)) + 0.6 * saw(f * 1.5)
    return fl(y, 40, 1800) * np.minimum(t / 0.05, 1) * np.exp(-1.1 * t)
@sfx
def cinematic_boom(): d = 3.5; return reverb(sine(chirp(70, 28, d)) * env(d, 0.002, 1.5) + fl(noise(d), 40, 600) * env(d, 0.002, 4) * 0.5, 1.8, 0.4)[:int(SR * d)]
@sfx
def gong(): return bell(110, 4.0, 1.1) * 0.9
@sfx
def bell_toll(): return bell(220, 3.2, 1.3)
@sfx
def downlifter(): d = 2.0; return fl(noise(d), 300, 9000) * ramp_dn(d, 1.8) * 0.7 + sine(chirp(1500, 150, d)) * ramp_dn(d, 1.5) * 0.3
@sfx
def uplifter(): d = 2.0; return fl(noise(d), 300, 12000) * ramp_up(d, 2.4) * 0.7 + sine(chirp(150, 1800, d)) * ramp_up(d, 2.2) * 0.3
@sfx
def sweep_up(): d = 1.0; return fl(noise(d), 500, 12000) * ramp_up(d, 1.6) * np.minimum((d - T(d)) / 0.03, 1)
@sfx
def sweep_down(): d = 1.0; return fl(noise(d), 500, 12000) * ramp_dn(d, 1.6)
@sfx
def drone_dark(): d = 6.0; t = T(d); y = saw(41.2 * (1 + 0.002 * np.sin(TAU * 0.3 * t))) * 0.5 + saw(41.9, d) * 0.4 + sine(82.4, d) * 0.4; return fl(y, 30, 600) * np.minimum(t / 1.5, 1) * np.minimum((d - t) / 1.5, 1)
@sfx
def shimmer(): d = 2.5; t = T(d); y = sum(sine(f, d) * (0.6 + 0.4 * np.sin(TAU * r * t)) for f, r in [(2093, 5), (2637, 6), (3136, 4), (3951, 7)]); return y * swell(d, 1.2, 0.4) * 0.3
@sfx
def reverse_cymbal(): d = 2.0; x = fl(noise(d), 3000, 14000) * env(d, 0.002, 2.2); return x[::-1] * np.minimum((d - T(d)) / 0.02, 1)
@sfx
def impact_metal(): d = 2.5; return reverb(bell(180, d, 1.6) * 0.8 + fl(noise(d), 1500, 9000) * env(d, 0.001, 18) * 0.6, 1.2, 0.3)[:int(SR * d)]
@sfx
def whoosh_double(): out = blank(1.1); put(out, whoosh_core(0.4), 0); put(out, whoosh_core(0.5), 0.45); return out
def whoosh_core(d, lo=300, hi=8000): return fl(noise(d), lo, hi) * swell(d, 1.5, 0.5)
@sfx
def tail_hit():
    d = 3.0; src = blank(0.5); put(src, _kick(0.5, 100, 35, 5) * 1.2, 0); put(src, fl(noise(0.3), 100, 3000) * env(0.3, 0.001, 15), 0)
    return reverb(src, 2.5, 0.55)[:int(SR * d)]

@sfx
def heartbeat_slow():
    out = blank(3.0)
    for i in range(3):
        put(out, _kick(0.3, 75, 40, 12) * 0.9, 0.2 + i); put(out, _kick(0.3, 70, 38, 12) * 0.6, 0.45 + i)
    return out

@sfx
def stinger_horror(): d = 2.5; t = T(d); y = sum(saw(f * (1 + 0.01 * np.sin(TAU * 7 * t))) for f in (233, 247, 466, 494)) * 0.3; return clip(fl(y, 100, 5000), 2) * env(d, 0.01, 1.8)
@sfx
def riser_pitch(): d = 2.5; return (saw(chirp(100, 1600, d, False)) * 0.4 + fl(noise(d), 800, 10000) * 0.4) * ramp_up(d, 2.0) * np.minimum((d - T(d)) / 0.04, 1)
@sfx
def brass_hit():
    d = 1.0; y = sum(saw(np.full(int(SR * d), 220.0 * k)) / (i + 1) for i, k in enumerate((1, 1.5, 2)))
    return fl(y, 150, 3000) * env(d, 0.02, 3.5)

# ================================================================== SCI-FI / TECH
@sfx
def power_charge(): d = 1.6; return (sine(chirp(120, 1800, d)) * 0.5 + saw(chirp(60, 900, d)) * 0.3) * ramp_up(d, 1.4)
@sfx
def laser_charge(): d = 1.2; return square(chirp(200, 3000, d), duty=0.3) * 0.3 * ramp_up(d, 1.2) + sine(chirp(100, 1500, d)) * 0.4 * ramp_up(d, 1.5)
@sfx
def warp(): d = 1.4; return (fl(noise(d), 200, 6000) * swell(d, 1.2, 0.6) + sine(chirp(80, 2200, d)) * swell(d, 1, 0.7) * 0.4)
@sfx
def teleport(): d = 0.9; t = T(d); return sine(chirp(2400, 300, d) * (1 + 0.05 * np.sin(TAU * 30 * t))) * swell(d, 0.8, 0.5) * 0.6 + fl(noise(d), 2000, 12000) * swell(d, 2, 0.6) * 0.2
@sfx
def hologram(): d = 1.0; t = T(d); return (sine(880, d) * np.sin(TAU * 18 * t) ** 2 + 0.5 * sine(1320, d)) * swell(d, 1, 0.5) * 0.4
@sfx
def scanner(): d = 1.5; f = 700 + 500 * np.abs(np.sin(TAU * 1.3 * T(d))); return sine(f) * 0.5 * swell(d, 0.4)
@sfx
def sonar_ping(): return reverb(sine(1100, 1.0) * env(1.0, 0.002, 4), 1.2, 0.45)[:int(SR * 1.8)]
@sfx
def radio_static(): d = 1.0; return fl(noise(d), 300, 7000) * (0.6 + 0.4 * (rng.uniform(0, 1, int(SR * d)) > 0.5)) * 0.6
@sfx
def tape_stop(): d = 1.0; t = T(d); f = 440 * (1 - t / d) ** 1.8 + 15; return saw(f) * 0.5 * np.minimum((d - t) / 0.02, 1)
@sfx
def tape_rewind(): d = 1.2; t = T(d); return fl(noise(d), 1500, 9000) * 0.3 * (0.6 + 0.4 * np.sin(TAU * 60 * t)) + sine(chirp(600, 2200, d, False)) * 0.15
@sfx
def vinyl_stop(): d = 1.0; t = T(d); f = 330 * (1 - t / d) ** 1.4 + 20; return (tri(f) * 0.6 + fl(noise(d), 200, 4000) * 0.1) * np.minimum((d - t) / 0.02, 1)
@sfx
def dial_up_chirp(): d = 1.2; f = np.where((T(d) * 14).astype(int) % 2 == 0, 1300, 2100) + 400 * np.sin(TAU * 5 * T(d)); return sine(f) * 0.5 * swell(d, 0.3)
@sfx
def zap_electric(): d = 0.5; t = T(d); return clip(fl(noise(d), 800, 9000) * (np.sin(TAU * 110 * t) > 0) * np.exp(-6 * t), 2) + sine(chirp(2000, 300, d)) * env(d, 0.001, 10) * 0.4
@sfx
def data_stream(): d = 1.0; return square((600 + 600 * (rng.integers(0, 6, int(SR * d / 400 + 1))).repeat(400)[:int(SR * d)]), duty=0.5) * 0.25 * swell(d, 0.3)
@sfx
def alarm(): d = 1.6; f = np.where((T(d) * 2.5).astype(int) % 2 == 0, 880, 660); return square(f) * 0.4 * np.minimum((d - T(d)) / 0.02, 1)
@sfx
def siren(): d = 2.0; f = 800 + 500 * np.sin(TAU * 0.9 * T(d) - np.pi / 2); return fl(saw(f), 300, 4000) * 0.6 * swell(d, 0.2)
@sfx
def countdown_beep(): out = blank(3.6); [put(out, sine(880, 0.15) * env(0.15, 0.002, 6), i * 1.0) for i in range(3)]; put(out, sine(1760, 0.6) * env(0.6, 0.002, 3), 3.0); return out
@sfx
def tick_up(): out = blank(1.0); [put(out, sine(1500 + 60 * i, 0.04) * env(0.04, 0.0005, 90), i * 0.05) for i in range(20)]; return out
@sfx
def clock_tick(): d = 0.12; return sine(1900, d) * env(d, 0.0005, 80) + sine(1200, d) * env(d, 0.0005, 70) * 0.5
@sfx
def clock_ticking(): out = blank(3.0); [put(out, clock_tick() * (1 if i % 2 == 0 else 0.7), i * 0.5) for i in range(6)]; return out
@sfx
def stopwatch(): out = blank(2.0); [put(out, sine(2400, 0.02) * env(0.02, 0.0005, 150) * 0.8, i * 0.1) for i in range(20)]; return out

# ================================================================== FOLEY-STYLE / REAL-WORLD (synthetic)
@sfx
def whip_crack(): return np.concatenate([fl(noise(0.1), 1500, 14000) * env(0.1, 0.0005, 60), blank(0.3)])
@sfx
def punch(): d = 0.3; return sine(chirp(160, 50, d)) * env(d, 0.001, 18) + fl(noise(d), 100, 2500) * env(d, 0.001, 35) * 0.8
@sfx
def slap(): d = 0.2; return fl(noise(d), 500, 7000) * env(d, 0.0005, 35) + sine(300, d) * env(d, 0.001, 40) * 0.4
@sfx
def sword_swish(): d = 0.45; return fl(noise(d), 2500, 14000) * swell(d, 2.2, 0.55) * 0.8
@sfx
def glass_ping(): return bell(2800, 1.2, 4) * 0.7
@sfx
def water_drop(): d = 0.4; t = T(d); return sine(700 * np.exp(-8 * t) + 900) * env(d, 0.001, 14)
@sfx
def splash(): d = 0.9; return fl(noise(d), 300, 9000) * (env(d, 0.002, 4) * (0.6 + 0.4 * np.sin(TAU * 30 * T(d)))) * 0.9
@sfx
def thunder(): d = 4.0; t = T(d); return fl(noise(d), 30, 500) * (np.exp(-1.0 * t) * (0.5 + 0.5 * np.sin(TAU * 3 * t) ** 2)) * 1.2
@sfx
def wind(): d = 4.0; t = T(d); return fl(noise(d), 150, 1800) * (0.5 + 0.5 * np.sin(TAU * 0.35 * t)) * np.minimum(t / 1, 1) * np.minimum((d - t) / 1, 1)
@sfx
def fire_crackle(): d = 3.0; n = fl(noise(d), 800, 9000) * (rng.uniform(0, 1, int(SR * d)) > 0.9985).astype(float); n = np.convolve(n, np.exp(-T(0.02) * 400), "same"); return n * 8 + fl(noise(d), 80, 500) * 0.05
@sfx
def rain(): d = 4.0; return fl(noise(d), 1500, 12000) * 0.5 * np.minimum(T(d) / 0.5, 1) * np.minimum((d - T(d)) / 0.5, 1)
@sfx
def door_knock():
    out = blank(0.9); knock = np.zeros(int(SR * 0.1))
    knock += sine(chirp(300, 160, 0.1)) * env(0.1, 0.001, 30); knock[:int(SR * 0.05)] += fl(noise(0.05), 200, 2000) * env(0.05, 0.0005, 80) * 0.5
    for i in range(3): put(out, knock, i * 0.2)
    return out

@sfx
def cash_register(): out = blank(1.4); put(out, fl(noise(0.1), 1500, 8000) * env(0.1, 0.0005, 40), 0); put(out, bell(2200, 1.2, 3.5), 0.15); put(out, bell(3300, 0.9, 4), 0.2); return out
@sfx
def coin_drop(): out = blank(1.0); [put(out, bell(f, 0.5, 8) * a, t0) for f, a, t0 in [(3100, 1, 0), (3100, 0.6, 0.18), (3100, 0.4, 0.3), (3100, 0.25, 0.38)]]; return out
@sfx
def footsteps(): out = blank(2.0); [put(out, fl(noise(0.12), 80, 1500) * env(0.12, 0.002, 28) * (0.8 + 0.2 * (i % 2)), 0.1 + i * 0.4) for i in range(5)]; return out
@sfx
def paper_rustle(): d = 0.8; return fl(noise(d), 2000, 12000) * (rng.uniform(0, 1, int(SR * d)) > 0.5) * swell(d, 0.8, 0.4) * 0.5
@sfx
def zipper(): d = 0.7; return (fl(noise(d), 1800, 9000) * (np.sin(TAU * 120 * T(d)) > 0)) * ramp_up(d, 0.3) * 0.7
@sfx
def pour_liquid(): d = 1.5; return fl(noise(d), 600, 5000) * (0.6 + 0.4 * np.sin(TAU * 17 * T(d))) * swell(d, 0.5, 0.5) * 0.7
@sfx
def drop_hit_wood(): d = 0.3; return sine(chirp(220, 120, d)) * env(d, 0.001, 22) + fl(noise(d), 300, 3000) * env(d, 0.001, 45) * 0.5
@sfx
def balloon_pop(): d = 0.25; return fl(noise(d), 300, 14000) * env(d, 0.0003, 55)
@sfx
def camera_click_old(): out = blank(0.3); put(out, fl(noise(0.04), 1000, 9000) * env(0.04, 0.0003, 120), 0); put(out, fl(noise(0.05), 600, 6000) * env(0.05, 0.0003, 100) * 0.7, 0.09); return out

# ================================================================== COMEDY / MEME / EMOTION
@sfx
def sad_trombone():
    out = blank(2.4)
    for i, (f, d) in enumerate([(293, 0.5), (277, 0.5), (261, 0.5), (233, 1.0)]):
        t0 = [0, 0.55, 1.1, 1.65][i]; g = fl(saw(vib(f, 0.02, 6, d) * (1 if i < 3 else (1 - 0.15 * T(d) / d))), 100, 1800) * np.minimum(T(d) / 0.04, 1) * np.minimum((d - T(d)) / 0.05, 1); put(out, g * 0.9, t0)
    return out
@sfx
def airhorn():
    d = 1.6; t = T(d); y = sum(saw(np.full(len(t), 440.0 * r)) for r in (1, 1.005, 1.5, 2)) * 0.3
    y = clip(fl(y, 250, 4500), 1.5); gate = np.where(t % 0.4 < 0.28, 1.0, 0.45)
    return y * gate * np.minimum(t / 0.02, 1) * np.minimum((d - t) / 0.1, 1)
@sfx
def dun_dun_dun(): out = blank(2.0); [put(out, braam()[:int(SR * 0.9)] * 0.8, i * 0.55) for i in range(3)]; return out
@sfx
def ba_dum_tss(): out = blank(1.4); put(out, _tom(160), 0); put(out, _kick(0.3), 0.18); put(out, crash_cymbal()[:int(SR * 1.0)], 0.4); return out
@sfx
def crickets(): d = 3.0; t = T(d); gate = np.where((t * 3) % 1 < 0.55, 1.0, 0.0) * (np.sin(TAU * 55 * t) > -0.2); return sine(4300, d) * gate * 0.4 + sine(4400, d) * gate * 0.2
@sfx
def tada():
    out = blank(1.5); [put(out, (saw(f, 0.5) * 0.4 + sine(f, 0.5)) * env(0.5, 0.003, 3), t0) for f, t0 in [(523, 0), (659, 0.15)]]
    for f in (784, 988, 1175, 1568): put(out, (saw(f, 1.0) * 0.3 + sine(f, 1.0) * 0.6) * env(1.0, 0.005, 2.4), 0.32)
    return out
@sfx
def fail_trumpet(): out = blank(1.5); [put(out, fl(saw(f, 0.3), 200, 2500) * env(0.3, 0.01, 3), t0) for f, t0 in [(311, 0), (294, 0.3), (277, 0.6), (261, 0.9)]]; return out
@sfx
def applause_synth(): d = 3.0; n = fl(noise(d), 1000, 8000) * (rng.uniform(0, 1, int(SR * d)) > 0.4) * (0.5 + 0.5 * np.abs(np.sin(TAU * 7 * T(d)))); return n * swell(d, 0.4, 0.4) * 0.6
@sfx
def wow_rise(): d = 0.8; return sine(chirp(400, 1000, d) * (1 + 0.03 * np.sin(TAU * 7 * T(d)))) * swell(d, 0.8, 0.6) * 0.7
@sfx
def awkward_cough_beep(): d = 0.6; return sine(np.where(T(d) < 0.25, 700, 0) + np.where(T(d) > 0.3, 700, 0), d) * 0.3 * env(d, 0.002, 3)
@sfx
def vine_boom(): d = 1.6; return sine(chirp(90, 30, d)) * env(d, 0.001, 2.2) + np.concatenate([fl(noise(0.2), 80, 1200) * env(0.2, 0.001, 20), blank(d - 0.2)]) * 0.6
@sfx
def bruh_low(): d = 0.6; t = T(d); return fl(saw(120 - 40 * t / d), 90, 900) * env(d, 0.01, 3.2)
@sfx
def ding_dong(): out = blank(1.6); put(out, bell(880, 1.0, 3), 0); put(out, bell(659, 1.3, 3), 0.55); return out

# ================================================================== EXTRA TRANSITIONS / WHOOSH VARIANTS
@sfx
def whoosh_blur(): d = 0.7; return fl(noise(d), 200, 4500) * swell(d, 1.2, 0.5)
@sfx
def whoosh_flutter(): d = 0.8; return fl(noise(d), 400, 8000) * swell(d, 1.2, 0.5) * (0.6 + 0.4 * np.sin(TAU * 28 * T(d)))
@sfx
def whoosh_dive(): d = 0.9; return fl(noise(d), 300, 9000) * ramp_dn(d, 1.0) * np.minimum(T(d) / 0.05, 1) + sine(chirp(1200, 150, d)) * ramp_dn(d, 1.3) * 0.2
@sfx
def whoosh_zoom_in(): d = 0.6; return fl(noise(d), 300, 10000) * ramp_up(d, 1.4) * np.minimum((d - T(d)) / 0.02, 1) + sine(chirp(200, 1400, d)) * ramp_up(d, 1.4) * 0.2
@sfx
def whoosh_zoom_out(): d = 0.6; return fl(noise(d), 300, 10000) * ramp_dn(d, 1.4) * np.minimum(T(d) / 0.02, 1) + sine(chirp(1400, 200, d)) * ramp_dn(d, 1.4) * 0.2
@sfx
def whoosh_glass(): d = 0.6; return fl(noise(d), 2500, 15000) * swell(d, 1.2, 0.5) * 0.7 + sine(chirp(1500, 3500, d)) * swell(d, 1, 0.5) * 0.15
@sfx
def whoosh_spin(): d = 0.7; t = T(d); return fl(noise(d), 400, 8000) * swell(d, 1.2, 0.5) * (0.5 + 0.5 * np.sin(TAU * (6 + 18 * t / d) * t))
@sfx
def whoosh_heavy(): d = 1.0; return fl(noise(d), 80, 3500) * swell(d, 1.5, 0.55) * 1.0 + sine(chirp(60, 140, d, False)) * swell(d, 1, 0.55) * 0.3
@sfx
def glitch_stutter(): d = 0.5; t = T(d); gate = (np.sin(TAU * 40 * t) > 0).astype(float); return (fl(noise(d), 200, 9000) * 0.5 + sine(np.where((t * 25).astype(int) % 3 == 0, 900, 1500), d) * 0.4) * gate
@sfx
def vhs_rewind(): d = 1.0; t = T(d); return fl(noise(d), 500, 8000) * 0.35 * (0.5 + 0.5 * np.sin(TAU * 90 * t)) + saw(chirp(2000, 500, d, False)) * 0.12
@sfx
def impact_boom_tight(): d = 0.8; return sine(chirp(110, 38, d)) * env(d, 0.001, 6)
@sfx
def pop_double(): out = blank(0.4); put(out, sine(chirp(500, 1000, 0.08)) * env(0.08, 0.001, 30), 0); put(out, sine(chirp(600, 1300, 0.08)) * env(0.08, 0.001, 30), 0.12); return out
@sfx
def shine_sparkle():
    out = blank(1.0)
    for i in range(14): put(out, sine(rng.choice([2093, 2637, 3136, 3520, 4186]), 0.25) * env(0.25, 0.001, 12) * rng.uniform(0.3, 1), i * 0.045)
    return out
@sfx
def magic_chime(): out = blank(1.6); [put(out, bell(f, 1.2, 4) * 0.7, i * 0.08) for i, f in enumerate([1047, 1319, 1568, 2093, 2637])]; return out
@sfx
def success_fanfare(): out = blank(1.8); [put(out, (saw(f, 0.4) * 0.25 + sine(f, 0.4) * 0.6) * env(0.4, 0.005, 3), t0) for f, t0 in [(392, 0), (523, 0.15), (659, 0.3), (784, 0.45)]]; [put(out, (saw(f, 1.0) * 0.25 + sine(f, 1.0) * 0.6) * env(1.0, 0.005, 2.2), 0.6) for f in (523, 659, 784, 1047)]; return out


# ================================================================== MUSIC BEDS (loopable, bar-aligned)
def midi(n): return 440.0 * 2 ** ((n - 69) / 12)
def pluck(f, d=0.6, damp=0.996):  # Karplus-Strong string
    n = max(2, int(SR / f)); buf = rng.uniform(-1, 1, n); out = np.zeros(int(SR * d))
    for i in range(len(out)):
        out[i] = buf[i % n]; buf[i % n] = damp * 0.5 * (buf[i % n] + buf[(i + 1) % n])
    return out
def pad(freqs, d, a=0.4):
    y = sum(saw(np.full(int(SR * d), f)) + saw(np.full(int(SR * d), f * 1.004)) for f in freqs) / (2 * len(freqs))
    y = fl(y, 80, 2200); return y * np.minimum(T(d) / a, 1) * np.minimum((d - T(d)) / a, 1)
def seq(out, step, pattern, fnx, vel=1.0):
    for i, p in enumerate(pattern):
        if p: put(out, fnx() * (p if isinstance(p, float) else 1.0) * vel, i * step)

def bed_trap():
    bpm = 140; beat = 60 / bpm; bar = 4 * beat; bars = 8; out = blank(bar * bars); s16 = beat / 4
    seq(out, s16, [1,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0] * bars, lambda: kick_808()[:int(SR * 0.5)] * 0.9)
    seq(out, s16, ([0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0]*bars), lambda: _snare(0.25)*0.8)
    seq(out, s16, ([0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0]*bars), lambda: _clap()*0.6)
    hat = ([1,0.5,1,0.5,1,0.5,1,1]*2)*bars; [put(out, _hat(0.05) * (0.5 if i % 2 else 0.8) * (1 if x else 0), i * s16) for i, x in enumerate(hat)]
    chords = [(57, 60, 64), (53, 57, 60), (55, 59, 62), (52, 55, 59)]
    for b in range(bars):
        notes = chords[(b // 2) % 4]
        for i, n in enumerate([0, 1, 2, 1, 2, 1, 0, 1]): put(out, pluck(midi(notes[n % 3] + 12), 0.4) * 0.35, b * bar + i * beat / 2)
        put(out, sine(np.full(int(SR * bar), midi(notes[0] - 24)), bar) * np.minimum(T(bar) / 0.01, 1) * 0.5, b * bar)
    return out
def bed_lofi():
    bpm = 78; beat = 60 / bpm; bar = 4 * beat; bars = 8; out = blank(bar * bars)
    chords = [(60, 64, 67, 71), (57, 60, 64, 67), (53, 57, 60, 64), (55, 59, 62, 65)]
    for b in range(bars):
        for k, n in enumerate(chords[b % 4]):
            f = midi(n); y = (sine(f, bar) + 0.4 * sine(2 * f, bar) * np.exp(-3 * T(bar))) * np.exp(-0.9 * T(bar)) * 0.18; put(out, y, b * bar + k * 0.012)
        for i in range(8): put(out, pluck(midi(chords[b % 4][i % 4] + 12), 0.5, 0.995) * 0.12, b * bar + i * beat / 2 + (0.03 if i % 2 else 0))
        put(out, _kick(0.35, 100, 45, 8) * 0.8, b * bar); put(out, _kick(0.35, 100, 45, 8) * 0.6, b * bar + 2.5 * beat)
        put(out, _snare(0.25) * 0.4, b * bar + beat); put(out, _snare(0.25) * 0.4, b * bar + 3 * beat)
        [put(out, _hat(0.04) * 0.35, b * bar + i * beat / 2 + (0.025 if i % 2 else 0)) for i in range(8)]
    out += fl(noise(len(out) / SR), 1500, 9000) * (rng.uniform(0, 1, len(out)) > 0.9993) * 0.4
    return fl(out, 60, 7500)
def bed_cinematic():
    bpm = 70; beat = 60 / bpm; bar = 4 * beat; bars = 8; out = blank(bar * bars)
    chords = [(45, 52, 57, 60), (41, 48, 53, 57), (43, 50, 55, 59), (40, 47, 52, 56)]
    for b in range(0, bars, 2): put(out, pad([midi(n) for n in chords[(b // 2) % 4]], bar * 2, 1.2) * 0.8, b * bar)
    for b in range(0, bars, 2): put(out, sine(np.full(int(SR * bar * 2), midi(chords[(b // 2) % 4][0] - 12)), bar * 2) * 0.35 * np.minimum(T(bar * 2) / 0.6, 1), b * bar)
    for b in range(bars): put(out, _kick(0.8, 70, 32, 3.5) * 0.7 * (1 if b % 2 == 0 else 0.5), b * bar)
    put(out, fl(noise(bar * 2), 300, 9000) * ramp_up(bar * 2, 2.2) * 0.18, (bars - 2) * bar)
    return out
def bed_corporate():
    bpm = 120; beat = 60 / bpm; bar = 4 * beat; bars = 8; out = blank(bar * bars)
    chords = [(60, 64, 67), (67, 71, 74), (69, 72, 76), (65, 69, 72)]
    for b in range(bars):
        ch = chords[b % 4]
        for i in range(4): put(out, _kick(0.3, 130, 50, 10) * 0.7, b * bar + i * beat)
        [put(out, _hat(0.05) * 0.5, b * bar + i * beat + beat / 2) for i in range(4)]
        put(out, _clap(0.25) * 0.5, b * bar + beat); put(out, _clap(0.25) * 0.5, b * bar + 3 * beat)
        for i in range(8): put(out, pluck(midi(ch[(0, 1, 2, 1, 0, 1, 2, 1)[i]] + 12), 0.35, 0.994) * 0.4, b * bar + i * beat / 2)
        put(out, pad([midi(n) for n in ch], bar, 0.05) * 0.12, b * bar)
        put(out, sine(np.full(int(SR * beat), midi(ch[0] - 24)), beat) * np.exp(-2 * T(beat)) * 0.5, b * bar)
    return out
def bed_suspense():
    bpm = 90; beat = 60 / bpm; bar = 4 * beat; bars = 8; out = blank(bar * bars)
    put(out, drone_dark()[:int(SR * bar * bars)] if bar * bars <= 6 else np.tile(drone_dark(), 4)[:int(SR * bar * bars)] * 0.7, 0)
    for i in range(int(bar * bars / (beat / 2))): put(out, clock_tick() * 0.35, i * beat / 2)
    for b in range(bars): put(out, _kick(0.5, 60, 30, 5) * 0.5, b * bar)
    for b in (3, 7): put(out, riser_pitch()[:int(SR * 2.2)] * 0.3, (b + 1) * bar - 2.2)
    return out
def bed_edm():
    bpm = 128; beat = 60 / bpm; bar = 4 * beat; bars = 8; out = blank(bar * bars)
    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]
    for b in range(bars):
        ch = chords[(b // 2) % 4]
        for i in range(4): put(out, _kick(0.35, 150, 45, 9) * 0.9, b * bar + i * beat)
        for i in range(4): put(out, _hat(0.15, 28) * 0.5, b * bar + i * beat + beat / 2)
        put(out, _clap(0.25) * 0.6, b * bar + beat); put(out, _clap(0.25) * 0.6, b * bar + 3 * beat)
        for i in range(8):
            f = midi(ch[0] - 24); y = fl(saw(np.full(int(SR * beat / 2), f)), 40, 400) * np.exp(-3 * T(beat / 2)); put(out, y * 0.6, b * bar + i * beat / 2 + 0.0)
        for i in (0, 3, 6): put(out, fl(sum(saw(np.full(int(SR * 0.25), midi(n + 12) * k)) for n in ch for k in (1, 1.006)), 300, 5000) * np.exp(-6 * T(0.25)) * 0.12, b * bar + i * beat / 2)
    return out
def bed_oriental():
    bpm = 96; beat = 60 / bpm; bar = 4 * beat; bars = 8; out = blank(bar * bars); s8 = beat / 2
    # maqsum: Dum Tek _ Tek Dum _ Tek _  (8 eighth-notes)
    pat = {"dum": [0, 3], "tek": [1, 5, 7], "ka": [4]}
    for b in range(bars):
        for i in pat["dum"]: put(out, darbuka_dum() * 0.9, b * bar + i * s8)
        for i in pat["tek"]: put(out, darbuka_tek() * 0.6, b * bar + i * s8)
        for i in pat["ka"]: put(out, darbuka_ka() * 0.5, b * bar + i * s8)
        for i in range(8): put(out, darbuka_ka() * 0.15, b * bar + i * s8 + s8 / 2)
    # hijaz on D: D Eb F# G A Bb C D
    D = 62; scale = [0, 1, 4, 5, 7, 8, 10, 12]
    mel = [[7, 4, 5, 4, 1, 0, 1, 0], [0, 1, 4, 5, 7, 5, 4, 1], [5, 7, 8, 7, 5, 4, 1, 0], [1, 4, 1, 0, 1, 0, 0, 0]]
    for b in range(bars):
        for i, idx in enumerate(mel[b % 4]): put(out, pluck(midi(D + scale[idx % 8] + 12), 0.7, 0.997) * 0.45, b * bar + i * s8 * 1.0 * (1 if i % 2 == 0 else 1) + (0.015 if i % 2 else 0))
        put(out, pad([midi(D - 12), midi(D - 5)], bar, 0.3) * 0.18, b * bar)
        put(out, sine(np.full(int(SR * beat), midi(D - 24)), beat) * np.exp(-1.5 * T(beat)) * 0.4, b * bar)
    return out
MUSIC_FUNCS = {"bed_hype_trap_140": bed_trap, "bed_lofi_chill_78": bed_lofi, "bed_cinematic_pad_70": bed_cinematic,
               "bed_corporate_upbeat_120": bed_corporate, "bed_suspense_tick_90": bed_suspense,
               "bed_edm_drive_128": bed_edm, "bed_oriental_darbuka_96": bed_oriental}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--only", default=""); ap.add_argument("--no-music", action="store_true")
    a = ap.parse_args()
    os.makedirs(SFX, exist_ok=True); os.makedirs(MUSIC, exist_ok=True)
    n = 0
    for name, fn in SFX_FUNCS.items():
        if a.only and a.only not in name: continue
        x = np.asarray(fn(), dtype=np.float64)
        write(os.path.join(SFX, name + ".mp3"), fade(x)); n += 1; print("  sfx", name, f"{len(x)/SR:.2f}s")
    if not a.no_music:
        for name, fn in MUSIC_FUNCS.items():
            if a.only and a.only not in name: continue
            x = np.asarray(fn(), dtype=np.float64); x = fl(x, 30, 14000)
            write(os.path.join(MUSIC, name + ".mp3"), fade(x, 0.002, 0.002), -6.0); print("  music", name, f"{len(x)/SR:.1f}s")
    print("done", n, "sfx")


if __name__ == "__main__":
    main()

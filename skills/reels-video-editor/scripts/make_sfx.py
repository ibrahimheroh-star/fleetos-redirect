#!/usr/bin/env python3
"""Synthesise a small, license-free sound-effects library with ffmpeg (no downloads, no copyright).

Everything is generated from math (noise, sine chirps, decaying envelopes), so the files are
original and safe to use commercially. They are intentionally clean and simple; for hero moments
swap in real recordings (see references/sound-design.md for free libraries).

Usage: python make_sfx.py [OUT_DIR]      (default: ../assets/sfx)
"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "assets", "sfx")
N = "(random(0)*2-1)"            # white noise sample in aeval
TAU = "2*PI"


def gen(name, expr, dur, post="", mono_to_stereo=True):
    """expr: aevalsrc expression of t. post: extra audio filter chain after generation."""
    chain = f"aevalsrc='{expr}':d={dur}:s=48000:c=mono"
    af = []
    if post:
        af.append(post)
    af.append("alimiter=limit=0.89")
    af.append("aformat=channel_layouts=stereo" if mono_to_stereo else "anull")
    path = os.path.join(OUT, name + ".mp3")
    wav = path[:-4] + ".tmp.wav"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", chain, "-af", ",".join(af),
                        "-ar", "48000", wav], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{name} failed:\n{r.stderr[-800:]}")
    # peak-normalise to -3 dB so every file has a predictable level; mix volume is then set per cue
    vd = subprocess.run(["ffmpeg", "-hide_banner", "-i", wav, "-af", "volumedetect", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    peak = float(re.search(r"max_volume: (-?[\d.]+) dB", vd).group(1))
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af", f"volume={-3.0 - peak:.2f}dB",
                        "-c:a", "libmp3lame", "-b:a", "192k", path], capture_output=True, text=True)
    os.remove(wav)
    if r.returncode:
        sys.exit(f"{name} failed:\n{r.stderr[-800:]}")
    print("  ", name, f"({dur}s)")


def env_bell(d, peak=0.5):          # swell up then down, for whooshes (0..1)
    return f"pow(sin(PI*min(t/{d},1)),1.6)" if peak == 0.5 else f"pow(sin(PI*pow(min(t/{d},1),{1/peak*0.5:.3f})),1.6)"


os.makedirs(OUT, exist_ok=True)
print("generating into", os.path.abspath(OUT))

# ---- WHOOSHES / SWISHES (transitions, camera moves, text slides) -------------------------
gen("whoosh_short", f"{N}*{env_bell(0.45)}*0.9", 0.45, "highpass=f=350,lowpass=f=7000,aecho=0.6:0.5:25:0.25")
gen("whoosh_medium", f"{N}*{env_bell(0.8)}*0.9", 0.8, "highpass=f=250,lowpass=f=6000,aecho=0.6:0.5:40:0.3")
gen("whoosh_long", f"{N}*{env_bell(1.4)}*0.9", 1.4, "highpass=f=180,lowpass=f=5500,aecho=0.6:0.5:60:0.3")
# fast swish: bright and tiny, for text pops and quick pans
gen("swish_fast", f"{N}*{env_bell(0.22)}*0.8", 0.22, "highpass=f=1500,lowpass=f=12000")
# rising / falling whoosh built from a chirped sine layered with noise (sounds like movement up/down)
gen("whoosh_rise", f"(0.25*sin({TAU}*(300*t+1800*t*t/2/0.7))+0.6*{N})*pow(min(t/0.7,1),2)", 0.7,
    "highpass=f=250,lowpass=f=9000,afade=t=out:st=0.6:d=0.1")
gen("whoosh_fall", f"(0.25*sin({TAU}*(2200*t-3000*t*t/2/0.7))+0.6*{N})*pow(1-min(t/0.7,1),1.5)*min(t/0.03,1)", 0.7,
    "highpass=f=200,lowpass=f=9000")

# ---- IMPACTS / HITS / BOOMS (button a cut, title reveal, beat drop) --------------------
gen("impact_hit", f"(sin({TAU}*55*t*(1+0.5*exp(-18*t)))*exp(-5*t)+0.5*{N}*exp(-30*t))*0.95", 1.2, "lowpass=f=9000")
gen("impact_heavy", f"(sin({TAU}*42*t*(1+0.7*exp(-14*t)))*exp(-2.8*t)+0.4*{N}*exp(-18*t)+0.2*sin({TAU}*90*t)*exp(-4*t))", 2.4,
    "lowpass=f=7000,aecho=0.7:0.6:80|140:0.35|0.2")
gen("boom_sub", f"sin({TAU}*(110*t-60*t*t/2/1.5))*exp(-2.2*t)*min(t/0.01,1)", 1.5, "lowpass=f=200")
gen("sub_drop", f"sin({TAU}*(90*exp(-1.6*t)*0.6+28)*t)*exp(-1.4*t)", 2.0, "lowpass=f=180")
gen("hit_snap", f"({N}*exp(-60*t)+0.7*sin({TAU}*180*t)*exp(-25*t))", 0.35, "highpass=f=120")
gen("stinger_cinematic",
    f"(sin({TAU}*50*t*(1+0.6*exp(-12*t)))*exp(-3.2*t)*0.9+0.3*sin({TAU}*220*t)*exp(-5*t)+0.35*{N}*exp(-22*t))", 2.2,
    "lowpass=f=8000,aecho=0.7:0.6:60|120|200:0.4|0.3|0.2")

# ---- RISERS / BUILDS (before the drop, tension into the hook or reveal) ----------------
gen("riser_short", f"(0.35*sin({TAU}*(200*t+2600*t*t/2/1.5))+0.55*{N})*pow(min(t/1.5,1),2.2)", 1.5,
    "highpass=f=200,lowpass=f=9000,afade=t=out:st=1.42:d=0.08")
gen("riser_long", f"(0.35*sin({TAU}*(150*t+3500*t*t/2/3.5))+0.55*{N})*pow(min(t/3.5,1),2.4)", 3.5,
    "highpass=f=150,lowpass=f=10000,afade=t=out:st=3.42:d=0.08")
gen("tension_drone", f"(0.4*sin({TAU}*55*t)+0.3*sin({TAU}*55.7*t)+0.2*sin({TAU}*110.4*t))*min(t/1.5,1)*min((4-t)/1.0,1)", 4.0, "")
gen("reverse_hit", f"(sin({TAU}*55*(1.2-t)*(1+0.5*exp(-18*(1.2-t))))*exp(-5*(1.2-t))+0.5*{N}*exp(-30*(1.2-t)))*0.95*pow(min(t/1.2,1),1.5)", 1.2,
    "lowpass=f=9000")

# ---- UI / POP / CLICK (captions, emphasis words, stickers, counters) ---------------------
gen("pop", f"sin({TAU}*(500+900*exp(-40*t))*t)*exp(-28*t)", 0.18, "")
gen("pop_soft", f"sin({TAU}*(350+500*exp(-35*t))*t)*exp(-22*t)*0.8", 0.2, "lowpass=f=3000")
gen("click", f"{N}*exp(-350*t)", 0.05, "highpass=f=2500")
gen("tick", f"sin({TAU}*2400*t)*exp(-260*t)", 0.06, "")
gen("keyboard_key", f"({N}*exp(-180*t)*0.8+sin({TAU}*1100*t)*exp(-120*t)*0.4)", 0.08, "highpass=f=900")
gen("camera_shutter", f"({N}*exp(-220*t)+0.8*{N}*exp(-220*(t-0.06))*gt(t,0.06))", 0.2, "highpass=f=1500,lowpass=f=9000")
gen("ding", f"(sin({TAU}*1568*t)*0.6+sin({TAU}*2352*t)*0.25+sin({TAU}*3136*t)*0.12)*exp(-4.5*t)", 1.2, "")
gen("success_chime",
    f"(sin({TAU}*880*t)*lt(t,0.12)+sin({TAU}*1108*t)*gte(t,0.12)*lt(t,0.24)+sin({TAU}*1318*t)*gte(t,0.24))*exp(-3.5*mod(t,0.12))*0.7*exp(-0.8*t)", 0.9, "")
gen("error_buzz", f"(sin({TAU}*150*t)+0.5*sin({TAU}*152*t))*exp(-4*t)*0.8", 0.5, "lowpass=f=1200")
gen("notification", f"(sin({TAU}*1320*t)*lt(t,0.1)+sin({TAU}*1760*t)*gte(t,0.1))*exp(-5*mod(t,0.1))*0.7", 0.4, "")

# ---- GLITCH / DIGITAL / RETRO (tech edits, hook interrupts, scene glitch) ----------------
gen("glitch_short", f"({N}*gt(mod(t,0.05),0.025)*0.7+sin({TAU}*(900+700*floor(t*30))*t)*0.25)*lt(t,0.35)", 0.35, "highpass=f=300")
gen("glitch_long", f"({N}*gt(mod(t,0.07),0.03+0.02*sin(t*40))*0.6+sin({TAU}*(500+1200*floor(t*24))*t)*0.3)*pow(1-t/0.9,0.6)", 0.9, "highpass=f=250")
gen("digital_zap", f"sin({TAU}*(4000-3500*t/0.25)*t)*lt(t,0.25)*exp(-8*t)", 0.25, "")
gen("record_scratch", f"({N}*0.5+sin({TAU}*(700-600*t/0.5)*t)*0.5)*lt(t,0.5)*min(t/0.02,1)", 0.5, "highpass=f=400,lowpass=f=6000,tremolo=f=22:d=0.7")
gen("laser", f"sin({TAU}*(3500*exp(-9*t)+200)*t)*exp(-6*t)", 0.45, "")

# ---- AMBIENCE / TEXTURE (transitions, underscores) --------------------------------------
gen("swoosh_air", f"{N}*pow(sin(PI*min(t/1.0,1)),0.8)*0.25", 1.0, "lowpass=f=2500,highpass=f=300")
gen("vinyl_crackle", f"({N}*gt(random(1),0.995)*0.9+0.03*{N})*min(t/0.3,1)", 3.0, "highpass=f=1500")
gen("heartbeat", f"(sin({TAU}*60*t)*exp(-22*mod(t,0.8))+0.7*sin({TAU}*58*t)*exp(-22*mod(t-0.22,0.8))*gte(t,0.22))", 3.2, "lowpass=f=160")

print("done:", len([f for f in os.listdir(OUT) if f.endswith('.mp3')]), "files")

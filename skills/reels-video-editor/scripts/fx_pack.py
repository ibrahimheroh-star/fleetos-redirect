#!/usr/bin/env python3
"""Video effects pack: 40+ editing moves for vertical short-form video, each usable on a time window.

  python fx_pack.py list                         # all effects with one-line descriptions
  python fx_pack.py NAME IN [EXTRA_IN] OUT [--at START:END] [--p key=value ...]

Examples:
  fx_pack.py rgb-split in.mp4 out.mp4 --at 2.0:2.4 --p amount=18
  fx_pack.py freeze in.mp4 out.mp4 --at 3.2 --p dur=1.2 --p mode=desat
  fx_pack.py glow in.mp4 out.mp4                 # no --at = whole clip

Effects that change length (freeze, stutter, reverse) shift later timestamps; do them FIRST, then time everything
else against the new file. Everything is ffmpeg-only (no extra dependencies). All outputs keep audio.
"""
import argparse, os, random, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reel_tools import run, probe_data, has_audio  # noqa: E402

REG = {}          # name -> dict(fn, doc, kind, defaults)
FPS = 30


def effect(name, doc, kind="window", **defaults):
    """kind: 'window'  fn returns '[in]...[out]' graph, wrapped so it only shows between --at S:E
             'direct'  fn returns '[in]...[out]' graph applied to the whole clip (it handles --at itself via enable=)
             'special' fn(ctx) does its own ffmpeg call"""
    def deco(fn):
        REG[name] = dict(fn=fn, doc=doc, kind=kind, defaults=defaults); return fn
    return deco


def lin(chain): return f"[in]{chain}[out]"


class Ctx:
    def __init__(self, inputs, out, s, e, p):
        self.inputs, self.out, self.s, self.e = inputs, out, s, e
        self.p = p
        d = probe_data(inputs[0]); v = next(x for x in d["streams"] if x["codec_type"] == "video")
        self.W, self.H, self.dur = int(v["width"]), int(v["height"]), float(d["format"].get("duration", 5))
        self.audio = has_audio(inputs[0])
    @property
    def s0(self): return 0.0 if self.s is None else self.s
    @property
    def e0(self): return self.dur if self.e is None else self.e
    def f(self, k): return float(self.p[k])
    def i(self, k): return int(float(self.p[k]))
    def enable(self): return f"enable='between(t,{self.s0},{self.e0})'"


def finish(ctx, vf_graph, extra_inputs=(), extra_args=()):
    cmd = ["ffmpeg", "-y", "-i", ctx.inputs[0]]
    for x in extra_inputs: cmd += x
    cmd += ["-filter_complex", vf_graph, "-map", "[v]"]
    if ctx.audio: cmd += ["-map", "0:a"]
    cmd += list(extra_args) + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p"]
    if ctx.audio: cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    run(cmd + [ctx.out])


def run_graph(ctx, graph, windowed):
    g = graph.replace("[in]", "[fxin]").replace("[out]", "[fxout]")
    if windowed and ctx.s is not None:
        full = f"[0:v]split[base][fxin];{g};[base][fxout]overlay={ctx.enable()},format=yuv420p[v]"
    else:
        full = f"[0:v]null[fxin];{g};[fxout]format=yuv420p[v]"
    finish(ctx, full)


# ================================================================== COLOUR / LOOK
@effect("rgb-split", "chromatic aberration: red/blue channels pull apart (hit, glitch, impact)", amount=14)
def _(c): a = c.i("amount"); return lin(f"rgbashift=rh=-{a}:bh={a}:rv={max(1, a // 3)}:bv=-{max(1, a // 3)}")

@effect("glow", "soft bloom / dreamy highlight glow", sigma=28, strength=0.45)
def _(c): return f"[in]split[a][b];[b]gblur=sigma={c.f('sigma')},eq=brightness=0.04:contrast=1.15,format=gbrp[g];[a]format=gbrp[a2];[a2][g]blend=all_mode=screen:all_opacity={c.f('strength')},format=yuv420p[out]"

@effect("duotone", "two-colour poster look. c1=shadow rgb, c2=highlight rgb (0-1 floats as r,g,b)", c1="0.05,0.02,0.25", c2="1.0,0.45,0.35")
def _(c):
    r1, g1, b1 = c.p["c1"].split(","); r2, g2, b2 = c.p["c2"].split(",")
    return lin(f"hue=s=0,curves=r='0/{r1} 1/{r2}':g='0/{g1} 1/{g2}':b='0/{b1} 1/{b2}'")

@effect("vhs", "retro VHS: colour bleed, scanlines, noise, soft focus", noise=18)
def _(c): return lin(f"eq=saturation=1.35:contrast=1.08,rgbashift=rh=-5:bh=5:rv=1,gblur=sigma=0.7,noise=alls={c.i('noise')}:allf=t,drawgrid=w=iw:h=5:t=1:c=black@0.16,vignette=PI/5")

@effect("old-film", "sepia + flicker + grain + vignette (vintage / flashback)", grain=14)
def _(c): return lin(f"hue=s=0,colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,eq=brightness='0.03*sin(t*37)+0.02*sin(t*11)':contrast=1.1:eval=frame,noise=alls={c.i('grain')}:allf=t,vignette=PI/4")

@effect("scanlines", "CRT scanlines overlay", gap=4, opacity=0.2)
def _(c): return lin(f"drawgrid=w=iw:h={c.i('gap')}:t=1:c=black@{c.f('opacity')}")

@effect("color-pop", "keep ONE colour, everything else goes black & white (hex like 0xFF0000)", color="0xFF3030", similarity=0.35, blend=0.12)
def _(c): return lin(f"colorhold=color={c.p['color']}:similarity={c.f('similarity')}:blend={c.f('blend')}")

@effect("toon", "cartoon look: posterised colours + ink outlines", levels=40)
def _(c): return f"[in]split[a][b];[b]edgedetect=low=0.08:high=0.25,negate,format=gbrp[e];[a]lutyuv=y='floor(val/{c.i('levels')})*{c.i('levels')}+{c.i('levels') // 2}',eq=saturation=1.5,format=gbrp[p];[p][e]blend=all_mode=multiply,format=yuv420p[out]"

@effect("sketch", "pencil-sketch outlines on white")
def _(c): return lin("edgedetect=low=0.05:high=0.2,negate")

@effect("invert-flash", "anime impact frame: colours invert for a few frames (use short --at, e.g. 2.0:2.1)")
def _(c): return lin("negate")

@effect("bw", "black & white with punchy contrast")
def _(c): return lin("hue=s=0,eq=contrast=1.25:gamma=0.95")

@effect("enhance", "denoise + normalise exposure + sharpen + tiny saturation lift (fix weak footage)", kind="direct")
def _(c): return lin("hqdn3d=3:2:4:3,normalize=smoothing=20,unsharp=5:5:0.8,eq=saturation=1.08")

@effect("lens-distort", "fisheye bulge for a hit or reveal", k=0.35)
def _(c): return lin(f"lenscorrection=k1=-{c.f('k')}:k2={c.f('k') / 3:.3f}")

@effect("trail", "ghost trails on motion (echo / afterimage)", decay=0.93)
def _(c): return lin(f"lagfun=decay={c.f('decay')}")

@effect("strobe", "strobing flicker (EDM drops, shock)", hz=10, amount=0.2)
def _(c): return lin(f"eq=brightness='{c.f('amount')}*gt(sin(t*{c.f('hz')}*6.2832),0)':eval=frame")

@effect("flash", "white flash that decays quickly (put on cuts and hits). --at is the flash START time", kind="direct", dur=0.35, power=0.9)
def _(c):
    s, d, pw = c.s0, c.f("dur"), c.f("power")
    return lin(f"eq=brightness='{pw}*exp(-(t-{s})*{12 / d:.2f})*between(t,{s},{s + d})':eval=frame")


# ================================================================== MOTION (single stream)
@effect("beat-pulse", "zoom pulse on every beat of the music. p: bpm, amount", kind="direct", bpm=120, amount=0.045)
def _(c):
    W, H = c.W, c.H
    return lin(f"fps={FPS},scale={int(W * 1.5)}:{int(H * 1.5)}:flags=bicubic,zoompan=z='1+{c.f('amount')}*exp(-6*mod(it*{c.f('bpm')}/60,1))':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps={FPS},setsar=1")

@effect("handheld", "gentle handheld camera drift for the whole clip (adds life to static shots)", kind="direct", amount=14)
def _(c):
    a, W, H = c.f("amount"), c.W, c.H
    return lin(f"scale=iw*1.07:ih*1.07,crop={W}:{H}:x='(iw-{W})/2+{a}*sin(t*1.3)+{a / 2}*sin(t*3.1)':y='(ih-{H})/2+{a}*cos(t*1.7)+{a / 2}*sin(t*2.3)'")

@effect("dutch-tilt", "rocking tilt / dutch angle", kind="direct", deg=3, hz=2.0)
def _(c):
    W, H = c.W, c.H
    return lin(f"rotate=a='{c.f('deg')}*PI/180*sin(t*{c.f('hz')})':c=black:ow=iw:oh=ih,scale=iw*1.16:ih*1.16,crop={W}:{H}")

@effect("spin-in", "quick roll/spin settle at the start (intro punch). --at start time", kind="direct", turns=1.0, dur=0.6)
def _(c):
    W, H, s, d, tr = c.W, c.H, c.s0, c.f("dur"), c.f("turns")
    return lin(f"rotate=a='{tr}*2*PI*pow(1-clip((t-{s})/{d},0,1),3)':c=black:ow=iw:oh=ih,scale=iw*1.0:ih*1.0")

@effect("blur-reveal", "starts blurred and snaps sharp (stepped). --at S:E is the reveal window", kind="direct", sigma=24)
def _(c):
    s, e = c.s0, c.e0; n = 5; step = (e - s) / n; sg = c.f("sigma"); parts = []
    for k in range(n):
        parts.append(f"gblur=sigma={max(1, sg * (1 - k / n) ** 1.5):.1f}:enable='between(t,{s + k * step:.3f},{s + (k + 1) * step:.3f})'")
    return lin(",".join(parts))

@effect("pixel-reveal", "mosaic that resolves into sharp (stepped). --at S:E is the window", kind="direct", block=96)
def _(c):
    s, e = c.s0, c.e0; n = 4; step = (e - s) / n; b = c.i("block"); parts = []
    for k in range(n):
        bs = max(2, b >> k)
        parts.append(f"pixelize=w={bs}:h={bs}:enable='between(t,{s + k * step:.3f},{s + (k + 1) * step:.3f})'")
    return lin(",".join(parts))

@effect("mirror", "mirror the frame: lr (left copied right), tb, or quad", mode="lr")
def _(c):
    m = c.p["mode"]
    if m == "lr": return "[in]split[a][b];[a]crop=iw/2:ih:0:0[l];[b]crop=iw/2:ih:0:0,hflip[r];[l][r]hstack[out]"
    if m == "tb": return "[in]split[a][b];[a]crop=iw:ih/2:0:0[t];[b]crop=iw:ih/2:0:0,vflip[u];[t][u]vstack[out]"
    return "[in]split=4[a][b][c][d];[a]crop=iw/2:ih/2:0:0[q1];[b]crop=iw/2:ih/2:0:0,hflip[q2];[c]crop=iw/2:ih/2:0:0,vflip[q3];[d]crop=iw/2:ih/2:0:0,hflip,vflip[q4];[q1][q2]hstack[top];[q3][q4]hstack[bot];[top][bot]vstack[out]"

@effect("tilt-shift", "miniature / depth-of-field look: sharp band, blurred top & bottom", kind="direct", sigma=14, band=0.5)
def _(c):
    W, H, d = c.W, c.H, c.dur
    return (f"[in]split[o][b];[b]gblur=sigma={c.f('sigma')}[bl];color=c=black:s={W}x{H}:r={FPS}:d={d},format=gray,"
            f"geq=lum='clip(abs(Y-H*{c.f('band')})/(H*0.5)*520-110,0,255)'[m];[bl][m]alphamerge[bla];[o][bla]overlay[out]")

@effect("letterbox", "cinematic black bars that slide in (and stay)", kind="direct", ratio=0.11, speed=0.6)
def _(c):
    r, sp = c.f("ratio"), c.f("speed"); s = c.s0
    return lin(f"drawbox=x=0:y=0:w=iw:h='ih*{r}*clip((t-{s})/{sp},0,1)':color=black:t=fill,drawbox=x=0:y='ih-ih*{r}*clip((t-{s})/{sp},0,1)':w=iw:h='ih*{r}*clip((t-{s})/{sp},0,1)':color=black:t=fill")

@effect("progress-bar", "thin retention bar filling across the video (top/bottom). p: pos=top|bottom, color", kind="direct", pos="bottom", color="yellow", height=14)
def _(c):
    y = "0" if c.p["pos"] == "top" else f"ih-{c.i('height')}"
    return lin(f"drawbox=x=0:y={y}:w='iw*clip(t/{c.dur},0,1)':h={c.i('height')}:color={c.p['color']}@0.95:t=fill")

@effect("fade-io", "fade from/to black (video + audio). p: fin, fout seconds", kind="special", fin=0.4, fout=0.5)
def _(c):
    fi, fo = c.f("fin"), c.f("fout"); so = max(0, c.dur - fo)
    cmd = ["ffmpeg", "-y", "-i", c.inputs[0], "-vf", f"fade=t=in:st=0:d={fi},fade=t=out:st={so:.3f}:d={fo}", "-map", "0:v"]
    if c.audio: cmd += ["-af", f"afade=t=in:st=0:d={fi},afade=t=out:st={so:.3f}:d={fo}", "-map", "0:a"]
    run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-b:a", "192k"] if c.audio else []) + [c.out])


# ================================================================== GLITCH (multi-overlay)
@effect("glitch", "digital glitch: slice displacement + RGB split bursts inside --at S:E", kind="direct", intensity=1.0, seed=3)
def _(c):
    s, e = c.s0, c.e0; rnd = random.Random(c.i("seed")); k = max(1, min(18, int((e - s) / 0.07)))
    a = int(14 * c.f("intensity"))
    g = f"[in]rgbashift=rh=-{a}:bh={a}:enable='between(t,{s},{e})'[g0]"
    for i in range(k):
        t0 = s + i * (e - s) / k; y = rnd.randint(0, int(c.H * 0.85)); h = rnd.randint(30, 220); dx = rnd.choice([-1, 1]) * rnd.randint(30, 140)
        g += (f";[g{i}]split[ga{i}][gb{i}];[gb{i}]crop=iw:{h}:0:{y}[st{i}];"
              f"[ga{i}][st{i}]overlay=x={dx}:y={y}:enable='between(t,{t0:.3f},{t0 + (e - s) / k * 0.8:.3f})'[g{i + 1}]")
    return g + f";[g{k}]null[out]"


# ================================================================== LENGTH-CHANGING / SPECIAL
def _audio_seg_graph(ctx, parts):
    return ""


@effect("freeze", "freeze-frame at --at T for p.dur seconds (mode=plain|desat|zoom). Adds dur to length", kind="special", dur=1.0, mode="desat")
def _(c):
    t, d = c.s0, c.f("dur"); n = max(1, int(d * FPS)); fe = 1 / FPS
    desat = ",hue=s=0" if c.p["mode"] == "desat" else ""
    zoom = f",scale=iw*1.08:ih*1.08,crop={c.W}:{c.H}" if c.p["mode"] == "zoom" else ""
    g = (f"[0:v]trim=0:{t},setpts=PTS-STARTPTS[v1];[0:v]trim=start={t}:end={t + fe},setpts=PTS-STARTPTS,loop=loop={n}:size=1:start=0{desat}{zoom}[v2];"
         f"[0:v]trim=start={t},setpts=PTS-STARTPTS[v3];[v1][v2][v3]concat=n=3:v=1:a=0[v]")
    cmd = ["ffmpeg", "-y", "-i", c.inputs[0]]
    if c.audio:
        g += (f";[0:a]atrim=0:{t},asetpts=PTS-STARTPTS[a1];anullsrc=r=48000:cl=stereo,atrim=0:{d}[a2];"
              f"[0:a]atrim=start={t},asetpts=PTS-STARTPTS[a3];[a1][a2][a3]concat=n=3:v=0:a=1[a]")
    cmd += ["-filter_complex", g, "-map", "[v]"] + (["-map", "[a]"] if c.audio else [])
    run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-b:a", "192k"] if c.audio else []) + [c.out])


@effect("reverse", "play --at S:E backwards (rewind moment), rest unchanged", kind="special")
def _(c):
    s, e = c.s0, c.e0
    g = (f"[0:v]trim=0:{s},setpts=PTS-STARTPTS[v1];[0:v]trim={s}:{e},setpts=PTS-STARTPTS,reverse[v2];[0:v]trim=start={e},setpts=PTS-STARTPTS[v3];"
         f"[v1][v2][v3]concat=n=3:v=1:a=0[v]")
    if c.audio:
        g += (f";[0:a]atrim=0:{s},asetpts=PTS-STARTPTS[a1];[0:a]atrim={s}:{e},asetpts=PTS-STARTPTS,areverse[a2];"
              f"[0:a]atrim=start={e},asetpts=PTS-STARTPTS[a3];[a1][a2][a3]concat=n=3:v=0:a=1[a]")
    cmd = ["ffmpeg", "-y", "-i", c.inputs[0], "-filter_complex", g, "-map", "[v]"] + (["-map", "[a]"] if c.audio else [])
    run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-b:a", "192k"] if c.audio else []) + [c.out])


@effect("stutter", "beat-repeat: loop a tiny slice p.n times at --at T (p.len seconds each). Adds time", kind="special", len=0.18, n=4)
def _(c):
    t, ln, n = c.s0, c.f("len"), c.i("n")
    g = (f"[0:v]trim=0:{t},setpts=PTS-STARTPTS[v1];[0:v]trim={t}:{t + ln},setpts=PTS-STARTPTS,loop=loop={n - 1}:size={max(1, int(ln * FPS))}:start=0[v2];"
         f"[0:v]trim=start={t + ln},setpts=PTS-STARTPTS[v3];[v1][v2][v3]concat=n=3:v=1:a=0[v]")
    if c.audio:
        g += (f";[0:a]atrim=0:{t},asetpts=PTS-STARTPTS[a1];[0:a]atrim={t}:{t + ln},asetpts=PTS-STARTPTS,aloop=loop={n - 1}:size={int(ln * 48000)}[a2];"
              f"[0:a]atrim=start={t + ln},asetpts=PTS-STARTPTS[a3];[a1][a2][a3]concat=n=3:v=0:a=1[a]")
    cmd = ["ffmpeg", "-y", "-i", c.inputs[0], "-filter_complex", g, "-map", "[v]"] + (["-map", "[a]"] if c.audio else [])
    run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-b:a", "192k"] if c.audio else []) + [c.out])


@effect("stabilize", "two-pass shake removal for handheld footage (vidstab)", kind="special", smoothing=12)
def _(c):
    trf = os.path.join(tempfile.mkdtemp(), "t.trf")
    run(["ffmpeg", "-y", "-i", c.inputs[0], "-vf", f"vidstabdetect=shakiness=6:accuracy=12:result={trf}", "-f", "null", "-"])
    cmd = ["ffmpeg", "-y", "-i", c.inputs[0], "-vf", f"vidstabtransform=input={trf}:smoothing={c.i('smoothing')}:zoom=3,unsharp=5:5:0.6", "-map", "0:v"] + (["-map", "0:a"] if c.audio else [])
    run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"] + (["-c:a", "copy"] if c.audio else []) + [c.out])


@effect("ken-burns", "turn a STILL IMAGE into a slow zoom/pan video. IN is the image. p: dur, direction=in|out|left|right|up, zoom, fit=contain|cover, bg=color", kind="special", dur=5, direction="in", zoom=1.25, w=1080, h=1920, fit="contain", bg="0x111116")
def _(c):
    W, H, d, z = c.i("w"), c.i("h"), c.f("dur"), c.f("zoom"); n = int(d * FPS)
    dr = c.p["direction"]; prog = f"on/{n}"; BW, BH = int(W * 1.6), int(H * 1.6)
    zexp = {"in": f"1+{z - 1}*{prog}", "out": f"{z}-{z - 1}*{prog}"}.get(dr, f"{z}")
    xexp = {"left": f"(iw-iw/zoom)*(1-{prog})", "right": f"(iw-iw/zoom)*{prog}"}.get(dr, "(iw-iw/zoom)/2")
    yexp = {"up": f"(ih-ih/zoom)*(1-{prog})"}.get(dr, "(ih-ih/zoom)/2")
    if c.p["fit"] == "cover":
        fg = f"[0:v]scale={BW}:{BH}:force_original_aspect_ratio=increase,crop={BW}:{BH},format=rgba[fg]"
    else:
        fg = f"[0:v]scale={int(BW * 0.9)}:{int(BH * 0.9)}:force_original_aspect_ratio=decrease,format=rgba[fg]"
    g = (f"color=c={c.p['bg']}:s={BW}x{BH}:r={FPS}:d={d}[bg];{fg};[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,"
         f"zoompan=z='{zexp}':x='{xexp}':y='{yexp}':d={n}:s={W}x{H}:fps={FPS},format=yuv420p[v]")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", c.inputs[0], "-filter_complex", g, "-map", "[v]", "-t", str(d),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", c.out])


@effect("pip", "picture-in-picture: 2nd input shrinks into a corner with border. p: pos=tr|tl|br|bl, scale, margin", kind="special", pos="br", scale=0.38, margin=40, border=6)
def _(c):
    W, H = c.W, c.H; w = int(W * c.f("scale")) // 2 * 2; m = c.i("margin"); b = c.i("border")
    x = {"tl": f"{m}", "bl": f"{m}", "tr": f"W-w-{m}", "br": f"W-w-{m}"}[c.p["pos"]]
    y = {"tl": f"{m}", "tr": f"{m}", "bl": f"H-h-{m}", "br": f"H-h-{m}"}[c.p["pos"]]
    en = f":enable='between(t,{c.s0},{c.e0})'" if c.s is not None else ""
    g = (f"[1:v]scale={w}:-2,pad=iw+{2 * b}:ih+{2 * b}:{b}:{b}:white[p];[0:v][p]overlay=x={x}:y={y}{en},format=yuv420p[v]")
    finish(c, g, extra_inputs=[["-i", c.inputs[1]]], extra_args=["-shortest"])


@effect("split-screen", "stack two videos vertically (reaction / before-after / comparison). IN, IN2", kind="special")
def _(c):
    W, H = c.W, c.H
    g = (f"[0:v]scale={W}:{H // 2}:force_original_aspect_ratio=increase,crop={W}:{H // 2}[t];"
         f"[1:v]scale={W}:{H // 2}:force_original_aspect_ratio=increase,crop={W}:{H // 2}[b];[t][b]vstack,format=yuv420p[v]")
    finish(c, g, extra_inputs=[["-i", c.inputs[1]]], extra_args=["-shortest"])


@effect("light-leak", "warm animated light leak that fades in/out over --at S:E (film/cinematic transitions)", kind="special", strength=0.7)
def _(c):
    s, e = c.s0, c.e0; ln = e - s; fd = min(0.5, ln / 3)
    # generate the leak for just the window, fade it from/to black, then pad black in front so screen-blend is neutral outside it
    leak = (f"gradients=s={c.W}x{c.H}:d={ln}:rate={FPS}:c0=0xff8a2b:c1=0xff2d6f:c2=0xffd36b:n=3:speed=0.06,"
            f"eq=brightness={-0.35 + 0.35 * c.f('strength'):.2f},fade=t=in:st=0:d={fd},fade=t=out:st={ln - fd:.3f}:d={fd},"
            f"tpad=start_duration={s}:start_mode=add:color=black,format=gbrp")
    # blend in RGB: screen on YUV chroma planes tints the whole frame magenta
    g = f"{leak}[lk];[0:v]format=gbrp[b];[b][lk]blend=all_mode=screen:eof_action=repeat,format=yuv420p[v]"
    finish(c, g)


# ================================================================== runner
def apply(name, inputs, out, s=None, e=None, p=None):
    if name not in REG: sys.exit(f"unknown effect '{name}'. `fx_pack.py list` shows all.")
    spec = REG[name]; params = dict(spec["defaults"]); params.update({k: str(v) for k, v in (p or {}).items()})
    ctx = Ctx(inputs, out, s, e, params)
    if spec["kind"] == "special": spec["fn"](ctx)
    else: run_graph(ctx, spec["fn"](ctx), windowed=(spec["kind"] == "window"))
    return out


def parse_at(txt):
    if txt is None: return None, None
    parts = [float(x) for x in txt.split(":")]
    return (parts[0], parts[1] if len(parts) > 1 else None)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for k, v in sorted(REG.items()):
            dflt = " ".join(f"{a}={b}" for a, b in v["defaults"].items())
            print(f"{k:14s} {v['doc']}" + (f"\n{'':14s} defaults: {dflt}" if dflt else ""))
        print(f"\n{len(REG)} effects"); return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name"); ap.add_argument("files", nargs="+", help="input(s) then output")
    ap.add_argument("--at", help="START:END (or START) in seconds; omit for whole clip")
    ap.add_argument("--p", action="append", default=[], metavar="key=value")
    a = ap.parse_args()
    s, e = parse_at(a.at)
    apply(a.name, a.files[:-1], a.files[-1], s, e, dict(x.split("=", 1) for x in a.p))
    print(a.files[-1])


if __name__ == "__main__":
    main()

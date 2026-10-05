#!/usr/bin/env python3
"""Pro-level effects for vertical video: punch-in zooms, camera shake, speed ramps, colour grading,
transitions, animated word-by-word captions, sound-effect mixing, and a one-shot `build` from a JSON plan.

Companion to reel_tools.py (basic cut/reframe/export). Run `python pro_fx.py <command> --help`.
All times are in seconds on the timeline of the file you pass in.
"""
import argparse, json, os, re, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reel_tools import run, probe_data, has_audio, pick_font, W, H  # noqa: E402

from assets_path import SFX_DIR, MUSIC_DIR  # noqa: E402  (unpacks the sound library on first use)
FPS = 30


def enc_hq(out):
    """Visually lossless-ish intermediate; the final delivery encode happens in `export`/build."""
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out]


def duration(path):
    return float(probe_data(path)["format"]["duration"])


def maps(path):
    return ["-map", "0:v"] + (["-map", "0:a"] if has_audio(path) else [])


# --------------------------------------------------------------------------- punch-zoom
def punch_zoom(inp, out, segs, focus=(0.5, 0.4), t_in=0.18, t_out=0.3):
    """segs: [(start, end, zoom)] e.g. (2.0, 3.4, 1.25). Eased push-in and release (smooth, not a jump)."""
    terms = "+".join(
        f"({z}-1)*sin(PI/2*max(0,min(1,min((it-{s})/{t_in},({e}-it)/{t_out}))))" for s, e, z in segs)
    fx, fy = focus
    # upscale 1.5x first so zoompan's integer crop rounding doesn't make the push-in jitter
    vf = (f"fps={FPS},scale={int(W*1.5)}:{int(H*1.5)}:flags=bicubic,"
          f"zoompan=z='1+{terms}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d=1:s={W}x{H}:fps={FPS},setsar=1")
    run(["ffmpeg", "-y", "-i", inp, "-vf", vf] + maps(inp) + enc_hq(out))


# --------------------------------------------------------------------------- shake
def shake(inp, out, shakes, scale=1.08):
    """shakes: [(start, dur, amp_px)]. Decaying handheld-impact shake. Video is scaled by `scale` to hide edges,
    so keep amp below (scale-1)/2*1080 (~43 px at 1.08)."""
    terms_x, terms_y = [], []
    for s, d, a in shakes:
        a = min(a, (scale - 1) / 2 * W * 0.9)
        k = f"between(t,{s},{s+d})*{a}*pow(1-(t-{s})/{d},2)"
        terms_x.append(f"{k}*sin(t*97)")
        terms_y.append(f"{k}*cos(t*83)")
    x = f"(iw-{W})/2+{'+'.join(terms_x)}"
    y = f"(ih-{H})/2+{'+'.join(terms_y)}"
    vf = f"scale=iw*{scale}:ih*{scale},crop={W}:{H}:x='{x}':y='{y}'"
    run(["ffmpeg", "-y", "-i", inp, "-vf", vf] + maps(inp) + enc_hq(out))


# --------------------------------------------------------------------------- speed ramp
def atempo_chain(f):
    parts = []
    while f > 2.0:
        parts.append("atempo=2.0"); f /= 2.0
    while f < 0.5:
        parts.append("atempo=0.5"); f /= 0.5
    parts.append(f"atempo={f:.4f}")
    return ",".join(parts)


def speed_ramp(inp, out, segs):
    """segs: [(start, end, speed)] e.g. (2.0, 3.0, 0.4) = slow-mo, (5, 6, 2.5) = fast-forward. Rest plays at 1x."""
    dur = duration(inp)
    segs = sorted(segs)
    plan, cur = [], 0.0
    for s, e, sp in segs:
        if s > cur:
            plan.append((cur, s, 1.0))
        plan.append((s, min(e, dur), sp)); cur = min(e, dur)
    if cur < dur:
        plan.append((cur, dur, 1.0))
    aud = has_audio(inp)
    parts = []
    for i, (s, e, sp) in enumerate(plan):
        parts.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=(PTS-STARTPTS)/{sp}[v{i}]")
        if aud:
            parts.append(f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,{atempo_chain(sp)}[a{i}]")
    cat = "".join(f"[v{i}]" + (f"[a{i}]" if aud else "") for i in range(len(plan)))
    fc = ";".join(parts) + f";{cat}concat=n={len(plan)}:v=1:a={1 if aud else 0}[v]" + ("[a]" if aud else "")
    cmd = ["ffmpeg", "-y", "-i", inp, "-filter_complex", fc, "-map", "[v]"] + (["-map", "[a]"] if aud else [])
    run(cmd + ["-r", str(FPS)] + enc_hq(out))


# --------------------------------------------------------------------------- colour grade
LOOKS = {
    # teal shadows / warm highlights, gentle S-curve: the "film" look
    "cinematic": "eq=contrast=1.10:saturation=1.08:gamma=0.98,"
                 "colorbalance=rs=-0.05:bs=0.08:rm=-0.02:bm=0.03:rh=0.08:gh=0.02:bh=-0.06,"
                 "curves=all='0/0.03 0.25/0.22 0.75/0.80 1/0.97'",
    "warm": "eq=contrast=1.06:saturation=1.12,colorbalance=rm=0.05:gm=0.01:bm=-0.05:rh=0.06:bh=-0.04",
    "punchy": "eq=contrast=1.16:saturation=1.32:gamma=0.97,unsharp=5:5:0.6",
    "moody": "eq=contrast=1.22:saturation=0.82:gamma=0.90,colorbalance=bs=0.07:bm=0.04:rh=0.03",
    "clean": "eq=contrast=1.04:saturation=1.06,unsharp=3:3:0.4",
    "bw": "hue=s=0,eq=contrast=1.25:gamma=0.95",
}


def grade(inp, out, look="cinematic", grain=0.3, vignette=0.25):
    chain = [LOOKS[look]]
    if vignette > 0:
        chain.append(f"vignette=angle={0.2 + vignette:.2f}*PI/2:mode=backward")
    if grain > 0:
        chain.append(f"noise=alls={int(grain*14)}:allf=t")
    run(["ffmpeg", "-y", "-i", inp, "-vf", ",".join(chain)] + maps(inp) + enc_hq(out))


# --------------------------------------------------------------------------- transitions
XFADES = ["fade", "fadeblack", "fadewhite", "fadegrays", "fadefast", "fadeslow", "dissolve", "pixelize", "radial", "hblur", "zoomin",
          "wipeleft", "wiperight", "wipeup", "wipedown", "wipetl", "wipetr", "wipebl", "wipebr",
          "slideleft", "slideright", "slideup", "slidedown", "smoothleft", "smoothright", "smoothup", "smoothdown",
          "coverleft", "coverright", "coverup", "coverdown", "revealleft", "revealright", "revealup", "revealdown",
          "circleopen", "circleclose", "circlecrop", "rectcrop", "vertopen", "vertclose", "horzopen", "horzclose",
          "diagtl", "diagtr", "diagbl", "diagbr", "hlslice", "hrslice", "vuslice", "vdslice",
          "hlwind", "hrwind", "vuwind", "vdwind", "squeezeh", "squeezev", "distance"]


def transition(clips, out, kinds, dur=0.4):
    """Join clips with xfade+acrossfade. kinds: list cycled over the joins."""
    norm = (f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")
    inputs, parts = [], []
    for i, c in enumerate(clips):
        inputs += ["-i", c]
        parts.append(f"[{i}:v]{norm}[v{i}]")
        parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{i}]")
    lens = [duration(c) for c in clips]
    vlab, alab, acc = "v0", "a0", lens[0]
    for i in range(1, len(clips)):
        k = kinds[(i - 1) % len(kinds)]
        off = acc - dur
        parts.append(f"[{vlab}][v{i}]xfade=transition={k}:duration={dur}:offset={off:.3f}[xv{i}]")
        parts.append(f"[{alab}][a{i}]acrossfade=d={dur}[xa{i}]")
        vlab, alab, acc = f"xv{i}", f"xa{i}", acc + lens[i] - dur
    run(["ffmpeg", "-y"] + inputs + ["-filter_complex", ";".join(parts), "-map", f"[{vlab}]", "-map", f"[{alab}]"]
        + enc_hq(out))


# --------------------------------------------------------------------------- animated captions
def parse_srt(path):
    txt = open(path, encoding="utf-8-sig").read().replace("\r", "")
    cues = []
    for block in re.split(r"\n\s*\n", txt.strip()):
        lines = block.strip().split("\n")
        m = next((re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", l) for l in lines
                  if "-->" in l), None)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        st, en = g[0]*3600 + g[1]*60 + g[2] + g[3]/1000, g[4]*3600 + g[5]*60 + g[6] + g[7]/1000
        body = " ".join(l for l in lines if "-->" not in l and not l.strip().isdigit()).strip()
        cues.append((st, en, body))
    return cues


def ass_time(t):
    h, rem = divmod(t, 3600); m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def pick_latin_font():
    fams = subprocess.run(["fc-list", "family"], capture_output=True, text=True).stdout.lower()
    for f in ["Anton", "Montserrat ExtraBold", "Montserrat", "Bebas Neue", "Impact", "DejaVu Sans"]:
        if f.lower() in fams:
            return f
    return "DejaVu Sans"


STYLES = {  # fontsize px on 1080x1920, outline px, highlight colour (ASS BGR), vertical margin from bottom
    "hormozi": dict(size=96, outline=8, hi="&H0033D9FF&", margin=int(H * 0.30), upper=True, pop=118),
    "clean": dict(size=70, outline=4, hi="&H00FFFFFF&", margin=int(H * 0.18), upper=False, pop=100),
    "neon": dict(size=88, outline=7, hi="&H00FFFF00&", margin=int(H * 0.30), upper=True, pop=122),
    "green": dict(size=96, outline=8, hi="&H0050F050&", margin=int(H * 0.30), upper=True, pop=118),
}


def animated_subs(inp, srt, out, lang="ar", style="hormozi", words=3, font=None):
    st = STYLES[style]
    # Encoding=-1 makes libass auto-detect bidi direction. With the default (1), any colour override tag flipped
    # Arabic lines to left-to-right word order (first word ended up leftmost), so highlights read backwards.
    fontname = font or (pick_font(None) if lang == "ar" else pick_latin_font())
    # Arabic must stay joined and un-uppercased; Latin gets the loud all-caps look
    upper = st["upper"] and lang != "ar"
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{st['size']},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,{st['outline']},3,2,70,70,{st['margin']},-1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for cs, ce, body in parse_srt(srt):
        toks = body.split()
        if not toks:
            continue
        # weight each word by its length so the highlight follows speech rhythm without word-level timestamps
        weights = [len(t) + 1 for t in toks]
        total = sum(weights)
        t0, edges = cs, []
        for w in weights:
            edges.append((t0, t0 + (ce - cs) * w / total)); t0 += (ce - cs) * w / total
        for c0 in range(0, len(toks), words):
            chunk = toks[c0:c0 + words]
            for j, _ in enumerate(chunk):
                ws, we = edges[c0 + j]
                if j == len(chunk) - 1:
                    we = edges[min(c0 + len(chunk), len(toks)) - 1][1]
                parts = []
                for k, tk in enumerate(chunk):
                    tk = tk.upper() if upper else tk
                    parts.append((f"{{\\c{st['hi']}}}{tk}{{\\c&H00FFFFFF&}}") if k == j else tk)
                pop = (f"{{\\fscx{st['pop']}\\fscy{st['pop']}\\t(0,110,\\fscx100\\fscy100)}}" if j == 0 else "")
                events.append(f"Dialogue: 0,{ass_time(ws)},{ass_time(we)},Default,,0,0,0,,{pop}{' '.join(parts)}")
    tmp = tempfile.mkdtemp()
    open(os.path.join(tmp, "c.ass"), "w", encoding="utf-8").write(header + "\n".join(events) + "\n")
    cmd = ["ffmpeg", "-y", "-i", os.path.abspath(inp), "-vf", "ass=c.ass"] + maps(inp) + enc_hq(os.path.abspath(out))
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp)  # cwd=tmp avoids filter path escaping
    if r.returncode:
        sys.exit(r.stderr[-1500:])


# --------------------------------------------------------------------------- sound effects
def resolve_sfx(name, sfx_dir=SFX_DIR):
    if os.path.isfile(name):
        return name
    for ext in (".mp3", ".wav", ".ogg", ".m4a"):
        p = os.path.join(sfx_dir, name + ext)
        if os.path.isfile(p):
            return p
    sys.exit(f"SFX '{name}' not found in {os.path.abspath(sfx_dir)} (use `sfx-list`).")


def sfx_mix(inp, out, cues, sfx_dir=SFX_DIR):
    """cues: [(time_s, name_or_path, gain_db)]. The sound STARTS at time_s, so to land a whoosh's peak on a cut,
    start it ~0.1-0.2 s before the cut."""
    aud = has_audio(inp)
    dur = duration(inp)
    cmd = ["ffmpeg", "-y", "-i", inp]
    for _, name, _ in cues:
        cmd += ["-i", resolve_sfx(name, sfx_dir)]
    parts = []
    if aud:
        base = "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[b]"
    else:
        base = f"anullsrc=r=48000:cl=stereo:d={dur}[b]"
    parts.append(base)
    labels = ["[b]"]
    for i, (t, _, db) in enumerate(cues, start=1):
        ms = max(0, int(t * 1000))
        parts.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay={ms}|{ms},volume={db}dB[s{i}]")
        labels.append(f"[s{i}]")
    parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.95[a]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", out]
    run(cmd)


def parse_triplets(items, n):
    res = []
    for it in items or []:
        p = it.split(":")
        res.append(tuple(float(x) for x in p[:n]))
    return res


def parse_cues(items):
    res = []
    for it in items or []:
        p = it.split(":")
        res.append((float(p[0]), p[1], float(p[2]) if len(p) > 2 else -12.0))
    return res


# --------------------------------------------------------------------------- one-shot build
def build(plan_path):
    """JSON plan -> finished video. Order: cut_silence -> reframe -> speed -> effects -> zoom -> shake -> grade -> overlays -> captions -> sfx -> music -> loudnorm -> export.
    Every time in the plan refers to the timeline AFTER speed ramps (so plan speed first, then place effects)."""
    plan = json.load(open(plan_path, encoding="utf-8"))
    tmp = tempfile.mkdtemp()
    cur = plan["input"]
    step = [0]

    def nxt():
        step[0] += 1
        return os.path.join(tmp, f"s{step[0]}.mp4")

    rt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reel_tools.py")
    if plan.get("cut_silence"):
        o = nxt(); args = plan["cut_silence"] if isinstance(plan["cut_silence"], list) else []
        subprocess.run([sys.executable, rt, "cut-silence", cur, o] + args, check=True, capture_output=True); cur = o
    if plan.get("reframe"):
        o = nxt()
        subprocess.run([sys.executable, rt, "reframe", cur, o, "--mode", plan["reframe"].get("mode", "crop"),
                        "--x-offset", str(plan["reframe"].get("x_offset", 0))], check=True, capture_output=True); cur = o
    if plan.get("speed"):
        o = nxt(); speed_ramp(cur, o, [tuple(x) for x in plan["speed"]]); cur = o
    if plan.get("effects"):
        import fx_pack
        for ef in plan["effects"]:     # list length-changing ones (freeze/reverse/stutter) first
            o = nxt(); at = ef.get("at"); s0, e0 = (None, None) if at is None else (at[0], at[1] if len(at) > 1 else None)
            fx_pack.apply(ef["name"], [cur] + list(ef.get("inputs", [])), o, s0, e0, ef.get("p")); cur = o
    if plan.get("zooms"):
        o = nxt(); punch_zoom(cur, o, [tuple(x) for x in plan["zooms"]], tuple(plan.get("zoom_focus", (0.5, 0.4)))); cur = o
    if plan.get("shakes"):
        o = nxt(); shake(cur, o, [tuple(x) for x in plan["shakes"]]); cur = o
    if plan.get("grade"):
        g = plan["grade"]; o = nxt()
        grade(cur, o, g.get("look", "cinematic"), g.get("grain", 0.3), g.get("vignette", 0.25)); cur = o
    if plan.get("overlays"):
        import mg
        for ov in plan["overlays"]:    # motion-graphic templates rendered with alpha and composited at a time
            mov = os.path.join(tmp, f"mg{step[0]}.mov"); o = nxt()
            mg.W, mg.H = W, H
            mg.render(ov["template"], mov, ov.get("dur"), None, None, {k: str(v) for k, v in ov.get("p", {}).items()})
            mg.overlay(cur, mov, o, ov.get("at", 0.0)); cur = o
    if plan.get("subs"):
        s = plan["subs"]; o = nxt()
        animated_subs(cur, s["srt"], o, s.get("lang", "ar"), s.get("style", "hormozi"), s.get("words", 3), s.get("font")); cur = o
    if plan.get("sfx"):
        o = nxt()
        sfx_mix(cur, o, [(c["t"], c["name"], c.get("db", -12)) for c in plan["sfx"]], plan.get("sfx_dir", SFX_DIR)); cur = o
    if plan.get("music"):
        m = plan["music"]; o = nxt()
        mf = m["file"]
        if not os.path.isfile(mf):     # allow bare names of the bundled beds, e.g. "bed_hype_trap_140"
            mf = os.path.join(MUSIC_DIR, mf + ("" if mf.endswith(".mp3") else ".mp3"))
        subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "reel_tools.py"), "mix-music",
                        cur, mf, o, "--music-db", str(m.get("db", -14))], check=True, capture_output=True)
        cur = o
    if plan.get("loudnorm", True):
        o = nxt()
        run(["ffmpeg", "-y", "-i", cur, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "copy", "-ar", "48000",
             "-c:a", "aac", "-b:a", "192k", o]); cur = o
    # final platform-safe encode (single high-quality pass)
    run(["ffmpeg", "-y", "-i", cur, "-c:v", "libx264", "-preset", "medium", "-crf", str(plan.get("crf", 18)),
         "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", plan["output"]])
    print(plan["output"])


# --------------------------------------------------------------------------- CLI
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("punch-zoom", help="eased push-in zooms on emphasis moments")
    s.add_argument("input"); s.add_argument("output")
    s.add_argument("--at", action="append", required=True, metavar="START:END:ZOOM", help="e.g. 2.0:3.4:1.25 (repeatable)")
    s.add_argument("--focus", default="0.5,0.4", help="x,y of zoom target, 0-1 (default face-height 0.5,0.4)")

    s = sp.add_parser("shake", help="decaying camera shake on impacts")
    s.add_argument("input"); s.add_argument("output")
    s.add_argument("--at", action="append", required=True, metavar="START:DUR:AMP_PX", help="e.g. 4.0:0.35:30")

    s = sp.add_parser("speed-ramp", help="slow-mo / fast-forward segments")
    s.add_argument("input"); s.add_argument("output")
    s.add_argument("--seg", action="append", required=True, metavar="START:END:SPEED", help="e.g. 2:3:0.4 (slow) or 5:6:2.5 (fast)")

    s = sp.add_parser("grade", help="colour grade + vignette + film grain")
    s.add_argument("input"); s.add_argument("output")
    s.add_argument("--look", choices=list(LOOKS), default="cinematic")
    s.add_argument("--grain", type=float, default=0.3); s.add_argument("--vignette", type=float, default=0.25)

    s = sp.add_parser("transition", help="join clips with a transition")
    s.add_argument("output"); s.add_argument("clips", nargs="+")
    s.add_argument("--kind", default="slideleft", help="comma list cycled over joins: " + ",".join(XFADES))
    s.add_argument("--dur", type=float, default=0.4)

    s = sp.add_parser("animated-subs", help="word-by-word highlighted captions (Hormozi/karaoke style)")
    s.add_argument("input"); s.add_argument("srt"); s.add_argument("output")
    s.add_argument("--lang", choices=["ar", "en"], default="ar"); s.add_argument("--style", choices=list(STYLES), default="hormozi")
    s.add_argument("--words", type=int, default=3, help="words shown at once"); s.add_argument("--font")

    s = sp.add_parser("sfx-mix", help="drop sound effects at timestamps")
    s.add_argument("input"); s.add_argument("output")
    s.add_argument("--cue", action="append", required=True, metavar="TIME:NAME[:DB]", help="e.g. 3.1:whoosh_short:-14")
    s.add_argument("--sfx-dir", default=SFX_DIR)

    sp.add_parser("sfx-list", help="list bundled sound effects")

    s = sp.add_parser("build", help="run a full JSON edit plan (see references/plan-example.json)")
    s.add_argument("plan")

    a = p.parse_args()
    if a.cmd == "punch-zoom":
        punch_zoom(a.input, a.output, parse_triplets(a.at, 3), tuple(float(x) for x in a.focus.split(",")))
    elif a.cmd == "shake":
        shake(a.input, a.output, parse_triplets(a.at, 3))
    elif a.cmd == "speed-ramp":
        speed_ramp(a.input, a.output, parse_triplets(a.seg, 3))
    elif a.cmd == "grade":
        grade(a.input, a.output, a.look, a.grain, a.vignette)
    elif a.cmd == "transition":
        transition(a.clips, a.output, a.kind.split(","), a.dur)
    elif a.cmd == "animated-subs":
        animated_subs(a.input, a.srt, a.output, a.lang, a.style, a.words, a.font)
    elif a.cmd == "sfx-mix":
        sfx_mix(a.input, a.output, parse_cues(a.cue), a.sfx_dir)
    elif a.cmd == "sfx-list":
        for f in sorted(os.listdir(SFX_DIR)):
            if f.endswith((".mp3", ".wav", ".ogg")):
                print(f"{os.path.splitext(f)[0]:24s}{duration(os.path.join(SFX_DIR, f)):5.2f}s")
    elif a.cmd == "build":
        build(a.plan)
    if a.cmd not in ("sfx-list", "build"):
        print(a.output)


if __name__ == "__main__":
    main()

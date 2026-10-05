---
name: reels-video-editor
description: "Professional editing of vertical short-form video (Reels, TikTok, Shorts) in Arabic and English: 9:16 reframing, silence cutting, 36 cinematic effects (punch-in zoom, shake, speed ramp, glitch, RGB split, freeze, light leak, VHS, beat-pulse), 29 motion-graphic templates (lower thirds, kinetic titles, counters, charts, callouts, confetti, logo reveal), 57 transitions, animated word-by-word captions with RTL Arabic, 188 sound effects, 7 music beds, image-to-animation, one-shot JSON builds and loudness-normalised export. Use whenever the user mentions montage, video editing, reels, shorts, motion graphics, animating an image or logo, effects, sound effects, captions, trimming, vertical resize, or wants a video or image to look professional, even without saying edit. Also Arabic: مونتاج، موشن جرافيك، ريلز، شورتس، مؤثرات، ترجمة الفيديو."
---

# Reels / Shorts video editor

Turn raw footage into a clean, platform-ready vertical video, and when the user wants it to look *professional*, add the cinematic layer (Step 7). Work from a short plan, run deterministic ffmpeg steps through the bundled script, and check the result before handing it over.

## Why this workflow

Short-form viewers decide in about 1–2 seconds whether to keep watching, and most watch muted. So the edit has to (1) open on the hook, (2) never sit on dead air, and (3) carry the message in readable on-screen text. Every step below serves one of those three goals. Mistakes that cost the most are re-encoding repeatedly (quality loss), burning subtitles with a font that lacks Arabic glyphs (empty boxes), and cropping a face out of frame.

## Step 0 - Gather what you need (ask only what is missing)

- Input file(s) and where to save output.
- Target platform (Reels, TikTok, Shorts) - default 1080x1920, 30 fps, H.264 + AAC, under 90 s unless told otherwise.
- Language of speech and of subtitles (Arabic, English, or both).
- Style: fast and punchy vs. calm; music or not; brand colours / logo.

If the user just says "edit this", do not interrogate them. Use the defaults, state them in one line, and proceed.

## Step 1 - Inspect

Run `python scripts/reel_tools.py probe INPUT` to get duration, resolution, fps, audio presence, and whether the clip is already vertical. Decide the plan from that: a landscape 16:9 source needs a reframe decision (Step 3); a vertical source usually needs only cuts and captions.

## Step 2 - Plan the cut

Write the plan as a short list before touching ffmpeg (timestamps in seconds):
1. Hook: the strongest 1-3 seconds go first. If it is in the middle of the clip, move it to the start.
2. Body: keep only beats that move the message forward.
3. Ending: a clear closer or CTA; loop-friendly if the platform rewards replays.

For talking-head footage, remove silences with `cut-silence` (it keeps a small breathing margin so cuts do not feel clipped). Prefer a cut every 2-4 seconds for energetic styles, 4-7 for calm ones. Show the plan to the user when the cuts are creative decisions (what to drop), and just do it when they are mechanical (silence removal).

## Step 3 - Reframe to 9:16

`reframe` offers three modes. Pick on purpose:
- `crop` (default): centre-crop to fill the screen. Best when the subject is centred. Offer `--x-offset` (-1 left to 1 right) when the subject is off-centre.
- `blur`: keep the whole landscape frame in the middle over a blurred, zoomed copy as background. Best for screen recordings, wide shots, and anything where cropping would cut off content.
- `fit`: letterbox with black bars. Avoid unless asked.

Check one extracted frame (`frame` subcommand) after reframing to confirm faces and key text are not cut off.

## Step 4 - Subtitles

**Order matters:** cutting silence or trimming shifts every timestamp, so transcribe/time the subtitles on the *already-cut* video, never on the raw footage. A user-supplied `.srt` that was timed to the raw footage must be re-timed or the cut skipped.

1. If the user supplies an `.srt`, use it. Otherwise get a transcript: use an available transcription tool (e.g. the ElevenLabs `creative_transcribe_audio` tool, the Speko `audio_transcribe` tool, or `whisper` if installed locally) and write an `.srt`. Keep lines to roughly 2 lines x 28-32 characters so they fit a phone screen, and 1-3 seconds per cue.
2. Burn in with `python scripts/reel_tools.py subs INPUT SRT OUTPUT --lang ar|en`. The script picks a font that actually contains Arabic glyphs, uses libass so Arabic letters join and run right-to-left correctly, and positions text in the safe zone (above the platform UI at the bottom, roughly 18% up from the edge).
3. For bilingual output, put the Arabic line first and the English line below it in the same cue, or ask which language is primary. Do not stack more than 2 lines total.
4. Always extract a frame with subtitles visible and look at it. Disconnected or reversed Arabic letters mean the font or libass shaping is wrong; switch font with `--font`.

Review the transcript itself for mistakes, especially names, numbers and dialect words, before burning in. Burned-in errors cannot be fixed without re-rendering.

## Step 5 - Audio

- `loudnorm` normalises to about -14 LUFS, which is what the major platforms target; skipping this makes the video sound quiet next to others.
- Music: `mix-music` lowers the track under speech (sidechain ducking) so the voice stays clear. Keep music around -20 to -24 dB under speech. Only use music the user owns or has licensed; do not pull copyrighted tracks.

## Step 6 - Export and verify

`export` re-encodes once with H.264 High, yuv420p, `-movflags +faststart`, 30 fps, AAC 128k, which every platform accepts. Do all filtering in a single pass where possible (chain subcommands only when a step needs the previous output) because each re-encode costs quality.

Before reporting done, verify with `probe` on the output: resolution 1080x1920, duration matches the plan, audio stream present, file size reasonable (under about 100 MB). Extract a frame at the hook and one mid-video and look at them.

## Step 7 - Pro layer: effects, motion graphics, sound design

This is what separates a clean edit from one that feels professionally cut. The more of these a video uses *in the right
places*, the better it feels, but every effect should answer a visual event (a hit, a reveal, a topic change), because
effects with no reason read as noise. Read before using:
- `references/catalog.md`: the full menu, auto-generated. 36 video effects, 29 motion-graphic templates, 57 transitions, 188 sounds,
  7 music beds, looks and caption styles, each with its parameters. Check it for the right tool instead of guessing names.
- `references/techniques.md`: pacing rules, which move for which moment, caption styling, structure of a high-retention short.
- `references/sound-design.md`: which sound for which moment, levels, landing sounds on the cut.

Tools (all in `scripts/`, each has `--help`; `list` prints every option):
| Script | Does |
|---|---|
| `pro_fx.py` | `punch-zoom`, `shake`, `speed-ramp`, `grade`, `transition`, `animated-subs`, `sfx-mix`, `sfx-list`, and `build` (full JSON plan) |
| `fx_pack.py` | 36 effects on a time window: `rgb-split`, `glitch`, `flash`, `freeze`, `reverse`, `stutter`, `light-leak`, `vhs`, `glow`, `tilt-shift`, `beat-pulse`, `pip`, `split-screen`, `ken-burns`, `stabilize`, ... |
| `mg.py` | 29 animated overlays rendered with alpha (`lower-third`, `title-card`, `counter`, `bar-chart`, `callout-circle`, `follow-button`, `confetti`, `speed-lines`, `logo-reveal`...) and `overlay` to composite them at a time |
| `make_sfx.py`, `make_sfx2.py` | regenerate the synthesised sound library and music beds |

Default approach for "make it pro / cinematic / viral":
1. Plan beats first: the hook, 3-6 emphasis moments, the reveal, the CTA. Put effects, overlays and SFX on those.
2. Write a JSON plan (copy `references/plan-example.json`; keys: `cut_silence`, `reframe`, `speed`, `effects`, `zooms`, `shakes`,
   `grade`, `overlays`, `subs`, `sfx`, `music`, `loudnorm`) and run `python scripts/pro_fx.py build plan.json`. Order is fixed;
   put length-changing effects (`freeze`, `reverse`, `stutter`) first in `effects`, and everything after them uses the new timeline.
3. Check frames at the hook, a zoom, an overlay, a caption, and the end with `reel_tools.py frame`. Fix and rebuild if text is cut,
   a zoom crops a face, or overlays collide with captions (captions sit at ~1335-1495 px on a 1920 canvas; keep overlays off that band).
4. Pass negative numbers as `--threshold=-35dB` (with `=`), or argparse treats them as flags.
5. Colour blends (`glow`, `toon`, `light-leak`) must run in RGB; the scripts handle it, but if you write your own `blend`, convert with
   `format=gbrp` first or the frame tints magenta.

Individual commands are fine when the user wants one thing. Arabic captions: one language per cue, no all-caps; use `animated-subs`
for word-by-word style. Overlay text supports Arabic too (it is shaped and ordered correctly).
Render time is real: a 5 s clip with several effects and overlays takes about a minute, a 60 s reel several minutes. Tell the user, and
work on a short test clip first if the plan is long.

## Still image to motion graphic (no footage)

When the user sends only an image (logo, product, illustration) and wants an animation, build it with
`examples/image_to_motion.py` (pillow + numpy; needs a PNG with transparency for the best result), then finish with the
same pro layer:
1. `python examples/image_to_motion.py IMAGE silent.mp4 --lines "LINE ONE" "LINE TWO" --cta "FOLLOW FOR MORE"` renders
   5 s: ring burst, overshoot pop-in, impact flash, sparks, screen shake, idle vibration that revs on caption beats,
   word-by-word captions (last word is the yellow hero word), and a CTA pill.
2. Copy `examples/engine_motion_plan.json`, point `input` at the silent clip, and run `python scripts/pro_fx.py build`.
   The SFX times in that plan are synced to the beat constants at the top of `image_to_motion.py` (`LAND`, `REVS`,
   `PHRASES`, `CTA_AT`). If you retime the animation, move the cues with it.
3. Pick sounds that match the subject (the library has `engine_rev`, `engine_idle`, `engine_start` for motors; use
   `camera_shutter`, `ding`, `glitch_*` for other themes). Write captions in the user's language: keep captions short
   (2-3 words per line), since long words overflow the 1080 px width.
Reference outputs: `examples/engine_motion_5s.mp4` (base animation + SFX) and `examples/engine_pro_demo_5s.mp4` (same animation with RGB split, glitch, lens distortion, light leak, lower third, speed lines, hearts, extra SFX and a music bed; built by `examples/engine_pro_plan.json`).


## Deliverable

Tell the user, briefly: where the file is, duration, what was cut or changed, and any decision they may want to revisit (e.g. "I used blur background because the speaker was off-centre"). Offer one or two follow-ups, such as a different crop, a version for another platform, or captions in the other language. Do not paste the whole ffmpeg command history.

## Other tools in this environment

If connectors are available, use them where they beat ffmpeg, and fall back to ffmpeg otherwise:
- Adobe tools (`video_resize`, `video_create_quick_cut`, `media_enhance_speech`) for resizing and cleaning noisy speech. Call `adobe_mandatory_init` first.
- ElevenLabs for voice-over, speech enhancement and transcription.
- vidIQ for titles, thumbnails, hooks and posting advice once the edit is done.

## Script reference

`python scripts/reel_tools.py <command> --help` for all options.

| Command | Purpose |
|---|---|
| `probe IN` | Print duration, size, fps, audio info |
| `cut-silence IN OUT` | Remove silent stretches (`--threshold -35dB --min-silence 0.4 --pad 0.12`) |
| `trim IN OUT --start S --end E` | Keep one range |
| `reframe IN OUT --mode crop\|blur\|fit` | Convert to 1080x1920 |
| `subs IN SRT OUT --lang ar\|en` | Burn in subtitles |
| `loudnorm IN OUT` | Normalise loudness |
| `mix-music IN MUSIC OUT` | Add ducked background music |
| `frame IN OUT.jpg --at S` | Extract a still to inspect |
| `export IN OUT` | Final platform-safe encode |

Pro layer scripts (`pro_fx.py`, `fx_pack.py`, `mg.py`, `make_sfx*.py`, `make_catalog.py`) are described in Step 7; the catalog lists every option.

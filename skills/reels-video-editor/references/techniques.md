# Pro editing techniques for Reels / Shorts / TikTok

Read this when planning an edit beyond basic trimming. Each technique says **what it does, when to use it,
and the command that does it**. Researched from current editor guides (sources at the bottom); numbers are
starting points, so trust your eyes over the digits.

## The pacing rule that underlies everything
Short-form viewers decide in ~2 s and most watch muted. Give the eye something new every **2-5 s** (cut, punch-in,
B-roll, graphic, caption change) and a bigger "pattern interrupt" every **5-10 s**. Never hold an identical frame
longer than ~5 s on talking-head footage. Static = swipe.

## Camera / frame moves

| Technique | What / when | Command |
|---|---|---|
| **Punch-in (emphasis zoom)** | Quick eased push 100% to 115-130% on a key word, joke, or number, held ~1-1.5 s, then released. Hides jump cuts and re-frames a static talking head. Alternate wide and tight so it feels like two cameras. | `pro_fx.py punch-zoom IN OUT --at 2.0:3.3:1.22 --at 6.5:7.6:1.3` |
| **Slow push-in** | Long drift 100% to 110-120% over 3-6 s on emotional or storytelling beats. | `punch-zoom ... --at 4:10:1.12` (long window) |
| **Impact shake** | 0.3-0.5 s decaying shake on a hit/drop/reveal. Pair with `impact_hit` or `boom_sub`. Use sparingly: 1-3 per video. | `pro_fx.py shake IN OUT --at 6.0:0.35:28` |
| **Speed ramp** | Slow to 0.3-0.5x for a beat (reaction, product reveal, action peak), or 2-3x to skip boring travel. Land the cut on the fast to slow switch with a whoosh. | `pro_fx.py speed-ramp IN OUT --seg 5:6:0.4` |
| **Whip pan / zoom transition** | Fast motion blur between two shots; match direction (pan right out, pan right in). In the tool: slide/zoom xfade. | `pro_fx.py transition OUT a.mp4 b.mp4 --kind zoomin,slideleft --dur 0.35` |

## Cuts that feel professional
- **Cut on action**: cut mid-movement (mid-reach, mid-turn), because motion masks the edit.
- **J-cut / L-cut**: let the next clip's audio start before its picture (J) or the previous audio linger (L). Hides
  edits in interviews and tutorials. Do it in the timeline by offsetting audio; for this toolset, apply the SFX/voice
  offset by starting audio 0.15-0.3 s early with `sfx-mix`/`trim`.
- **Match cut / smash cut**: cut between two shapes or movements that match, or hard-cut from silence to loud.
- **B-roll cutaways (2-5 s each)**: show what is being said (hands, product, location). Covers jump cuts, resets attention.
- **Jump cuts** are a feature in short-form; keep each beat tight and remove breaths/"umm" with `reel_tools.py cut-silence`.

## Transitions: pick on purpose
Hard cut is the default and usually best. Use a styled transition only on a **topic change**, never between
every clip. Good short-form set: `zoomin`, `slideleft/slideright` (match motion), `fadeblack` (time jump),
`fadewhite` (flash/dream), `pixelize`/`radial`/`hblur` (tech, hype), `circleopen` (reveal). Duration 0.25-0.5 s.
Always add a whoosh whose peak lands on the cut (see sound-design.md).

## Colour, look, finish
- **Grade** gives the "bought-it" look: `pro_fx.py grade IN OUT --look cinematic|warm|punchy|moody|clean|bw`.
  Cinematic = teal-leaning shadows + warm highlights + soft S-curve. Match the same look across all clips.
- **Vignette** (subtle) pulls the eye to centre; **film grain** (0.2-0.4) adds texture and masks compression banding.
  Both are subtle: if you notice them, it is too much.
- Do colour LAST on visuals but BEFORE burning captions, so captions stay pure white/yellow.

## Captions (they are the hook for muted viewers)
- Word-by-word, 1-3 words on screen, active word highlighted, tiny scale "pop" on each phrase.
- Heavy condensed sans in ALL CAPS for English (Anton / Montserrat Black / Bebas Neue), thick black stroke, white
  base text, yellow (~#FFD933) highlight. Roughly 10-15% of frame height, lower-middle of the frame (clear of the
  platform UI), not the very bottom.
- Arabic: no all-caps and no letter-spacing (it breaks joining). Use a bold Arabic-capable sans, keep the
  highlight colour, and keep one language per cue (mixed Arabic/English in one cue can reorder words).
- Command: `pro_fx.py animated-subs IN captions.srt OUT --lang ar --style hormozi --words 3`
  Styles: `hormozi` (white + yellow), `green`, `neon` (cyan), `clean` (white, smaller, no pop).
- Highlight timing follows word length inside each cue (no word-level timestamps needed). If you do have exact
  word timings (from a transcription tool), split the cues so each is 1-3 words for perfect sync.

## Structure of a high-retention short
1. **0-2 s hook**: strongest line/visual first. Add a riser or a hit and a punch-in. Hook text on screen.
2. **Body**: a new visual beat every 2-5 s; punch-ins on emphasis words; B-roll on every claim.
3. **Payoff + CTA**: land the answer, end on a clear line; end so it loops cleanly if possible.
4. Keep it as short as the idea allows; cut anything that does not earn its second.

## Recipe: "pro polish" on a talking-head reel
1. `reel_tools.py cut-silence` (tight pacing), `reframe --mode crop` (or `blur` for wide/screen content).
2. Transcribe the CUT video, then write `captions.srt` (1-3 s cues, one language per cue).
3. Put punch-ins on 3-6 emphasis moments, speed ramp on one beat if there is a reveal, shake on the biggest hit.
4. Grade (`cinematic` or `punchy`), SFX (whoosh on cuts, hit on punch-ins/reveals, pop on key words, riser into the hook).
5. Music at about -24 dB under speech (`music` in the plan), loudnorm to -14 LUFS, export.
   One-shot: write a JSON plan (see `plan-example.json`) and run `pro_fx.py build plan.json`.
   Remember: times in the plan after `speed` refer to the post-speed timeline.

## Sources
- [Insta360: film transitions](https://www.insta360.com/blog/tips/how-to-create-film-transitions.html), [Pond5: creative editing techniques](https://blog.pond5.com/11099-13-creative-editing-techniques-every-video-editor-should-know/), [Nikon: 10 tricks to add pace and energy](https://www.nikon.co.uk/en_GB/learn-and-explore/magazine/tips-and-tricks/cut-to-the-chase-10-tricks-to-add-pace-and-energy-to-your-edits), [Inside Editors: professional transitions](https://insideeditors.com/video-editing-transitions/), [AICut: transitions for viral shorts](https://www.aicut.pro/blog/cool-video-transitions)
- [Wikipedia: cutting on action](https://en.wikipedia.org/wiki/Cutting_on_action), [Captions.ai: using B-roll](https://captions.ai/blog/practical-guide-b-roll-video), [Virlo: 11 tips to edit like a pro](https://virlo.ai/blog/how-to-edit-videos-like-a-pro)
- [Ascynd: Hormozi caption specs](https://ascynd.io/en/blog/hormozi-captions), [Animate Captions: karaoke captions](https://animatecaptions.com/karaoke-captions), [Karadeo: Hormozi captions](https://karadeo.com/resources/how-to-make-alex-hormozi-captions)
- [OpusClip: auto zoom / punch-in tools](https://www.opus.pro/blog/best-auto-zoom-in-tools), [Frame.io: how a pro colorist uses film grain](https://blog.frame.io/2023/08/14/how-a-pro-colorist-uses-film-grain/), [Adobe: vignette and grain in video](https://helpx.adobe.com/lightroom/mobile/edit-videos/add-vignette-and-grain-effects-to-videos.html)

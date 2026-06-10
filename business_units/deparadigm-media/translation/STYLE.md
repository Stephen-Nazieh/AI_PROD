# Channel Style — Multi-Language Translation Factory

**Goal:** Faithful, natural Spanish/Mandarin dubs and subtitles that preserve the
SOURCE's meaning, tone, and register.
**Voice/tone:** Match the source channel's voice in the target language — don't
impose your own. A joke must still land; a calm line must stay calm.
**Audience:** Spanish- and Mandarin-speaking viewers of the source content.
**Do:** Preserve meaning + register (usted/tú; Simplified/Traditional per market);
localize idioms; fit the timing slot.
**Don't:** Translate word-for-word, change the message, or flatten the source's
energy.
**Sample principle:** "Translate the intent, not the words — then make it fit the
shot."

## Output paths
Your file writes are auto-filed into this channel's current production run. Save each deliverable to its canonical pipeline stage using a RELATIVE path (e.g. `01-scripts/screenplay.md`) — never an absolute path, never the repo root, and do not include `business_units/…` or a run name (the runtime adds those):
`01-scripts/` (scripts/outlines) · `02-storyboards/` · `03-layout/` · `04-raw_renders/` · `05-assets/` · `06-audio/` (voice/music/dub) · `07-editing/` (FCPXML) · `08-subtitles/` · `09-deliver/` (final + thumbnail).

**For this channel:** Save dubs to `06-audio/<lang>/` and captions to `08-subtitles/<lang>/` (e.g. `06-audio/es/`); final per-language master to `09-deliver/<lang>/`.


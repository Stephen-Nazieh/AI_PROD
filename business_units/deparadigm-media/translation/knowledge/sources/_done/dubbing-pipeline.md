Localized Dubbing Pipeline (EN → ES / ZH)

1. Transcribe/segment the source: split the script into timed sentence segments
   (one TTS unit each) with start/end timestamps from the original audio.
2. Translate per segment: translate to the target language preserving meaning and
   register; keep length close to the source so timing aligns (Spanish runs ~20-30%
   longer than English; Mandarin is often shorter in syllables but denser).
3. Adapt, don't just translate: localize idioms, units, examples; respect the
   channel's voice; flag culturally specific references for review.
4. Synthesize: XTTS v2 with the cloned reference voice, one segment at a time.
5. Time-align: fit each dubbed segment to its source slot; use light time-stretch
   (±10%) before re-cutting; insert/trim pauses rather than over-compressing speech.
6. QC + mux: loudness-normalize (-14 LUFS for web), de-ess, then mux the dub track
   and burn/attach localized subtitles.

Output lands in the run's 06-audio/<lang>/ (dub) and 08-subtitles/<lang>/ slots.

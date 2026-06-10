---
title: dubbing-pipeline
date: 2026-06-10
tags:
  - ingested
source: dubbing-pipeline.md
---
# Localized Dubbing Pipeline (EN → ES / ZH)

## 1. Transcribe/Segment the Source
- Split the script into timed sentence segments (one TTS unit each) with start/end timestamps from the original audio.

## 2. Translate per Segment
- Translate each segment to the target language while preserving meaning and register. Keep the length close to the source to ensure timing aligns. Note that Spanish runs ~20-30% longer than English, and Mandarin is often shorter in syllables but denser.

## 3. Adapt, Don't Just Translate
- Localize idioms, units, and examples. Respect the channel's voice and flag culturally specific references for review.

## 4. Synthesize
- Use XTTS v2 with the cloned reference voice, one segment at a time.

## 5. Time-align
- Fit each dubbed segment to its source slot. Use light time-stretch (±10%) before re-cutting. Insert or trim pauses rather than over-compressing speech.

## 6. QC + mux
- Loudness-normalize (-14 LUFS for web), de-ess, then mux the dub track and burn/attach localized subtitles.

The output will be placed in the run's `06-audio/<lang>/` (dub) and `08-subtitles/<lang>/` slots.<|im_end|>

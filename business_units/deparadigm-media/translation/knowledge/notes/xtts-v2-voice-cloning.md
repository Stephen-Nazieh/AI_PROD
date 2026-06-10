---
title: xtts-v2-voice-cloning
date: 2026-06-10
tags:
  - ingested
source: xtts-v2-voice-cloning.md
---
# XTTS v2 — Voice Cloning for Dubbing

XTTS v2 (Coqui) is a multilingual TTS model that clones a voice from a short reference clip (6-30 seconds of clean speech) and synthesizes new speech in 17 languages, including English, Spanish, and Mandarin Chinese.

## Reference Audio
- Use 10-20 seconds of clean, single-speaker, noise-free speech at the target emotional register.
- Multiple short clips can improve stability.
- Avoid music or reverb in the reference.

## Cross-Lingual Cloning
- A reference recorded in English can drive Spanish or Mandarin output, preserving timbre — but prosody and accent shift toward the target language.
- For best results, match the reference language to the output when possible.

## Quality Knobs
- **Temperature (0.65-0.75)**: Trades stability for expressiveness.
- **Repetition Penalty**: Curbs stutters.
- **Length Penalty**: Tunes pacing.
- Always denoise the output (the studio's de-essing/anomaly pass) before muxing.

## Limits
- Long passages drift — synthesize per sentence/segment and concatenate.
- Numbers, acronyms, and code-switching need normalization before synthesis.<|im_end|>

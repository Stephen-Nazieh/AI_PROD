XTTS v2 — Voice Cloning for Dubbing

XTTS v2 (Coqui) is a multilingual TTS model that clones a voice from a short
reference clip (6-30s of clean speech) and synthesizes new speech in 17 languages,
including English, Spanish, and Mandarin Chinese.

Reference audio: use 10-20s of clean, single-speaker, noise-free speech at the
target emotional register. Multiple short clips can improve stability. Avoid music
or reverb in the reference.

Cross-lingual cloning: a reference recorded in English can drive Spanish or
Mandarin output, preserving timbre — but prosody and accent shift toward the target
language. For best results, match the reference language to the output when
possible.

Quality knobs: temperature (0.65-0.75) trades stability vs expressiveness;
repetition_penalty curbs stutters; length_penalty tunes pacing. Always denoise the
output (the studio's de-essing/anomaly pass) before muxing.

Limits: long passages drift — synthesize per sentence/segment and concatenate.
Numbers, acronyms, and code-switching need normalization before synthesis.

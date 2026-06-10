---
title: seamless-loops
date: 2026-06-10
tags:
  - ingested
source: seamless-loops.md
---
# Seamless Loops — Audio & Video for 10-Hour Ambience

## Audio

1. **Loop Requirements**:
   - The loop must be sample-accurate.
   - Render a base bed of N minutes whose end flows into its start.
   - Crossfade the tail into the head (equal-power, ~2-4 seconds) and trim to a zero-crossing to eliminate any clicks.
   - Verify by playing the loop boundary on repeat.
   - Keep the bed harmonically static (no resolving cadence) to ensure the seam is inaudible.

## Video

1. **Motion Clip**:
   - Produce a short motion clip (30 seconds to 3 minutes) that loops cleanly.
   - Match the first and last frame, or use a boomerang/ping-pong effect for organic motion (e.g., rain, fire, drifting particles).
   - Avoid hard cuts at the seam.

## 10-Hour Assembly

1. **Looping**:
   - Do not render 10 hours of unique content.
   - Use FFmpeg to loop a short, clean base:
     - For audio: Use the `-stream_loop` option.
     - For video: Use the `loop` filter.
   - Mux the looped content to the target duration.

2. **Encoding**:
   - Encode in H.264 with the yuv420p color space.
   - Use AAC audio.
   - Set a low but clean bitrate:
     - Video: ~2-4 Mbps for static scenes.
   - Add subtle long-period variation (e.g., slow LFO on filter/volume, gentle visual parallax) to make the content feel alive, not robotic.<|im_end|>

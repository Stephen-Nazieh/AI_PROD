Seamless Loops — Audio & Video for 10-Hour Ambience

Audio: a loop must be sample-accurate. Render a base bed of N minutes whose end
flows into its start. Crossfade the tail into the head (equal-power, ~2-4s) and
trim to a zero-crossing so there is no click. Verify by playing the loop boundary
on repeat. Keep the bed harmonically static (no resolving cadence) so the seam is
inaudible.

Video: produce a short motion clip (30s-3min) that loops cleanly — match first and
last frame, or use a boomerang/ping-pong for organic motion (rain, fire, drifting
particles). Avoid hard cuts at the seam.

10-hour assembly: do NOT render 10 hours of unique content. Loop a short, clean
base with FFmpeg: `-stream_loop` for audio and `loop` filter for video, then mux to
the target duration. Encode H.264 (yuv420p), AAC audio, and a low-but-clean bitrate
(video ~2-4 Mbps for static scenes) to keep the file manageable. Add subtle long-
period variation (slow LFO on filter/volume, gentle visual parallax) so it feels
alive, not robotic.

VTuber Production Pipeline (studio: 06_SPATIAL/vtuber_twin)

The studio drives an avatar via the spatial twin: MediaPipe Pose Landmarker (33
landmarks) maps body motion to a Blender armature, and ARKit/iFacialMocap streams
52 facial blend shapes over UDP to the IK viewport. Use this for performance
capture or procedural idle motion.

Episode flow:
1. Script with delivery beats (see sarcasm-writing): mark pauses, emphasis, and
   expression cues ([smirk], [deadpan], [eye-roll]) inline.
2. Voice: synthesize the character's cloned voice (XTTS v2) per line so prosody
   matches the written timing; keep one canonical reference voice for consistency.
3. Performance: either live-capture (MediaPipe + ARKit over UDP) or apply
   procedural idle + scripted expression keys; lip-sync the avatar to the voice
   track (visemes from the audio).
4. Render in Blender; composite the avatar over the scene/background.
5. Edit to the comedic timing — sarcasm dies if the cut is late. Hold on the
   reaction beat.
6. Deliver: master + thumbnail (the unimpressed face is the brand). Outputs land in
   the run's 01-scripts … 09-deliver tree.

Consistency rules: same model, same voice, same resting expression across episodes.
Heavy 3D writes go to the external RAID, not internal disk.

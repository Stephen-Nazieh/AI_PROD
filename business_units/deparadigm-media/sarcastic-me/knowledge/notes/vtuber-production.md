---
title: vtuber-production
date: 2026-06-10
tags:
  - ingested
source: vtuber-production.md
---
# VTuber Production Pipeline (Studio: 06_SPATIAL/vtuber_twin)

## Overview
The studio utilizes the spatial twin for VTuber production. MediaPipe Pose Landmarker (33 landmarks) maps body motion to a Blender armature, while ARKit/iFacialMocap streams 52 facial blend shapes over UDP to the IK viewport. This setup is used for performance capture or procedural idle motion.

## Episode Flow

1. **Scripting**:
   - Write the script with delivery beats, including pauses, emphasis, and expression cues (e.g., [smirk], [deadpan], [eye-roll]) inline.

2. **Voice Synthesis**:
   - Synthesize the character's cloned voice (XTTS v2) per line to match the written timing. Maintain one canonical reference voice for consistency.

3. **Performance**:
   - Capture performance either live (using MediaPipe + ARKit over UDP) or apply procedural idle motion with scripted expression keys. Lip-sync the avatar to the voice track using visemes from the audio.

4. **Rendering**:
   - Render the avatar in Blender and composite it over the scene/background.

5. **Editing**:
   - Edit to comedic timing, ensuring sarcasm is maintained. Hold on the reaction beat.

6. **Delivery**:
   - Master the video and create a thumbnail (the unimpressed face is the brand). Outputs are stored in the run's 01-scripts … 09-deliver tree.

## Consistency Rules
- Use the same model, voice, and resting expression across episodes.
- Heavy 3D writes should be stored on the external RAID, not the internal disk.<|im_end|>

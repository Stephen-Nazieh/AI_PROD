"""Blender proof: a rigged VRM character that TALKS (audio-driven lip-sync) and
MOVES (head/torso motion + blinks), rendered to a frame sequence.
Run via the .app binary (NOT the /usr/local/bin symlink — breaks bundled Python):
  /Applications/Blender.app/Contents/MacOS/Blender -b --python bl_talking_proof.py -- <vrm.glb> <vo.wav> <out_frames_dir>
VRM viseme morph indices (this avatar): A=39 I=40 U=41 E=42 O=43 blink=13.
"""
import bpy, sys, wave, math
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
VRM, WAV, OUTDIR = argv[0], argv[1], argv[2]
FPS = 24
A_KEY, BLINK_KEY = "target_39", "target_13"

# ---- audio loudness envelope (0..1 per frame) ----
with wave.open(WAV, "rb") as w:
    sr, ch, sw, nfr = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    raw = w.readframes(nfr)
dt = {1: np.int8, 2: np.int16, 4: np.int32}.get(sw, np.int16)
a = np.frombuffer(raw, dtype=dt).astype(np.float32)
if ch > 1:
    a = a.reshape(-1, ch).mean(axis=1)
a /= (np.abs(a).max() + 1e-9)
dur = nfr / sr
total_frames = max(1, math.ceil(dur * FPS))
env = []
for f in range(total_frames):
    i0, i1 = int(f / FPS * sr), int((f + 1) / FPS * sr)
    seg = a[i0:i1] if i1 > i0 else a[i0:i0 + 1]
    env.append(min(1.0, float(np.sqrt(np.mean(seg ** 2))) * 3.2) if seg.size else 0.0)

# ---- scene ----
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=VRM)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
face = next(o for o in bpy.data.objects if o.type == 'MESH' and o.data.shape_keys
            and len(o.data.shape_keys.key_blocks) > 40)
kb = face.data.shape_keys.key_blocks

# ---- lip-sync + blink keyframes ----
def blink_val(f):
    # quick blink every ~2s (3-frame close)
    return 1.0 if (f % (FPS * 2)) in (0, 1, 2) else 0.0

for f in range(total_frames):
    kb[A_KEY].value = round(0.08 + 0.85 * env[f], 3)   # mouth open with loudness
    kb[A_KEY].keyframe_insert("value", frame=f + 1)
    if BLINK_KEY in kb:
        kb[BLINK_KEY].value = blink_val(f)
        kb[BLINK_KEY].keyframe_insert("value", frame=f + 1)

# ---- head/torso motion (subtle "alive" movement) ----
def anim_bone(name, axis_amps):
    if name not in arm.pose.bones:
        return
    pb = arm.pose.bones[name]; pb.rotation_mode = 'XYZ'
    for f in range(total_frames):
        t = f / FPS
        e = [amp * math.sin(2 * math.pi * freq * t + ph) for (amp, freq, ph) in axis_amps]
        pb.rotation_euler = e
        pb.keyframe_insert("rotation_euler", frame=f + 1)

anim_bone("J_Bip_C_Head",  [(0.05, 0.5, 0), (0.0, 0, 0), (0.06, 0.33, 1.1)])   # nod + turn
anim_bone("J_Bip_C_Chest", [(0.025, 0.4, 0), (0.0, 0, 0), (0.02, 0.27, 0.5)])  # breathing sway
anim_bone("J_Bip_C_Spine", [(0.015, 0.4, 0.3), (0.0, 0, 0), (0.0, 0, 0)])

# ---- medium close-up camera (head + shoulders), character faces +Y ----
head = arm.matrix_world @ arm.pose.bones["J_Bip_C_Head"].head
neck = arm.matrix_world @ arm.pose.bones["J_Bip_C_Neck"].head
target = (head + neck) / 2
cam_d = bpy.data.cameras.new("Cam"); cam = bpy.data.objects.new("Cam", cam_d)
bpy.context.scene.collection.objects.link(cam)
cam_d.lens = 70
cam.location = (target.x, target.y + 0.85, target.z + 0.02)
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

# ---- lighting (key + fill) ----
def light(name, kind, loc, rot, energy):
    l = bpy.data.lights.new(name, kind); lo = bpy.data.objects.new(name, l)
    bpy.context.scene.collection.objects.link(lo); lo.location = loc; lo.rotation_euler = rot
    l.energy = energy
    if kind == 'AREA':
        l.size = 2.0
key = light("Key", 'AREA', (1.2, 1.5, target.z + 0.6), (1.0, 0.3, 2.4), 220)
fill = light("Fill", 'AREA', (-1.4, 1.2, target.z + 0.3), (1.1, -0.3, -2.0), 80)

w = bpy.data.worlds.new("W"); bpy.context.scene.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.09, 0.11, 0.15, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.5

# ---- render settings ----
sc = bpy.context.scene
for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'BLENDER_WORKBENCH'):
    try:
        sc.render.engine = eng; break
    except Exception:
        continue
sc.render.resolution_x = sc.render.resolution_y = 768
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, total_frames
sc.render.image_settings.file_format = 'PNG'
sc.render.filepath = OUTDIR.rstrip("/") + "/f_"
print(f"PROOF rendering {total_frames} frames @ {FPS}fps, engine={sc.render.engine}")
bpy.ops.render.render(animation=True)
print("PROOF_RENDER_DONE", total_frames)

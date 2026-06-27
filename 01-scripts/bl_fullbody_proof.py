"""Blender proof #2: full-body talking + GESTURING 3D character.
Arms-down base (UpperArm local-Z ±1.15, found empirically) + a gesture track on the
right arm, plus lip-sync / head-torso motion / blinks. Wider upper-body shot.
Run via the .app binary. Args: <vrm.glb> <vo.wav> <out_frames_dir>
"""
import bpy, sys, wave, math, mathutils
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
VRM, WAV, OUTDIR = argv[0], argv[1], argv[2]
FPS = 24
A_KEY, BLINK_KEY = "target_39", "target_13"

# audio envelope
with wave.open(WAV, "rb") as w:
    sr, ch, sw, nfr = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    raw = w.readframes(nfr)
dt = {1: np.int8, 2: np.int16, 4: np.int32}.get(sw, np.int16)
a = np.frombuffer(raw, dtype=dt).astype(np.float32)
if ch > 1:
    a = a.reshape(-1, ch).mean(axis=1)
a /= (np.abs(a).max() + 1e-9)
dur = nfr / sr
N = max(1, math.ceil(dur * FPS))
env = []
for f in range(N):
    i0, i1 = int(f / FPS * sr), int((f + 1) / FPS * sr)
    seg = a[i0:i1] if i1 > i0 else a[i0:i0 + 1]
    env.append(min(1.0, float(np.sqrt(np.mean(seg ** 2))) * 3.2) if seg.size else 0.0)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=VRM)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
face = next(o for o in bpy.data.objects if o.type == 'MESH' and o.data.shape_keys
            and len(o.data.shape_keys.key_blocks) > 40)
kb = face.data.shape_keys.key_blocks
for pb in arm.pose.bones:
    pb.rotation_mode = 'XYZ'

# lip-sync + blink
def blink(f):
    return 1.0 if (f % (FPS * 2)) in (0, 1, 2) else 0.0
for f in range(N):
    kb[A_KEY].value = round(0.08 + 0.85 * env[f], 3); kb[A_KEY].keyframe_insert("value", frame=f + 1)
    if BLINK_KEY in kb:
        kb[BLINK_KEY].value = blink(f); kb[BLINK_KEY].keyframe_insert("value", frame=f + 1)

# idle head/torso
def idle(name, amps):
    pb = arm.pose.bones.get(name)
    if not pb: return
    for f in range(N):
        t = f / FPS
        pb.rotation_euler = [amp * math.sin(2*math.pi*fr*t + ph) for (amp, fr, ph) in amps]
        pb.keyframe_insert("rotation_euler", frame=f + 1)
idle("J_Bip_C_Head",  [(0.05,0.5,0),(0,0,0),(0.06,0.33,1.1)])
idle("J_Bip_C_Chest", [(0.025,0.4,0),(0,0,0),(0.02,0.27,0.5)])

# arms-down base + right-arm gesture track (keyframed poses across the clip)
def key_bone(name, frame, euler):
    pb = arm.pose.bones.get(name)
    if not pb: return
    pb.rotation_euler = euler; pb.keyframe_insert("rotation_euler", frame=frame)

# left arm: rest down + tiny sway
for f in (1, N):
    key_bone("J_Bip_L_UpperArm", f, (0, 0, 1.15))
    key_bone("J_Bip_L_LowerArm", f, (0, 0, 0.1))
# right arm: rest → raise/gesture → open → gesture2 → rest (Z drives swing, gesture reads)
g = [(1,        (0,0,-1.15), (0,0,0.0)),
     (int(N*0.25),(0,0,-0.78),(0,0,-0.55)),
     (int(N*0.45),(0,0,-0.92),(0,0,-0.28)),
     (int(N*0.68),(0,0,-0.72),(0,0,-0.66)),
     (int(N*0.88),(0,0,-0.95),(0,0,-0.30)),
     (N,         (0,0,-1.15), (0,0,0.0))]
for fr, ua, la in g:
    key_bone("J_Bip_R_UpperArm", fr, ua)
    key_bone("J_Bip_R_LowerArm", fr, la)

# wider upper-body camera (faces +Y)
hips = arm.matrix_world @ arm.pose.bones["J_Bip_C_Hips"].head
head = arm.matrix_world @ arm.pose.bones["J_Bip_C_Head"].head
ctr = hips.lerp(head, 0.62)
cam_d = bpy.data.cameras.new("Cam"); cam = bpy.data.objects.new("Cam", cam_d)
bpy.context.scene.collection.objects.link(cam); cam_d.lens = 55
cam.location = (ctr.x, ctr.y + 2.3, ctr.z + 0.05)
cam.rotation_euler = (ctr - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

def light(name, loc, rot, e, size=2.0):
    l = bpy.data.lights.new(name, 'AREA'); lo = bpy.data.objects.new(name, l)
    bpy.context.scene.collection.objects.link(lo); lo.location = loc; lo.rotation_euler = rot
    l.energy = e; l.size = size
light("Key", (1.4, 1.8, ctr.z + 0.8), (1.0, 0.3, 2.4), 300)
light("Fill", (-1.6, 1.4, ctr.z + 0.4), (1.1, -0.3, -2.0), 110)
w = bpy.data.worlds.new("W"); bpy.context.scene.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.09, 0.11, 0.15, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.5

sc = bpy.context.scene
for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'BLENDER_WORKBENCH'):
    try: sc.render.engine = eng; break
    except Exception: pass
sc.render.resolution_x = 720; sc.render.resolution_y = 900
sc.render.fps = FPS; sc.frame_start, sc.frame_end = 1, N
sc.render.filepath = OUTDIR.rstrip("/") + "/f_"
print(f"FULLBODY rendering {N} frames, engine={sc.render.engine}")
bpy.ops.render.render(animation=True)
print("FULLBODY_DONE", N)

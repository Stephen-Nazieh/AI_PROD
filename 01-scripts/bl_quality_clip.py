"""Blender quality clip: talking character at CYCLES quality (the hero-still look in
motion) — lip-sync + head/torso idle + blinks, 3-point lighting, DOF, AgX, Cycles GPU.
Run via the .app binary. Args: <vrm.glb> <vo.wav> <out_frames_dir>
"""
import bpy, sys, wave, math, mathutils
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
VRM, WAV, OUTDIR = argv[0], argv[1], argv[2]
FPS = 24; A_KEY, BLINK_KEY = "target_39", "target_13"

with wave.open(WAV, "rb") as w:
    sr, ch, sw, nfr = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    raw = w.readframes(nfr)
dt = {1: np.int8, 2: np.int16, 4: np.int32}.get(sw, np.int16)
a = np.frombuffer(raw, dtype=dt).astype(np.float32)
if ch > 1: a = a.reshape(-1, ch).mean(axis=1)
a /= (np.abs(a).max() + 1e-9)
N = max(1, math.ceil(nfr / sr * FPS))
env = []
for f in range(N):
    i0, i1 = int(f/FPS*sr), int((f+1)/FPS*sr)
    seg = a[i0:i1] if i1 > i0 else a[i0:i0+1]
    env.append(min(1.0, float(np.sqrt(np.mean(seg**2)))*3.2) if seg.size else 0.0)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=VRM)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
face = next(o for o in bpy.data.objects if o.type == 'MESH' and o.data.shape_keys and len(o.data.shape_keys.key_blocks) > 40)
kb = face.data.shape_keys.key_blocks
for side, s in (("L", 1), ("R", -1)):
    for bn, ang in ((f"J_Bip_{side}_UpperArm", 1.15*s), (f"J_Bip_{side}_LowerArm", 0.12*s)):
        b = arm.pose.bones.get(bn)
        if b: b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, ang)

def blink(f): return 1.0 if (f % (FPS*2)) in (0, 1, 2) else 0.0
for f in range(N):
    kb[A_KEY].value = round(0.08 + 0.85*env[f], 3); kb[A_KEY].keyframe_insert("value", frame=f+1)
    if BLINK_KEY in kb: kb[BLINK_KEY].value = blink(f); kb[BLINK_KEY].keyframe_insert("value", frame=f+1)
def idle(name, amps):
    pb = arm.pose.bones.get(name)
    if not pb: return
    pb.rotation_mode = 'XYZ'
    for f in range(N):
        t = f/FPS
        pb.rotation_euler = [amp*math.sin(2*math.pi*fr*t+ph) for (amp, fr, ph) in amps]
        pb.keyframe_insert("rotation_euler", frame=f+1)
idle("J_Bip_C_Head", [(0.05,0.5,0),(0,0,0),(0.06,0.33,1.1)])
idle("J_Bip_C_Chest", [(0.025,0.4,0),(0,0,0),(0.02,0.27,0.5)])

head = arm.matrix_world @ arm.pose.bones["J_Bip_C_Head"].head
neck = arm.matrix_world @ arm.pose.bones["J_Bip_C_Neck"].head
target = head.lerp(neck, 0.3)
# backdrop behind (-Y) + floor
bpy.ops.mesh.primitive_plane_add(size=20, location=(target.x, target.y-2.0, target.z)); back=bpy.context.object; back.rotation_euler=(math.radians(90),0,0)
bpy.ops.mesh.primitive_plane_add(size=20, location=(target.x, target.y-1.0, 0)); floor=bpy.context.object
mat=bpy.data.materials.new("BD"); mat.use_nodes=True
b=mat.node_tree.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value=(0.14,0.16,0.21,1); b.inputs["Roughness"].default_value=0.85
back.data.materials.append(mat); floor.data.materials.append(mat)

cam_d=bpy.data.cameras.new("Cam"); cam=bpy.data.objects.new("Cam",cam_d); bpy.context.scene.collection.objects.link(cam)
cam_d.lens=85; cam.location=(target.x+0.18, target.y+1.25, target.z+0.03)
cam.rotation_euler=(target-mathutils.Vector(cam.location)).to_track_quat('-Z','Y').to_euler()
cam_d.dof.use_dof=True; cam_d.dof.focus_distance=(target-mathutils.Vector(cam.location)).length; cam_d.dof.aperture_fstop=2.2
bpy.context.scene.camera=cam
def area(name, loc, e, sz, col):
    l=bpy.data.lights.new(name,'AREA'); o=bpy.data.objects.new(name,l); bpy.context.scene.collection.objects.link(o)
    o.location=loc; l.energy=e; l.size=sz; l.color=col
    o.rotation_euler=(target-mathutils.Vector(loc)).to_track_quat('-Z','Y').to_euler()
area("Key",(target.x+1.3,target.y+1.6,target.z+0.9),60,1.2,(1.0,0.96,0.9))
area("Fill",(target.x-1.5,target.y+1.3,target.z+0.3),18,2.2,(0.85,0.9,1.0))
area("Rim",(target.x-0.6,target.y-1.4,target.z+1.3),90,0.6,(0.9,0.95,1.0))
w=bpy.data.worlds.new("W"); bpy.context.scene.world=w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[0].default_value=(0.05,0.06,0.08,1); w.node_tree.nodes["Background"].inputs[1].default_value=0.4

# Eevee Next + good lighting/DOF/AgX = quality look, fast + stable for animation
# (Cycles crashes on Metal over long sequences; the flat early proof was bad LIGHTING, not Eevee).
sc=bpy.context.scene
sc.render.engine='BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in type(sc.render).bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
ee = sc.eevee
for attr, val in (("taa_render_samples", 64), ("use_raytracing", True),
                  ("use_shadows", True), ("use_gtao", True), ("use_bloom", False)):
    try: setattr(ee, attr, val)
    except Exception: pass
sc.view_settings.view_transform='AgX'
sc.render.resolution_x=864; sc.render.resolution_y=1080
sc.render.fps=FPS; sc.frame_start, sc.frame_end = 1, N
sc.render.filepath=OUTDIR.rstrip("/")+"/f_"
print(f"QUALITY CLIP {N} frames, Cycles {sc.cycles.device}")
bpy.ops.render.render(animation=True)
print("QUALITY_CLIP_DONE", N)

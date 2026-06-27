"""AP Stats hero shot: drop a rigged VRM character into the real Blender Classroom set,
frame a cinematic shot, light the face, lip-sync + idle motion to a VO line, render with
Eevee Next (Cycles crashes on Metal over long sequences). Run via the .app binary.

Args:  <classroom.blend> <vrm.glb> <vo.wav|NONE> <out>  [mode=still|anim]
  mode=still -> single PNG to <out> (validate composition before committing to a sequence)
  mode=anim  -> frame sequence f_#### into dir <out>, lip-synced to <vo.wav>
"""
import bpy, sys, math, wave, mathutils
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
ROOM, VRM, WAV, OUT = argv[0], argv[1], argv[2], argv[3]
MODE = argv[4] if len(argv) > 4 else "still"
FPS = 24

def find_key(kb, names, default_idx=None):
    """Locate a shape key across VRM naming schemes (VRoid 'Fcl_MTH_A' or glTF 'target_39')."""
    low = {k.name.lower(): k.name for k in kb}
    for want in names:
        for ln, real in low.items():
            if ln == want.lower() or ln.endswith(want.lower()):
                return real
    if default_idx is not None and default_idx < len(kb):
        return kb[default_idx].name
    return None

def add_anime_outline(objs, thickness=0.0028):
    """Classic inverted-hull ink outline: a flipped Solidify shell with a black material.
    Gives the VRoid character a drawn-anime silhouette instead of the plastic default look."""
    ink = bpy.data.materials.new("InkOutline"); ink.use_nodes = True
    nt = ink.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs[0].default_value = (0.012, 0.012, 0.016, 1.0)   # near-black ink
    nt.links.new(emit.outputs[0], out.inputs["Surface"])
    ink.use_backface_culling = True          # cull front faces of the shell -> only rim shows
    try: ink.use_transparent_shadow = False
    except Exception: pass
    for o in objs:
        if o.type != 'MESH':
            continue
        idx = len(o.data.materials)
        o.data.materials.append(ink)
        m = o.modifiers.new("Outline", 'SOLIDIFY')
        m.thickness = thickness
        m.offset = 1
        m.use_flip_normals = True
        m.material_offset = idx
        m.use_rim = False

def cel_boost(objs):
    """Nudge each body material toward a cel look: kill specular sheen, flatten roughness,
    keep base color. Cheap NPR approximation that reads far less plasticky in Eevee."""
    seen = set()
    for o in objs:
        if o.type != 'MESH':
            continue
        for mat in o.data.materials:
            if not mat or mat.name in seen or mat.name == "InkOutline":
                continue
            seen.add(mat.name)
            if not mat.use_nodes:
                continue
            bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if not bsdf:
                continue
            for sock, val in (("Specular IOR Level", 0.05), ("Roughness", 0.55),
                              ("Specular", 0.05), ("Sheen Weight", 0.0)):
                if sock in bsdf.inputs:
                    try: bsdf.inputs[sock].default_value = val
                    except Exception: pass

# ---- open the real classroom set (brings its geometry, textures, world, sun/window) ----
bpy.ops.wm.open_mainfile(filepath=ROOM)
sc = bpy.context.scene

# ---- import the character on top of the open set ----
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=VRM)
imported = [o for o in bpy.data.objects if o not in before]
arm = next(o for o in imported if o.type == 'ARMATURE')
face = next(o for o in imported if o.type == 'MESH' and o.data.shape_keys
            and len(o.data.shape_keys.key_blocks) > 40)
kb = face.data.shape_keys.key_blocks
A_KEY     = find_key(kb, ["Fcl_MTH_A", "MTH_A", "jawOpen", "aa", "mouth_open"], default_idx=39)
BLINK_KEY = find_key(kb, ["Fcl_EYE_Close", "EYE_Close", "blink", "blinkLeft"], default_idx=13)
SMILE_KEY = find_key(kb, ["Fcl_MTH_Fun", "Fcl_ALL_Fun", "MTH_Fun"])
print("VISEME keys -> A:", A_KEY, "BLINK:", BLINK_KEY, "SMILE:", SMILE_KEY)

# ---- NPR upgrade: cel-flatten the body materials + add an inked silhouette outline ----
cel_boost(imported)
add_anime_outline(imported)

# arms-down from T-pose (empirically: UpperArm local-Z +/-1.15, slight LowerArm bend)
for side, s in (("L", 1), ("R", -1)):
    for bn, ang in ((f"J_Bip_{side}_UpperArm", 1.15 * s), (f"J_Bip_{side}_LowerArm", 0.12 * s)):
        b = arm.pose.bones.get(bn)
        if b:
            b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, ang)

# ---- place the character: standing in the room, facing +Y. Camera goes on the +Y side,
# so keep STAND.y low enough that camera (≈look.y+2.4) stays INSIDE the room (y_max≈3.57). ----
STAND = Vector((0.3, 0.25, 0.0))      # forward in the front aisle -> no desk crossing her body
arm.location = STAND
bpy.context.view_layer.update()
# ground the feet on the floor (z=0) using FOOT BONES (reliable; mesh bound-boxes include
# stray geometry that overcorrects). VRoid soles sit ~0.07m below the foot-bone head.
foot_zs = [(arm.matrix_world @ arm.pose.bones[b].head).z
           for b in ("J_Bip_L_Foot", "J_Bip_R_Foot") if b in arm.pose.bones]
sole = (min(foot_zs) - 0.07) if foot_zs else 0.0
arm.location.z -= sole
bpy.context.view_layer.update()
print("GROUNDCHECK sole_was=", round(sole, 3))

head = arm.matrix_world @ arm.pose.bones["J_Bip_C_Head"].head
chest = arm.matrix_world @ arm.pose.bones["J_Bip_C_Chest"].head
look = head.lerp(chest, 0.22)          # aim near the face -> cinematic medium (chest-up)

# ---- cinematic camera: 55mm medium on the +Y side, eye level, desks blurred behind ----
cam_d = bpy.data.cameras.new("HeroCam"); cam = bpy.data.objects.new("HeroCam", cam_d)
sc.collection.objects.link(cam)
cam_d.lens = 55                                   # tighter medium; flatters the face
CAM0 = Vector((look.x + 0.12, look.y + 2.0, look.z + 0.04))   # eye level
print("CAMCHECK look=", [round(v,2) for v in look], "cam=", [round(v,2) for v in CAM0])
cam.location = CAM0
cam.rotation_euler = (look - CAM0).to_track_quat('-Z', 'Y').to_euler()
cam_d.dof.use_dof = True
cam_d.dof.focus_distance = (look - CAM0).length
cam_d.dof.aperture_fstop = 2.0                     # soft classroom behind, sharp character
sc.camera = cam

# ---- light the face: keep the room's sun/window, add a soft key + cool rim on the char ----
def area(name, loc, energy, size, color):
    l = bpy.data.lights.new(name, 'AREA'); o = bpy.data.objects.new(name, l)
    sc.collection.objects.link(o)
    o.location = Vector(loc); l.energy = energy; l.size = size; l.color = color
    o.rotation_euler = (look - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return o
area("CharKey",  (look.x + 1.0, look.y + 1.9, look.z + 0.55), 340, 1.2, (1.0, 0.94, 0.84))
area("CharFill", (look.x - 1.4, look.y + 1.5, look.z + 0.3),  95,  2.4, (0.82, 0.88, 1.0))
area("CharRim",  (look.x - 0.7, look.y - 1.3, look.z + 1.5), 180, 0.6, (0.85, 0.92, 1.0))

# ---- lip-sync + idle motion (anim mode only) ----
N = 1
if MODE == "anim" and WAV != "NONE":
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
        i0, i1 = int(f / FPS * sr), int((f + 1) / FPS * sr)
        seg = a[i0:i1] if i1 > i0 else a[i0:i0 + 1]
        env.append(min(1.0, float(np.sqrt(np.mean(seg ** 2))) * 3.2) if seg.size else 0.0)

    def blink(f): return 1.0 if (f % (FPS * 2)) in (0, 1, 2) else 0.0
    if SMILE_KEY:                                   # gentle resting expression (not deadpan)
        kb[SMILE_KEY].value = 0.18
    for f in range(N):
        if A_KEY:
            kb[A_KEY].value = round(0.06 + 0.85 * env[f], 3); kb[A_KEY].keyframe_insert("value", frame=f + 1)
        if BLINK_KEY:
            kb[BLINK_KEY].value = blink(f); kb[BLINK_KEY].keyframe_insert("value", frame=f + 1)

    def idle(name, amps):
        pb = arm.pose.bones.get(name)
        if not pb: return
        pb.rotation_mode = 'XYZ'
        for f in range(N):
            t = f / FPS
            pb.rotation_euler = [amp * math.sin(2 * math.pi * fr * t + ph) for (amp, fr, ph) in amps]
            pb.keyframe_insert("rotation_euler", frame=f + 1)
    idle("J_Bip_C_Head",  [(0.05, 0.5, 0), (0, 0, 0), (0.06, 0.33, 1.1)])
    idle("J_Bip_C_Chest", [(0.025, 0.4, 0), (0, 0, 0), (0.02, 0.27, 0.5)])

    # slow cinematic push-in over the clip
    cam.location = CAM0; cam.keyframe_insert("location", frame=1)
    push = CAM0 + (look - CAM0).normalized() * 0.35
    cam.location = push; cam.keyframe_insert("location", frame=N)

# ---- render: Eevee Next, AgX, 16:9 (fast + stable for sequences) ----
sc.render.engine = ('BLENDER_EEVEE_NEXT'
    if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in type(sc.render).bl_rna.properties['engine'].enum_items]
    else 'BLENDER_EEVEE')
ee = sc.eevee
for attr, val in (("taa_render_samples", 64), ("use_raytracing", True),
                  ("use_shadows", True), ("use_gtao", True)):
    try: setattr(ee, attr, val)
    except Exception: pass
sc.view_settings.view_transform = 'AgX'
sc.view_settings.exposure = 1.6           # lift the moody classroom to a readable level
sc.view_settings.look = 'AgX - Medium High Contrast'
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.resolution_percentage = 100
sc.render.fps = FPS

if MODE == "still":
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = OUT
    print("CLASSROOM STILL rendering (Eevee Next)...")
    bpy.ops.render.render(write_still=True)
    print("STILL_DONE", OUT)
else:
    sc.frame_start, sc.frame_end = 1, N
    sc.render.filepath = OUT.rstrip("/") + "/f_"
    print(f"CLASSROOM ANIM rendering {N} frames (Eevee Next)...")
    bpy.ops.render.render(animation=True)
    print("ANIM_DONE", N)

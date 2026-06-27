"""SIGNIFICANT S01E01 COLD OPEN — Harbor Analytics open-plan office, NIGHT.
Builds a moody single-practical-light office in-script (floor, the glowing "$92,000"
slide hero-prop, a warm desk lamp, dark windows, empty-desk silhouettes), drops in the
Maya VRM with an anime ink outline, and renders one SHOT of cinematic coverage.

Run via the .app binary.  Args:  <vrm.glb> <SHOT> <out> [vo.wav|NONE]
  SHOT in {SH01,SH02,SH03,SH04}   out=.png (still) for SH01/SH03 ambience, or a dir for anim
  If <out> ends in .png -> single still. Else -> frame sequence f_#### + lip-sync to vo.wav.
"""
import bpy, sys, os, math, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bl_anim_lib import apply_body_motion, relaxed_hands
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
VRM, SHOT, OUT = argv[0], argv[1], argv[2]
WAV = argv[3] if len(argv) > 3 else "NONE"
STILL = OUT.lower().endswith(".png")
FPS = 24

# ---------------------------------------------------------------- helpers ----
def find_key(kb, names, default_idx=None):
    low = {k.name.lower(): k.name for k in kb}
    for want in names:
        for ln, real in low.items():
            if ln == want.lower() or ln.endswith(want.lower()):
                return real
    if default_idx is not None and default_idx < len(kb):
        return kb[default_idx].name
    return None

def emit_mat(name, color, strength):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes): nt.nodes.remove(n)
    o = nt.nodes.new("ShaderNodeOutputMaterial"); e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*color, 1.0); e.inputs[1].default_value = strength
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    return m

def diffuse_mat(name, color, rough=0.5, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    if "Metallic" in b.inputs: b.inputs["Metallic"].default_value = metal
    return m

def text_obj(body, location, size, mat, align='CENTER'):
    cu = bpy.data.curves.new("font", 'FONT'); cu.body = body; cu.size = size
    cu.align_x = align; cu.align_y = 'CENTER'
    ob = bpy.data.objects.new("Txt", cu); bpy.context.scene.collection.objects.link(ob)
    ob.location = Vector(location)
    ob.rotation_euler = (math.radians(90), 0, math.radians(180))  # stand up, face +Y, reads correctly
    ob.data.materials.append(mat)
    return ob

def box(name, location, scale, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    o = bpy.context.object; o.name = name; o.scale = scale
    o.data.materials.append(mat)
    return o

def add_anime_outline(objs, thickness=0.0028):
    ink = emit_mat("InkOutline", (0.012, 0.012, 0.016), 1.0)
    ink.use_backface_culling = True
    for o in objs:
        if o.type != 'MESH': continue
        idx = len(o.data.materials); o.data.materials.append(ink)
        m = o.modifiers.new("Outline", 'SOLIDIFY')
        m.thickness = thickness; m.offset = 1; m.use_flip_normals = True
        m.material_offset = idx; m.use_rim = False

def cel_boost(objs):
    seen = set()
    for o in objs:
        if o.type != 'MESH': continue
        for mat in o.data.materials:
            if not mat or mat.name in seen or mat.name == "InkOutline": continue
            seen.add(mat.name)
            bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat.use_nodes else None
            if not bsdf: continue
            for sock, val in (("Specular IOR Level", 0.05), ("Roughness", 0.6), ("Sheen Weight", 0.0)):
                if sock in bsdf.inputs:
                    try: bsdf.inputs[sock].default_value = val
                    except Exception: pass

# ---------------------------------------------------------------- build set ----
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# near-black night world
w = bpy.data.worlds.new("Night"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.012, 0.014, 0.02, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.25

# floor (dark, faintly reflective to catch the lamp + slide)
floor = box("Floor", (0, 0, -0.02), (40, 40, 0.04), diffuse_mat("FloorMat", (0.03, 0.035, 0.045), rough=0.45))
# back wall behind the slide (pushed back so the slide blurs into a glow), side wall w/ windows
box("BackWall", (0, -4.4, 1.6), (12, 0.1, 6), diffuse_mat("WallMat", (0.04, 0.045, 0.06), rough=0.8))
box("SideWall", (4.2, -0.5, 1.6), (0.1, 9, 6), diffuse_mat("WallMat2", (0.04, 0.045, 0.06), rough=0.8))

# ---- HERO PROP: the glowing presentation slide behind Maya ----
slide_panel = box("Slide", (-0.1, -4.25, 1.55), (2.0, 0.06, 1.15), emit_mat("SlideBG", (0.05, 0.09, 0.16), 1.1))
text_obj("AVG USER INCOME", (-0.1, -4.10, 1.98), 0.15, emit_mat("SlideHdr", (0.7, 0.82, 1.0), 3.0))
text_obj("$92,000",        (-0.1, -4.10, 1.42), 0.52, emit_mat("SlideBig", (0.85, 0.95, 1.0), 6.0))

# dark windows on the side wall (glossy near-black -> reads as night glass)
box("Window", (4.13, -0.5, 1.7), (0.02, 5.5, 3.2), diffuse_mat("Glass", (0.02, 0.025, 0.04), rough=0.08, metal=0.7))

# empty desk silhouettes scattered in the room
deskmat = diffuse_mat("DeskMat", (0.05, 0.05, 0.06), rough=0.6)
for (dx, dy) in [(-2.6, -1.2), (-2.4, 0.6), (2.5, -1.4), (2.7, 0.5), (-0.2, -2.2)]:
    box("Desk", (dx, dy, 0.37), (1.1, 0.6, 0.74), deskmat)

# ---- warm practical desk lamp (the key); a small visible bulb + a warm face key area ----
lamp_bulb = box("Bulb", (1.5, 0.6, 0.92), (0.08, 0.08, 0.08), emit_mat("BulbMat", (1.0, 0.72, 0.42), 22.0))
lp = bpy.data.lights.new("Lamp", 'POINT'); lo = bpy.data.objects.new("Lamp", lp)
sc.collection.objects.link(lo); lo.location = (1.5, 0.6, 0.95)
lp.energy = 60; lp.color = (1.0, 0.7, 0.4); lp.shadow_soft_size = 0.15
# a soft warm key shaping the face from camera-right (motivated by the lamp)
wk = bpy.data.lights.new("WarmKey", 'AREA'); wko = bpy.data.objects.new("WarmKey", wk)
sc.collection.objects.link(wko); wko.location = (1.5, 1.6, 1.45)
wk.energy = 190; wk.size = 1.0; wk.color = (1.0, 0.82, 0.62)

# ---------------------------------------------------------------- character ----
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=VRM)
imported = [o for o in bpy.data.objects if o not in before]
arm = next(o for o in imported if o.type == 'ARMATURE')
face = next(o for o in imported if o.type == 'MESH' and o.data.shape_keys
            and len(o.data.shape_keys.key_blocks) > 40)
kb = face.data.shape_keys.key_blocks
A_KEY = find_key(kb, ["Fcl_MTH_A", "MTH_A", "jawOpen", "aa"], default_idx=39)
BLINK_KEY = find_key(kb, ["Fcl_EYE_Close", "EYE_Close", "blink"], default_idx=13)
SMILE_KEY = find_key(kb, ["Fcl_MTH_Fun", "Fcl_ALL_Fun"])

for side, s in (("L", 1), ("R", -1)):
    for bn, ang in ((f"J_Bip_{side}_UpperArm", 1.15 * s), (f"J_Bip_{side}_LowerArm", 0.12 * s)):
        b = arm.pose.bones.get(bn)
        if b: b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, ang)

arm.location = Vector((-0.1, -0.2, 0.0))     # standing in front of the slide, facing +Y
arm.rotation_euler = (0, 0, math.radians(-12))   # slight turn -> 3/4, more dynamic than dead-on
bpy.context.view_layer.update()
foot_zs = [(arm.matrix_world @ arm.pose.bones[b].head).z
           for b in ("J_Bip_L_Foot", "J_Bip_R_Foot") if b in arm.pose.bones]
arm.location.z -= (min(foot_zs) - 0.07) if foot_zs else 0.0
bpy.context.view_layer.update()
cel_boost(imported); add_anime_outline(imported); relaxed_hands(arm)

head = arm.matrix_world @ arm.pose.bones["J_Bip_C_Head"].head
chest = arm.matrix_world @ arm.pose.bones["J_Bip_C_Chest"].head

# soft cool fill (low) so shadows read as cool ambient, not pure black
fl = bpy.data.lights.new("Fill", 'AREA'); fo = bpy.data.objects.new("Fill", fl)
sc.collection.objects.link(fo); fo.location = (-1.4, 2.0, 1.6); fl.energy = 26; fl.size = 3.0
fl.color = (0.6, 0.72, 1.0)
ftgt = head.lerp(chest, 0.4)
fo.rotation_euler = (ftgt - Vector(fo.location)).to_track_quat('-Z', 'Y').to_euler()
wko.rotation_euler = (ftgt - Vector(wko.location)).to_track_quat('-Z', 'Y').to_euler()  # aim warm key

# ---------------------------------------------------------------- shot table ----
# look_bias: 0->chest .. 1->head ;  push: extra dolly toward subject over the clip
SHOTS = {
    "SH01": dict(loc=(1.7, 4.6, 1.45), lens=28, look=0.45, fstop=2.8, push=0.5,  tgt="char"),
    "SH02": dict(loc=(0.55, 2.15, 1.45), lens=58, look=0.80, fstop=2.0, push=0.30, tgt="char"),
    "SH03": dict(loc=(1.15, 0.7, 1.62), lens=85, look=0.0, fstop=2.2, push=0.45, tgt="slide"),
    "SH04": dict(loc=(0.5, 1.45, 1.52), lens=85, look=0.96, fstop=1.8, push=0.18, tgt="char"),
}
s = SHOTS[SHOT]
if s["tgt"] == "slide":
    look = Vector((-0.1, -4.10, 1.5))            # the $92,000 text
else:
    look = chest.lerp(head, s["look"])           # look=1 -> head, look=0 -> chest

cam_d = bpy.data.cameras.new("Cam"); cam = bpy.data.objects.new("Cam", cam_d)
sc.collection.objects.link(cam); sc.camera = cam
cam_d.lens = s["lens"]
CAM0 = Vector(s["loc"])
cam.location = CAM0
cam.rotation_euler = (look - CAM0).to_track_quat('-Z', 'Y').to_euler()
cam_d.dof.use_dof = True
cam_d.dof.focus_distance = (look - CAM0).length
cam_d.dof.aperture_fstop = s["fstop"]

# ---------------------------------------------------------------- animation ----
N = 1
if not STILL:
    if WAV != "NONE":
        with wave.open(WAV, "rb") as wv:
            sr, ch, sw, nfr = wv.getframerate(), wv.getnchannels(), wv.getsampwidth(), wv.getnframes()
            raw = wv.readframes(nfr)
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
        if SMILE_KEY: kb[SMILE_KEY].value = 0.12
        for f in range(N):
            if A_KEY: kb[A_KEY].value = round(0.05 + 0.85 * env[f], 3); kb[A_KEY].keyframe_insert("value", frame=f + 1)
            if BLINK_KEY:
                kb[BLINK_KEY].value = 1.0 if (f % (FPS * 2)) in (0, 1, 2) else 0.0
                kb[BLINK_KEY].keyframe_insert("value", frame=f + 1)
    else:
        N = int(FPS * 2.5)        # silent ambience beat (SH01 establish / SH03 insert)

    apply_body_motion(arm, N, talking=(WAV != "NONE"),
                      env=(env if WAV != "NONE" else None), phase=0.0)

    # slow cinematic push-in
    cam.location = CAM0; cam.keyframe_insert("location", frame=1)
    cam.location = CAM0 + (look - CAM0).normalized() * s["push"]; cam.keyframe_insert("location", frame=N)

# ---------------------------------------------------------------- render ----
sc.render.engine = ('BLENDER_EEVEE_NEXT'
    if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in type(sc.render).bl_rna.properties['engine'].enum_items]
    else 'BLENDER_EEVEE')
ee = sc.eevee
for attr, val in (("taa_render_samples", 64), ("use_raytracing", True), ("use_shadows", True), ("use_gtao", True)):
    try: setattr(ee, attr, val)
    except Exception: pass
sc.view_settings.view_transform = 'AgX'
sc.view_settings.exposure = 0.7
sc.view_settings.look = 'AgX - Medium High Contrast'
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.fps = FPS
print(f"OFFICE {SHOT} still={STILL} N={N} look={[round(v,2) for v in look]}")
if STILL:
    sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = OUT
    bpy.ops.render.render(write_still=True); print("STILL_DONE", OUT)
else:
    sc.frame_start, sc.frame_end = 1, N
    sc.render.filepath = OUT.rstrip("/") + "/f_"
    bpy.ops.render.render(animation=True); print("ANIM_DONE", SHOT, N)

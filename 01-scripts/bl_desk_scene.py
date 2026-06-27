"""SIGNIFICANT S01E01 — INT. MAYA'S DESK — CONTINUOUS.
Maya behind her workstation, a glowing monitor showing the raw income export with the
whale rows ($4.5M/$2.1M/$3.8M) in red. Monitor-lit, moody. Renders one SHOT.

Run via .app binary.  Args: <maya.glb> <SHOT> <out> [vo.wav|NONE]
  SHOT in {SH01 desk-medium, SH02 screen-insert, SH03 maya-tight}
"""
import bpy, sys, math, wave
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
VRM, SHOT, OUT = argv[0], argv[1], argv[2]
WAV = argv[3] if len(argv) > 3 else "NONE"
STILL = OUT.lower().endswith(".png")
FPS = 24

def find_key(kb, names, default_idx=None):
    low = {k.name.lower(): k.name for k in kb}
    for want in names:
        for ln, real in low.items():
            if ln == want.lower() or ln.endswith(want.lower()): return real
    if default_idx is not None and default_idx < len(kb): return kb[default_idx].name
    return None
def emit_mat(name, color, strength):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    for n in list(nt.nodes): nt.nodes.remove(n)
    o = nt.nodes.new("ShaderNodeOutputMaterial"); e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*color, 1.0); e.inputs[1].default_value = strength
    nt.links.new(e.outputs[0], o.inputs["Surface"]); return m
def diffuse_mat(name, color, rough=0.6, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs["Base Color"].default_value = (*color, 1.0); b.inputs["Roughness"].default_value = rough
    if "Metallic" in b.inputs: b.inputs["Metallic"].default_value = metal
    return m
def box(name, loc, scale, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o = bpy.context.object
    o.name = name; o.scale = scale; o.data.materials.append(mat); return o
def text_line(body, loc, size, mat, align='LEFT'):
    cu = bpy.data.curves.new("f", 'FONT'); cu.body = body; cu.size = size
    cu.align_x = align; cu.align_y = 'CENTER'
    ob = bpy.data.objects.new("T", cu); bpy.context.scene.collection.objects.link(ob)
    ob.location = Vector(loc); ob.rotation_euler = (math.radians(90), 0, math.radians(180))
    ob.data.materials.append(mat); return ob
def add_anime_outline(objs, thickness=0.0028):
    ink = emit_mat("Ink", (0.012, 0.012, 0.016), 1.0); ink.use_backface_culling = True
    for o in objs:
        if o.type != 'MESH': continue
        idx = len(o.data.materials); o.data.materials.append(ink)
        m = o.modifiers.new("Outline", 'SOLIDIFY'); m.thickness = thickness; m.offset = 1
        m.use_flip_normals = True; m.material_offset = idx; m.use_rim = False
def cel_boost(objs):
    seen = set()
    for o in objs:
        if o.type != 'MESH': continue
        for mat in o.data.materials:
            if not mat or mat.name in seen or mat.name == "Ink": continue
            seen.add(mat.name)
            bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat.use_nodes else None
            if not bsdf: continue
            for sock, val in (("Specular IOR Level", 0.05), ("Roughness", 0.6), ("Sheen Weight", 0.0)):
                if sock in bsdf.inputs:
                    try: bsdf.inputs[sock].default_value = val
                    except Exception: pass

# ---------------- build dim office workstation ----------------
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.024, 0.032, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.35
box("Floor", (0, 0, -0.02), (40, 40, 0.04), diffuse_mat("Fl", (0.04, 0.045, 0.05), rough=0.5))
box("BackWall", (0, -3.0, 1.6), (14, 0.1, 6), diffuse_mat("Wa", (0.05, 0.055, 0.07), rough=0.85))
# desk + a normal-sized monitor sitting on it, beside Maya (camera-left), facing +Y
box("Desk", (0.1, 0.55, 0.5), (2.6, 0.75, 1.0), diffuse_mat("Dk", (0.06, 0.06, 0.07), rough=0.5))
MON_X, MON_Y = 0.62, 0.18
box("MonBody", (MON_X, MON_Y, 1.26), (0.56, 0.06, 0.40), diffuse_mat("Mon", (0.02, 0.02, 0.025), rough=0.4))
box("MonStand", (MON_X, MON_Y + 0.05, 1.04), (0.08, 0.06, 0.18), diffuse_mat("St", (0.03, 0.03, 0.035), rough=0.4))
# screen bg faces +Y; TEXT sits slightly IN FRONT of it (higher y, toward camera) so it isn't occluded
screen = box("Screen", (MON_X, MON_Y + 0.035, 1.26), (0.50, 0.02, 0.34), emit_mat("ScrBG", (0.04, 0.07, 0.11), 1.0))
hdr = emit_mat("Hdr", (0.55, 0.7, 0.95), 2.4)
norm = emit_mat("Norm", (0.62, 0.8, 0.96), 2.8)
whale = emit_mat("Whale", (1.0, 0.32, 0.22), 4.5)
# CENTER-align (flip-immune; LEFT collides with the text 180° flip) at the monitor center
TY = MON_Y + 0.055           # in front of the screen bg
text_line("RAW  EXPORT  ·  8,100  USERS", (MON_X, TY, 1.41), 0.025, hdr, align='CENTER')
z = 1.36
for r in ["00412      $31,200", "00413      $40,800", "00414      $36,500", "00415      $28,900"]:
    text_line(r, (MON_X, TY, z), 0.030, norm, align='CENTER'); z -= 0.044
for r in ["07788   $4,500,000", "07789   $2,100,000", "07790   $3,800,000"]:
    text_line(r, (MON_X, TY, z), 0.031, whale, align='CENTER'); z -= 0.044

# ---------------- Maya ----------------
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=VRM)
imp = [o for o in bpy.data.objects if o not in before]
arm = next(o for o in imp if o.type == 'ARMATURE')
face = next(o for o in imp if o.type == 'MESH' and o.data.shape_keys and len(o.data.shape_keys.key_blocks) > 40)
kb = face.data.shape_keys.key_blocks
A_KEY = find_key(kb, ["Fcl_MTH_A", "MTH_A", "jawOpen", "aa"], default_idx=39)
BLINK_KEY = find_key(kb, ["Fcl_EYE_Close", "EYE_Close", "blink"], default_idx=13)
for side, s in (("L", 1), ("R", -1)):
    for bn, ang in ((f"J_Bip_{side}_UpperArm", 1.18 * s), (f"J_Bip_{side}_LowerArm", 0.2 * s)):
        b = arm.pose.bones.get(bn)
        if b: b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, ang)
arm.location = Vector((-0.5, -0.2, 0.0))   # camera-right of the monitor, facing +Y (camera)
bpy.context.view_layer.update()
foot_zs = [(arm.matrix_world @ arm.pose.bones[b].head).z for b in ("J_Bip_L_Foot", "J_Bip_R_Foot") if b in arm.pose.bones]
arm.location.z -= (min(foot_zs) - 0.07) if foot_zs else 0.0
bpy.context.view_layer.update()
cel_boost(imp); add_anime_outline(imp)
# reading head tilt (down toward screen) unless the tight reaction shot
READING_PITCH = 0.0 if SHOT == "SH03" else 0.16
hb = arm.pose.bones.get("J_Bip_C_Head")
if hb: hb.rotation_mode = 'XYZ'; hb.rotation_euler = (READING_PITCH, 0, 0)
bpy.context.view_layer.update()
head = arm.matrix_world @ arm.pose.bones["J_Bip_C_Head"].head
chest = arm.matrix_world @ arm.pose.bones["J_Bip_C_Chest"].head

# ---------------- lighting: monitor glow key + dim rim ----------------
def area(name, loc, e, sz, col, tgt):
    l = bpy.data.lights.new(name, 'AREA'); o = bpy.data.objects.new(name, l)
    sc.collection.objects.link(o); o.location = Vector(loc); l.energy = e; l.size = sz; l.color = col
    o.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler(); return o
ftgt = head.lerp(chest, 0.5)
area("Glow", (0.0, 0.9, 1.25), 120, 1.4, (0.5, 0.68, 1.0), ftgt)   # cool monitor wash on face
area("Rim",  (-1.1, -1.2, 1.7), 90, 0.7, (0.9, 0.85, 1.0), ftgt)
area("Amb",  (1.6, 2.2, 1.8), 22, 3.0, (0.7, 0.75, 0.9), ftgt)

# ---------------- shot table ----------------
SHOTS = {
    "SH01": dict(tgt="wide", off=(0.0, 2.7, 0.30), lens=40, look=0.6, fstop=2.8, push=0.28, spk=False),
    "SH02": dict(tgt="screen", off=(0.0, 1.22, -0.05), lens=46, look=0.0, fstop=3.2, push=0.20, spk=False),
    "SH03": dict(tgt="maya", off=(0.3, 1.65, 0.2),  lens=88, look=0.95, fstop=1.9, push=0.16, spk=True),
}
s = SHOTS[SHOT]
if s["tgt"] == "screen":
    look = Vector((MON_X, MON_Y + 0.05, 1.22)); base = look.copy()   # text vertical centre
elif s["tgt"] == "wide":
    mtgt = chest.lerp(head, s["look"])
    look = Vector(((mtgt.x + MON_X) * 0.5, mtgt.y, mtgt.z)); base = look.copy()   # frame Maya + monitor
else:
    look = chest.lerp(head, s["look"]); base = look.copy()
CAM0 = base + Vector(s["off"])
cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam); sc.camera = cam; cam_d.lens = s["lens"]
cam.location = CAM0; cam.rotation_euler = (look - CAM0).to_track_quat('-Z', 'Y').to_euler()
cam_d.dof.use_dof = True; cam_d.dof.focus_distance = (look - CAM0).length; cam_d.dof.aperture_fstop = s["fstop"]

# ---------------- animation ----------------
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
        N = max(1, math.ceil(nfr / sr * FPS)); env = []
        for f in range(N):
            i0, i1 = int(f / FPS * sr), int((f + 1) / FPS * sr)
            seg = a[i0:i1] if i1 > i0 else a[i0:i0 + 1]
            env.append(min(1.0, float(np.sqrt(np.mean(seg ** 2))) * 3.2) if seg.size else 0.0)
    else:
        N = int(FPS * 2.6)
    if s["spk"] and WAV != "NONE":
        for f in range(N):
            if A_KEY: kb[A_KEY].value = round(0.05 + 0.85 * env[f], 3); kb[A_KEY].keyframe_insert("value", frame=f + 1)
    for f in range(N):
        if BLINK_KEY:
            kb[BLINK_KEY].value = 1.0 if (f % (FPS * 2)) in (0, 1, 2) else 0.0
            kb[BLINK_KEY].keyframe_insert("value", frame=f + 1)
    if hb:
        for f in range(N):
            t = f / FPS
            hb.rotation_euler = (READING_PITCH + 0.03 * math.sin(2 * math.pi * 0.4 * t),
                                 0.04 * math.sin(2 * math.pi * 0.33 * t + 1.1), 0)
            hb.keyframe_insert("rotation_euler", frame=f + 1)
    cam.location = CAM0; cam.keyframe_insert("location", frame=1)
    cam.location = CAM0 + (look - CAM0).normalized() * s["push"]; cam.keyframe_insert("location", frame=N)

# ---------------- render ----------------
sc.render.engine = 'BLENDER_EEVEE'
ee = sc.eevee
for attr, val in (("taa_render_samples", 64), ("use_raytracing", True), ("use_shadows", True), ("use_gtao", True)):
    try: setattr(ee, attr, val)
    except Exception: pass
sc.view_settings.view_transform = 'AgX'; sc.view_settings.exposure = 0.5
sc.view_settings.look = 'AgX - Medium High Contrast'
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080; sc.render.fps = FPS
print(f"DESK {SHOT} still={STILL} N={N}")
if STILL:
    sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = OUT
    bpy.ops.render.render(write_still=True); print("STILL_DONE", OUT)
else:
    sc.frame_start, sc.frame_end = 1, N; sc.render.filepath = OUT.rstrip("/") + "/f_"
    bpy.ops.render.render(animation=True); print("ANIM_DONE", SHOT, N)

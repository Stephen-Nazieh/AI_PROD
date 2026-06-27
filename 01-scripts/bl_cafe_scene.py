"""SIGNIFICANT S01E01 ACT TWO — Drydock Café, DAY.
Two-character dialogue (Maya + Prof. Okafor). Warm daylight café; a high table with a
laptop + tea between them. Shot/reverse-shot with speaker-aware lip-sync. Okafor avatar
is a stylized stand-in (no 60s-professor VRM exists).

Run via .app binary.  Args: <maya.glb> <okafor.glb> <SHOT> <out> [vo.wav|NONE]
  SHOT in {SH01 two-shot, SH02 maya, SH03 okafor, SH04 maya, SH05 okafor, SH06 okafor}
"""
import bpy, sys, os, math, wave
import numpy as np
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bl_anim_lib import apply_body_motion, relaxed_hands

argv = sys.argv[sys.argv.index("--") + 1:]
MAYA_VRM, OK_VRM, SHOT, OUT = argv[0], argv[1], argv[2], argv[3]
WAV = argv[4] if len(argv) > 4 else "NONE"
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
def add_anime_outline(objs, thickness=0.0026):
    ink = emit_mat("Ink_" + objs[0].name, (0.012, 0.012, 0.016), 1.0); ink.use_backface_culling = True
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
            if not mat or mat.name in seen or mat.name.startswith("Ink_"): continue
            seen.add(mat.name)
            bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat.use_nodes else None
            if not bsdf: continue
            for sock, val in (("Specular IOR Level", 0.05), ("Roughness", 0.6), ("Sheen Weight", 0.0)):
                if sock in bsdf.inputs:
                    try: bsdf.inputs[sock].default_value = val
                    except Exception: pass
def place(vrm, location, rot_z_deg):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=vrm)
    imp = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in imp if o.type == 'ARMATURE')
    face = next(o for o in imp if o.type == 'MESH' and o.data.shape_keys and len(o.data.shape_keys.key_blocks) > 40)
    kb = face.data.shape_keys.key_blocks
    for side, s in (("L", 1), ("R", -1)):
        for bn, ang in ((f"J_Bip_{side}_UpperArm", 1.12 * s), (f"J_Bip_{side}_LowerArm", 0.22 * s)):
            b = arm.pose.bones.get(bn)
            if b: b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, ang)
    arm.location = Vector(location); arm.rotation_euler = (0, 0, math.radians(rot_z_deg))
    bpy.context.view_layer.update()
    fz = [(arm.matrix_world @ arm.pose.bones[b].head).z for b in ("J_Bip_L_Foot", "J_Bip_R_Foot") if b in arm.pose.bones]
    arm.location.z -= (min(fz) - 0.07) if fz else 0.0
    bpy.context.view_layer.update()
    cel_boost(imp); add_anime_outline(imp); relaxed_hands(arm)
    return dict(arm=arm, kb=kb,
                A=find_key(kb, ["Fcl_MTH_A", "MTH_A", "jawOpen", "aa"], default_idx=39),
                BLINK=find_key(kb, ["Fcl_EYE_Close", "EYE_Close", "blink"], default_idx=13),
                SMILE=find_key(kb, ["Fcl_MTH_Fun", "Fcl_ALL_Fun"]),
                head=lambda a=arm: a.matrix_world @ a.pose.bones["J_Bip_C_Head"].head)

# ---------------- build warm daytime café ----------------
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
w = bpy.data.worlds.new("Day"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.52, 0.5, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.75
box("Floor", (0, 0, -0.02), (40, 40, 0.04), diffuse_mat("Fl", (0.16, 0.11, 0.07), rough=0.45))
box("BackWall", (0, -2.7, 1.6), (14, 0.1, 6), diffuse_mat("Wa", (0.42, 0.34, 0.27), rough=0.9))
# bright warm window (camera-left) = the riverside daylight key
box("Window", (-4.3, 0.6, 1.8), (0.05, 3.4, 2.6), emit_mat("Sky", (1.0, 0.92, 0.78), 2.6))
box("Mullion", (-4.25, 0.6, 1.8), (0.06, 0.05, 2.6), diffuse_mat("Mul", (0.1, 0.08, 0.06), rough=0.6))
# high café table between them + props
box("Table", (0, 0.05, 0.92), (1.7, 1.05, 0.08), diffuse_mat("Tbl", (0.12, 0.08, 0.05), rough=0.35))
box("TableLeg", (0, 0.05, 0.46), (0.12, 0.12, 0.9), diffuse_mat("Leg", (0.05, 0.04, 0.03), rough=0.4))
# tea near Okafor
box("Cup", (0.5, 0.15, 1.00), (0.10, 0.10, 0.10), diffuse_mat("Cup", (0.85, 0.83, 0.78), rough=0.3))
# laptop near Maya (base + an emissive screen angled up)
box("LapBase", (-0.35, 0.18, 0.97), (0.36, 0.26, 0.03), diffuse_mat("Lap", (0.08, 0.08, 0.09), rough=0.4))
lid = box("LapLid", (-0.35, 0.02, 1.10), (0.36, 0.02, 0.24), emit_mat("Scr", (0.5, 0.62, 0.85), 1.4))
lid.rotation_euler = (math.radians(-18), 0, 0)

# ---------------- characters ----------------
maya = place(MAYA_VRM, (-0.7, 0.05, 0.0), -65)
okaf = place(OK_VRM,   (0.7, 0.05, 0.0),  65)
mhead, ohead = maya["head"](), okaf["head"]()
mid = (mhead + ohead) * 0.5

def area(name, loc, e, sz, col, tgt):
    l = bpy.data.lights.new(name, 'AREA'); o = bpy.data.objects.new(name, l)
    sc.collection.objects.link(o); o.location = Vector(loc); l.energy = e; l.size = sz; l.color = col
    o.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler(); return o
area("WinKey", (-3.4, 1.0, 2.0), 360, 2.8, (1.0, 0.9, 0.74), mid)   # warm daylight
area("Fill",   (2.8, 2.2, 1.7),  60, 3.0, (0.78, 0.84, 1.0), mid)
area("MayaKey", (mhead.x + 0.6, mhead.y + 1.6, mhead.z + 0.5), 80, 1.0, (1.0, 0.94, 0.84), mhead)
area("OkKey",   (ohead.x - 0.6, ohead.y + 1.6, ohead.z + 0.5), 80, 1.0, (1.0, 0.94, 0.84), ohead)

# ---------------- shot table (spk: 'maya' | 'okaf' | None) ----------------
SHOTS = {
    "SH01": dict(tgt="two",  off=(0.0, 2.95, 0.30), lens=34, fstop=4.0, push=0.28, spk=None),
    "SH02": dict(tgt="maya", off=(0.85, 1.95, 0.10), lens=72, fstop=2.2, push=0.18, spk="maya"),
    "SH03": dict(tgt="okaf", off=(-0.85, 1.95, 0.10), lens=72, fstop=2.2, push=0.18, spk="okaf"),
    "SH04": dict(tgt="maya", off=(0.85, 1.85, 0.10), lens=78, fstop=2.0, push=0.16, spk="maya"),
    "SH05": dict(tgt="okaf", off=(-0.85, 1.95, 0.10), lens=72, fstop=2.2, push=0.18, spk="okaf"),
    "SH06": dict(tgt="okaf", off=(-0.7, 1.75, 0.12), lens=80, fstop=2.0, push=0.16, spk="okaf"),
}
s = SHOTS[SHOT]
if s["tgt"] == "two":
    look = Vector((mid.x, mid.y, mid.z - 0.05)); base = look.copy()
else:
    look = (mhead if s["tgt"] == "maya" else ohead).copy(); base = look.copy()
CAM0 = base + Vector(s["off"])
cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam); sc.camera = cam; cam_d.lens = s["lens"]
cam.location = CAM0; cam.rotation_euler = (look - CAM0).to_track_quat('-Z', 'Y').to_euler()
cam_d.dof.use_dof = True; cam_d.dof.focus_distance = (look - CAM0).length; cam_d.dof.aperture_fstop = s["fstop"]

# ---------------- animation ----------------
def idle(arm, name, amps, N):
    pb = arm.pose.bones.get(name)
    if not pb: return
    pb.rotation_mode = 'XYZ'
    for f in range(N):
        t = f / FPS
        pb.rotation_euler = [amp * math.sin(2 * math.pi * fr * t + ph) for (amp, fr, ph) in amps]
        pb.keyframe_insert("rotation_euler", frame=f + 1)
def blink(h, N):
    if h["BLINK"]:
        for f in range(N):
            h["kb"][h["BLINK"]].value = 1.0 if (f % (FPS * 2)) in (0, 1, 2) else 0.0
            h["kb"][h["BLINK"]].keyframe_insert("value", frame=f + 1)

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
        N = int(FPS * 2.2)
    spk = {"maya": maya, "okaf": okaf}.get(s["spk"])
    for who in (maya, okaf):
        talking = who is spk and WAV != "NONE"
        if talking:
            if who["SMILE"]: who["kb"][who["SMILE"]].value = 0.08
            for f in range(N):
                if who["A"]:
                    who["kb"][who["A"]].value = round(0.05 + 0.85 * env[f], 3)
                    who["kb"][who["A"]].keyframe_insert("value", frame=f + 1)
        blink(who, N)
        apply_body_motion(who["arm"], N, talking=talking, env=(env if talking else None),
                          phase=(0.0 if who is maya else 1.6),
                          gesture=(1.0 if who is maya else 0.5))   # Okafor = composed anchor
    cam.location = CAM0; cam.keyframe_insert("location", frame=1)
    cam.location = CAM0 + (look - CAM0).normalized() * s["push"]; cam.keyframe_insert("location", frame=N)

# ---------------- render ----------------
sc.render.engine = 'BLENDER_EEVEE'
ee = sc.eevee
for attr, val in (("taa_render_samples", 64), ("use_raytracing", True), ("use_shadows", True), ("use_gtao", True)):
    try: setattr(ee, attr, val)
    except Exception: pass
sc.view_settings.view_transform = 'AgX'; sc.view_settings.exposure = 0.1
sc.view_settings.look = 'AgX - Medium High Contrast'
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080; sc.render.fps = FPS
print(f"CAFE {SHOT} still={STILL} spk={s['spk']} N={N}")
if STILL:
    sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = OUT
    bpy.ops.render.render(write_still=True); print("STILL_DONE", OUT)
else:
    sc.frame_start, sc.frame_end = 1, N; sc.render.filepath = OUT.rstrip("/") + "/f_"
    bpy.ops.render.render(animation=True); print("ANIM_DONE", SHOT, N)

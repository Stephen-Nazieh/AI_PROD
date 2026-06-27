"""QUALITY PASS — body-motion test bed. A clean studio medium of Maya, lip-synced, with
the new procedural body motion (breathing, weight-shift, speech-driven arm gestures,
relaxed hands). Iterate here, then port apply_body_motion()/relaxed_hands() into scenes.

Run via .app binary.  Args: <vrm.glb> <vo.wav> <out_dir|out.png>
"""
import bpy, sys, math, wave
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
VRM, WAV, OUT = argv[0], argv[1], argv[2]
STILL = OUT.lower().endswith(".png")
FPS = 24

def find_key(kb, names, di=None):
    low = {k.name.lower(): k.name for k in kb}
    for want in names:
        for ln, real in low.items():
            if ln == want.lower() or ln.endswith(want.lower()): return real
    return kb[di].name if (di is not None and di < len(kb)) else None
def emit_mat(name, color, strength):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    for n in list(nt.nodes): nt.nodes.remove(n)
    o = nt.nodes.new("ShaderNodeOutputMaterial"); e = nt.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*color, 1.0); e.inputs[1].default_value = strength
    nt.links.new(e.outputs[0], o.inputs["Surface"]); return m
def add_anime_outline(objs, th=0.0026):
    ink = emit_mat("Ink", (0.012, 0.012, 0.016), 1.0); ink.use_backface_culling = True
    for o in objs:
        if o.type != 'MESH': continue
        idx = len(o.data.materials); o.data.materials.append(ink)
        m = o.modifiers.new("OL", 'SOLIDIFY'); m.thickness = th; m.offset = 1
        m.use_flip_normals = True; m.material_offset = idx; m.use_rim = False
def cel(objs):
    seen = set()
    for o in objs:
        if o.type != 'MESH': continue
        for mat in o.data.materials:
            if not mat or mat.name in seen or mat.name == "Ink": continue
            seen.add(mat.name)
            b = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat.use_nodes else None
            if not b: continue
            for s, v in (("Specular IOR Level", 0.05), ("Roughness", 0.6), ("Sheen Weight", 0.0)):
                if s in b.inputs:
                    try: b.inputs[s].default_value = v
                    except Exception: pass

# ---------- the reusable motion module (the thing we're tuning) ----------
def relaxed_hands(arm):
    """Curl fingers into a natural relaxed hand instead of the splayed rig default."""
    for side, s in (("L", 1), ("R", -1)):
        for fi, fname in enumerate(["Index", "Middle", "Ring", "Little"]):
            curl = 0.30 + 0.06 * fi
            for seg in (1, 2, 3):
                b = arm.pose.bones.get(f"J_Bip_{side}_{fname}{seg}")
                if b:
                    b.rotation_mode = 'XYZ'
                    b.rotation_euler = (0, 0, -curl * s)   # curl toward palm (sign per side)
        for seg in (1, 2):
            b = arm.pose.bones.get(f"J_Bip_{side}_Thumb{seg}")
            if b:
                b.rotation_mode = 'XYZ'; b.rotation_euler = (0.15, 0.1 * s, 0)

def _fbm(t, comps):
    return sum(a * math.sin(2 * math.pi * fr * t + p) for (fr, a, p) in comps)

def _smooth_env(env, N, win=4):
    """smooth the speech envelope so gestures glide instead of jitter per-frame"""
    if not env: return [0.0] * N
    out = []
    for f in range(N):
        lo, hi = max(0, f - win), min(N, f + win + 1)
        out.append(sum(env[lo:hi]) / (hi - lo))
    return out

def apply_body_motion(arm, N, talking, env=None, phase=0.0):
    """Procedural life that reads in a medium shot: breathing (spine/chest/shoulders),
    slow weight-shift (hips), organic head with emphasis nods, and — when talking — the
    forearms lift into the gesture zone and move with the (smoothed) speech envelope."""
    g_env = _smooth_env(env, N) if (talking and env) else [0.0] * N
    def key(bone, fn):
        pb = arm.pose.bones.get(bone)
        if not pb: return
        pb.rotation_mode = 'XYZ'
        for f in range(N):
            pb.rotation_euler = fn(f / FPS, f); pb.keyframe_insert("rotation_euler", frame=f + 1)
    br = lambda t: math.sin(2 * math.pi * 0.27 * t)                 # ~16 breaths/min
    # torso: breathing + weight shift
    key("J_Bip_C_Hips",  lambda t, f: (0, 0, 0.04 * _fbm(t, [(0.06, 1, phase), (0.11, 0.4, phase + 2)])))
    key("J_Bip_C_Spine", lambda t, f: (0.018 * br(t), 0, 0.016 * _fbm(t, [(0.13, 1, phase), (0.07, 0.5, phase + 1)])))
    key("J_Bip_C_Chest", lambda t, f: (0.030 * br(t) + 0.006, 0, 0.014 * _fbm(t, [(0.2, 1, phase + 0.4)])))
    if arm.pose.bones.get("J_Bip_C_UpperChest"):
        key("J_Bip_C_UpperChest", lambda t, f: (0.020 * br(t), 0, 0))
    # head + neck: organic drift + a small nod on speech emphasis
    key("J_Bip_C_Neck", lambda t, f: (0.02 * _fbm(t, [(0.4, 1, 0.3)]), 0, 0.02 * _fbm(t, [(0.33, 1, 0.7)])))
    key("J_Bip_C_Head", lambda t, f: (0.05 * _fbm(t, [(0.4, 1, 0), (0.7, 0.4, 1)]) - 0.07 * g_env[f],
                                      0.02 * _fbm(t, [(0.3, 1, 0.5)]),
                                      0.06 * _fbm(t, [(0.3, 1, 1.1), (0.6, 0.4, 0.2)])))
    # shoulders rise gently with the breath
    for side, s in (("L", 1), ("R", -1)):
        key(f"J_Bip_{side}_Shoulder", lambda t, f, s=s: (0, 0.025 * br(t) * s, 0))
    # arms: relaxed-down base; talking lifts the forearms into a gesture and sways them
    for side, s in (("L", 1), ("R", -1)):
        ub, lb = 1.15 * s, 0.12 * s
        def up_fn(t, f, s=s, ub=ub):
            g = g_env[f]
            return (0, 0, ub - 0.10 * (1 if talking else 0) - 0.05 * g * s + 0.02 * math.sin(2 * math.pi * 0.3 * t + phase) * s)
        def lo_fn(t, f, s=s, lb=lb):
            g = g_env[f]
            # Y bends the elbow forward -> forearm rises to waist-front (the gesture stance)
            base = 0.95 if talking else 0.0
            osc = (0.16 * math.sin(2 * math.pi * 0.5 * t + phase) + 0.28 * g) if talking else 0.0
            return (0, (base + osc) * s, lb)
        key(f"J_Bip_{side}_UpperArm", up_fn)
        key(f"J_Bip_{side}_LowerArm", lo_fn)

# ---------- studio set + character ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=VRM)
imp = [o for o in bpy.data.objects if o not in before]
arm = next(o for o in imp if o.type == 'ARMATURE')
face = next(o for o in imp if o.type == 'MESH' and o.data.shape_keys and len(o.data.shape_keys.key_blocks) > 40)
kb = face.data.shape_keys.key_blocks
A_KEY = find_key(kb, ["Fcl_MTH_A", "MTH_A"], 39); BLINK = find_key(kb, ["Fcl_EYE_Close"], 13)
SMILE = find_key(kb, ["Fcl_MTH_Fun", "Fcl_ALL_Fun"])
relaxed_hands(arm)
bpy.context.view_layer.update()
fz = [(arm.matrix_world @ arm.pose.bones[b].head).z for b in ("J_Bip_L_Foot", "J_Bip_R_Foot") if b in arm.pose.bones]
arm.location.z -= (min(fz) - 0.07) if fz else 0.0
bpy.context.view_layer.update()
cel(imp); add_anime_outline(imp)
head = arm.matrix_world @ arm.pose.bones["J_Bip_C_Head"].head
chest = arm.matrix_world @ arm.pose.bones["J_Bip_C_Chest"].head
look = chest.lerp(head, 0.30)   # aim lower -> waist-up framing so hands/gestures read

# backdrop + floor
def box(name, loc, scale, col, rough=0.8):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o = bpy.context.object; o.name = name; o.scale = scale
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs["Base Color"].default_value = (*col, 1); b.inputs["Roughness"].default_value = rough
    o.data.materials.append(m); return o
box("Back", (0, -2.0, 1.6), (12, 0.1, 6), (0.13, 0.15, 0.2))
box("Floor", (0, 0, -0.02), (12, 12, 0.04), (0.12, 0.13, 0.17), rough=0.5)

cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d); sc.collection.objects.link(cam)
sc.camera = cam; cam_d.lens = 40
CAM0 = Vector((look.x + 0.1, look.y + 2.9, look.z + 0.35)); cam.location = CAM0
cam.rotation_euler = (look - CAM0).to_track_quat('-Z', 'Y').to_euler()
cam_d.dof.use_dof = True; cam_d.dof.focus_distance = (look - CAM0).length; cam_d.dof.aperture_fstop = 2.2

def area(loc, e, sz, col):
    l = bpy.data.lights.new("L", 'AREA'); o = bpy.data.objects.new("L", l); sc.collection.objects.link(o)
    o.location = Vector(loc); l.energy = e; l.size = sz; l.color = col
    o.rotation_euler = (look - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
area((look.x + 1.3, look.y + 1.7, look.z + 0.8), 200, 1.2, (1.0, 0.95, 0.86))
area((look.x - 1.4, look.y + 1.4, look.z + 0.3), 70, 2.4, (0.82, 0.88, 1.0))
area((look.x - 0.7, look.y - 1.3, look.z + 1.4), 130, 0.6, (0.85, 0.92, 1.0))
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[1].default_value = 0.35

# ---------- animation ----------
N = 1
if not STILL:
    with wave.open(WAV, "rb") as wv:
        sr, ch, sw, nfr = wv.getframerate(), wv.getnchannels(), wv.getsampwidth(), wv.getnframes()
        raw = wv.readframes(nfr)
    dt = {1: np.int8, 2: np.int16, 4: np.int32}.get(sw, np.int16)
    a = np.frombuffer(raw, dtype=dt).astype(np.float32)
    if ch > 1: a = a.reshape(-1, ch).mean(axis=1)
    a /= (np.abs(a).max() + 1e-9)
    N = max(1, math.ceil(nfr / sr * FPS)); env = []
    for f in range(N):
        i0, i1 = int(f/FPS*sr), int((f+1)/FPS*sr); seg = a[i0:i1] if i1 > i0 else a[i0:i0+1]
        env.append(min(1.0, float(np.sqrt(np.mean(seg**2)))*3.2) if seg.size else 0.0)
    if SMILE: kb[SMILE].value = 0.12
    for f in range(N):
        if A_KEY: kb[A_KEY].value = round(0.05 + 0.85*env[f], 3); kb[A_KEY].keyframe_insert("value", frame=f+1)
        if BLINK: kb[BLINK].value = 1.0 if (f % (FPS*2)) in (0,1,2) else 0.0; kb[BLINK].keyframe_insert("value", frame=f+1)
    apply_body_motion(arm, N, talking=True, env=env, phase=0.0)
else:
    apply_body_motion(arm, 1, talking=True, env=[0.6], phase=0.0)   # show the gesture pose in a still
    bpy.context.scene.frame_set(1)

sc.render.engine = 'BLENDER_EEVEE'
ee = sc.eevee
for at, v in (("taa_render_samples", 64), ("use_raytracing", True), ("use_shadows", True), ("use_gtao", True)):
    try: setattr(ee, at, v)
    except Exception: pass
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Medium High Contrast'
sc.render.resolution_x, sc.render.resolution_y = 1280, 720; sc.render.fps = FPS
if STILL:
    sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = OUT
    bpy.ops.render.render(write_still=True); print("STILL_DONE")
else:
    sc.frame_start, sc.frame_end = 1, N; sc.render.filepath = OUT.rstrip("/") + "/f_"
    bpy.ops.render.render(animation=True); print("ANIM_DONE", N)

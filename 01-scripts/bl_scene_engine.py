"""SIGNIFICANT — GENERIC SCENE ENGINE. One Blender renderer for every dialogue/presenting
scene, driven by a JSON config. Replaces the bespoke bl_*_scene.py scripts.

Run:  Blender -b --python bl_scene_engine.py -- <config.json>

config = {
  "set": "kitchenette", "props": {...},
  "characters": [{"name","vrm","pos":[x,y,z],"rot":deg,"gesture":1.0}, ...],
  "shot": {"tgt": "<charname>|two|obj:<Name>|[x,y,z]", "off":[x,y,z], "lens":50,
           "fstop":2.2, "push":0.2, "spk":"<charname>|null"},
  "vo": "/abs/line.wav"|null,  "out": "/abs/dir"|"/abs/x.png",
  "fps":24, "res":[1920,1080], "still_talk": false
}
"""
import bpy, sys, os, json, math, wave
import numpy as np
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_sets
from bl_anim_lib import apply_body_motion, relaxed_hands, apply_emotion, head_yaw_to, recolor

CFG = json.load(open(sys.argv[sys.argv.index("--") + 1:][0]))
FPS = CFG.get("fps", 24)
RES = CFG.get("res", [1920, 1080])
OUT = CFG["out"]
STILL = OUT.lower().endswith(".png")

def find_key(kb, names, di=None):
    low = {k.name.lower(): k.name for k in kb}
    for want in names:
        for ln, real in low.items():
            if ln == want.lower() or ln.endswith(want.lower()): return real
    return kb[di].name if (di is not None and di < len(kb)) else None

# ---- outline / cel (consistent look) ----
def add_outline(objs, th=0.0026):
    ink = bl_sets.emit_mat("Ink_" + objs[0].name, (0.012, 0.012, 0.016), 1.0); ink.use_backface_culling = True
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
            if not mat or mat.name in seen or mat.name.startswith("Ink_"): continue
            seen.add(mat.name)
            b = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if mat.use_nodes else None
            if not b: continue
            for s, v in (("Specular IOR Level", 0.05), ("Roughness", 0.6), ("Sheen Weight", 0.0)):
                if s in b.inputs:
                    try: b.inputs[s].default_value = v
                    except Exception: pass

def bone_world(arm, names, substrs, frac):
    """World-space head position of a key bone, tolerant of non-VRoid rigs.
    Tries exact candidate names, then priority-ordered substring match, then a
    geometric fallback (frac of the armature's vertical bone span). Avoids hard
    KeyErrors on rigs that don't use the J_Bip_* naming convention."""
    for n in names:
        b = arm.pose.bones.get(n)
        if b: return arm.matrix_world @ b.head
    for s in substrs:                                  # priority-ordered substring match
        for pb in arm.pose.bones:
            if s in pb.name.lower(): return arm.matrix_world @ pb.head
    pts = [arm.matrix_world @ pb.head for pb in arm.pose.bones]
    if pts:
        lo = min(p.z for p in pts); hi = max(p.z for p in pts)
        cx = sum(p.x for p in pts) / len(pts); cy = sum(p.y for p in pts) / len(pts)
        return Vector((cx, cy, lo + (hi - lo) * frac))
    return arm.matrix_world @ arm.location

# ---- build scene ----
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
look_cfg = bl_sets.build(CFG["set"], sc, CFG.get("props"))

chars = {}
for c in CFG["characters"]:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=c["vrm"])
    imp = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in imp if o.type == 'ARMATURE')
    face = next((o for o in imp if o.type == 'MESH' and o.data.shape_keys and len(o.data.shape_keys.key_blocks) > 40), None)
    kb = face.data.shape_keys.key_blocks if face else None
    for side, s in (("L", 1), ("R", -1)):
        for bn, ang in ((f"J_Bip_{side}_UpperArm", 1.13 * s), (f"J_Bip_{side}_LowerArm", 0.2 * s)):
            b = arm.pose.bones.get(bn)
            if b: b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, ang)
    arm.location = Vector(c["pos"]); arm.rotation_euler = (0, 0, math.radians(c.get("rot", 0)))
    bpy.context.view_layer.update()
    fz = [(arm.matrix_world @ arm.pose.bones[b].head).z for b in ("J_Bip_L_Foot", "J_Bip_R_Foot") if b in arm.pose.bones]
    arm.location.z -= (min(fz) - 0.07) if fz else 0.0
    bpy.context.view_layer.update()
    cel(imp); add_outline(imp); relaxed_hands(arm)
    if c.get("recolor"):
        recolor(imp, {k.lower(): v for k, v in c["recolor"].items()})
    chars[c["name"]] = dict(arm=arm, kb=kb, gesture=c.get("gesture", 1.0),
                            A=find_key(kb, ["Fcl_MTH_A", "MTH_A"], 39) if kb else None,
                            BLINK=find_key(kb, ["Fcl_EYE_Close"], 13) if kb else None,
                            SMILE=find_key(kb, ["Fcl_MTH_Fun", "Fcl_ALL_Fun"]) if kb else None,
                            head=bone_world(arm, ["J_Bip_C_Head", "Head", "head", "mixamorig:Head"],
                                            ["head"], 0.92),
                            chest=bone_world(arm, ["J_Bip_C_Chest", "J_Bip_C_UpperChest", "Chest",
                                                   "chest", "mixamorig:Spine2"],
                                             ["upperchest", "chest", "spine"], 0.62))

# ---- resolve look target ----
shot = CFG["shot"]
tgt = shot["tgt"]
if isinstance(tgt, list):
    look = Vector(tgt)
elif tgt == "two":
    hs = [c["head"] for c in chars.values()]
    look = sum(hs, Vector((0, 0, 0))) / len(hs); look.z += shot.get("look_dz", 0.0)
elif tgt.startswith("obj:"):
    ob = bpy.data.objects.get(tgt[4:]); look = ob.location.copy() if ob else Vector((0, 0, 1.3))
else:
    c = chars[tgt]; look = c["chest"].lerp(c["head"], shot.get("look", 0.85))

CAM0 = look + Vector(shot["off"])
cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
sc.collection.objects.link(cam); sc.camera = cam; cam_d.lens = shot.get("lens", 50)
cam.location = CAM0; cam.rotation_euler = (look - CAM0).to_track_quat('-Z', 'Y').to_euler()
cam_d.dof.use_dof = True; cam_d.dof.focus_distance = (look - CAM0).length
cam_d.dof.aperture_fstop = shot.get("fstop", 2.2)

# ---- lighting: set's keys + a per-character face key ----
def area(name, loc, e, sz, col, t):
    l = bpy.data.lights.new(name, 'AREA'); o = bpy.data.objects.new(name, l)
    sc.collection.objects.link(o); o.location = Vector(loc); l.energy = e; l.size = sz; l.color = col
    o.rotation_euler = (Vector(t) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
mid = sum([c["head"] for c in chars.values()], Vector((0, 0, 0))) / max(1, len(chars))
if "winkey" in look_cfg:
    wl = look_cfg["winkey"]; area("WinKey", wl[0], wl[1], wl[2], wl[3], mid)
if "key" in look_cfg:
    k = look_cfg["key"]; area("Key", k[1], k[2], 1.1, k[3], mid)
if "fill" in look_cfg:
    fl = look_cfg["fill"]; area("Fill", fl[0], fl[1], 2.6, fl[2], mid)
for nm, c in chars.items():
    h = c["head"]; area(f"K_{nm}", (h.x + 0.6, h.y + 1.6, h.z + 0.5), 80, 1.0, (1.0, 0.95, 0.88), h)

# ---- animation ----
N = 1
if not STILL or CFG.get("still_talk"):
    env = None; spk = shot.get("spk")
    if CFG.get("vo") and CFG["vo"] != "null":
        with wave.open(CFG["vo"], "rb") as wv:
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
        N = int(FPS * CFG.get("silent_sec", 2.2))
    if STILL: N = 1

    names = list(chars.keys())
    for i, (nm, c) in enumerate(chars.items()):
        talking = (nm == spk) and env is not None
        if talking and c["A"]:
            if c["SMILE"]: c["kb"][c["SMILE"]].value = 0.08
            for f in range(N):
                c["kb"][c["A"]].value = round(0.05 + 0.85 * env[f], 3); c["kb"][c["A"]].keyframe_insert("value", frame=f + 1)
        if c["BLINK"]:
            for f in range(N):
                c["kb"][c["BLINK"]].value = 1.0 if (f % (FPS * 2)) in (0, 1, 2) else 0.0
                c["kb"][c["BLINK"]].keyframe_insert("value", frame=f + 1)
        # ACTING: emotion on the speaker (from the line's parenthetical) + eye-line to partner
        if talking and shot.get("emotion"):
            apply_emotion(c["kb"], shot["emotion"])
        hy = 0.0
        if len(names) >= 2:
            other = chars[names[1 - i]] if i < 2 else None
            if other:
                hy = head_yaw_to(c["arm"], other["head"])
        apply_body_motion(c["arm"], N, talking=talking, env=(env if talking else None),
                          phase=1.6 * i, gesture=c["gesture"], head_yaw=hy)
    if not STILL:
        cam.location = CAM0; cam.keyframe_insert("location", frame=1)
        cam.location = CAM0 + (look - CAM0).normalized() * shot.get("push", 0.2); cam.keyframe_insert("location", frame=N)

# ---- render ----
sc.render.engine = 'BLENDER_EEVEE'
for at, v in (("taa_render_samples", 64), ("use_raytracing", True), ("use_shadows", True), ("use_gtao", True)):
    try: setattr(sc.eevee, at, v)
    except Exception: pass
sc.view_settings.view_transform = 'AgX'; sc.view_settings.exposure = look_cfg.get("exposure", 0.3)
sc.view_settings.look = 'AgX - Medium High Contrast'
sc.render.resolution_x, sc.render.resolution_y = RES[0], RES[1]; sc.render.fps = FPS
if STILL:
    bpy.context.scene.frame_set(1)
    sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = OUT
    bpy.ops.render.render(write_still=True); print("ENGINE_STILL_DONE", OUT)
else:
    sc.frame_start, sc.frame_end = 1, N; sc.render.filepath = OUT.rstrip("/") + "/f_"
    bpy.ops.render.render(animation=True); print("ENGINE_ANIM_DONE", N)

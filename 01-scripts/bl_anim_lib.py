"""SIGNIFICANT — shared animation/quality library (the codified standard).
Imported by every scene script so motion + look stay consistent across episodes.

Public API:
  relaxed_hands(arm)                         -> natural curled hands
  apply_body_motion(arm, N, talking, env)    -> breathing/sway/head + speech gestures
  recolor(mat_substr -> rgb)                  -> optional outfit/material recolor helper
"""
import math

FPS = 24

def relaxed_hands(arm):
    """Curl the fingers into a relaxed hand instead of the splayed rig default."""
    for side, s in (("L", 1), ("R", -1)):
        for fi, fname in enumerate(["Index", "Middle", "Ring", "Little"]):
            curl = 0.30 + 0.06 * fi
            for seg in (1, 2, 3):
                b = arm.pose.bones.get(f"J_Bip_{side}_{fname}{seg}")
                if b:
                    b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, -curl * s)
        for seg in (1, 2):
            b = arm.pose.bones.get(f"J_Bip_{side}_Thumb{seg}")
            if b:
                b.rotation_mode = 'XYZ'; b.rotation_euler = (0.15, 0.1 * s, 0)

# ─────────────────── EMOTION (acting) ───────────────────
# Use BROW + EYE shapes only, so the mouth stays free for lip-sync.
EMO_SHAPES = {
    "angry":     [("Fcl_BRW_Angry", 1.0), ("Fcl_EYE_Angry", 0.7)],
    "fun":       [("Fcl_BRW_Fun", 0.8), ("Fcl_EYE_Fun", 0.7)],
    "joy":       [("Fcl_BRW_Joy", 0.9), ("Fcl_EYE_Joy", 0.6)],
    "sorrow":    [("Fcl_BRW_Sorrow", 1.0), ("Fcl_EYE_Sorrow", 0.7)],
    "surprised": [("Fcl_BRW_Surprised", 1.0), ("Fcl_EYE_Surprised", 0.55)],
}
EMO_KW = {
    "angry":     ["angry", "anger", "sharp", "snap", "accus", "hard", "cold"],
    "fun":       ["smil", "grin", "danger", "wry", "amused", "sly", "sardonic", "dry", "teas", "skeptic", "doubt", "knowing"],
    "joy":       ["happy", "warm", "laugh", "delight", "bright", "excited"],
    "sorrow":    ["sad", "sorrow", "quiet", "hesitat", "defeat", "tilting", "sigh", "soft", "weary", "small"],
    "surprised": ["surpris", "shock", "flicker", "pause", "realiz", "stunned", "caught", "beat"],
}
def emotion_from_paren(paren):
    if not paren: return None
    p = paren.lower()
    for emo, kws in EMO_KW.items():
        if any(k in p for k in kws):
            return emo
    return None

def apply_emotion(kb, emotion, intensity=0.72):
    """Set brow/eye emotion shapes statically (they hold across the clip; lip-sync + blink
    key OTHER shapes per-frame, so they coexist)."""
    if not kb or not emotion or emotion not in EMO_SHAPES:
        return
    names = {k.name.lower(): k.name for k in kb}
    for shp, w in EMO_SHAPES[emotion]:
        real = names.get(shp.lower())
        if real:
            kb[real].value = round(w * intensity, 3)

def head_yaw_to(arm, target):
    """Signed yaw (radians) to turn this character's head toward a world point — for eye-lines."""
    try:
        h = arm.matrix_world @ arm.pose.bones["J_Bip_C_Head"].head
    except Exception:
        return 0.0
    d = (target - h); d.z = 0
    if d.length < 1e-4: return 0.0
    d = d.normalized()
    rz = arm.rotation_euler.z
    facing = (-math.sin(rz), math.cos(rz), 0.0)   # local +Y rotated by armature Z
    dot = facing[0] * d.x + facing[1] * d.y
    cross = facing[0] * d.y - facing[1] * d.x
    return math.atan2(cross, dot)

def _fbm(t, comps):
    return sum(a * math.sin(2 * math.pi * fr * t + p) for (fr, a, p) in comps)

def _smooth(env, N, win=4):
    if not env:
        return [0.0] * N
    out = []
    for f in range(N):
        lo, hi = max(0, f - win), min(N, f + win + 1)
        out.append(sum(env[lo:hi]) / (hi - lo))
    return out

def apply_body_motion(arm, N, talking, env=None, phase=0.0, gesture=1.0, head_yaw=0.0):
    """Procedural life that reads in a medium shot. Drives the FULL upper body, so it
    REPLACES any separate head/chest idle. `talking` + `env` (per-frame speech RMS, 0..1)
    add forearm gestures + emphasis nods; listeners (talking=False) still breathe & sway.
    `gesture` scales hand-gesture amplitude (set lower for restrained characters)."""
    g_env = _smooth(env, N) if (talking and env) else [0.0] * N
    def key(bone, fn):
        pb = arm.pose.bones.get(bone)
        if not pb:
            return
        pb.rotation_mode = 'XYZ'
        for f in range(N):
            pb.rotation_euler = fn(f / FPS, f); pb.keyframe_insert("rotation_euler", frame=f + 1)
    br = lambda t: math.sin(2 * math.pi * 0.27 * t)
    key("J_Bip_C_Hips",  lambda t, f: (0, 0, 0.04 * _fbm(t, [(0.06, 1, phase), (0.11, 0.4, phase + 2)])))
    key("J_Bip_C_Spine", lambda t, f: (0.018 * br(t), 0, 0.016 * _fbm(t, [(0.13, 1, phase), (0.07, 0.5, phase + 1)])))
    key("J_Bip_C_Chest", lambda t, f: (0.030 * br(t) + 0.006, 0, 0.014 * _fbm(t, [(0.2, 1, phase + 0.4)])))
    if arm.pose.bones.get("J_Bip_C_UpperChest"):
        key("J_Bip_C_UpperChest", lambda t, f: (0.020 * br(t), 0, 0))
    key("J_Bip_C_Neck", lambda t, f: (0.02 * _fbm(t, [(0.4, 1, 0.3)]), 0, 0.02 * _fbm(t, [(0.33, 1, 0.7)])))
    # keep head pitch modest so the face never drops out of a dialogue single;
    # head_yaw biases the gaze toward the scene partner (eye-line), at 0.5x so the
    # face stays camera-friendly 3/4 rather than turning to full profile.
    key("J_Bip_C_Head", lambda t, f: (0.028 * _fbm(t, [(0.4, 1, 0), (0.7, 0.4, 1)]) - 0.035 * g_env[f],
                                      0.02 * _fbm(t, [(0.3, 1, 0.5)]),
                                      0.05 * _fbm(t, [(0.3, 1, 1.1), (0.6, 0.4, 0.2)]) + 0.5 * head_yaw))
    for side, s in (("L", 1), ("R", -1)):
        key(f"J_Bip_{side}_Shoulder", lambda t, f, s=s: (0, 0.025 * br(t) * s, 0))
    for side, s in (("L", 1), ("R", -1)):
        ub, lb = 1.15 * s, 0.12 * s
        def up_fn(t, f, s=s, ub=ub):
            g = g_env[f]
            return (0, 0, ub - 0.10 * (1 if talking else 0) - 0.05 * g * s + 0.02 * math.sin(2 * math.pi * 0.3 * t + phase) * s)
        def lo_fn(t, f, s=s, lb=lb):
            g = g_env[f]
            base = (0.95 if talking else 0.0) * gesture
            osc = ((0.16 * math.sin(2 * math.pi * 0.5 * t + phase) + 0.28 * g) * gesture) if talking else 0.0
            return (0, (base + osc) * s, lb)
        key(f"J_Bip_{side}_UpperArm", up_fn)
        key(f"J_Bip_{side}_LowerArm", lo_fn)

def recolor(objs, rules):
    """Tint a garment material by name substring. rules = {substr_lower: (r,g,b)}.
    VRoid garments are TEXTURE-driven, so we multiply the texture by the tint (mutes /
    shifts tone; can't add a hue the texture lacks). Falls back to base-color set if
    unlinked. Safe no-op for non-matching materials."""
    for o in objs:
        if getattr(o, "type", None) != 'MESH':
            continue
        for mat in o.data.materials:
            if not mat or not mat.use_nodes:
                continue
            nm = mat.name.lower()
            for sub, rgb in rules.items():
                if sub not in nm:
                    continue
                nt = mat.node_tree
                b = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if not b or "Base Color" not in b.inputs:
                    continue
                bc = b.inputs["Base Color"]
                if bc.is_linked:
                    src = bc.links[0].from_socket
                    mix = nt.nodes.new("ShaderNodeMixRGB"); mix.blend_type = 'MULTIPLY'
                    mix.inputs[0].default_value = 1.0; mix.inputs[2].default_value = (*rgb, 1.0)
                    nt.links.new(src, mix.inputs[1]); nt.links.new(mix.outputs[0], bc)
                else:
                    bc.default_value = (*rgb, 1.0)

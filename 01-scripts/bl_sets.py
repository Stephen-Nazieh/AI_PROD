"""SIGNIFICANT — SET REGISTRY. Reusable 3D set builders keyed by id, refactored from the
proven bespoke scenes. Each builder takes the Blender scene + a props dict and returns a
`look` dict (exposure/world already applied). The generic scene engine calls SETS[id].

Add a new location = add one builder here + map it in the show bible. Everything else
(characters, coverage, lip-sync, motion, edit) is automatic.
"""
import bpy, math
from mathutils import Vector

# ---------------- shared material/geometry helpers ----------------
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

def text_line(body, loc, size, mat, align='CENTER'):
    cu = bpy.data.curves.new("f", 'FONT'); cu.body = body; cu.size = size
    cu.align_x = align; cu.align_y = 'CENTER'
    ob = bpy.data.objects.new("T", cu); bpy.context.scene.collection.objects.link(ob)
    ob.location = Vector(loc); ob.rotation_euler = (math.radians(90), 0, math.radians(180))
    ob.data.materials.append(mat); return ob

def _world(sc, color, strength):
    w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*color, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = strength

def _light(sc, name, loc, e, sz, col, tgt):
    l = bpy.data.lights.new(name, 'AREA'); o = bpy.data.objects.new(name, l)
    sc.collection.objects.link(o); o.location = Vector(loc); l.energy = e; l.size = sz; l.color = col
    o.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler(); return o

# ---------------- the sets ----------------
def office_night(sc, props):
    """Dark open-plan office: glowing presentation slide, warm desk lamp, dark windows."""
    _world(sc, (0.012, 0.014, 0.02), 0.25)
    box("Floor", (0, 0, -0.02), (40, 40, 0.04), diffuse_mat("Fl", (0.03, 0.035, 0.045), 0.45))
    box("BackWall", (0, -4.4, 1.6), (12, 0.1, 6), diffuse_mat("Wa", (0.04, 0.045, 0.06), 0.8))
    box("SideWall", (4.2, -0.5, 1.6), (0.1, 9, 6), diffuse_mat("Wa2", (0.04, 0.045, 0.06), 0.8))
    box("Slide", (-0.1, -4.25, 1.55), (2.0, 0.06, 1.15), emit_mat("ScrBG", (0.05, 0.09, 0.16), 1.1))
    lines = props.get("slide", [])   # generic dark glow unless a show provides slide text
    if len(lines) >= 1:
        text_line(lines[0], (-0.1, -4.10, 1.98), 0.15, emit_mat("S1", (0.7, 0.82, 1.0), 3.0))
    if len(lines) >= 2:
        text_line(lines[1], (-0.1, -4.10, 1.42), 0.52, emit_mat("S2", (0.85, 0.95, 1.0), 6.0))
    box("Window", (4.13, -0.5, 1.7), (0.02, 5.5, 3.2), diffuse_mat("Glass", (0.02, 0.025, 0.04), 0.08, 0.7))
    for (dx, dy) in [(-2.6, -1.2), (-2.4, 0.6), (2.5, -1.4), (2.7, 0.5), (-0.2, -2.2)]:
        box("Desk", (dx, dy, 0.37), (1.1, 0.6, 0.74), diffuse_mat("Dk", (0.05, 0.05, 0.06), 0.6))
    box("Bulb", (1.5, 0.6, 0.92), (0.08, 0.08, 0.08), emit_mat("Bulb", (1.0, 0.72, 0.42), 22.0))
    lp = bpy.data.lights.new("Lamp", 'POINT'); lo = bpy.data.objects.new("Lamp", lp)
    sc.collection.objects.link(lo); lo.location = (1.5, 0.6, 0.95)
    lp.energy = 60; lp.color = (1.0, 0.7, 0.4); lp.shadow_soft_size = 0.15
    return {"exposure": 0.7, "key": ("warm", (1.5, 1.6, 1.45), 190, (1.0, 0.82, 0.62)),
            "fill": ((-1.4, 2.0, 1.6), 26, (0.6, 0.72, 1.0))}

def kitchenette(sc, props):
    """Bright morning office kitchenette: counter, cabinets, coffee machine, window key."""
    _world(sc, (0.5, 0.55, 0.62), 0.7)
    box("Floor", (0, 0, -0.02), (40, 40, 0.04), diffuse_mat("Fl", (0.22, 0.20, 0.18), 0.5))
    box("BackWall", (0, -2.6, 1.6), (14, 0.1, 6), diffuse_mat("Wa", (0.62, 0.60, 0.56), 0.9))
    box("Counter", (0, -2.15, 0.46), (3.6, 0.7, 0.92), diffuse_mat("CT", (0.14, 0.13, 0.13), 0.3))
    box("UpperCab", (0, -2.45, 2.25), (3.6, 0.45, 0.7), diffuse_mat("Cab", (0.32, 0.24, 0.17), 0.6))
    box("CoffeeM", (1.2, -2.2, 1.1), (0.34, 0.4, 0.42), diffuse_mat("Mc", (0.05, 0.05, 0.06), 0.3))
    box("CoffeeLED", (1.05, -1.98, 1.12), (0.03, 0.02, 0.03), emit_mat("LED", (1.0, 0.3, 0.15), 6.0))
    box("Window", (-4.3, 0.8, 1.7), (0.04, 3.2, 2.4), emit_mat("Sky", (1.0, 0.96, 0.85), 2.2))
    return {"exposure": 0.2, "winkey": ((-3.6, 1.2, 1.9), 320, 2.6, (1.0, 0.93, 0.8)),
            "fill": ((2.6, 2.2, 1.7), 70, (0.8, 0.86, 1.0))}

def cafe_day(sc, props):
    """Warm daytime café: high table w/ laptop + tea, riverside window key."""
    _world(sc, (0.5, 0.52, 0.5), 0.75)
    box("Floor", (0, 0, -0.02), (40, 40, 0.04), diffuse_mat("Fl", (0.16, 0.11, 0.07), 0.45))
    box("BackWall", (0, -2.7, 1.6), (14, 0.1, 6), diffuse_mat("Wa", (0.42, 0.34, 0.27), 0.9))
    box("Window", (-4.3, 0.6, 1.8), (0.05, 3.4, 2.6), emit_mat("Sky", (1.0, 0.92, 0.78), 2.6))
    box("Table", (0, 0.05, 0.92), (1.7, 1.05, 0.08), diffuse_mat("Tb", (0.12, 0.08, 0.05), 0.35))
    box("TableLeg", (0, 0.05, 0.46), (0.12, 0.12, 0.9), diffuse_mat("Lg", (0.05, 0.04, 0.03), 0.4))
    box("Cup", (0.5, 0.15, 1.00), (0.10, 0.10, 0.10), diffuse_mat("Cu", (0.85, 0.83, 0.78), 0.3))
    box("LapBase", (-0.35, 0.18, 0.97), (0.36, 0.26, 0.03), diffuse_mat("Lp", (0.08, 0.08, 0.09), 0.4))
    lid = box("LapLid", (-0.35, 0.02, 1.10), (0.36, 0.02, 0.24), emit_mat("Scr", (0.5, 0.62, 0.85), 1.4))
    lid.rotation_euler = (math.radians(-18), 0, 0)
    return {"exposure": 0.1, "winkey": ((-3.4, 1.0, 2.0), 360, 2.8, (1.0, 0.9, 0.74)),
            "fill": ((2.8, 2.2, 1.7), 60, (0.78, 0.84, 1.0))}

def conference_day(sc, props):
    """Polished conference room: big table, back-wall presentation slide, corporate window."""
    _world(sc, (0.55, 0.58, 0.62), 0.8)
    box("Floor", (0, 0, -0.02), (40, 40, 0.04), diffuse_mat("Fl", (0.10, 0.10, 0.12), 0.35))
    box("BackWall", (0, -2.9, 1.7), (16, 0.1, 6.4), diffuse_mat("Wa", (0.30, 0.32, 0.36), 0.85))
    box("Window", (4.5, 1.0, 1.9), (0.05, 3.6, 2.8), emit_mat("Sky", (0.95, 0.97, 1.0), 2.4))
    box("Table", (0, 0.05, 0.95), (2.0, 1.15, 0.08), diffuse_mat("Tb", (0.06, 0.06, 0.07), 0.25, 0.2))
    box("TableLeg", (0, 0.05, 0.47), (0.14, 0.14, 0.92), diffuse_mat("Lg", (0.04, 0.04, 0.05), 0.4))
    box("ScreenFrame", (0, -2.83, 2.0), (2.7, 0.04, 1.3), diffuse_mat("Fr", (0.02, 0.02, 0.03), 0.4))
    box("Screen", (0, -2.80, 2.0), (2.5, 0.02, 1.15), emit_mat("ScrBG", (0.06, 0.10, 0.16), 1.1))
    sl = props.get("slide", [])   # generic screen unless a show provides slide text
    if len(sl) >= 1:
        text_line(sl[0], (0, -2.74, 2.42), 0.13, emit_mat("S1", (0.7, 0.82, 1.0), 2.6))
    if len(sl) >= 2:
        text_line(sl[1], (0, -2.74, 2.06), 0.40, emit_mat("S2", (0.85, 0.95, 1.0), 5.0))
    if len(sl) > 2:
        text_line(sl[2], (0, -2.74, 1.62), 0.105, emit_mat("S3", (0.6, 0.78, 0.7), 2.4))
    return {"exposure": 0.1, "winkey": ((3.6, 1.2, 2.1), 320, 2.8, (0.95, 0.96, 1.0)),
            "fill": ((-2.8, 2.2, 1.8), 70, (0.85, 0.88, 0.95))}

def whiteboard(sc, props):
    """Bright office nook with a whiteboard on the back wall (Maya/Nina work the problem)."""
    _world(sc, (0.5, 0.54, 0.6), 0.7)
    box("Floor", (0, 0, -0.02), (40, 40, 0.04), diffuse_mat("Fl", (0.20, 0.19, 0.18), 0.5))
    box("BackWall", (0, -2.6, 1.6), (14, 0.1, 6), diffuse_mat("Wa", (0.56, 0.57, 0.6), 0.9))
    box("WBFrame", (0, -2.52, 1.7), (3.0, 0.05, 1.5), diffuse_mat("Frm", (0.2, 0.2, 0.22), 0.4))
    box("WB", (0, -2.49, 1.7), (2.8, 0.02, 1.35), emit_mat("WBm", (0.92, 0.93, 0.94), 0.9))
    scr = props.get("board", [])   # blank board unless a show provides text
    z = 2.1
    for ln in scr:
        text_line(ln, (0, -2.44, z), 0.12, emit_mat("Mk", (0.12, 0.14, 0.4), 1.0)); z -= 0.34
    box("Window", (-4.3, 0.8, 1.7), (0.04, 3.2, 2.4), emit_mat("Sky", (1.0, 0.96, 0.86), 2.0))
    return {"exposure": 0.25, "winkey": ((-3.6, 1.2, 1.9), 300, 2.6, (1.0, 0.94, 0.84)),
            "fill": ((2.6, 2.2, 1.7), 70, (0.82, 0.86, 1.0))}

def studio(sc, props):
    """Neutral fallback set for any unmapped location: backdrop + floor, 3-point ready."""
    _world(sc, (0.13, 0.15, 0.2), 0.35)
    box("Back", (0, -2.0, 1.6), (12, 0.1, 6), diffuse_mat("Bk", (0.13, 0.15, 0.2), 0.8))
    box("Floor", (0, 0, -0.02), (12, 12, 0.04), diffuse_mat("Fl", (0.12, 0.13, 0.17), 0.5))
    return {"exposure": 0.4}

SETS = {
    "office_night": office_night,
    "kitchenette": kitchenette,
    "cafe_day": cafe_day,
    "conference_day": conference_day,
    "whiteboard": whiteboard,
    "studio": studio,
}

def build(set_id, sc, props=None):
    return SETS.get(set_id, studio)(sc, props or {})

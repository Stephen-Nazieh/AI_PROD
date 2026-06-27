"""Show Blender's real quality ceiling: a single CYCLES hero still — GPU(Metal) +
denoise, cinematic 3-point lighting, depth-of-field, a studio backdrop. The opposite
of the flat Eevee proof. Run via the .app binary. Args: <vrm.glb> <out.png>
"""
import bpy, sys, math, mathutils

argv = sys.argv[sys.argv.index("--") + 1:]
VRM, OUT = argv[0], argv[1]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=VRM)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

# arms-down rest pose
for side, s in (("L", 1), ("R", -1)):
    b = arm.pose.bones.get(f"J_Bip_{side}_UpperArm")
    if b:
        b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, 1.15 * s)
    lb = arm.pose.bones.get(f"J_Bip_{side}_LowerArm")
    if lb:
        lb.rotation_mode = 'XYZ'; lb.rotation_euler = (0, 0, 0.12 * s)

head = arm.matrix_world @ arm.pose.bones["J_Bip_C_Head"].head
neck = arm.matrix_world @ arm.pose.bones["J_Bip_C_Neck"].head
target = head.lerp(neck, 0.35)

# ---- studio backdrop: wall BEHIND the character (away from camera = -Y) + floor ----
bpy.ops.mesh.primitive_plane_add(size=20, location=(target.x, target.y - 2.0, target.z))
back = bpy.context.object; back.rotation_euler = (math.radians(90), 0, 0)
bpy.ops.mesh.primitive_plane_add(size=20, location=(target.x, target.y - 1.0, 0))
floor = bpy.context.object
mat = bpy.data.materials.new("Backdrop"); mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.14, 0.16, 0.21, 1)
bsdf.inputs["Roughness"].default_value = 0.85
for o in (back, floor):
    o.data.materials.append(mat)

# ---- camera with depth of field ----
cam_d = bpy.data.cameras.new("Cam"); cam = bpy.data.objects.new("Cam", cam_d)
bpy.context.scene.collection.objects.link(cam)
cam_d.lens = 85
cam.location = (target.x + 0.25, target.y + 1.3, target.z + 0.03)
cam.rotation_euler = (target - mathutils.Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
cam_d.dof.use_dof = True
cam_d.dof.focus_distance = (target - mathutils.Vector(cam.location)).length
cam_d.dof.aperture_fstop = 2.2   # shallow → soft background
bpy.context.scene.camera = cam

# ---- cinematic 3-point lighting ----
def area(name, loc, energy, size, color=(1, 1, 1)):
    l = bpy.data.lights.new(name, 'AREA'); o = bpy.data.objects.new(name, l)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc; l.energy = energy; l.size = size; l.color = color
    d = (target - mathutils.Vector(loc)); o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return o
area("Key",  (target.x + 1.3, target.y + 1.6, target.z + 0.9), 60, 1.2, (1.0, 0.96, 0.9))
area("Fill", (target.x - 1.5, target.y + 1.3, target.z + 0.3), 18, 2.2, (0.85, 0.9, 1.0))
area("Rim",  (target.x - 0.6, target.y - 1.4, target.z + 1.3), 90, 0.6, (0.9, 0.95, 1.0))

w = bpy.data.worlds.new("W"); bpy.context.scene.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.06, 0.08, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.4

# ---- Cycles GPU + denoise ----
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    sc.cycles.device = 'GPU'
    print("CYCLES device: GPU/METAL")
except Exception as e:
    sc.cycles.device = 'CPU'; print("CYCLES device: CPU (", e, ")")
sc.cycles.samples = 160
sc.cycles.use_denoising = True
sc.view_settings.view_transform = 'AgX'   # filmic-style tonemap
sc.render.resolution_x = 1080; sc.render.resolution_y = 1350
sc.render.image_settings.file_format = 'PNG'
sc.render.filepath = OUT
print("HERO rendering (Cycles)...")
bpy.ops.render.render(write_still=True)
print("HERO_DONE", OUT)

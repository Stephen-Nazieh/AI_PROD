"""Fast VRM thumbnail for casting: import, arms-down, front 3-point, Eevee, 480x600.
Run via .app binary.  Args: <vrm.glb> <out.png>"""
import bpy, sys, math, mathutils
from mathutils import Vector
argv = sys.argv[sys.argv.index("--") + 1:]
VRM, OUT = argv[0], argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=VRM)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
for side, s in (("L", 1), ("R", -1)):
    b = arm.pose.bones.get(f"J_Bip_{side}_UpperArm")
    if b: b.rotation_mode = 'XYZ'; b.rotation_euler = (0, 0, 1.15 * s)
bpy.context.view_layer.update()
head = arm.matrix_world @ arm.pose.bones["J_Bip_C_Head"].head
chest = arm.matrix_world @ arm.pose.bones["J_Bip_C_Chest"].head
look = chest.lerp(head, 0.75)
cam_d = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cam_d)
bpy.context.scene.collection.objects.link(cam); cam_d.lens = 50
loc = Vector((look.x, look.y + 1.9, look.z + 0.02)); cam.location = loc
cam.rotation_euler = (look - loc).to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam
def area(loc, e, c):
    l = bpy.data.lights.new("L", 'AREA'); o = bpy.data.objects.new("L", l)
    bpy.context.scene.collection.objects.link(o); o.location = loc; l.energy = e; l.size = 1.5; l.color = c
    o.rotation_euler = (look - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
area((look.x + 1.2, look.y + 1.6, look.z + 0.8), 200, (1, .96, .9))
area((look.x - 1.2, look.y + 1.4, look.z + 0.4), 90, (.85, .9, 1))
w = bpy.data.worlds.new("W"); bpy.context.scene.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[1].default_value = 0.5
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'   # in Blender 5.x this IS EEVEE-Next
sc.view_settings.view_transform = 'AgX'
sc.render.resolution_x, sc.render.resolution_y = 480, 600
sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = OUT
bpy.ops.render.render(write_still=True); print("THUMB_DONE", OUT)

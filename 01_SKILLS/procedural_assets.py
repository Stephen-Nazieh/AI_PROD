#!/usr/bin/env python3
"""
procedural_assets.py — Reusable Procedural Geometry Nodes Presets

Generates Blender .blend files with pre-built procedural assets:
trees, crowds, clouds, water, cities, grass, rocks, fire, smoke.

Usage:
    python procedural_assets.py init-library
    python procedural_assets.py generate <preset_name> --output path.blend
    python procedural_assets.py import <project_slug> --preset trees --count 10

Presets:
    trees      — Geometry nodes forest with wind animation
    clouds     — Volumetric cloud fields with drift
    water      — Animated ocean/water surface
    city       — Procedural building blocks
    grass      — Wind-swept grass field
    rocks      — Scattered rocky terrain
    crowd      — Instanced animated figures
    fire       — Procedural fire + smoke
"""

import argparse
import json
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
PRESET_LIBRARY = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "procedural-presets"

PRESETS = {
    "trees": "Procedural forest with trunk, branches, leaves, and wind sway",
    "clouds": "Volumetric cloud volumes with noise-based shape and drift",
    "water": "Animated ocean mesh with wave displacement",
    "city": "Grid-based building generator with random height/width",
    "grass": "Hair/particle grass with wind force field",
    "rocks": "Scattered rock instances on terrain with noise",
    "crowd": "Instanced human figures with random offsets",
    "fire": "Procedural fire using emission + smoke domain",
}


def init_library() -> dict:
    PRESET_LIBRARY.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "presets": PRESETS,
        "note": "Each preset is a standalone .blend file with geometry nodes.",
    }
    (PRESET_LIBRARY / "preset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "ok", "library_dir": str(PRESET_LIBRARY), "presets": len(PRESETS)}


def generate_preset_script(preset: str) -> str:
    """Generate a Blender Python script for a procedural preset."""
    
    if preset == "trees":
        return '''
import bpy
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# Tree trunk
bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=4, location=(0, 0, 2))
trunk = bpy.context.active_object
trunk.name = "TreeTrunk"

# Branches via geometry nodes
bpy.ops.mesh.primitive_ico_sphere_add(radius=0.1, location=(0, 0, 4))
branch = bpy.context.active_object
branch.name = "BranchEmitter"

# Add geometry nodes modifier
mod = branch.modifiers.new(name="TreeGen", type="NODES")
node_group = bpy.data.node_groups.new(name="TreeGenNodes", type="GeometryNodeTree")
mod.node_group = node_group

# Basic node setup
in_node = node_group.nodes.new("NodeGroupInput")
out_node = node_group.nodes.new("NodeGroupOutput")
instance = node_group.nodes.new("GeometryNodeInstanceOnPoints")
scale = node_group.nodes.new("GeometryNodeRandomValue")
scale.data_type = "FLOAT_VECTOR"
scale.inputs["Min"].default_value = (0.8, 0.8, 0.8)
scale.inputs["Max"].default_value = (1.5, 1.5, 1.5)

# Create leaf object
bpy.ops.mesh.primitive_ico_sphere_add(radius=0.5, location=(2, 0, 4))
leaf = bpy.context.active_object
leaf.name = "Leaf"

instance.inputs["Instance"].default_value = leaf
node_group.links.new(in_node.outputs[0], instance.inputs["Points"])
node_group.links.new(scale.outputs["Value"], instance.inputs["Scale"])
node_group.links.new(instance.outputs["Instances"], out_node.inputs["Geometry"])

# Wind force field
bpy.ops.object.effector_add(type="WIND", location=(0, -5, 3))
wind = bpy.context.active_object
wind.field.strength = 2.0

bpy.ops.wm.save_as_mainfile(filepath=r"''' + str(PRESET_LIBRARY / "trees.blend") + '''")
'''

    elif preset == "clouds":
        return '''
import bpy
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# Cloud volume
bpy.ops.mesh.primitive_cube_add(size=10, location=(0, 0, 5))
cloud = bpy.context.active_object
cloud.name = "CloudField"

# Add volume scatter material
mat = bpy.data.materials.new(name="CloudMaterial")
mat.use_nodes = True
nodes = mat.node_tree.nodes
nodes.clear()

output = nodes.new("ShaderNodeOutputMaterial")
scatter = nodes.new("ShaderNodeVolumeScatter")
scatter.inputs["Density"].default_value = 5.0

tex = nodes.new("ShaderNodeTexNoise")
tex.inputs["Scale"].default_value = 3.0
tex.inputs["Detail"].default_value = 8.0

mat.node_tree.links.new(tex.outputs["Fac"], scatter.inputs["Density"])
mat.node_tree.links.new(scatter.outputs["Volume"], output.inputs["Volume"])
cloud.data.materials.append(mat)

# Animate texture offset
for f in range(1, 250):
    cloud.location.x = f * 0.02
    cloud.keyframe_insert(data_path="location", frame=f)

bpy.ops.wm.save_as_mainfile(filepath=r"''' + str(PRESET_LIBRARY / "clouds.blend") + '''")
'''

    elif preset == "water":
        return '''
import bpy
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# Ocean plane
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
water = bpy.context.active_object
water.name = "Ocean"

# Add ocean modifier
ocean = water.modifiers.new(name="Ocean", type="OCEAN")
ocean.wave_scale = 1.5
ocean.choppiness = 1.0
ocean.wind_velocity = 15.0

# Animate time
for f in range(1, 250):
    ocean.time = f * 0.1
    ocean.keyframe_insert(data_path="time", frame=f)

# Water material
mat = bpy.data.materials.new(name="Water")
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.05, 0.15, 0.3, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.1
    bsdf.inputs["IOR"].default_value = 1.33
water.data.materials.append(mat)

bpy.ops.wm.save_as_mainfile(filepath=r"''' + str(PRESET_LIBRARY / "water.blend") + '''")
'''

    elif preset == "city":
        return '''
import bpy, random
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# Ground
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "CityGround"

# Building blocks
for i in range(50):
    x = random.uniform(-8, 8)
    y = random.uniform(-8, 8)
    w = random.uniform(0.5, 2.0)
    d = random.uniform(0.5, 2.0)
    h = random.uniform(2.0, 8.0)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, h/2))
    building = bpy.context.active_object
    building.scale = (w, d, h)
    building.name = f"Building_{i:03d}"

bpy.ops.wm.save_as_mainfile(filepath=r"''' + str(PRESET_LIBRARY / "city.blend") + '''")
'''

    elif preset == "grass":
        return '''
import bpy
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# Ground
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "GrassField"

# Particle system for grass
part = ground.modifiers.new(name="GrassParticles", type="PARTICLE_SYSTEM")
psys = ground.particle_systems[0]
psys.settings.type = "HAIR"
psys.settings.count = 10000
psys.settings.hair_length = 0.5
psys.settings.child_type = "SIMPLE"
psys.settings.rendered_child_count = 50

# Wind
bpy.ops.object.effector_add(type="WIND", location=(0, -5, 2))
wind = bpy.context.active_object
wind.field.strength = 1.5

bpy.ops.wm.save_as_mainfile(filepath=r"''' + str(PRESET_LIBRARY / "grass.blend") + '''")
'''

    elif preset == "rocks":
        return '''
import bpy, random
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# Terrain
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
terrain = bpy.context.active_object
terrain.name = "Terrain"

# Displace modifier
subsurf = terrain.modifiers.new(name="Subsurf", type="SUBSURF")
subsurf.levels = 4
disp = terrain.modifiers.new(name="Displacement", type="DISPLACE")
tex = bpy.data.textures.new(name="RockNoise", type="MARBLE")
tex.noise_scale = 2.0
disp.texture = tex
disp.strength = 2.0

# Rock instances
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.5, location=(0, 0, 0))
rock_template = bpy.context.active_object
rock_template.name = "RockTemplate"

for i in range(30):
    x = random.uniform(-8, 8)
    y = random.uniform(-8, 8)
    z = random.uniform(0.5, 2.0)
    s = random.uniform(0.3, 1.5)
    rock = rock_template.copy()
    rock.data = rock_template.data.copy()
    rock.location = (x, y, z)
    rock.scale = (s, s, s * 0.7)
    bpy.context.collection.objects.link(rock)

bpy.ops.wm.save_as_mainfile(filepath=r"''' + str(PRESET_LIBRARY / "rocks.blend") + '''")
'''

    elif preset == "crowd":
        return '''
import bpy, random
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# Simple human figure
bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=1.6, location=(0, 0, 0.8))
body = bpy.context.active_object
body.name = "CrowdBody"

bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(0, 0, 1.8))
head = bpy.context.active_object
head.name = "CrowdHead"

# Join
body.select_set(True)
head.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()

figure = bpy.context.active_object
figure.name = "CrowdFigure"

# Instancing
for i in range(20):
    x = random.uniform(-5, 5)
    y = random.uniform(-5, 5)
    rot_z = random.uniform(0, 6.28)
    instance = figure.copy()
    instance.data = figure.data.copy()
    instance.location = (x, y, 0)
    instance.rotation_euler = (0, 0, rot_z)
    bpy.context.collection.objects.link(instance)

bpy.ops.wm.save_as_mainfile(filepath=r"''' + str(PRESET_LIBRARY / "crowd.blend") + '''")
'''

    elif preset == "fire":
        return '''
import bpy
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()

# Smoke domain
bpy.ops.mesh.primitive_cube_add(size=4, location=(0, 0, 2))
domain = bpy.context.active_object
domain.name = "SmokeDomain"

# Add smoke modifier
smoke = domain.modifiers.new(name="Smoke", type="FLUID")
smoke.fluid_type = "DOMAIN"
smoke.domain_settings.domain_type = "GAS"
smoke.domain_settings.resolution_max = 64

# Emitter
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0.1))
emitter = bpy.context.active_object
emitter.name = "FireEmitter"

fluid = emitter.modifiers.new(name="Fluid", type="FLUID")
fluid.fluid_type = "FLOW"
fluid.flow_settings.flow_type = "FIRE_SMOKE"
fluid.flow_settings.fuel_amount = 1.0

# Animate emitter
for f in range(1, 250):
    emitter.scale = (1.0 + 0.3 * (f % 10) / 10, 1.0 + 0.3 * (f % 10) / 10, 1.0)
    emitter.keyframe_insert(data_path="scale", frame=f)

bpy.ops.wm.save_as_mainfile(filepath=r"''' + str(PRESET_LIBRARY / "fire.blend") + '''")
'''

    else:
        return None


def generate_preset(preset: str) -> dict:
    if preset not in PRESETS:
        return {"status": "error", "message": f"Unknown preset: {preset}. Choose from {list(PRESETS.keys())}"}
    
    script = generate_preset_script(preset)
    if not script:
        return {"status": "error", "message": "Failed to generate script"}
    
    script_path = PRESET_LIBRARY / f"_{preset}_gen.py"
    script_path.write_text(script, encoding="utf-8")
    
    # Run in Blender
    try:
        subprocess.run([BLENDER, "--background", "--python", str(script_path)],
                       capture_output=True, timeout=60, check=True)
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Blender timed out"}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": f"Blender error: {e.stderr.decode()[:200]}"}
    
    blend_path = PRESET_LIBRARY / f"{preset}.blend"
    return {"status": "ok", "preset": preset, "blend": str(blend_path)}


def import_preset(project_slug: str, preset: str, count: int = 1) -> dict:
    blend_path = PRESET_LIBRARY / f"{preset}.blend"
    if not blend_path.exists():
        result = generate_preset(preset)
        if result["status"] != "ok":
            return result
    
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    layout_path = project_dir / "03-layout" / "layout.blend"
    
    # Build Blender import script
    import_script = f'''
import bpy
bpy.ops.wm.open_mainfile(filepath=r"{str(layout_path)}")

with bpy.data.libraries.load(r"{str(blend_path)}", link=False) as (data_from, data_to):
    data_to.objects = [name for name in data_from.objects if name]

for obj in data_to.objects:
    if obj is not None:
        bpy.context.collection.objects.link(obj)

bpy.ops.wm.save_as_mainfile(filepath=r"{str(layout_path)}")
'''
    script_path = PRESET_LIBRARY / f"_{preset}_import.py"
    script_path.write_text(import_script, encoding="utf-8")
    
    try:
        subprocess.run([BLENDER, "--background", "--python", str(script_path)],
                       capture_output=True, timeout=60, check=True)
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
    return {"status": "ok", "preset": preset, "project": project_slug, "imported": count}


def main():
    parser = argparse.ArgumentParser(description="Procedural Assets")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-library", help="Create preset library")

    p_gen = sub.add_parser("generate", help="Generate a preset .blend")
    p_gen.add_argument("preset", choices=list(PRESETS.keys()))

    p_imp = sub.add_parser("import", help="Import preset into project")
    p_imp.add_argument("project_slug")
    p_imp.add_argument("--preset", required=True, choices=list(PRESETS.keys()))
    p_imp.add_argument("--count", type=int, default=1)

    args = parser.parse_args()

    if args.command == "init-library":
        print(json.dumps(init_library(), indent=2))
    elif args.command == "generate":
        print(json.dumps(generate_preset(args.preset), indent=2))
    elif args.command == "import":
        print(json.dumps(import_preset(args.project_slug, args.preset, args.count), indent=2))


if __name__ == "__main__":
    main()

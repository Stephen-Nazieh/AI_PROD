#!/usr/bin/env python3
"""
test_suite.py — Automated Pipeline Validation

Runs smoke tests on all pipeline scripts to catch regressions.
Tests import, basic functionality, and output format.

Usage:
    python test_suite.py run
    python test_suite.py run --category 2d
    python test_suite.py run --script animation_2d_compositor
"""

import argparse
import importlib
import importlib.util
import json
import subprocess
import sys
import traceback
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = WORKSPACE_ROOT / "01_SKILLS"

TESTS = {
    "core": ["script_parser", "storyboard_generator", "blender_layout", "blender_set_designer",
             "blender_character_importer", "blender_grease_pencil", "blender_ae_bridge",
             "blender_geometry_nodes_animator", "comfyui_generator", "prompt_refiner",
             "procedural_assets", "asset_manager"],
    "audio": ["auto_dubbing_pipeline", "logic_pro_scorer", "sound_designer", "audio_lipsync",
                "openvoice_cloner", "kokoro_tts"],
    "animation": ["blender_ai_keyframer", "body_mocap", "motion_library", "pose_estimator",
                  "mocap_to_2d", "storyboard_to_2d"],
    "rendering": ["blender_render_dispatcher", "neural_upscaler", "parallel_renderer",
                  "frame_interpolator", "render_queue", "render_scenes"],
    "2d": ["character_2d_generator", "background_2d_generator", "animation_2d_compositor", "lipsync_2d"],
    "editing": ["resolve_auto_editor", "creative_editor", "distribution_formatter",
                "subtitle_generator", "thumbnail_generator"],
    "quality": ["quality_gate", "advanced_color_grader", "auto_color_grader"],
    "mocap": ["arkit_mocap_bridge", "vroid_facial_animator", "vroid_automation"],
    "management": ["episode_manager", "project_dashboard", "build_cache", "asset_acquisition",
                   "pipeline_orchestrator", "preview_player", "error_recovery", "init_project",
                   "curriculum_runner", "init_database", "openclaw_bridge", "skills",
                   "solocorn_cli", "solocorn_media_bridge", "health_check", "start_services",
                   "notify", "asset_cleanup"],
}


def test_import(module_name: str) -> dict:
    """Test that a module can be imported."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, SKILLS_DIR / f"{module_name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return {"status": "pass", "test": "import", "module": module_name}
    except Exception as e:
        return {"status": "fail", "test": "import", "module": module_name, "error": str(e)[:100]}


def test_syntax(module_name: str) -> dict:
    """Test that a module compiles."""
    try:
        import py_compile
        py_compile.compile(SKILLS_DIR / f"{module_name}.py", doraise=True)
        return {"status": "pass", "test": "syntax", "module": module_name}
    except py_compile.PyCompileError as e:
        return {"status": "fail", "test": "syntax", "module": module_name, "error": str(e)[:100]}


def test_functional_init_project() -> dict:
    """Functional test: init_project creates correct directory tree."""
    test_slug = "__test_init_project__"
    test_dir = WORKSPACE_ROOT / "05_PROJECTS" / test_slug
    try:
        # Clean up if exists
        if test_dir.exists():
            import shutil
            shutil.rmtree(test_dir)
        
        python = WORKSPACE_ROOT / "env" / "bin" / "python3"
        script = SKILLS_DIR / "init_project.py"
        result = subprocess.run(
            [str(python), str(script), "create", test_slug, "--title", "Test"],
            capture_output=True, text=True, timeout=30, cwd=WORKSPACE_ROOT,
        )
        
        if result.returncode != 0:
            return {"status": "fail", "test": "functional_init_project", "error": result.stderr[:200]}
        
        # Verify key dirs exist
        expected_dirs = [
            test_dir / "01-scripts",
            test_dir / "05-assets" / "characters_2d",
            test_dir / "06-audio" / "dialogue",
            test_dir / "07-editing",
            test_dir / "09-deliver" / "masters",
        ]
        missing = [str(d) for d in expected_dirs if not d.exists()]
        if missing:
            return {"status": "fail", "test": "functional_init_project", "error": f"Missing dirs: {missing}"}
        
        # Verify config files
        if not (test_dir / "01-scripts" / "shot-list.json").exists():
            return {"status": "fail", "test": "functional_init_project", "error": "shot-list.json missing"}
        
        return {"status": "pass", "test": "functional_init_project"}
    except Exception as e:
        return {"status": "fail", "test": "functional_init_project", "error": str(e)[:200]}
    finally:
        if test_dir.exists():
            import shutil
            shutil.rmtree(test_dir)


def test_functional_orchestrator_dry_run() -> dict:
    """Functional test: pipeline orchestrator dry-run completes 14 steps."""
    test_slug = "__test_orchestrator__"
    test_dir = WORKSPACE_ROOT / "05_PROJECTS" / test_slug
    try:
        # Create project first
        python = WORKSPACE_ROOT / "env" / "bin" / "python3"
        init_script = SKILLS_DIR / "init_project.py"
        subprocess.run(
            [str(python), str(init_script), "create", test_slug, "--title", "Test"],
            capture_output=True, timeout=30, cwd=WORKSPACE_ROOT,
        )
        
        orch_script = SKILLS_DIR / "pipeline_orchestrator.py"
        result = subprocess.run(
            [str(python), str(orch_script), "dry-run", test_slug, "--mode", "2d", "--title", "Test"],
            capture_output=True, text=True, timeout=60, cwd=WORKSPACE_ROOT,
        )
        
        if result.returncode != 0:
            return {"status": "fail", "test": "functional_orchestrator_dry_run", "error": result.stderr[:200]}
        
        if "14/14 steps successful" not in result.stdout:
            return {"status": "fail", "test": "functional_orchestrator_dry_run", "error": "Did not complete 14 steps"}
        
        return {"status": "pass", "test": "functional_orchestrator_dry_run"}
    except Exception as e:
        return {"status": "fail", "test": "functional_orchestrator_dry_run", "error": str(e)[:200]}
    finally:
        if test_dir.exists():
            import shutil
            shutil.rmtree(test_dir)


def test_functional_health_check() -> dict:
    """Functional test: health_check runs and produces valid output."""
    try:
        python = WORKSPACE_ROOT / "env" / "bin" / "python3"
        script = SKILLS_DIR / "health_check.py"
        result = subprocess.run(
            [str(python), str(script), "--json"],
            capture_output=True, text=True, timeout=30, cwd=WORKSPACE_ROOT,
        )
        if result.returncode not in (0, 1):
            return {"status": "fail", "test": "functional_health_check", "error": f"exit code {result.returncode}"}
        
        try:
            data = json.loads(result.stdout)
        except Exception as e:
            return {"status": "fail", "test": "functional_health_check", "error": f"JSON parse error: {e}"}
        if "summary" not in data:
            return {"status": "fail", "test": "functional_health_check", "error": "missing summary in output"}
        if "mlx_servers" not in data:
            return {"status": "fail", "test": "functional_health_check", "error": "missing mlx_servers in output"}
        
        return {"status": "pass", "test": "functional_health_check"}
    except Exception as e:
        return {"status": "fail", "test": "functional_health_check", "error": str(e)[:200]}


def test_functional_start_services_status() -> dict:
    """Functional test: start_services --status runs without crashing."""
    try:
        python = WORKSPACE_ROOT / "env" / "bin" / "python3"
        script = SKILLS_DIR / "start_services.py"
        result = subprocess.run(
            [str(python), str(script), "--status"],
            capture_output=True, text=True, timeout=15, cwd=WORKSPACE_ROOT,
        )
        if "Service Status" not in result.stdout and "mlx_llama4" not in result.stdout:
            return {"status": "fail", "test": "functional_start_services_status", "error": "unexpected output"}
        return {"status": "pass", "test": "functional_start_services_status"}
    except Exception as e:
        return {"status": "fail", "test": "functional_start_services_status", "error": str(e)[:200]}


def test_functional_3d_render() -> dict:
    """Verify Blender can render a minimal 3D scene."""
    try:
        out_path = WORKSPACE_ROOT / "03_ASSETS" / "test_3d_suite.png"
        expr = '''
import bpy
for obj in list(bpy.data.objects):
    if obj.name in ["Cube", "Light", "Camera"]:
        bpy.data.objects.remove(obj, do_unlink=True)
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
cube = bpy.context.active_object
mat = bpy.data.materials.new(name="TestMat")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.8, 0.3, 0.2, 1.0)
cube.data.materials.append(mat)
bpy.ops.object.light_add(type="SUN", location=(5, 5, 10))
sun = bpy.context.active_object
sun.data.energy = 5.0
bpy.ops.object.camera_add(location=(0, -6, 3))
cam = bpy.context.active_object
cam.rotation_euler = (1.3, 0, 0)
bpy.context.scene.camera = cam
bpy.context.scene.render.engine = "BLENDER_EEVEE"
bpy.context.scene.render.resolution_x = 640
bpy.context.scene.render.resolution_y = 360
bpy.context.scene.render.filepath = "''' + str(out_path) + '''"
bpy.context.scene.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)
print("3D_RENDER_OK")
'''
        result = subprocess.run(
            ["/Applications/Blender.app/Contents/MacOS/Blender", "--background", "--python-expr", expr],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {"status": "fail", "test": "functional_3d_render", "error": result.stderr[:200]}
        if not out_path.exists():
            return {"status": "fail", "test": "functional_3d_render", "error": "Output PNG not created"}
        if out_path.stat().st_size < 1000:
            return {"status": "fail", "test": "functional_3d_render", "error": "Output PNG too small"}
        out_path.unlink(missing_ok=True)
        return {"status": "pass", "test": "functional_3d_render"}
    except Exception as e:
        return {"status": "fail", "test": "functional_3d_render", "error": str(e)[:200]}


def test_functional_error_recovery() -> dict:
    """Functional test: error_recovery creates and reads state file."""
    test_slug = "__test_error_recovery__"
    test_dir = WORKSPACE_ROOT / "05_PROJECTS" / test_slug
    try:
        python = WORKSPACE_ROOT / "env" / "bin" / "python3"
        init_script = SKILLS_DIR / "init_project.py"
        subprocess.run(
            [str(python), str(init_script), "create", test_slug, "--title", "Test"],
            capture_output=True, timeout=30, cwd=WORKSPACE_ROOT,
        )
        
        # Import and test directly
        spec = importlib.util.spec_from_file_location("error_recovery", SKILLS_DIR / "error_recovery.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["error_recovery"] = mod
        spec.loader.exec_module(mod)
        
        # Initialize state
        init_result = mod.init_state(test_slug)
        if init_result["status"] != "ok":
            return {"status": "fail", "test": "functional_error_recovery", "error": "init_state failed"}
        
        status = mod.get_status(test_slug)
        
        if "steps" not in status:
            return {"status": "fail", "test": "functional_error_recovery", "error": "No steps in status"}
        if len(status["steps"]) != 14:
            return {"status": "fail", "test": "functional_error_recovery", "error": f"Expected 14 steps, got {len(status['steps'])}"}
        
        # Test mark_step
        mod.mark_step(test_slug, "ingest", "completed")
        status2 = mod.get_status(test_slug)
        if status2["steps"]["ingest"]["status"] != "completed":
            return {"status": "fail", "test": "functional_error_recovery", "error": "mark_step did not update status"}
        
        return {"status": "pass", "test": "functional_error_recovery"}
    except Exception as e:
        return {"status": "fail", "test": "functional_error_recovery", "error": str(e)[:200]}
    finally:
        if test_dir.exists():
            import shutil
            shutil.rmtree(test_dir)


def run_tests(category: str = None, script_name: str = None) -> dict:
    """Run all tests."""
    modules_to_test = []
    
    if script_name:
        modules_to_test = [script_name]
    elif category:
        modules_to_test = TESTS.get(category, [])
    else:
        for cat_list in TESTS.values():
            modules_to_test.extend(cat_list)
    
    results = []
    passed = 0
    failed = 0
    
    for mod in modules_to_test:
        path = SKILLS_DIR / f"{mod}.py"
        if not path.exists():
            results.append({"status": "skip", "module": mod, "reason": "file not found"})
            continue
        
        # Syntax test
        r = test_syntax(mod)
        results.append(r)
        if r["status"] == "pass":
            passed += 1
        else:
            failed += 1
        
        # Import test
        r = test_import(mod)
        results.append(r)
        if r["status"] == "pass":
            passed += 1
        else:
            failed += 1
    
    # Run functional/integration tests if no specific category/script or if "integration" category
    if not script_name and (not category or category == "integration"):
        for func_test in [test_functional_init_project, test_functional_orchestrator_dry_run, test_functional_error_recovery, test_functional_health_check, test_functional_start_services_status, test_functional_3d_render]:
            r = func_test()
            results.append(r)
            if r["status"] == "pass":
                passed += 1
            else:
                failed += 1
    
    return {
        "status": "ok",
        "total": len([r for r in results if r["status"] != "skip"]),
        "passed": passed,
        "failed": failed,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("--category")
    parser.add_argument("--script")
    args = parser.parse_args()
    
    result = run_tests(args.category, args.script)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["failed"] == 0 else 1)

if __name__ == "__main__":
    main()

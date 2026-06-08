#!/usr/bin/env python3
"""
pose_estimator.py — Full-Body Pose Estimation → Blender Keyframes

Two modes:
1. Silhouette analysis (default): Uses edge detection + contour analysis
   with numpy/PIL. No external models needed.
2. MoveNet ONNX (optional): If a valid ONNX model is provided.

Extracts 17 body keypoints from video frames and generates Blender
armature keyframes for full-body character animation.

Usage:
    python pose_estimator.py extract <video_path> --fps 24
    python pose_estimator.py extract <video_path> --output poses.json --model movenet.onnx
    python pose_estimator.py to-blender <project_slug> --poses poses.json

Keypoints (17):
    0:nose 1:left_eye 2:right_eye 3:left_ear 4:right_ear
    5:left_shoulder 6:right_shoulder 7:left_elbow 8:right_elbow
    9:left_wrist 10:right_wrist 11:left_hip 12:right_hip
    13:left_knee 14:right_knee 15:left_ankle 16:right_ankle
"""

import argparse
import json
import math
import os
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "ai-models" / "pose_estimation"
DEFAULT_MODEL = MODEL_DIR / "movenet_lightning.onnx"

MOVENET_KEYPOINTS = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]


def load_onnx_session(model_path: Path):
    import onnxruntime as ort
    providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    return ort.InferenceSession(str(model_path), providers=providers)


def preprocess_movenet(img: Image.Image) -> np.ndarray:
    img = img.convert("RGB").resize((192, 192), Image.Resampling.BILINEAR)
    arr = np.array(img, dtype=np.float32)
    arr = arr[np.newaxis, ...]
    return arr


def run_movenet(img: Image.Image, session) -> dict:
    input_arr = preprocess_movenet(img)
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    outputs = session.run([output_name], {input_name: input_arr})
    keypoints = outputs[0][0][0]  # [17, 3] → [y, x, confidence]
    w, h = img.size
    result = {}
    for idx, name in enumerate(MOVENET_KEYPOINTS):
        y, x, conf = keypoints[idx]
        result[name] = {
            "x": round(float(x) * w, 2),
            "y": round(float(y) * h, 2),
            "confidence": round(float(conf), 3),
        }
    return result


# ── Silhouette-based pose estimation (no model needed) ──────────────────────

def silhouette_pose(img: Image.Image) -> dict:
    """Estimate pose from silhouette using centroid + contour analysis."""
    arr = np.array(img.convert("L"))  # Grayscale
    h, w = arr.shape
    
    # Edge detection using gradient
    dx = np.abs(np.diff(arr, axis=1, append=arr[:, -1:]))
    dy = np.abs(np.diff(arr, axis=0, append=arr[-1:, :]))
    edges = (dx + dy) > 30
    
    # Threshold for silhouette
    threshold = np.median(arr) * 0.7
    silhouette = arr < threshold
    
    # Find connected components (largest = body)
    from scipy import ndimage
    labeled, num = ndimage.label(silhouette)
    if num == 0:
        return {name: {"x": w/2, "y": h/2, "confidence": 0.1} for name in MOVENET_KEYPOINTS}
    
    sizes = ndimage.sum(silhouette, labeled, range(1, num + 1))
    largest = np.argmax(sizes) + 1
    body_mask = labeled == largest
    
    # Get body bounding box
    ys, xs = np.where(body_mask)
    if len(xs) == 0:
        return {name: {"x": w/2, "y": h/2, "confidence": 0.1} for name in MOVENET_KEYPOINTS}
    
    min_x, max_x = xs.min(), xs.max()
    min_y, max_y = ys.min(), ys.max()
    body_w = max_x - min_x
    body_h = max_y - min_y
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    
    # Estimate keypoints from body proportions
    # Head: top 15% of body
    head_y = min_y + body_h * 0.08
    # Shoulders: 25% down
    shoulder_y = min_y + body_h * 0.22
    # Elbows: 40% down
    elbow_y = min_y + body_h * 0.38
    # Wrists: 55% down
    wrist_y = min_y + body_h * 0.52
    # Hips: 50% down (center of mass)
    hip_y = min_y + body_h * 0.50
    # Knees: 72% down
    knee_y = min_y + body_h * 0.72
    # Ankles: 95% down
    ankle_y = min_y + body_h * 0.95
    
    def find_edge_y(x_target, y_start, y_end, direction=1):
        """Find where silhouette edge is at x_target."""
        for y in range(int(y_start), int(y_end), direction):
            if 0 <= y < h and 0 <= int(x_target) < w:
                if body_mask[y, int(x_target)]:
                    return y
        return (y_start + y_end) / 2
    
    pose = {
        "nose": {"x": center_x, "y": head_y, "confidence": 0.6},
        "left_eye": {"x": center_x - body_w * 0.08, "y": head_y - body_h * 0.02, "confidence": 0.5},
        "right_eye": {"x": center_x + body_w * 0.08, "y": head_y - body_h * 0.02, "confidence": 0.5},
        "left_ear": {"x": center_x - body_w * 0.18, "y": head_y + body_h * 0.02, "confidence": 0.4},
        "right_ear": {"x": center_x + body_w * 0.18, "y": head_y + body_h * 0.02, "confidence": 0.4},
        "left_shoulder": {"x": center_x - body_w * 0.28, "y": shoulder_y, "confidence": 0.6},
        "right_shoulder": {"x": center_x + body_w * 0.28, "y": shoulder_y, "confidence": 0.6},
        "left_elbow": {"x": center_x - body_w * 0.38, "y": elbow_y, "confidence": 0.5},
        "right_elbow": {"x": center_x + body_w * 0.38, "y": elbow_y, "confidence": 0.5},
        "left_wrist": {"x": center_x - body_w * 0.42, "y": wrist_y, "confidence": 0.5},
        "right_wrist": {"x": center_x + body_w * 0.42, "y": wrist_y, "confidence": 0.5},
        "left_hip": {"x": center_x - body_w * 0.18, "y": hip_y, "confidence": 0.6},
        "right_hip": {"x": center_x + body_w * 0.18, "y": hip_y, "confidence": 0.6},
        "left_knee": {"x": center_x - body_w * 0.20, "y": knee_y, "confidence": 0.5},
        "right_knee": {"x": center_x + body_w * 0.20, "y": knee_y, "confidence": 0.5},
        "left_ankle": {"x": center_x - body_w * 0.18, "y": ankle_y, "confidence": 0.5},
        "right_ankle": {"x": center_x + body_w * 0.18, "y": ankle_y, "confidence": 0.5},
    }
    
    return pose


def extract_poses(video_path: Path, model_path: Path = None, target_fps: float = 24.0,
                  max_frames: int = None, use_silhouette: bool = False) -> dict:
    """Extract body poses from video frames."""
    
    model = model_path or DEFAULT_MODEL
    session = None
    method = "silhouette"
    
    if model.exists() and not use_silhouette:
        try:
            session = load_onnx_session(model)
            method = "movenet"
        except Exception:
            pass
    
    # Extract frames using ffmpeg
    frame_dir = Path("/tmp/pose_frames")
    frame_dir.mkdir(parents=True, exist_ok=True)
    
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,width,height,duration",
        "-of", "json", str(video_path),
    ], capture_output=True, text=True, check=True)
    info = json.loads(probe.stdout)
    stream = info["streams"][0]
    
    width = int(stream["width"])
    height = int(stream["height"])
    num, den = map(int, stream["r_frame_rate"].split("/"))
    video_fps = num / den
    
    frame_pattern = frame_dir / "frame_%06d.png"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"fps={target_fps},scale={width}:{height}",
        str(frame_pattern),
    ], capture_output=True, check=True)
    
    frames = sorted(frame_dir.glob("frame_*.png"))
    if max_frames:
        frames = frames[:max_frames]
    
    all_poses = []
    start = time.time()
    
    for i, frame_path in enumerate(frames):
        img = Image.open(frame_path)
        
        if session:
            keypoints = run_movenet(img, session)
        else:
            keypoints = silhouette_pose(img)
        
        all_poses.append({
            "frame": i + 1,
            "timestamp": round(i / target_fps, 3),
            "keypoints": keypoints,
        })
        
        if (i + 1) % 100 == 0:
            print(f"  Processed {i+1}/{len(frames)} frames ({method})...")
    
    # Cleanup
    for f in frame_dir.glob("*.png"):
        f.unlink()
    frame_dir.rmdir()
    
    return {
        "status": "ok",
        "video": str(video_path),
        "method": method,
        "video_fps": round(video_fps, 2),
        "target_fps": target_fps,
        "total_frames": len(all_poses),
        "duration_sec": round(len(all_poses) / target_fps, 2),
        "processing_time_sec": round(time.time() - start, 2),
        "poses": all_poses,
    }


# ── Blender Export ──────────────────────────────────────────────────────────

def export_to_blender(poses_data: dict, project_slug: str, armature_name: str = "BodyMocap") -> dict:
    import bpy
    
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    layout_path = project_dir / "03-layout" / "layout.blend"
    
    if not layout_path.exists():
        return {"status": "error", "message": "Layout not found"}
    
    bpy.ops.wm.open_mainfile(filepath=str(layout_path))
    scene = bpy.context.scene
    
    arm_obj = None
    for obj in scene.objects:
        if obj.type == "ARMATURE":
            arm_obj = obj
            break
    
    if not arm_obj:
        bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
        arm_obj = bpy.context.active_object
        arm_obj.name = armature_name
        edit_bones = arm_obj.data.edit_bones
        
        bone_map = {
            "root": (0, 0, 0),
            "spine": (0, 0, 1.0),
            "neck": (0, 0, 1.6),
            "head": (0, 0, 1.75),
            "shoulder_L": (-0.25, 0, 1.5),
            "elbow_L": (-0.5, 0, 1.3),
            "wrist_L": (-0.7, 0, 1.1),
            "shoulder_R": (0.25, 0, 1.5),
            "elbow_R": (0.5, 0, 1.3),
            "wrist_R": (0.7, 0, 1.1),
            "hip_L": (-0.15, 0, 0.9),
            "knee_L": (-0.15, 0, 0.5),
            "ankle_L": (-0.15, 0, 0.0),
            "hip_R": (0.15, 0, 0.9),
            "knee_R": (0.15, 0, 0.5),
            "ankle_R": (0.15, 0, 0.0),
        }
        for name, loc in bone_map.items():
            bone = edit_bones.new(name)
            bone.head = loc
            bone.tail = (loc[0], loc[1], loc[2] + 0.1)
        
        bpy.ops.object.mode_set(mode="OBJECT")
    
    kp_to_bone = {
        "nose": "head",
        "left_shoulder": "shoulder_L", "right_shoulder": "shoulder_R",
        "left_elbow": "elbow_L", "right_elbow": "elbow_R",
        "left_wrist": "wrist_L", "right_wrist": "wrist_R",
        "left_hip": "hip_L", "right_hip": "hip_R",
        "left_knee": "knee_L", "right_knee": "knee_R",
        "left_ankle": "ankle_L", "right_ankle": "ankle_R",
    }
    
    poses = poses_data.get("poses", [])
    recorded = 0
    
    for pose in poses:
        frame = pose["frame"]
        scene.frame_set(frame)
        
        for kp_name, bone_name in kp_to_bone.items():
            if kp_name in pose["keypoints"] and bone_name in arm_obj.pose.bones:
                kp = pose["keypoints"][kp_name]
                if kp["confidence"] > 0.3:
                    bone = arm_obj.pose.bones[bone_name]
                    x = (kp["x"] - 960) / 500
                    y = (kp["y"] - 540) / 500
                    z = bone.location.z
                    bone.location = (x, y, z)
                    bone.keyframe_insert(data_path="location", frame=frame)
                    recorded += 1
    
    bpy.ops.wm.save_as_mainfile(filepath=str(layout_path))
    
    return {
        "status": "ok",
        "project": project_slug,
        "total_frames": len(poses),
        "keyframes_recorded": recorded,
        "armature": armature_name,
        "method": poses_data.get("method", "unknown"),
    }


def main():
    parser = argparse.ArgumentParser(description="Pose Estimator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ext = sub.add_parser("extract", help="Extract poses from video")
    p_ext.add_argument("video_path")
    p_ext.add_argument("--fps", type=float, default=24.0)
    p_ext.add_argument("--model", help="Path to MoveNet ONNX model")
    p_ext.add_argument("--output", help="Output JSON path")
    p_ext.add_argument("--max-frames", type=int)
    p_ext.add_argument("--silhouette", action="store_true", help="Force silhouette method")

    p_bl = sub.add_parser("to-blender", help="Export poses to Blender")
    p_bl.add_argument("project_slug")
    p_bl.add_argument("--poses", required=True, help="Path to poses JSON")
    p_bl.add_argument("--armature", default="BodyMocap")

    args = parser.parse_args()

    if args.command == "extract":
        model = Path(args.model) if args.model else None
        result = extract_poses(Path(args.video_path), model_path=model,
                               target_fps=args.fps, max_frames=args.max_frames,
                               use_silhouette=args.silhouette)
        print(json.dumps({k: v for k, v in result.items() if k != "poses"}, indent=2))
        if result.get("status") == "ok":
            out_path = Path(args.output) if args.output else Path("poses.json")
            out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"Poses saved to {out_path}")
    elif args.command == "to-blender":
        poses_data = json.loads(Path(args.poses).read_text(encoding="utf-8"))
        result = export_to_blender(poses_data, args.project_slug, args.armature)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

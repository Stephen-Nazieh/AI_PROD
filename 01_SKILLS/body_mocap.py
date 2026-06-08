#!/usr/bin/env python3
"""
body_mocap.py — MediaPipe Full-Body Mocap → Joint Rotations → Blender Keyframes

Extracts 33 MediaPipe body landmarks from video, computes 3D joint angles,
and generates Blender armature keyframes with proper bone rotations.

Usage:
    python body_mocap.py extract <video_path> --fps 24 --output mocap.json
    python body_mocap.py to-blender <project_slug> --mocap mocap.json
    python body_mocap.py batch <project_slug> --video path/to/performance.mp4

Landmarks (33):
    0:nose 1:left_eye_inner 2:left_eye 3:left_eye_outer 4:right_eye_inner
    5:right_eye 6:right_eye_outer 7:left_ear 8:right_ear 9:mouth_left
    10:mouth_right 11:left_shoulder 12:right_shoulder 13:left_elbow
    14:right_elbow 15:left_wrist 16:right_wrist 17:left_pinky
    18:right_pinky 19:left_index 20:right_index 21:left_thumb
    22:right_thumb 23:left_hip 24:right_hip 25:left_knee
    26:right_knee 27:left_ankle 28:right_ankle 29:left_heel
    30:right_heel 31:left_foot_index 32:right_foot_index
"""

import argparse
import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = WORKSPACE_ROOT / "06_SHARED_ASSETS" / "ai-models" / "mediapipe" / "pose_landmarker_full.task"

# MediaPipe landmark indices
MP = {
    "nose": 0,
    "left_shoulder": 11, "right_shoulder": 12,
    "left_elbow": 13, "right_elbow": 14,
    "left_wrist": 15, "right_wrist": 16,
    "left_hip": 23, "right_hip": 24,
    "left_knee": 25, "right_knee": 26,
    "left_ankle": 27, "right_ankle": 28,
    "left_heel": 29, "right_heel": 30,
    "left_foot_index": 31, "right_foot_index": 32,
}


def angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    """Angle in degrees between two vectors."""
    cos = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8)
    return math.degrees(math.acos(np.clip(cos, -1.0, 1.0)))


def vector(p1: dict, p2: dict) -> np.ndarray:
    """Vector from p1 to p2 using world coordinates."""
    return np.array([p2["x"] - p1["x"], p2["y"] - p1["y"], p2["z"] - p1["z"]])


def compute_joint_angles(landmarks: list) -> dict:
    """Compute joint angles from MediaPipe landmarks."""
    lm = {name: landmarks[idx] for name, idx in MP.items()}
    
    angles = {}
    
    # Shoulder angles (arm relative to torso)
    for side in ["left", "right"]:
        shoulder = lm[f"{side}_shoulder"]
        elbow = lm[f"{side}_elbow"]
        wrist = lm[f"{side}_wrist"]
        hip = lm[f"{side}_hip"]
        
        # Upper arm vector
        upper_arm = vector(shoulder, elbow)
        # Forearm vector
        forearm = vector(elbow, wrist)
        # Torso vector
        torso = vector(hip, shoulder)
        
        # Elbow bend
        angles[f"{side}_elbow_bend"] = angle_between(upper_arm, forearm)
        # Shoulder forward/back
        angles[f"{side}_shoulder_forward"] = angle_between(torso, upper_arm)
        # Shoulder outward
        angles[f"{side}_shoulder_outward"] = math.degrees(math.atan2(upper_arm[0], upper_arm[2]))
    
    # Hip/knee angles
    for side in ["left", "right"]:
        hip = lm[f"{side}_hip"]
        knee = lm[f"{side}_knee"]
        ankle = lm[f"{side}_ankle"]
        
        thigh = vector(hip, knee)
        shin = vector(knee, ankle)
        
        # Knee bend
        angles[f"{side}_knee_bend"] = angle_between(thigh, shin)
        # Hip forward/back
        angles[f"{side}_hip_forward"] = math.degrees(math.atan2(thigh[2], thigh[1]))
        # Hip outward
        angles[f"{side}_hip_outward"] = math.degrees(math.atan2(thigh[0], thigh[2]))
    
    # Spine twist (from shoulders)
    left_s = lm["left_shoulder"]
    right_s = lm["right_shoulder"]
    angles["spine_twist"] = math.degrees(math.atan2(right_s["z"] - left_s["z"], right_s["x"] - left_s["x"]))
    
    # Head tilt (nose relative to shoulders)
    nose = lm["nose"]
    shoulder_mid = {
        "x": (left_s["x"] + right_s["x"]) / 2,
        "y": (left_s["y"] + right_s["y"]) / 2,
        "z": (left_s["z"] + right_s["z"]) / 2,
    }
    head_vec = vector(shoulder_mid, nose)
    angles["head_tilt_x"] = math.degrees(math.atan2(head_vec[0], head_vec[1]))
    angles["head_tilt_z"] = math.degrees(math.atan2(head_vec[2], head_vec[1]))
    
    return angles


def extract_mocap(video_path: Path, target_fps: float = 24.0, max_frames: int = None) -> dict:
    """Extract full-body mocap from video using MediaPipe."""
    import mediapipe as mp
    from mediapipe.tasks.python.core.base_options import BaseOptions
    from mediapipe.tasks.python import vision
    
    # Setup detector
    base_options = BaseOptions(model_asset_path=str(MODEL_PATH))
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    detector = vision.PoseLandmarker.create_from_options(options)
    
    # Extract frames
    frame_dir = Path("/tmp/mocap_frames")
    frame_dir.mkdir(parents=True, exist_ok=True)
    
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,width,height",
        "-of", "json", str(video_path),
    ], capture_output=True, text=True, check=True)
    info = json.loads(probe.stdout)
    stream = info["streams"][0]
    width, height = int(stream["width"]), int(stream["height"])
    
    frame_pattern = frame_dir / "frame_%06d.png"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"fps={target_fps},scale={width}:{height}",
        str(frame_pattern),
    ], capture_output=True, check=True)
    
    frames = sorted(frame_dir.glob("frame_*.png"))
    if max_frames:
        frames = frames[:max_frames]
    
    all_frames = []
    start = time.time()
    
    for i, frame_path in enumerate(frames):
        mp_image = mp.Image.create_from_file(str(frame_path))
        result = detector.detect(mp_image)
        
        if result.pose_landmarks:
            landmarks = result.pose_landmarks[0]
            
            # Extract landmark data
            lm_data = []
            for idx, lm in enumerate(landmarks):
                lm_data.append({
                    "x": lm.x, "y": lm.y, "z": lm.z,
                    "visibility": lm.visibility,
                    "presence": lm.presence,
                })
            
            # Compute joint angles
            angles = compute_joint_angles(lm_data)
            
            all_frames.append({
                "frame": i + 1,
                "timestamp": round(i / target_fps, 3),
                "landmarks": lm_data,
                "angles": angles,
            })
        else:
            # No pose detected - use neutral pose
            all_frames.append({
                "frame": i + 1,
                "timestamp": round(i / target_fps, 3),
                "landmarks": None,
                "angles": None,
            })
        
        if (i + 1) % 100 == 0:
            print(f"  Processed {i+1}/{len(frames)} frames...")
    
    # Cleanup
    for f in frame_dir.glob("*.png"):
        f.unlink()
    frame_dir.rmdir()
    
    return {
        "status": "ok",
        "video": str(video_path),
        "total_frames": len(all_frames),
        "detected_frames": sum(1 for f in all_frames if f["angles"] is not None),
        "processing_time_sec": round(time.time() - start, 2),
        "fps": target_fps,
        "frames": all_frames,
    }


def export_to_blender(mocap_data: dict, project_slug: str, armature_name: str = "BodyMocap") -> dict:
    """Export mocap data to Blender armature with IK."""
    import bpy
    
    project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
    layout_path = project_dir / "03-layout" / "layout.blend"
    
    if not layout_path.exists():
        return {"status": "error", "message": "Layout not found"}
    
    bpy.ops.wm.open_mainfile(filepath=str(layout_path))
    scene = bpy.context.scene
    
    # Find or create armature
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
        
        bones = {
            "root": ((0, 0, 0), (0, 0, 0.1)),
            "spine": ((0, 0, 0.9), (0, 0, 1.4)),
            "neck": ((0, 0, 1.4), (0, 0, 1.6)),
            "head": ((0, 0, 1.6), (0, 0, 1.75)),
            "shoulder_L": ((-0.25, 0, 1.4), (-0.4, 0, 1.4)),
            "upperarm_L": ((-0.4, 0, 1.4), (-0.55, 0, 1.1)),
            "forearm_L": ((-0.55, 0, 1.1), (-0.6, 0, 0.85)),
            "hand_L": ((-0.6, 0, 0.85), (-0.6, 0, 0.75)),
            "shoulder_R": ((0.25, 0, 1.4), (0.4, 0, 1.4)),
            "upperarm_R": ((0.4, 0, 1.4), (0.55, 0, 1.1)),
            "forearm_R": ((0.55, 0, 1.1), (0.6, 0, 0.85)),
            "hand_R": ((0.6, 0, 0.85), (0.6, 0, 0.75)),
            "hip_L": ((-0.15, 0, 0.9), (-0.15, 0, 0.6)),
            "thigh_L": ((-0.15, 0, 0.6), (-0.15, 0, 0.3)),
            "shin_L": ((-0.15, 0, 0.3), (-0.15, 0, 0.05)),
            "foot_L": ((-0.15, 0, 0.05), (-0.15, 0.1, 0.05)),
            "hip_R": ((0.15, 0, 0.9), (0.15, 0, 0.6)),
            "thigh_R": ((0.15, 0, 0.6), (0.15, 0, 0.3)),
            "shin_R": ((0.15, 0, 0.3), (0.15, 0, 0.05)),
            "foot_R": ((0.15, 0, 0.05), (0.15, 0.1, 0.05)),
        }
        for name, (head, tail) in bones.items():
            bone = edit_bones.new(name)
            bone.head = head
            bone.tail = tail
        
        bpy.ops.object.mode_set(mode="OBJECT")
    
    # Mapping: angle name → (bone_name, axis, scale)
    angle_map = {
        "left_elbow_bend": ("forearm_L", "x", -0.01),
        "right_elbow_bend": ("forearm_R", "x", -0.01),
        "left_shoulder_forward": ("upperarm_L", "x", 0.01),
        "right_shoulder_forward": ("upperarm_R", "x", 0.01),
        "left_shoulder_outward": ("upperarm_L", "z", 0.01),
        "right_shoulder_outward": ("upperarm_R", "z", -0.01),
        "left_knee_bend": ("shin_L", "x", -0.01),
        "right_knee_bend": ("shin_R", "x", -0.01),
        "left_hip_forward": ("thigh_L", "x", 0.01),
        "right_hip_forward": ("thigh_R", "x", 0.01),
        "left_hip_outward": ("thigh_L", "z", 0.01),
        "right_hip_outward": ("thigh_R", "z", -0.01),
        "head_tilt_x": ("head", "x", 0.01),
        "head_tilt_z": ("head", "z", 0.01),
        "spine_twist": ("spine", "z", 0.005),
    }
    
    frames = mocap_data.get("frames", [])
    recorded = 0
    
    for frame_data in frames:
        frame = frame_data["frame"]
        angles = frame_data.get("angles")
        
        if not angles:
            continue
        
        scene.frame_set(frame)
        
        for angle_name, (bone_name, axis, scale) in angle_map.items():
            if angle_name in angles and bone_name in arm_obj.pose.bones:
                bone = arm_obj.pose.bones[bone_name]
                value = angles[angle_name] * scale
                
                if axis == "x":
                    bone.rotation_euler.x = value
                elif axis == "y":
                    bone.rotation_euler.y = value
                elif axis == "z":
                    bone.rotation_euler.z = value
                
                bone.keyframe_insert(data_path="rotation_euler", frame=frame)
                recorded += 1
    
    bpy.ops.wm.save_as_mainfile(filepath=str(layout_path))
    
    return {
        "status": "ok",
        "project": project_slug,
        "total_frames": len(frames),
        "keyframes_recorded": recorded,
        "armature": armature_name,
    }


def main():
    parser = argparse.ArgumentParser(description="Body Mocap")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ext = sub.add_parser("extract", help="Extract mocap from video")
    p_ext.add_argument("video_path")
    p_ext.add_argument("--fps", type=float, default=24.0)
    p_ext.add_argument("--output", help="Output JSON path")
    p_ext.add_argument("--max-frames", type=int)

    p_bl = sub.add_parser("to-blender", help="Export mocap to Blender")
    p_bl.add_argument("project_slug")
    p_bl.add_argument("--mocap", required=True)
    p_bl.add_argument("--armature", default="BodyMocap")

    p_batch = sub.add_parser("batch", help="Extract + export in one step")
    p_batch.add_argument("project_slug")
    p_batch.add_argument("--video", required=True)
    p_batch.add_argument("--fps", type=float, default=24.0)

    args = parser.parse_args()

    if args.command == "extract":
        result = extract_mocap(Path(args.video_path), target_fps=args.fps, max_frames=args.max_frames)
        summary = {k: v for k, v in result.items() if k != "frames"}
        print(json.dumps(summary, indent=2))
        if result.get("status") == "ok":
            out_path = Path(args.output) if args.output else Path("mocap.json")
            out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"Mocap saved to {out_path}")
    elif args.command == "to-blender":
        mocap_data = json.loads(Path(args.mocap).read_text(encoding="utf-8"))
        result = export_to_blender(mocap_data, args.project_slug, args.armature)
        print(json.dumps(result, indent=2))
    elif args.command == "batch":
        result = extract_mocap(Path(args.video), target_fps=args.fps)
        if result.get("status") == "ok":
            mocap_path = WORKSPACE_ROOT / "05_PROJECTS" / args.project_slug / "08-mocap" / "body_mocap.json"
            mocap_path.parent.mkdir(parents=True, exist_ok=True)
            mocap_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"Extracted {result['detected_frames']}/{result['total_frames']} frames")
            
            result2 = export_to_blender(result, args.project_slug)
            print(json.dumps(result2, indent=2))


if __name__ == "__main__":
    main()

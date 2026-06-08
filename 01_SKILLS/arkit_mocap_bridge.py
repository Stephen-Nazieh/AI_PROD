#!/usr/bin/env python3
"""
arkit_mocap_bridge.py — ARKit Face Tracking + Eye Rotation → VRoid Blend Shapes

Receives iOS ARKit face tracking data via UDP (iFacialMocap) or WebSocket,
with full support for 52 blend shapes AND eye rotation data (6 floats).
Maps to VRM standard blend shapes AND eye bone rotations.

Usage (UDP server for iFacialMocap):
    python arkit_mocap_bridge.py serve --protocol udp --port 49983

Usage (WebSocket server for custom apps):
    python arkit_mocap_bridge.py serve --protocol ws --port 49984

Usage (Blender client):
    blender --background --python arkit_mocap_bridge.py -- blender-client <project_slug>

iFacialMocap binary packet format:
    Header: b"iFacialMocap_sahu" (17 bytes)
    Blend shapes: 52 floats (4 bytes each) = 208 bytes
    Eye rotation: 6 floats (4 bytes each) = 24 bytes
    Total minimum: 249 bytes
"""

import argparse
import asyncio
import json
import math
import struct
from pathlib import Path

import numpy as np

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 49983
MOCAP_STATE = WORKSPACE_ROOT / ".mocap_state.json"

IFM_HEADER = b"iFacialMocap_sahu"
IFM_HEADER_LEN = len(IFM_HEADER)  # 17
IFM_BLEND_COUNT = 52
IFM_BLEND_SIZE = IFM_BLEND_COUNT * 4  # 208
IFM_EYE_COUNT = 6
IFM_EYE_SIZE = IFM_EYE_COUNT * 4  # 24
IFM_PACKET_MIN = IFM_HEADER_LEN + IFM_BLEND_SIZE + IFM_EYE_SIZE  # 249

# 52 ARKit blend shape names in iFacialMocap order
ARKIT_SHAPES = [
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight", "eyeBlinkLeft", "eyeBlinkRight",
    "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight",
    "eyeLookOutLeft", "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight",
    "eyeSquintLeft", "eyeSquintRight", "eyeWideLeft", "eyeWideRight",
    "jawForward", "jawLeft", "jawOpen", "jawRight",
    "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight",
    "mouthFunnel", "mouthLeft", "mouthLowerDownLeft", "mouthLowerDownRight",
    "mouthPressLeft", "mouthPressRight", "mouthPucker", "mouthRight",
    "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
    "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft", "noseSneerRight",
    "tongueOut",
]

# ARKit → VRM blend shape mapping
ARKIT_TO_VRM = {
    "eyeBlinkLeft": "Blink",
    "eyeBlinkRight": "Blink",
    "jawOpen": "A",
    "mouthFunnel": "U",
    "mouthPucker": "U",
    "mouthSmileLeft": "I",
    "mouthSmileRight": "I",
    "mouthFrownLeft": "E",
    "mouthFrownRight": "E",
    "mouthClose": "O",
    "jawForward": "A",
}

# Eye rotation indices in packet
EYE_ROTATION = {
    "left_eye_x": 0, "left_eye_y": 1, "left_eye_z": 2,
    "right_eye_x": 3, "right_eye_y": 4, "right_eye_z": 5,
}


def get_local_ip() -> str:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def parse_ifm_packet(data: bytes) -> dict:
    """Parse iFacialMocap UDP binary packet with eye rotation."""
    if len(data) < IFM_PACKET_MIN:
        return None
    
    has_header = data.startswith(IFM_HEADER)
    offset = IFM_HEADER_LEN if has_header else 0
    
    # Parse blend shapes
    blend_data = data[offset:offset + IFM_BLEND_SIZE]
    if len(blend_data) < IFM_BLEND_SIZE:
        return None
    blend_floats = struct.unpack(f"<{IFM_BLEND_COUNT}f", blend_data)
    blend_shapes = dict(zip(ARKIT_SHAPES, blend_floats))
    
    # Parse eye rotation
    eye_offset = offset + IFM_BLEND_SIZE
    eye_data = data[eye_offset:eye_offset + IFM_EYE_SIZE]
    if len(eye_data) >= IFM_EYE_SIZE:
        eye_floats = struct.unpack(f"<{IFM_EYE_COUNT}f", eye_data)
        eye_rotation = {
            "left": {"x": eye_floats[0], "y": eye_floats[1], "z": eye_floats[2]},
            "right": {"x": eye_floats[3], "y": eye_floats[4], "z": eye_floats[5]},
        }
    else:
        eye_rotation = {"left": {"x": 0, "y": 0, "z": 0}, "right": {"x": 0, "y": 0, "z": 0}}
    
    return {
        "blend_shapes": blend_shapes,
        "eye_rotation": eye_rotation,
    }


def write_mocap_state(data: dict):
    """Write blend shapes + eye rotation to shared state file."""
    blend_shapes = data.get("blend_shapes", {})
    eye_rotation = data.get("eye_rotation", {})
    
    vrm_shapes = {}
    for arkit_name, value in blend_shapes.items():
        vrm_name = ARKIT_TO_VRM.get(arkit_name)
        if vrm_name:
            vrm_shapes[vrm_name] = max(vrm_shapes.get(vrm_name, 0.0), float(value))
    
    state = {
        "blend_shapes": vrm_shapes,
        "eye_rotation": eye_rotation,
        "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0,
    }
    MOCAP_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── UDP Server ──────────────────────────────────────────────────────────────

class iFacialMocapProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        try:
            result = parse_ifm_packet(data)
            if result:
                write_mocap_state(result)
        except Exception:
            pass


async def serve_udp(port: int = DEFAULT_PORT):
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: iFacialMocapProtocol(),
        local_addr=("0.0.0.0", port),
    )
    print(f"🎭 ARKit UDP Mocap Bridge on 0.0.0.0:{port}")
    print(f"   iFacialMocap → {get_local_ip()}:{port}")
    print("   Press Ctrl+C to stop")
    try:
        await asyncio.Future()
    finally:
        transport.close()


# ── WebSocket Server ────────────────────────────────────────────────────────

async def handle_ws(websocket):
    print(f"  📱 WS client: {websocket.remote_address}")
    async for message in websocket:
        try:
            data = json.loads(message)
            blend_shapes = data.get("blendShapes", {})
            eye_rotation = data.get("eyeRotation", {})
            write_mocap_state({"blend_shapes": blend_shapes, "eye_rotation": eye_rotation})
        except Exception:
            pass


async def serve_ws(port: int = 49984):
    try:
        import websockets
    except ImportError:
        print("❌ pip install websockets")
        return
    print(f"🎭 WebSocket Mocap Bridge on ws://0.0.0.0:{port}")
    async with websockets.serve(handle_ws, "0.0.0.0", port):
        await asyncio.Future()


# ── Blender Client ──────────────────────────────────────────────────────────

class BlenderMocapClient:
    def __init__(self, project_slug: str):
        self.project_slug = project_slug
        self.project_dir = WORKSPACE_ROOT / "05_PROJECTS" / project_slug
        self.layout_path = self.project_dir / "03-layout" / "layout.blend"

    def apply_frame(self, state: dict) -> dict:
        import bpy
        blend_shapes = state.get("blend_shapes", {})
        eye_rotation = state.get("eye_rotation", {})
        
        # Find VRM mesh with shape keys
        vrm_mesh = None
        for obj in bpy.context.scene.objects:
            if obj.type == "MESH" and obj.data.shape_keys:
                vrm_mesh = obj
                break
        
        applied_blend = []
        if vrm_mesh and vrm_mesh.data.shape_keys:
            key = vrm_mesh.data.shape_keys
            for vrm_name, value in blend_shapes.items():
                for shape in key.key_blocks:
                    if shape.name == vrm_name:
                        shape.value = min(1.0, max(0.0, value))
                        shape.keyframe_insert(data_path="value", frame=bpy.context.scene.frame_current)
                        applied_blend.append(vrm_name)
        
        # Apply eye rotations to eye bones
        applied_eyes = []
        armature = None
        for obj in bpy.context.scene.objects:
            if obj.type == "ARMATURE":
                armature = obj
                break
        
        if armature:
            for eye_side in ["left", "right"]:
                rot = eye_rotation.get(eye_side, {})
                if any(rot.values()):
                    bone_name = f"Eye_{eye_side.capitalize()}" if f"Eye_{eye_side.capitalize()}" in armature.pose.bones else eye_side
                    if bone_name in armature.pose.bones:
                        bone = armature.pose.bones[bone_name]
                        bone.rotation_euler = (
                            rot.get("x", 0) * 0.5,
                            rot.get("y", 0) * 0.5,
                            rot.get("z", 0) * 0.5,
                        )
                        bone.keyframe_insert(data_path="rotation_euler", frame=bpy.context.scene.frame_current)
                        applied_eyes.append(bone_name)
        
        return {
            "status": "ok",
            "frame": bpy.context.scene.frame_current,
            "blend_shapes": applied_blend,
            "eye_bones": applied_eyes,
        }

    def record_session(self, duration_sec: float = 10.0, fps: float = 24.0) -> dict:
        import bpy
        if not self.layout_path.exists():
            return {"status": "error", "message": "Layout not found"}
        
        bpy.ops.wm.open_mainfile(filepath=str(self.layout_path))
        scene = bpy.context.scene
        total_frames = int(duration_sec * fps)
        recorded = []
        
        for frame in range(1, total_frames + 1):
            scene.frame_set(frame)
            if MOCAP_STATE.exists():
                try:
                    state = json.loads(MOCAP_STATE.read_text(encoding="utf-8"))
                    result = self.apply_frame(state)
                    if result["status"] == "ok":
                        recorded.append(frame)
                except Exception:
                    pass
        
        bpy.ops.wm.save_as_mainfile(filepath=str(self.layout_path))
        return {
            "status": "ok",
            "project": self.project_slug,
            "total_frames": total_frames,
            "recorded_frames": len(recorded),
        }


def run_blender_client(project_slug: str, duration: float = 10.0):
    import bpy
    client = BlenderMocapClient(project_slug)
    result = client.record_session(duration_sec=duration)
    print(json.dumps(result, indent=2))


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ARKit Mocap Bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Start mocap server")
    p_serve.add_argument("--protocol", choices=["udp", "ws"], default="udp")
    p_serve.add_argument("--port", type=int, default=DEFAULT_PORT)

    p_client = sub.add_parser("blender-client", help="Run Blender client")
    p_client.add_argument("project_slug")
    p_client.add_argument("--duration", type=float, default=10.0)

    p_info = sub.add_parser("info", help="Show connection info")

    args = parser.parse_args()

    if args.command == "serve":
        try:
            if args.protocol == "udp":
                asyncio.run(serve_udp(port=args.port))
            else:
                asyncio.run(serve_ws(port=args.port))
        except KeyboardInterrupt:
            print("\n🛑 Server stopped")
    elif args.command == "blender-client":
        run_blender_client(args.project_slug, duration=args.duration)
    elif args.command == "info":
        print(f"Local IP: {get_local_ip()}")
        print(f"iFacialMocap UDP: {get_local_ip()}:{DEFAULT_PORT}")
        print(f"WebSocket: ws://{get_local_ip()}:49984")
        print(f"\niFacialMocap settings:")
        print(f"  Server: {get_local_ip()}")
        print(f"  Port: {DEFAULT_PORT}")


if __name__ == "__main__":
    main()

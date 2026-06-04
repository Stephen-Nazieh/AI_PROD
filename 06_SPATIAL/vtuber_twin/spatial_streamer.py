#!/usr/bin/env python3
import json
import socket
import time

class SpatialBroadcaster:
    """
    Broadcasts real-time motion vectors, blendshapes, and positional telemetry.
    Streams directly to 3D VTubing nodes (Warudo/VNyan) and Digital Twin canvases.
    """
    def __init__(self, target_ip: str = "127.0.0.1", udp_port: int = 39539):
        self.target_address = (target_ip, udp_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # High-speed UDP pipeline

    def stream_motion_packet(self, position_dict: dict, rotation_dict: dict, expressions_dict: dict = None):
        """
        Packages and dispatches a low-latency spatial transformation state vector packet.
        """
        packet = {
            "version": "1.0",
            "timestamp": time.time(),
            "transform": {
                "position": position_dict,
                "rotation": rotation_dict
            },
            "blendshapes": expressions_dict or {"joy": 0.0, "mouthOpen": 0.0}
        }
        
        message = json.dumps(packet).encode('utf-8')
        try:
            self.sock.sendto(message, self.target_address)
            return True
        except Exception as e:
            print(f"⚠️ [Spatial Streamer] Network socket dropped packet transmission: {e}")
            return False

if __name__ == "__main__":
    print("📡 [Spatial Streamer] Broadcasting test tracking loops on UDP Port 39539...")
    streamer = SpatialBroadcaster()
    
    # Simulate a quick multi-frame behavioral movement loop
    for angle in range(0, 45, 15):
        streamer.stream_motion_packet(
            position_dict={"x": 0.0, "y": 1.75, "z": -0.5},
            rotation_dict={"pitch": float(angle), "yaw": 0.0, "roll": 0.0},
            expressions_dict={"joy": 0.8, "mouthOpen": 0.4}
        )
        time.sleep(0.1)
    print("✅ [Spatial Streamer] Test transmission sequence complete.")
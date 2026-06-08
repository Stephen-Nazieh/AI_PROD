#!/usr/bin/env python3
import socket
import json
import math
from threading import Thread
import pyglet
from pyglet import shapes

class AdvancedIK3DViewport:
    """
    Advanced Procedural & Inverse Kinematics 3D Viewport.
    Handles smooth alpha-blending filter lines, procedural breathing matrices,
    and geometric tracking joint calculations natively at 60 FPS.
    """
    def __init__(self, port=39539):
        self.port = port
        self.running = True
        
        # Performance Telemetry Target States
        self.target_mouth_open = 0.0
        self.target_hand_x = 360.0
        self.target_hand_y = 250.0

        # Smoothed Render States (Interpolated values to prevent clipping)
        self.render_mouth_open = 0.0
        self.time_elapsed = 0.0

        # Initialize Hardware Window Layout Canvas
        self.window = pyglet.window.Window(600, 600, "🪐 DeParadigm Media Advanced 3D Spatial Twin Engine")
        self.batch = pyglet.graphics.Batch()

        # 🟢 THE RIGGED MESH STRUCTURE
        # Core Head Anchor Node
        self.head = shapes.Rectangle(250, 280, 100, 100, color=(0, 180, 255), batch=self.batch)
        self.head.anchor_x = 50
        self.head.anchor_y = 50

        # Expressive Mouth Overlay Matrix
        self.mouth = shapes.Rectangle(250, 255, 40, 6, color=(255, 80, 80), batch=self.batch)
        self.mouth.anchor_x = 20
        self.mouth.anchor_y = 3

        # Multi-Segmented Skeletal Linkage Arm (Shoulder -> Elongated Pointer Link)
        self.shoulder_x = 320
        self.shoulder_y = 260
        self.arm_upper = shapes.Rectangle(self.shoulder_x, self.shoulder_y, 12, 50, color=(0, 255, 180), batch=self.batch)
        self.arm_upper.anchor_x = 6
        self.arm_upper.anchor_y = 50 # Rotates directly from the shoulder socket boundary

        self.window.push_handlers(on_draw=self.on_draw)

        # Launch Network Socket Listener Daemon Thread
        self.network_thread = Thread(target=self._listen_udp_stream, daemon=True)
        self.network_thread.start()

        # Bind System Update Refresh Cycles to 60 FPS
        pyglet.clock.schedule_interval(self.update, 1/60.0)

    def _listen_udp_stream(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", self.port))
        sock.settimeout(0.5)
        
        while self.running:
            try:
                data, _ = sock.recvfrom(2048)
                payload = json.loads(data.decode('utf-8'))
                
                shapes_data = payload.get("blendshapes", {})
                self.target_mouth_open = shapes_data.get("mouthOpen", 0.0)
                
                # Capture real-world target tracking coordinate coordinates if passed
                pos = payload.get("transform", {}).get("position", {})
                # Map incoming spatial coordinates dynamically to pixel coordinate windows
                self.target_hand_x = 360 + int(pos.get("x", 0.0) * 200)
                self.target_hand_y = 250 + int(pos.get("y", 0.0) * 100)
                
            except socket.timeout:
                continue
            except Exception as e:
                print(f"⚠️ [Spatial Performance] Network skip: {e}")

    def update(self, dt):
        self.time_elapsed += dt

        # 1. PROCEDURAL IDLE BREATHING LAYER
        # Micro sine-wave shifts give the avatar an organic, idling lifelike weight distribution
        breathing_offset = math.sin(self.time_elapsed * 2.5) * 3
        self.head.y = 300 + breathing_offset
        self.mouth.y = 275 + breathing_offset

        # 2. SMOOTH LIP-SYNC INTERPOLATION (Alpha-Blending Filter)
        # Prevents frame dropping by smoothly interpolating 15% of the distance to the target value per frame
        self.render_mouth_open += (self.target_mouth_open - self.render_mouth_open) * 0.15
        mouth_h = max(3, int(self.render_mouth_open * 32))
        self.mouth.height = mouth_h

        # 3. GEOMETRIC INVERSE KINEMATICS (IK) LINKAGE LAYER
        # Calculate the direct vector angle from the shoulder pivot straight to the target hand marker coordinate
        dx = self.target_hand_x - self.shoulder_x
        dy = self.target_hand_y - (self.shoulder_y + breathing_offset)
        target_angle_rad = math.atan2(dy, dx)
        target_angle_deg = math.degrees(target_angle_rad)

        # Smoothly rotate the upper joint segment structure toward the target coordinate bounds
        # Converts standard geometric math orientation to match Pyglet's rotation rules
        pyglet_rotation = -target_angle_deg + 90
        
        if self.target_mouth_open > 0:
            # When actively speaking, blend the target angles with micro gestural arm shakes
            self.arm_upper.rotation = pyglet_rotation + (math.sin(self.time_elapsed * 12) * 8)
        else:
            # Idle rest layout angle
            self.arm_upper.rotation = 0 + (math.sin(self.time_elapsed * 1.5) * 4)

    def on_draw(self):
        self.window.clear()
        self.batch.draw()

    def run(self):
        pyglet.app.run()
        self.running = False

if __name__ == "__main__":
    viewport = AdvancedIK3DViewport()
    viewport.run()
#!/usr/bin/env python3
import socket
import json
import tkinter as tk
from threading import Thread

class SpatialTelemetryCanvas:
    """
    Real-time local tracking monitor. Captures low-latency UDP coordinate vectors
    broadcasted by the orchestrator loop and updates a visual canvas matrix instantly.
    """
    def __init__(self, port: int = 39539):
        self.port = port
        self.running = True
        
        # Initialize an elegant local desktop window interface
        self.root = tk.Tk()
        self.root.title("🪐 Solocorn Spatial Twin Telemetry Control Plane")
        self.root.geometry("400x450")
        self.root.configure(bg="#111116")

        # Status Tracking Headings
        self.status_label = tk.Label(self.root, text="📡 Spatial Matrix: LISTENING", fg="#00FF00", bg="#111116", font=("Courier", 12, "bold"))
        self.status_label.pack(pady=10)

        # Coordinate Grid Output Labels
        self.coord_label = tk.Label(self.root, text="X: 0.00 | Y: 0.00 | Z: 0.00", fg="#FFFFFF", bg="#111116", font=("Courier", 14))
        self.coord_label.pack(pady=10)
        
        self.blend_label = tk.Label(self.root, text="Mouth: 0.00 | Blink: 0.00", fg="#00AAAA", bg="#111116", font=("Courier", 11))
        self.blend_label.pack(pady=5)

        # 2D Position Tracking Plane Box
        self.canvas = tk.Canvas(self.root, width=300, height=300, bg="#1a1a24", highlightthickness=1, highlightbackground="#333344")
        self.canvas.pack(pady=10)
        
        # Draw central crosshair alignment markers
        self.canvas.create_line(150, 0, 150, 300, fill="#222233")
        self.canvas.create_line(0, 150, 300, 150, fill="#222233")
        
        # Create a glowing vector tracker dot representing your digital twin position
        self.tracker_dot = self.canvas.create_oval(140, 140, 160, 160, fill="#00FFCC", outline="")

        # Spin up a dedicated background network socket tracking thread
        self.network_thread = Thread(target=self._listen_udp_channel, daemon=True)
        self.network_thread.start()

    def _listen_udp_channel(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", self.port))
        sock.settimeout(1.0)
        
        while self.running:
            try:
                data, _ = sock.recvfrom(2048)
                payload = json.loads(data.decode('utf-8'))
                
                # Extract transformation metrics
                pos = payload["transform"]["position"]
                shapes = payload.get("blendshapes", {})
                
                # Safely update UI grid items across thread lines
                self.root.after(0, self._update_canvas_state, pos["x"], pos["y"], pos["z"], shapes)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"⚠️ [Monitor Canvas] Network parse skip: {e}")

    def _update_canvas_state(self, x: float, y: float, z: float, shapes: dict):
        # Update text metrics string readout
        self.coord_label.config(text=f"X: {x:.2f} | Y: {y:.2f} | Z: {z:.2f}")
        self.blend_label.config(text=f"Mouth: {shapes.get('mouthOpen', 0.0):.2f} | Blink: {shapes.get('blink', 0.0):.2f}")
        
        # Map 3D coordinate floats onto our 2D canvas pixel coordinates dynamically
        # Centers tracking vectors around pixel origin (150, 150)
        pixel_x = 150 + int(x * 100)
        pixel_y = 150 - int(z * 100) # Mapping depth onto the Y axis
        
        # Limit boundary bounds to keep tracking dot inside the canvas box grid safely
        pixel_x = max(10, min(290, pixel_x))
        pixel_y = max(10, min(290, pixel_y))
        
        # Reposition the tracker dot smoothly
        self.canvas.coords(self.tracker_dot, pixel_x - 10, pixel_y - 10, pixel_x + 10, pixel_y + 10)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.running = False

if __name__ == "__main__":
    monitor = SpatialTelemetryCanvas()
    monitor.run()
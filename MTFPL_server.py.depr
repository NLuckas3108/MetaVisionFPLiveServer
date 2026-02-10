import zmq
import time
import cv2
import numpy as np
import threading
import os

# Ports müssen offen sein (ufw allow ...)
PORT_CMD = 5555
PORT_VID = 5556

print("=== ZMQ CONNECTION TEST SERVER ===")
print(f"Lausche auf Ports: {PORT_CMD} (CMD) und {PORT_VID} (VIDEO)")

def command_loop():
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(f"tcp://0.0.0.0:{PORT_CMD}")
    
    while True:
        try:
            msg = socket.recv_pyobj()
            cmd = msg.get("cmd")
            print(f"[CMD] Empfangen: {cmd}")
            
            if cmd == "UPLOAD_CAD":
                # Datei speichern um zu beweisen, dass Daten ankommen
                data = msg["data"]
                filename = msg["filename"]
                save_path = f"server_received_{filename}"
                
                with open(save_path, "wb") as f:
                    f.write(data)
                    
                print(f" -> Datei gespeichert: {save_path} ({len(data)} bytes)")
                socket.send_string(f"OK: Saved as {save_path}")
                
            elif cmd == "SET_MASK":
                print(f" -> Masken-Koordinaten: {msg['points']}")
                socket.send_string("OK: Mask received")
                
            else:
                socket.send_string("UNKNOWN CMD")
                
        except Exception as e:
            print(f"[CMD ERROR] {e}")
            socket.send_string("ERROR")

def video_loop():
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(f"tcp://0.0.0.0:{PORT_VID}")
    
    frame_count = 0
    
    while True:
        try:
            # 1. Empfangen
            packet = socket.recv_pyobj()
            rgb_img = packet["rgb"]
            # depth_img = packet["depth"] # Brauchen wir für den Test noch nicht
            
            # 2. Bearbeiten (Beweis, dass wir auf dem Server sind)
            frame_count += 1
            
            # Wir malen ein Rechteck und Text auf das Bild
            # Wenn du das auf dem Laptop siehst, war das Bild im Netzwerk!
            cv2.rectangle(rgb_img, (10, 10), (400, 60), (0, 255, 0), -1)
            cv2.putText(rgb_img, f"SERVER PROCESSED: {frame_count}", (20, 45), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
            
            # 3. Zurücksenden
            response = {"image": rgb_img}
            socket.send_pyobj(response)
            
        except Exception as e:
            print(f"[VIDEO ERROR] {e}")

# Command Thread im Hintergrund
t = threading.Thread(target=command_loop, daemon=True)
t.start()

# Video Loop im Main Thread
video_loop()
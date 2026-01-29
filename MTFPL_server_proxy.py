import zmq
import threading
import os
import shutil
import time

# --- KONFIGURATION ---
EXT_PORT_CMD = 5555
EXT_PORT_VID = 5556
INT_PORT_CMD = 6666
INT_PORT_VID = 6667

SHARED_DIR = "/tmp/fp_shared"

print(f"=== Host Proxy Server ===")

class ProxyServer:
    def __init__(self):
        self.context = zmq.Context()
        self.current_filename = None
        self.tracking_active = False
        
        # CMD Socket
        self.docker_cmd = self.context.socket(zmq.REQ)
        self.docker_cmd.connect(f"tcp://127.0.0.1:{INT_PORT_CMD}")
        self.docker_cmd.setsockopt(zmq.RCVTIMEO, 20000) # 20s für Init
        
        # VIDEO Socket Setup
        self.connect_video_socket()

    def connect_video_socket(self):
        """Erstellt den Video-Socket neu (für Reset bei Timeout)"""
        try:
            # Falls er schon existiert, schließen
            if hasattr(self, 'docker_vid'):
                self.docker_vid.close()
        except: pass
            
        self.docker_vid = self.context.socket(zmq.REQ)
        self.docker_vid.connect(f"tcp://127.0.0.1:{INT_PORT_VID}")
        # Timeout hoch setzen! Initial Register dauert oft 3-5 Sek.
        self.docker_vid.setsockopt(zmq.RCVTIMEO, 10000) 
        self.docker_vid.setsockopt(zmq.LINGER, 0)
        print("[PROXY] Docker Video Socket verbunden/resettet.")

    def save_cad_locally(self, filename, data):
        filepath = os.path.join(SHARED_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(data)
        print(f"[HOST] Gespeichert: {filepath}")
        return filepath

    def send_init_to_docker(self, rect, K):
        if not self.current_filename: return False
        try:
            payload = { 
                "cmd": "INIT", 
                "filename": self.current_filename, 
                "mask_rect": rect,
                "K": K
            }
            print("[HOST] Sende INIT an Docker...")
            self.docker_cmd.send_pyobj(payload)
            resp = self.docker_cmd.recv_string()
            print(f"[HOST] Docker antwortet: {resp}")
            return resp == "OK"
        except Exception as e:
            print(f"[ERROR] Docker Init Timeout/Error: {e}")
            return False

proxy = ProxyServer()

def ext_command_loop():
    socket = proxy.context.socket(zmq.REP)
    socket.bind(f"tcp://0.0.0.0:{EXT_PORT_CMD}")
    print(f"[EXTERN] CMD Listening on {EXT_PORT_CMD}")
    
    while True:
        try:
            msg = socket.recv_pyobj()
            cmd = msg.get("cmd")
            
            if cmd == "UPLOAD_CAD":
                proxy.save_cad_locally(msg["filename"], msg["data"])
                proxy.current_filename = msg["filename"]
                socket.send_string("OK")
                
            elif cmd == "SET_MASK":
                pts = msg['points']
                x = min(pts[0][0], pts[1][0])
                y = min(pts[0][1], pts[1][1])
                w = abs(pts[0][0] - pts[1][0])
                h = abs(pts[0][1] - pts[1][1])
                
                K = msg.get("K", [[615.3, 0, 320], [0, 615.3, 240], [0, 0, 1]])
                
                if proxy.send_init_to_docker([x, y, w, h], K):
                    proxy.tracking_active = True
                    socket.send_string("OK")
                else:
                    socket.send_string("ERROR")
            else:
                socket.send_string("UNKNOWN")
        except Exception as e:
            print(f"CMD Error: {e}")

def ext_video_loop():
    socket = proxy.context.socket(zmq.REP)
    socket.bind(f"tcp://0.0.0.0:{EXT_PORT_VID}")
    print(f"[EXTERN] VIDEO Listening on {EXT_PORT_VID}")
    
    while True:
        try:
            packet = socket.recv_pyobj()
            resp_img = packet["rgb"] # Default: Original zurück
            
            if proxy.tracking_active:
                try:
                    # 1. Senden
                    proxy.docker_vid.send_pyobj(packet)
                    # 2. Empfangen
                    resp_img = proxy.docker_vid.recv_pyobj()["image"]
                except zmq.Again:
                    print("[WARN] Docker Timeout! Resette Verbindung...")
                    # WICHTIG: Socket neu aufbauen, sonst Deadlock beim nächsten Frame
                    proxy.connect_video_socket()
                except Exception as e:
                    print(f"[ERROR] Bridge Fehler: {e}")
                    proxy.connect_video_socket()
            
            socket.send_pyobj({"image": resp_img})
        except Exception as e:
            pass

if __name__ == "__main__":
    if not os.path.exists(SHARED_DIR):
        os.makedirs(SHARED_DIR)
    os.chmod(SHARED_DIR, 0o777)

    try:
        t1 = threading.Thread(target=ext_command_loop, daemon=True)
        t1.start()
        ext_video_loop()
    except KeyboardInterrupt:
        print("\n[HOST] Beende Proxy...")
    finally:
        if os.path.exists(SHARED_DIR):
            try: shutil.rmtree(SHARED_DIR)
            except: pass
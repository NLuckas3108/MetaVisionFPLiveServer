import zmq
import threading
import os
import shutil
import time
import socket
import cv2
import base64

# Externe Ports 
EXT_PORT_CMD = 5555
EXT_PORT_VID_IN = 5556
EXT_PORT_VID_OUT = 5557

# Interne Ports
INT_PORT_CMD = 6666
INT_PORT_VID_IN = 6667 
INT_PORT_VID_OUT = 6668 

SHARED_DIR = "/tmp/fp_shared"

print(f"=== Host Proxy Server ===")

class ProxyServer:
    def __init__(self):
        self.context = zmq.Context()
        self.current_filename = None
        
        self.docker_cmd = self.context.socket(zmq.REQ)
        self.docker_cmd.connect(f"tcp://127.0.0.1:{INT_PORT_CMD}")
        self.docker_cmd.setsockopt(zmq.RCVTIMEO, 20000)

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

def video_forwarder():
    try:
        ctx = zmq.Context()
        
        frontend = ctx.socket(zmq.PULL)
        frontend.bind(f"tcp://0.0.0.0:{EXT_PORT_VID_IN}")
        
        backend = ctx.socket(zmq.PUSH)
        backend.connect(f"tcp://127.0.0.1:{INT_PORT_VID_IN}")
        
        print(f"[PROXY] Video Forwarder läuft: :{EXT_PORT_VID_IN} -> :{INT_PORT_VID_IN}")
        
        zmq.proxy(frontend, backend)
    except Exception as e:
        print(f"[ERROR] Video Forwarder Crash: {e}")

def result_forwarder():
    try:
        ctx = zmq.Context()
        
        frontend = ctx.socket(zmq.PULL)
        frontend.connect(f"tcp://127.0.0.1:{INT_PORT_VID_OUT}")
        
        backend = ctx.socket(zmq.PUSH)
        backend.bind(f"tcp://0.0.0.0:{EXT_PORT_VID_OUT}")
        
        print(f"[PROXY] Result Forwarder läuft: :{INT_PORT_VID_OUT} -> :{EXT_PORT_VID_OUT}")
        
        zmq.proxy(frontend, backend)
    except Exception as e:
        print(f"[ERROR] Result Forwarder Crash: {e}")

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
                    socket.send_string("OK")
                else:
                    socket.send_string("ERROR")
                    
            elif cmd == "STOP":
                print("[HOST] Leite STOP an Docker weiter...")
                try:
                    proxy.docker_cmd.send_pyobj({"cmd": "STOP"})
                    resp = proxy.docker_cmd.recv_string() 
                    socket.send_string(resp) 
                except Exception as e:
                    print(f"[HOST] Fehler beim Stoppen: {e}")
                    socket.send_string("ERROR")
                    
            elif cmd == "GET_TEXTURES":
                print("[CONTROL] Client fragt nach Texturen...")
                textures = get_available_textures()
                socket.send_pyobj({"status": "OK", "textures": textures})
                
            elif cmd == "GET_TEXTURE_FULL":
                tex_name = msg.get("name")
                print(f"[PROXY] Client will High-Res Textur: {tex_name}")
                full_data = load_full_texture_data(tex_name)
                
                if full_data:
                    socket.send_pyobj({"status": "OK", "data": full_data})
                else:
                    socket.send_pyobj({"status": "ERROR"})

            elif cmd == "SET_TEXTURE":
                tex_name = msg.get("name")
                print(f"[PROXY] Leite Textur-Wahl an Docker weiter: {tex_name}")
                
                try:
                    proxy.docker_cmd.send_pyobj({
                        "cmd": "SET_TEXTURE", 
                        "name": tex_name
                    })
                    resp = proxy.docker_cmd.recv_string()
                    socket.send_string(resp)
                except Exception as e:
                    print(f"[PROXY] Fehler beim Weiterleiten von SET_TEXTURE: {e}")
                    socket.send_string("ERROR")
                    
            else:
                socket.send_string("UNKNOWN")
        except Exception as e:
            print(f"CMD Error: {e}")
            
def get_available_textures(texture_path="textures"):
    texture_list = []
    
    if not os.path.exists(texture_path):
        return []

    for item in os.listdir(texture_path):
        sub_dir = os.path.join(texture_path, item)
        if os.path.isdir(sub_dir):
            image_file = None
            for f in os.listdir(sub_dir):
                if "Color" in f and f.endswith(('.jpg', '.png')):
                    image_file = os.path.join(sub_dir, f)
                    break
            
            if not image_file:
                for f in os.listdir(sub_dir):
                    if f.endswith(('.jpg', '.png')):
                        image_file = os.path.join(sub_dir, f)
                        break
            
            if image_file:
                img = cv2.imread(image_file)
                thumb = cv2.resize(img, (64, 64))
                _, buffer = cv2.imencode('.jpg', thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                thumb_bytes = buffer.tobytes()
                
                texture_list.append({
                    "name": item,       
                    "thumbnail": thumb_bytes
                })
    
    return texture_list

def load_full_texture_data(texture_name, base_path="textures"):
    """Sucht die Original-Datei für eine Textur und gibt die Bytes zurück"""
    target_dir = os.path.join(base_path, texture_name)
    if not os.path.exists(target_dir):
        return None
    
    image_path = None
    for f in os.listdir(target_dir):
        if "Color" in f and f.endswith(('.jpg', '.png')):
            image_path = os.path.join(target_dir, f)
            break
    
    if not image_path:
        for f in os.listdir(target_dir):
            if f.endswith(('.jpg', '.png')):
                image_path = os.path.join(target_dir, f)
                break
                
    if image_path:
        with open(image_path, "rb") as f:
            return f.read() 
    return None

if __name__ == "__main__":
    if not os.path.exists(SHARED_DIR):
        os.makedirs(SHARED_DIR)
    
    try:
        os.chmod(SHARED_DIR, 0o777)
    except PermissionError:
        print(f"[WARN] Konnte Rechte für {SHARED_DIR} nicht ändern (gehört evtl. root?). Mache weiter...")
    except Exception as e:
        print(f"[WARN] chmod Fehler: {e}")

    try:
        t1 = threading.Thread(target=ext_command_loop, daemon=True)
        t2 = threading.Thread(target=video_forwarder, daemon=True)
        t3 = threading.Thread(target=result_forwarder, daemon=True)
        
        t1.start()
        t2.start()
        t3.start()
    
        print("[PROXY] Alle Services gestartet. Drücke STRG+C zum Beenden.")
        while True: time.sleep(1)
        
    except KeyboardInterrupt:
        print("\n[HOST] Beende Proxy...")
    finally:
        if os.path.exists(SHARED_DIR):
            try: shutil.rmtree(SHARED_DIR)
            except: pass
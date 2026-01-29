import zmq
import threading
import os
import shutil
import time

# --- KONFIGURATION ---
# Externe Ports (Laptop <-> Workstation)
EXT_PORT_CMD = 5555
EXT_PORT_VID_IN = 5556  # NEU: Laptop PUSH -> Hier rein
EXT_PORT_VID_OUT = 5557 # NEU: Hier raus -> Laptop PULL

# Interne Ports (Workstation <-> Docker)
INT_PORT_CMD = 6666
INT_PORT_VID_IN = 6667  # Hier rein -> Docker PULL
INT_PORT_VID_OUT = 6668 # Docker PUSH -> Hier rein

SHARED_DIR = "/tmp/fp_shared"

print(f"=== Host Proxy Server (Async PUSH/PULL) ===")

class ProxyServer:
    def __init__(self):
        self.context = zmq.Context()
        self.current_filename = None
        
        # CMD Socket (Bleibt synchron REQ-REP!)
        self.docker_cmd = self.context.socket(zmq.REQ)
        self.docker_cmd.connect(f"tcp://127.0.0.1:{INT_PORT_CMD}")
        self.docker_cmd.setsockopt(zmq.RCVTIMEO, 20000) # 20s für Init
        
        # HINWEIS: Wir brauchen hier KEINEN Video-Socket mehr.
        # Das machen jetzt die Forwarder-Threads separat.

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

# Globale Instanz für CMD Loop
proxy = ProxyServer()

def video_forwarder():
    """
    Kanal 1: Bilder vom Laptop -> Docker
    Laptop (PUSH) -> Proxy (PULL) -> Proxy (PUSH) -> Docker (PULL)
    """
    try:
        ctx = zmq.Context()
        
        # Eingang vom Laptop
        frontend = ctx.socket(zmq.PULL)
        frontend.bind(f"tcp://0.0.0.0:{EXT_PORT_VID_IN}")
        
        # Ausgang zum Docker
        backend = ctx.socket(zmq.PUSH)
        backend.connect(f"tcp://127.0.0.1:{INT_PORT_VID_IN}")
        
        print(f"[PROXY] Video Forwarder läuft: :{EXT_PORT_VID_IN} -> :{INT_PORT_VID_IN}")
        
        # ZMQ Proxy Device (Effiziente Weiterleitung)
        zmq.proxy(frontend, backend)
    except Exception as e:
        print(f"[ERROR] Video Forwarder Crash: {e}")

def result_forwarder():
    """
    Kanal 2: Ergebnisse vom Docker -> Laptop
    Docker (PUSH) -> Proxy (PULL) -> Proxy (PUSH) -> Laptop (PULL)
    """
    try:
        ctx = zmq.Context()
        
        # Eingang vom Docker
        frontend = ctx.socket(zmq.PULL)
        frontend.connect(f"tcp://127.0.0.1:{INT_PORT_VID_OUT}")
        
        # Ausgang zum Laptop
        backend = ctx.socket(zmq.PUSH)
        backend.bind(f"tcp://0.0.0.0:{EXT_PORT_VID_OUT}")
        
        print(f"[PROXY] Result Forwarder läuft: :{INT_PORT_VID_OUT} -> :{EXT_PORT_VID_OUT}")
        
        zmq.proxy(frontend, backend)
    except Exception as e:
        print(f"[ERROR] Result Forwarder Crash: {e}")

def ext_command_loop():
    """Synchroner Command Loop (Bleibt wie er war)"""
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
                    resp = proxy.docker_cmd.recv_string() # Antwort vom Docker (OK)
                    socket.send_string(resp) # Antwort an Laptop
                except Exception as e:
                    print(f"[HOST] Fehler beim Stoppen: {e}")
                    socket.send_string("ERROR")
                    
            else:
                socket.send_string("UNKNOWN")
        except Exception as e:
            print(f"CMD Error: {e}")

if __name__ == "__main__":
    if not os.path.exists(SHARED_DIR):
        os.makedirs(SHARED_DIR)
    os.chmod(SHARED_DIR, 0o777)

    try:
        # 3 Threads starten
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
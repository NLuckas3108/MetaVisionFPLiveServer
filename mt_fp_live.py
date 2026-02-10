import sys
import os
sys.path.append("/workspace")
import time
import numpy as np
import cv2
import zmq
import trimesh

# --- Deine originalen Imports ---
from estimater import *
from datareader import *
from myUtils import *

# --- KONFIGURATION (INTERN IM DOCKER) ---
PORT_CMD = 6666
PORT_VID_IN = 6667   # Korrekter Name
PORT_VID_OUT = 6668
SHARED_DIR = "/data"

def make_mask_from_rect(rect, width, height):
    """Erstellt die Boolesche Maske für FoundationPose aus dem Rechteck"""
    x, y, w, h = rect
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[y:y+h, x:x+w] = 1
    return mask.astype(bool).astype(np.uint8)

class FPRunner:
    def __init__(self):
        self.est = None
        self.scorer = ScorePredictor()
        self.refiner = PoseRefinePredictor()
        self.glctx = dr.RasterizeCudaContext()
        
        # State
        self.mesh_loaded = False
        self.bbox = None
        self.to_origin = None
        self.is_first_frame = True
        self.mask_rect = None 
        self.K = np.array([[615.3, 0.0, 320.0], [0.0, 615.3, 240.0], [0.0, 0.0, 1.0]])

    def load_mesh(self, filename):
        mesh_path = os.path.join(SHARED_DIR, filename)
        print(f"[DOCKER] Lade Mesh von: {mesh_path}")
        
        mesh = trimesh.load(mesh_path, force='mesh')
        mesh.apply_scale(0.001) 
        
        if len(mesh.faces) > 100000:
            mesh = mesh.simplify_quadratic_decimation(100000)
            
        color_array = np.array([90, 160, 200])
        mesh = trimesh_add_pure_colored_texture(mesh, color_array)
        
        self.bbox = mesh.bounds # [[min_x, y, z], [max_x, y, z]]
        
        self.est = FoundationPose(
            model_pts=mesh.vertices, 
            model_normals=mesh.vertex_normals, 
            mesh=mesh, 
            scorer=self.scorer, 
            refiner=self.refiner, 
            glctx=self.glctx
        )
        self.mesh_loaded = True
        print("[DOCKER] FoundationPose ready.")

    def get_box_points_2d(self, pose, K):
        """Berechnet die 2D-Bildkoordinaten der simplen AABB"""
        
        # 1. Die 8 Ecken der Box basierend auf den min/max Werten des Meshes
        min_pt = self.bbox[0]
        max_pt = self.bbox[1]
        
        corners_3d = np.array([
            [min_pt[0], min_pt[1], min_pt[2]],
            [min_pt[0], min_pt[1], max_pt[2]],
            [min_pt[0], max_pt[1], min_pt[2]],
            [min_pt[0], max_pt[1], max_pt[2]],
            [max_pt[0], min_pt[1], min_pt[2]],
            [max_pt[0], min_pt[1], max_pt[2]],
            [max_pt[0], max_pt[1], min_pt[2]],
            [max_pt[0], max_pt[1], max_pt[2]]
        ])
        
        # Rotation (3x3) und Translation (3)
        R = pose[:3, :3]
        t = pose[:3, 3]
        
        # P_cam = R * P_obj + t
        corners_cam = (R @ corners_3d.T).T + t
        
        # 3. Projizieren
        corners_2d_hom = (K @ corners_cam.T).T
        corners_2d_hom[:, 2] = np.maximum(corners_2d_hom[:, 2], 0.001) # Schutz vor Z=0
        
        corners_2d = corners_2d_hom[:, :2] / corners_2d_hom[:, 2:]
        
        return corners_2d.astype(int).tolist()

    def process_frame(self, rgb, depth):
        if not self.mesh_loaded: return None, None

        H, W = rgb.shape[:2]
        pose = None
        
        iter_count = 1
        
        if self.is_first_frame:
            mask = make_mask_from_rect(self.mask_rect, W, H)
            pose = self.est.register(K=self.K, rgb=rgb, depth=depth, ob_mask=mask, iteration=5)
            self.is_first_frame = False
            print("[DOCKER] Initial Registration done.")
        else:
            # Nur Tracking, keine Zeitmessung 
            pose = self.est.track_one(rgb=rgb, depth=depth, K=self.K, iteration=iter_count)

        # Berechne nur die Punkte
        try:
            points_2d = self.get_box_points_2d(pose, self.K)
            return points_2d, pose
        except Exception as e:
            print(f"Calc Error: {e}")
            return None

def main():
    context = zmq.Context()
    
    # Sockets
    cmd_socket = context.socket(zmq.REP)
    cmd_socket.bind(f"tcp://0.0.0.0:{PORT_CMD}")
    
    vid_in_socket = context.socket(zmq.PULL)
    vid_in_socket.setsockopt(zmq.CONFLATE, 1)
    vid_in_socket.bind(f"tcp://0.0.0.0:{PORT_VID_IN}")
    
    vid_out_socket = context.socket(zmq.PUSH)
    vid_out_socket.bind(f"tcp://0.0.0.0:{PORT_VID_OUT}")
    
    print(f"[DOCKER] High-Perf Pipeline (Points Only). CMD:{PORT_CMD}, IN:{PORT_VID_IN}, OUT:{PORT_VID_OUT}")
    
    runner = FPRunner()
    
    poller = zmq.Poller()
    poller.register(cmd_socket, zmq.POLLIN)
    poller.register(vid_in_socket, zmq.POLLIN)

    while True:
        socks = dict(poller.poll())

        if cmd_socket in socks:
            msg = cmd_socket.recv_pyobj()
            cmd = msg.get("cmd")
            
            if cmd == "INIT":
                try:
                    runner.mask_rect = msg["mask_rect"]
                    if "K" in msg:
                        runner.K = np.array(msg["K"])
                        print(f"[DOCKER] Nutze Kamera-Intrinsics: \n{runner.K}")
                    runner.load_mesh(msg["filename"])
                    runner.is_first_frame = True 
                    cmd_socket.send_string("OK")
                except Exception as e:
                    print(f"Init Error: {e}")
                    cmd_socket.send_string("ERROR")

            elif cmd == "STOP":
                runner.mesh_loaded = False 
                cmd_socket.send_string("OK")
                print("[DOCKER] Tracking gestoppt.")

        if vid_in_socket in socks:
            packet = vid_in_socket.recv_pyobj()
            
            if not runner.mesh_loaded:
                continue 
            
            # --- 1. RGB BEHANDLUNG (Unabhängig von Depth!) ---
            if "rgb_compressed" in packet:
                # Fall A: JPEG Komprimiert (Standard vom Client)
                rgb_bytes = packet["rgb_compressed"]
                rgb_bgr = cv2.imdecode(rgb_bytes, cv2.IMREAD_COLOR)
                rgb = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2RGB)
            elif "rgb" in packet:
                # Fall B: Rohdaten (Fallback)
                rgb_bgr = packet["rgb"]
                rgb = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2RGB)
            else:
                print("[ERROR] Paket enthält weder 'rgb' noch 'rgb_compressed'.")
                continue # Frame überspringen

            # --- 2. DEPTH BEHANDLUNG ---
            if "depth_compressed" in packet:
                # Fall A: Komprimiert (PNG oder ZLIB)
                if "encoding" in packet and packet["encoding"] == "png":
                    # PNG Dekodierung (CV2)
                    depth_raw = cv2.imdecode(packet["depth_compressed"], cv2.IMREAD_UNCHANGED)
                else:
                    # ZLIB Dekodierung (Standard/Schnell)
                    import zlib
                    depth_data = zlib.decompress(packet["depth_compressed"])
                    dtype = packet.get("dtype", "uint16")
                    shape = packet.get("shape", (480, 640))
                    depth_raw = np.frombuffer(depth_data, dtype=dtype).reshape(shape)
                
                depth = depth_raw.astype(np.float32) / 1000.0

            elif "depth" in packet:
                # Fall B: Rohdaten
                depth_raw = packet["depth"]
                depth = depth_raw.astype(np.float32) / 1000.0
            else:
                print("[ERROR] Paket enthält keine Tiefendaten.")
                continue

            try:
                # --- ZEITMESSUNG START ---
                t_start = time.time()
                points_2d, pose = runner.process_frame(rgb, depth)
                # --- ZEITMESSUNG ENDE ---
                dt = time.time() - t_start
                if dt > 0:
                    print(f"Compute FPS: {1.0/dt:.1f} ({dt*1000:.1f}ms)")
                
                if points_2d is not None:
                    ts = time.time() 
                    
                    payload = {
                        "box_points": points_2d,
                        "pose": pose, 
                        "timestamp": ts 
                    }
                    vid_out_socket.send_pyobj(payload)
                else:
                    vid_out_socket.send_pyobj({"status": "error"})
                
            except Exception as e:
                print(f"[DOCKER] Crash: {e}")

if __name__ == '__main__':
    set_logging_format()
    set_seed(0)
    main()
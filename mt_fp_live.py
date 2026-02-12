import sys
import os
sys.path.append("/workspace")
import time
import numpy as np
import cv2
import zmq
import trimesh
import threading
import queue
from PIL import Image

from estimater import *
from datareader import *
from myUtils import *

PORT_CMD = 6666
PORT_VID_IN = 6667   
PORT_VID_OUT = 6668
SHARED_DIR = "/workspace/shared_data"
script_dir = os.path.dirname(os.path.realpath(__file__))
texture_dir = os.path.join(script_dir, "textures")
print(f"[DEBUG] Suche Texturen in: {texture_dir}")

def make_mask_from_rect(rect, width, height):
    x, y, w, h = rect
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[y:y+h, x:x+w] = 1
    return mask.astype(bool).astype(np.uint8)

class PacketDecoder(threading.Thread):
    def __init__(self, context, port_in):
        super().__init__()
        self.socket = context.socket(zmq.PULL)
        self.socket.setsockopt(zmq.CONFLATE, 1)
        self.socket.bind(f"tcp://0.0.0.0:{port_in}")
        self.running = True
        self.latest_frame = None
        self.lock = threading.Lock()
        
        self.packet_count = 0
        self.start_time = time.time()
        
    def run(self):
        print("[DOCKER] Decoder-Thread gestartet.")
        while self.running:
            try:
                packet = self.socket.recv_pyobj()
                
                rgb = None
                depth = None
                
                if "rgb_compressed" in packet:
                    rgb_bytes = packet["rgb_compressed"]
                    rgb_bgr = cv2.imdecode(rgb_bytes, cv2.IMREAD_COLOR)
                    rgb = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2RGB)
                elif "rgb" in packet:
                    rgb_bgr = packet["rgb"]
                    rgb = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2RGB)
                
                if "depth_compressed" in packet:
                    if "encoding" in packet and packet["encoding"] == "png":
                        depth_raw = cv2.imdecode(packet["depth_compressed"], cv2.IMREAD_UNCHANGED)
                    else:
                        import zlib
                        depth_data = zlib.decompress(packet["depth_compressed"])
                        dtype = packet.get("dtype", "uint16")
                        shape = packet.get("shape", (480, 640))
                        depth_raw = np.frombuffer(depth_data, dtype=dtype).reshape(shape)
                    
                    depth = depth_raw.astype(np.float32) / 1000.0
                elif "depth" in packet:
                    depth_raw = packet["depth"]
                    depth = depth_raw.astype(np.float32) / 1000.0

                if rgb is not None and depth is not None:
                    with self.lock:
                        self.latest_frame = (rgb, depth)
                    
            except Exception as e:
                print(f"Decoder Error: {e}")

    def get_latest(self):
        with self.lock:
            frame = self.latest_frame
            self.latest_frame = None
            return frame

class FPRunner:
    def __init__(self):
        self.est = None
        self.scorer = ScorePredictor()
        self.refiner = PoseRefinePredictor()
        self.glctx = dr.RasterizeCudaContext()

        self.mesh_loaded = False
        self.bbox = None
        self.to_origin = None
        self.is_first_frame = True
        self.mask_rect = None 
        self.K = np.array([[615.3, 0.0, 320.0], [0.0, 615.3, 240.0], [0.0, 0.0, 1.0]])
        
        self.current_mesh_file = None
        self.current_texture_name = None

    def load_mesh(self, filename, texture_name=None):
        mesh_path = os.path.join(SHARED_DIR, filename)
        print(f"[DOCKER] Lade Mesh von: {mesh_path}")
        
        self.current_mesh_file = filename
        self.current_texture_name = texture_name
        
        mesh = trimesh.load(mesh_path, force='mesh')
        mesh.apply_scale(0.001) 
        
        if len(mesh.faces) > 10000:
            mesh = mesh.simplify_quadratic_decimation(10000)
            
        if texture_name:
            tex_path = os.path.join(texture_dir, texture_name)
            image_file = None
            if os.path.exists(tex_path):
                for f in os.listdir(tex_path):
                    if "Color" in f and f.endswith(('.jpg', '.png')):
                        image_file = os.path.join(tex_path, f)
                        break
                if not image_file:
                    for f in os.listdir(tex_path):
                        if f.endswith(('.jpg', '.png')):
                            image_file = os.path.join(tex_path, f)
                            break
            
            if image_file:
                print(f"[DOCKER] Appliziere Textur: {image_file}")
                try:
                    pil_image = Image.open(image_file)
                    material = trimesh.visual.texture.SimpleMaterial(image=pil_image)
                    
                    if hasattr(mesh.visual, 'uv') and mesh.visual.uv is not None:
                        mesh.visual.material = material
                    else:
                        print("[WARN] Mesh hat keine UV-Koordinaten! Textur wird komisch aussehen.")
                        mesh.visual = trimesh.visual.TextureVisuals(uv=mesh.vertices[:, :2], material=material)
                except Exception as e:
                    print(f"[ERROR] Textur konnte nicht geladen werden: {e}")
                    mesh = trimesh_add_pure_colored_texture(mesh, np.array([200, 50, 50]))
            else:
                print("[WARN] Textur-Ordner leer oder nicht gefunden. Nutze Standard-Farbe.")
                mesh = trimesh_add_pure_colored_texture(mesh, np.array([90, 160, 200]))
        else:
            color_array = np.array([90, 160, 200])
            mesh = trimesh_add_pure_colored_texture(mesh, color_array)
        
        self.bbox = mesh.bounds 
        
        self.est = FoundationPose(
            model_pts=mesh.vertices, 
            model_normals=mesh.vertex_normals, 
            mesh=mesh, 
            scorer=self.scorer, 
            refiner=self.refiner, 
            glctx=self.glctx
        )
        self.mesh_loaded = True
        print("[DOCKER] FoundationPose (Re-)Initialized.")

    def get_box_points_2d(self, pose, K):
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
        
        R = pose[:3, :3]
        t = pose[:3, 3]
        
        corners_cam = (R @ corners_3d.T).T + t
        
        corners_2d_hom = (K @ corners_cam.T).T
        corners_2d_hom[:, 2] = np.maximum(corners_2d_hom[:, 2], 0.001) 
        
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
            pose = self.est.track_one(rgb=rgb, depth=depth, K=self.K, iteration=iter_count)

        try:
            points_2d = self.get_box_points_2d(pose, self.K)
            return points_2d, pose
        except Exception as e:
            print(f"Calc Error: {e}")
            return None

def main():
    context = zmq.Context()
    
    cmd_socket = context.socket(zmq.REP)
    cmd_socket.bind(f"tcp://0.0.0.0:{PORT_CMD}")
    
    vid_out_socket = context.socket(zmq.PUSH)
    vid_out_socket.bind(f"tcp://0.0.0.0:{PORT_VID_OUT}")
    
    decoder_thread = PacketDecoder(context, PORT_VID_IN)
    decoder_thread.daemon = True
    decoder_thread.start()
    
    runner = FPRunner()
    
    poller = zmq.Poller()
    poller.register(cmd_socket, zmq.POLLIN)

    print("[DOCKER] High-Perf Pipeline (Threaded Decode).")

    while True:
        socks = dict(poller.poll(0))
        
        if cmd_socket in socks:
            msg = cmd_socket.recv_pyobj()
            cmd = msg.get("cmd")
            
            if cmd == "INIT":
                try:
                    runner.mask_rect = msg["mask_rect"]
                    if "K" in msg: runner.K = np.array(msg["K"])
                    runner.load_mesh(msg["filename"])
                    runner.is_first_frame = True 
                    cmd_socket.send_string("OK")
                except Exception as e: 
                    print(f"INIT Error: {e}")
                    cmd_socket.send_string("ERROR")
            
            elif cmd == "STOP":
                runner.mesh_loaded = False 
                cmd_socket.send_string("OK")
                
            elif cmd == "SET_TEXTURE":
                try:
                    tex_name = msg.get("name")
                    if runner.current_mesh_file:
                        runner.load_mesh(runner.current_mesh_file, texture_name=tex_name)
                        cmd_socket.send_string("OK")
                    else:
                        cmd_socket.send_string("ERROR: NO MESH")
                except Exception as e:
                    print(f"Texture Error: {e}")
                    cmd_socket.send_string("ERROR")

        frame_data = decoder_thread.get_latest()
        
        if frame_data and runner.mesh_loaded:
            rgb, depth = frame_data
            try:
                t_start = time.time()
                points_2d, pose = runner.process_frame(rgb, depth)
                dt = time.time() - t_start
                
                if points_2d is not None:
                    vid_out_socket.send_pyobj({
                        "box_points": points_2d,
                        "pose": pose,
                        "timestamp": time.time()
                    })
            except Exception as e:
                print(f"Tracking Crash: {e}")
        else:
            time.sleep(0.001)

if __name__ == '__main__':
    set_logging_format()
    set_seed(0)
    main()
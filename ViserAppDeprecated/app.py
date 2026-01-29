import viser                                                                    # | app.py:2
import viser.transforms as tf                                                   # | app.py:3
import numpy as np                                                              # | app.py:4
import cv2                                                                      # | app.py:5
import time                                                                     # | app.py:6
import trimesh                                                                  # | app.py:7
import io                                                                       # | app.py:8
import os                                                                       # | app.py:9
import json                                                                     # | app.py:10

def run_gui():                                                                  # | app.py:12
    server = viser.ViserServer(host="0.0.0.0", port=8080)                     # | app.py:13
    server.gui.configure_theme(dark_mode=True)                                  # | app.py:14

    st = {                                                                      # | app.py:16
        "mesh": None, "cad_filename": "None", "folder": "./textures",           # | app.py:17
        "textures": [], "cam_ok": False, "bbox_points": [],                     # | app.py:18
        "current_img": None, "p1_node": None, "rect_node": None                 # | app.py:19
    }                                                                           # | app.py:20

    def refresh():                                                              # | app.py:22
        if not os.path.exists(st["folder"]): os.makedirs(st["folder"])          # | app.py:23
        f_list = os.listdir(st["folder"])                                       # | app.py:24
        st["textures"] = sorted([f for f in f_list if f.lower().endswith(('.png', '.jpg', '.jpeg'))]) 
        return st["textures"]                                                   # | app.py:26

    refresh()                                                                   # | app.py:28

    # --- SIDEBAR UI ---
    server.gui.add_markdown("# Foundation Pose")                                # | app.py:31
    cad_btn = server.gui.add_upload_button("1. CAD Data", color="red")          # | app.py:32
    
    server.gui.add_markdown("### 2. Textures")                                  # | app.py:34
    categories = ["All", "Metal", "Wood", "Plastic", "Stone", "Concrete", "Fabric", "Brick", "Tiles"] 
    cat_drop = server.gui.add_dropdown("Category", options=categories)          # | app.py:36
    
    # The file dropdown starts with all textures
    drop = server.gui.add_dropdown("Select File", options=st["textures"] if st["textures"] else ["None"]) 
    prev_ui = server.gui.add_image(np.zeros((150, 150, 3), dtype=np.uint8))     # | app.py:39

    # --- FILTERING LOGIC (The Fix) ---
    @cat_drop.on_update                                                         # | app.py:42
    def _(_):                                                                   # | app.py:43
        category = cat_drop.value.lower()                                       # | app.py:44
        if category == "all":                                                   # | app.py:45
            filtered = st["textures"]                                           # | app.py:46
        else:                                                                   # | app.py:47
            # Filters files by checking if category name is in the filename
            filtered = [f for f in st["textures"] if category in f.lower()]     # | app.py:49
        
        drop.options = filtered if filtered else ["No matches found"]           # | app.py:51

    # --- REST OF THE UI ---
    server.gui.add_markdown("### 3. Connection")                                # | app.py:54
    cam_status = server.gui.add_button("RGB-D Status", color="red")             # | app.py:55

    server.gui.add_markdown("### 4. Initialization")                            # | app.py:57
    mask_btn = server.gui.add_button("Draw Mask", color="red")                  # | app.py:58
    reset_btn = server.gui.add_button("Reset Bounding Box")                     # | app.py:59
    save_btn = server.gui.add_button("SAVE CONFIG", color="gray")               # | app.py:60

    # --- CLICK HANDLER ---
    @server.on_client_connect                                                   # | app.py:63
    def _(client: viser.ClientHandle):                                          # | app.py:64
        client.camera.position, client.camera.look_at = (0, 0, 10), (0, 0, 0)   # | app.py:65
        client.camera.up_direction = (0, 1, 0)                                  # | app.py:66
        
        @client.scene.on_pointer_event(event_type="click")                      # | app.py:68
        def _(pointer: viser.ScenePointerEvent):                                # | app.py:69
            if len(st["bbox_points"]) >= 2: return                              # | app.py:70
            origin, direction = np.array(pointer.ray_origin), np.array(pointer.ray_direction) 
            t = -origin[2] / direction[2]                                       # | app.py:72
            pos = origin + t * direction                                        # | app.py:73
            st["bbox_points"].append(pos)                                       # | app.py:74
            
            if len(st["bbox_points"]) == 1:                                     # | app.py:76
                st["p1_node"] = server.scene.add_icosphere("/world/mask/p1", 
                                radius=0.1, position=pos, color=(0, 255, 0))    # | app.py:78
            elif len(st["bbox_points"]) == 2:                                   # | app.py:79
                if st["p1_node"]: st["p1_node"].remove()                        # | app.py:80
                p1, p2 = st["bbox_points"][0], st["bbox_points"][1]             # | app.py:81
                x_min, x_max = min(p1[0], p2[0]), max(p1[0], p2[0])             # | app.py:82
                y_min, y_max = min(p1[1], p2[1]), max(p1[1], p2[1])             # | app.py:83
                v = np.array([[x_min,y_min,0.05],[x_max,y_min,0.05],[x_max,y_max,0.05],[x_min,y_max,0.05]]) 
                f = np.array([[0,1,2],[0,2,3]])                                 # | app.py:85
                st["rect_node"] = server.scene.add_mesh_simple("/world/mask/rect", 
                                  vertices=v, faces=f, color=(0,255,0), opacity=0.3) 
                mask_btn.color, mask_btn.label = "green", "Mask: Ready"         # | app.py:88

    @reset_btn.on_click                                                         # | app.py:90
    def _(_):                                                                   # | app.py:91
        st["bbox_points"] = []                                                  # | app.py:92
        if st["p1_node"]: st["p1_node"].remove()                                # | app.py:93
        if st["rect_node"]: st["rect_node"].remove()                            # | app.py:94
        mask_btn.color, mask_btn.label = "red", "Draw Mask"                     # | app.py:95

    @drop.on_update                                                             # | app.py:97
    def _(_):                                                                   # | app.py:98
        if drop.value in ["None", "No matches found"]: return                   # | app.py:99
        img = cv2.imread(os.path.join(st["folder"], drop.value))                # | app.py:100
        if img is not None:                                                     # | app.py:101
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)                          # | app.py:102
            st["current_img"], prev_ui.image = rgb, cv2.resize(rgb, (150, 150)) # | app.py:103
            if st["mesh"]: 
                # Textur am Mesh-Objekt aktualisieren
                from PIL import Image
                pil_img = Image.fromarray(rgb)
                st["mesh"].visual = trimesh.visual.TextureVisuals(image=pil_img)
                
                # Neu rendern ohne 'texture' Argument
                server.scene.add_mesh_trimesh("/world/mesh", st["mesh"])

    @cad_btn.on_upload
    def _(e: viser.GuiEvent):
        uploaded_file = cad_btn.value 
        if uploaded_file is None: return
        st["cad_filename"] = uploaded_file.name
        file_content = uploaded_file.content
        
        try:
            # 1. Mesh laden
            mesh = trimesh.load(io.BytesIO(file_content), file_type='obj')
            
            # Scene zu Mesh konvertieren falls nötig
            if isinstance(mesh, trimesh.Scene):
                 if len(mesh.geometry) > 0:
                     mesh = list(mesh.geometry.values())[0]
                 else: return # Leere Szene abfangen

            # --- NEU: Auto-Scaling & Zentrierung ---
            print(f"Original Größe: {mesh.extents}") # Debugging
            
            # A. Zentrieren: Den Mittelpunkt des Meshes auf (0,0,0) schieben
            mesh.apply_translation(-mesh.centroid)
            
            # B. Skalieren: Wir bringen das Mesh auf eine Größe von ca. 0.5 Einheiten
            # Damit passt es perfekt ins Bild.
            scale_factor = 0.5 / np.max(mesh.extents)
            mesh.apply_scale(scale_factor)
            
            # C. Rotation: Viele CADs sind "liegend". Wir drehen es 90 Grad um X.
            # (Optional: Falls es auf dem Kopf steht, nimm np.pi/2 statt -np.pi/2)
            #rot_matrix = tf.SO3.from_x_radians(-np.pi/2).as_matrix()
            # Wir bauen eine 4x4 Matrix für trimesh
            #transform = np.eye(4)
            #transform[:3, :3] = rot_matrix
            #mesh.apply_transform(transform)
            
            st["mesh"] = mesh # Das bearbeitete Mesh speichern
            # ----------------------------------------

            # Textur Logik (wie gehabt)
            if st["current_img"] is not None:
                from PIL import Image
                pil_img = Image.fromarray(st["current_img"])
                st["mesh"].visual = trimesh.visual.TextureVisuals(image=pil_img)

            # Anzeigen
            server.scene.add_mesh_trimesh("/world/mesh", st["mesh"])
            
            cad_btn.color = "green"
            cad_btn.label = "CAD: Geladen"
            print(f"Erfolg: {st['cad_filename']} geladen und skaliert.")

        except Exception as err:
            print(f"Fehler beim Laden: {err}")
            server.gui.add_notification("Error loading CAD", color="red")                                           # | app.py:112

    @save_btn.on_click                                                          # | app.py:114
    def _(_):                                                                   # | app.py:115
        if len(st["bbox_points"]) < 2: return                                   # | app.py:116
        config = {"cad": st["cad_filename"], "bbox": [p.tolist() for p in st["bbox_points"]]} 
        with open("config.json", "w") as f: json.dump(config, f, indent=4)      # | app.py:118
        server.gui.add_notification("Saved!")                                   # | app.py:119

    cap = cv2.VideoCapture(2)
    #cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    #cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)                                               # | app.py:121
    while True:                                                                 # | app.py:122
        ret, frame = cap.read()                                                 # | app.py:123
        if ret:                                                                 # | app.py:124
            if not st["cam_ok"]:                                                # | app.py:125
                cam_status.color, cam_status.label, st["cam_ok"] = "green", "RGB-D: Online", True 
            frame = cv2.flip(frame, -1)                                         # | app.py:127
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)                      # | app.py:128
            server.scene.add_image("/world/cam", frame, render_width=8.0, 
                                   render_height=6.0, position=(0, 0, 0), 
                                   wxyz=(1, 0, 0, 0))                           # | app.py:131
        time.sleep(0.01)                                                        # | app.py:132

if __name__ == "__main__": run_gui()                                            # | app.py:134

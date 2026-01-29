import os                                                                       # | download_all.py:1
import requests                                                                 # | download_all.py:2
import zipfile                                                                  # | download_all.py:3
import io                                                                       # | download_all.py:4
from tqdm import tqdm                                                           # | download_all.py:5

def download_library(limit=100):                                               # | download_all.py:7
    # API v2 endpoint for all materials
    url = f"https://ambientcg.com/api/v2/full_json?type=Material&limit={limit}" # | download_all.py:9
    assets = requests.get(url).json().get('foundAssets', [])                    # | download_all.py:10
    
    os.makedirs("./textures", exist_ok=True)                                    # | app.py:12
    
    for asset in tqdm(assets, desc="Downloading textures"):                     # | app.py:14
        aid = asset['assetId']                                                  # | app.py:15
        # Skip if we already have it
        if os.path.exists(f"./textures/{aid}.png"): continue                   # | app.py:17
        
        dl_url = f"https://ambientcg.com/get?file={aid}_1K-PNG.zip"             # | app.py:19
        try:                                                                    # | app.py:20
            r = requests.get(dl_url, timeout=10)                                # | app.py:21
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:                   # | app.py:22
                for f in z.namelist():                                          # | app.py:23
                    if "Color.png" in f or "Albedo.png" in f:                   # | app.py:24
                        with open(f"./textures/{aid}.png", "wb") as out:        # | app.py:25
                            out.write(z.read(f))                                # | app.py:26
        except: pass                                                            # | app.py:27

if __name__ == "__main__":                                                      # | app.py:29
    # Change limit to 2000 for the full library
    download_library(limit=2000)                                                 # | app.py:31

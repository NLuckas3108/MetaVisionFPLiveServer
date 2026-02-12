import os
import requests
import zipfile
import io
from tqdm import tqdm

def download_specific_materials(limit_per_category=100):
    base_path = os.path.dirname(os.path.realpath(__file__))
    textures_root = os.path.join(base_path, "textures")
    
    os.makedirs(textures_root, exist_ok=True)

    categories = ["Metal", "Plastic", "Wood", "Fabric"]

    print(f"=== Starte Download in: {textures_root} ===")
    print(f"=== Kategorien: {', '.join(categories)} ===")

    for cat in categories:
        print(f"\nSuche nach Kategorie: {cat}...")
        
        url = f"https://ambientcg.com/api/v2/full_json?type=Material&category={cat}&limit={limit_per_category}"
        
        try:
            response = requests.get(url, timeout=10)
            assets = response.json().get('foundAssets', [])
        except Exception as e:
            print(f"Fehler bei API Abfrage für {cat}: {e}")
            continue

        for asset in tqdm(assets, desc=f"Lade {cat}"):
            aid = asset['assetId']
            
            material_dir = os.path.join(textures_root, aid)
            
            if os.path.exists(material_dir) and os.listdir(material_dir):
                continue

            dl_url = f"https://ambientcg.com/get?file={aid}_1K-PNG.zip"
            
            try:
                r = requests.get(dl_url, timeout=30)
                if r.status_code != 200:
                    continue

                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    os.makedirs(material_dir, exist_ok=True)
                    
                    for filename in z.namelist():
                        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                            z.extract(filename, material_dir)
                            
            except Exception as e:
                print(f"Fehler bei {aid}: {e}")

if __name__ == "__main__":
    download_specific_materials(limit_per_category=100)
    
    print("\nFertig! Alle Texturen liegen im Ordner 'textures'.")
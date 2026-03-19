import zivid
import cv2

# Zivid Anwendung initialisieren
app = zivid.Application()

print("Suche und verbinde Kamera...")
try:
    camera = app.connect_camera()
except RuntimeError as e:
    print(f"Fehler: Kamera nicht gefunden. Netzwerk checken! Details: {e}")
    exit()

# Settings für ein reines 2D-Bild konfigurieren
settings_2d = zivid.Settings2D()
settings_2d.acquisitions.append(zivid.Settings2D.Acquisition())

print("Starte Capture-Schleife (Drücke 'q' im Fenster zum Beenden)...")

try:
    while True:
        frame_2d = camera.capture(settings_2d)
        
        image_rgba = frame_2d.image_rgba().copy_data()
        
        image_cv = cv2.cvtColor(image_rgba, cv2.COLOR_RGBA2BGRA)
        
        image_resized = cv2.resize(image_cv, (0, 0), fx=0.25, fy=0.25)
        
        cv2.imshow("Zivid 2+ Live View", image_resized)
        
        # Abbruchbedingung
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
finally:
    cv2.destroyAllWindows()
    camera.disconnect()

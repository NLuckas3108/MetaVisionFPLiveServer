MetaVision Server Tools Readme
---

Dieses Repository beinhaltet die hostseitigen Skripte und Werkzeuge, um den MetaVision Tracking-Server zu betreiben. Die komplette Tracking-Umgebung, welche auf Foundation Pose basiert, wird separat als fertiges Docker-Image bereitgestellt und ist aufgrund der Dateigröße von 27 GB nicht in diesem Repository enthalten.
Dieses Repository enthält einzelnen Skripte und Funktionalitäten die für die Entwicklung genutzt wurden bzw. zum Starten und Stoppen des Server genutzt werden können.

Dateien und Funktionen
---
### Docker Container Steuerung
mtfpl_server_start.sh: Über dieses Skript wird der Docker-Container mit den benötigten GPU-Ressourcen und Host-Netzwerkeinstellungen gestartet.

mtfpl_server_stop.sh: Dieses Skript dient zum sicheren Beenden des laufenden Containers.

### Proxy Server (MTFPL_server_proxy.py)
Dieser Server fungiert als Brücke zwischen dem externen Client und dem internen Docker-Container. Es werden Steuerbefehle, Videostreams und Tracking-Ergebnisse über ZeroMQ zwischen den externen und internen Ports weitergeleitet. Zudem wird das lokale Speichern von hochgeladenen CAD-Modellen sowie die Bereitstellung der Texturen an den Client verwaltet.

### Textur-Downloader (download_textures.py)
Mit diesem Skript können automatisch hochauflösende Material-Texturen (wie Metall, Plastik, Holz, Stoff) von ambientcg.com heruntergeladen werden. Die Dateien werden entpackt und in einem lokalen Ordner abgelegt, auf den der Proxy-Server anschließend zugreift.

Nutzung und Ablauf
---

Schritt 1:
Im Ordner in dem das heruntergeladene Docker-Image liegt den folgenden Befehl ausführen um das Docker-Image zu laden:

    `sudo docker load -i mtfpl_v1_dist.tar`

Dies kann aufgrund der Größe des Images einige Zeit dauern.

Schritt 2:
Starten des Servers durch Ausführen der mtfpl_server_start.sh Datei.

Schritt 3:
Beenden des Servers durch Ausführen der mtfpl_server_stop.sh Datei.


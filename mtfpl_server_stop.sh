#!/bin/bash

CONTAINER_NAME="fp_server_instance"

if [ ! "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
    echo -e "\033[0;33m[INFO] Der Server '$CONTAINER_NAME' läuft gar nicht.\033[0m"
    exit 0
fi

echo -e "\033[0;31m[STOP] Beende Server...\033[0m"

docker stop $CONTAINER_NAME

if [ $? -eq 0 ]; then
    echo "✅ Server erfolgreich gestoppt."
else
    echo "❌ Fehler beim Stoppen (vielleicht schon beendet?)."
fi
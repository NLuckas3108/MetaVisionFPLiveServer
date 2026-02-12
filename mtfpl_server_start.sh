#!/bin/bash

CONTAINER_NAME="mtfpl_server_instance"
IMAGE_NAME="mtfpl:v1"

if [ "$(docker ps -q -f name=$CONTAINER_NAME)" ]; then
    echo -e "\033[0;33m[INFO] Der Server '$CONTAINER_NAME' läuft bereits.\033[0m"
    echo "Logs ansehen mit: docker logs -f $CONTAINER_NAME"
    exit 0
fi

docker rm $CONTAINER_NAME 2>/dev/null

echo -e "\033[0;32m[START] Starte FoundationPose Server ($IMAGE_NAME)...\033[0m"

docker run -d \
  --gpus all \
  --network host \
  --name $CONTAINER_NAME \
  --rm \
  $IMAGE_NAME

if [ $? -eq 0 ]; then
    echo "✅ Server erfolgreich gestartet!"
    echo "Logs ansehen: ./docker logs -f $CONTAINER_NAME"
else
    echo -e "\033[0;31m❌ Fehler beim Starten des Servers.\033[0m"
fi
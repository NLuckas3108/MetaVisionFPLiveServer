#!/bin/bash

cd /workspace/MetaVisionFPLiveServer

mkdir -p /workspace/shared_data

echo "[ENTRYPOINT] Starte Proxy Server..."
python MTFPL_server_proxy.py &

sleep 2

echo "[ENTRYPOINT] Starte FoundationPose Runner..."
python mt_fp_live.py
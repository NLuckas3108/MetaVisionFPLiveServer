FROM mtfpl:v1
WORKDIR /workspace
COPY MTFPL_server_proxy.py /workspace/MTFPL_server_proxy.py
COPY download_textures.py /workspace/download_textures.py
COPY mt_fp_live.py /workspace/mt_fp_live.py
COPY run.sh /workspace/run.sh

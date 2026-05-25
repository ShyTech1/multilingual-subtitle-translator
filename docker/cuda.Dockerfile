# NVIDIA GPU image. Requires:
#   - NVIDIA GPU + driver on host
#   - NVIDIA Container Toolkit installed (Linux) OR Docker Desktop w/ WSL2 GPU support (Windows)
#   - Invoked with `--gpus all`
#
# Base image already contains the matching cuBLAS + cuDNN libraries that
# ctranslate2 needs.
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/cache/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-pip ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/local/bin/python

# Ubuntu 24.04 ships PEP 668; allow system-site installs in the container.
RUN pip install --break-system-packages --upgrade pip

WORKDIR /app
COPY requirements.txt ./
RUN pip install --break-system-packages -r requirements.txt

COPY subtitle.py translate_srt.py rtl_srt.py ./
COPY docker/entrypoint.sh /usr/local/bin/entrypoint
RUN chmod +x /usr/local/bin/entrypoint

WORKDIR /data
VOLUME ["/data", "/cache/huggingface"]
ENTRYPOINT ["/usr/local/bin/entrypoint"]
CMD ["auto"]

# CPU-only image. Works on any machine with Docker (no NVIDIA needed).
# Slower transcription (~30-60 min per episode on a fast CPU).
FROM python:3.13-slim

ENV PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/cache/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY subtitle.py translate_srt.py rtl_srt.py ./
COPY docker/entrypoint.sh /usr/local/bin/entrypoint
RUN chmod +x /usr/local/bin/entrypoint

WORKDIR /data
VOLUME ["/data", "/cache/huggingface"]
ENTRYPOINT ["/usr/local/bin/entrypoint"]
CMD ["auto"]

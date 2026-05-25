#!/usr/bin/env bash
# Docker launcher (Linux / macOS). Auto-detects NVIDIA GPU.
#
# Usage:
#   ./run-docker.sh                    # auto-find a video in the current folder
#   ./run-docker.sh path/to/video.mkv
#   ./run-docker.sh path/to/video.mkv --model large-v3
set -euo pipefail

if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
    image=subtitle-translator:cuda
    dockerfile=docker/cuda.Dockerfile
    gpu_args=(--gpus all)
    echo "GPU detected — using $image"
else
    image=subtitle-translator:cpu
    dockerfile=docker/cpu.Dockerfile
    gpu_args=()
    echo "No NVIDIA GPU detected — using $image (CPU-only, slow)"
fi

if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "Building $image (one-time, a few minutes)..."
    docker build -f "$dockerfile" -t "$image" .
fi

if [ $# -gt 0 ] && [ -e "$1" ]; then
    abs=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
    mount_dir=$(dirname "$abs")
    name=$(basename "$abs")
    shift
    set -- "$name" "$@"
else
    mount_dir="$PWD"
fi

hf_cache="${HF_HOME:-$HOME/.cache/huggingface}"
mkdir -p "$hf_cache"

set -x
exec docker run --rm -it "${gpu_args[@]}" \
    -v "$mount_dir:/data" \
    -v "$hf_cache:/cache/huggingface" \
    "$image" "$@"

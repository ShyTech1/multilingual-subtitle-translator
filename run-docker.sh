#!/usr/bin/env bash
# Docker launcher (Linux / macOS). Auto-detects NVIDIA GPU.
#
# Usage:
#   ./run-docker.sh                    # auto-find a video in the current folder
#   ./run-docker.sh path/to/video.mkv
#   ./run-docker.sh path/to/video.mkv --model large-v3
#
# By default pulls a pre-built image from GHCR. Set TRANSLATOR_BUILD_LOCAL=1
# to force a local build instead.
set -euo pipefail

registry="ghcr.io/shytech1/multilingual-subtitle-translator"

if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
    variant=cuda
    dockerfile=docker/cuda.Dockerfile
    gpu_args=(--gpus all)
    echo "GPU detected — using $variant image"
else
    variant=cpu
    dockerfile=docker/cpu.Dockerfile
    gpu_args=()
    echo "No NVIDIA GPU detected — using $variant image (CPU-only, slow)"
fi

image="${registry}:${variant}"
force_local=${TRANSLATOR_BUILD_LOCAL:-0}

if ! docker image inspect "$image" >/dev/null 2>&1; then
    if [ "$force_local" != "1" ]; then
        echo "Pulling $image ..."
        if ! docker pull "$image"; then
            echo "Pull failed — falling back to local build."
            force_local=1
        fi
    fi
    if [ "$force_local" = "1" ]; then
        echo "Building $image locally (one-time, a few minutes)..."
        docker build -f "$dockerfile" -t "$image" .
    fi
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

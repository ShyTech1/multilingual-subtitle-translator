# Docker setup

Two images, auto-picked by a launcher:

| Image | Base | Size | When |
|---|---|---|---|
| `subtitle-translator:cuda` | `nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04` | ~6 GB | You have an NVIDIA GPU + driver |
| `subtitle-translator:cpu`  | `python:3.13-slim`                            | ~1.2 GB | Anything else (Mac, no-GPU Linux/Windows) |

The Whisper model (~1.5 GB for `medium`, ~3 GB for `large-v3`) lives in a
named Docker volume / a bind-mount to `~/.cache/huggingface` so it is
**downloaded once** and shared between containers and the native install.

## Prerequisites

| Host OS | What you need |
|---|---|
| Linux + NVIDIA | NVIDIA driver + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) |
| Windows + NVIDIA | Docker Desktop with **WSL2 backend** + recent NVIDIA driver. GPU passthrough is automatic in modern Docker Desktop. |
| Anything else | Just Docker. CPU-only image will be picked automatically. |

## Quick start (Windows / PowerShell)

```powershell
# From the project root
.\run-docker.ps1                       # auto-find any video in this folder
.\run-docker.ps1 C:\path\to\show.mkv   # specific file
.\run-docker.ps1 show.mkv --model large-v3 --languages he,ar,fr
```

The first invocation builds the image and downloads the Whisper model.
Subsequent runs reuse both.

## Quick start (Linux / macOS)

```bash
chmod +x run-docker.sh
./run-docker.sh                        # auto-find any video here
./run-docker.sh /path/to/show.mkv      # specific file
./run-docker.sh show.mkv --model large-v3
```

## Using docker compose

```bash
# Build (pick the profile matching your hardware)
docker compose --profile gpu build
docker compose --profile cpu build

# Drop your videos into ./videos, then:
docker compose --profile gpu run --rm gpu                # auto-finds first video
docker compose --profile gpu run --rm gpu show.mkv       # specific file
docker compose --profile cpu run --rm cpu --help         # see all pipeline args
```

## Volumes

| Mount | Purpose |
|---|---|
| `<your video folder>:/data` | Input videos go in, `.srt` outputs come out |
| `~/.cache/huggingface:/cache/huggingface` | Whisper model cache (shared with native install) |

## Cleaning up

```bash
docker image rm subtitle-translator:cuda subtitle-translator:cpu
docker volume rm translator_hf-cache   # delete the cached models
```

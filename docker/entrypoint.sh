#!/usr/bin/env bash
# Container entrypoint. Behavior:
#   entrypoint auto            -> find first video in /data and process it
#   entrypoint <filename>      -> process /data/<filename>
#   entrypoint <abs-path>      -> process the absolute path (must be in /data)
#   entrypoint <args>...       -> passed through to subtitle.py
#
# Default subtitle.py flags can be overridden by appending more args after
# the video name.
set -euo pipefail

CMD=(python /app/subtitle.py)
DEFAULTS=(--model medium --languages he,ar,fr)

# Pick device automatically. The CUDA image has nvidia-smi (via runtime
# injection); the CPU image does not.
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
    DEFAULTS+=(--device cuda)
else
    DEFAULTS+=(--device cpu --compute-type int8)
fi

resolve_video() {
    local arg="$1"
    if [ -f "$arg" ]; then
        printf '%s' "$arg"
        return 0
    fi
    if [ -f "/data/$arg" ]; then
        printf '/data/%s' "$arg"
        return 0
    fi
    return 1
}

if [ $# -eq 0 ] || [ "${1:-}" = "auto" ]; then
    shift || true
    for ext in mkv mp4 avi mov m4v webm; do
        for f in /data/*.$ext; do
            [ -e "$f" ] || continue
            echo ">> Auto-detected video: $f"
            exec "${CMD[@]}" "$f" "${DEFAULTS[@]}" "$@"
        done
    done
    echo "ERROR: no .mkv/.mp4/.avi/.mov/.m4v/.webm file found in /data" >&2
    echo "       mount your video folder: -v /path/to/videos:/data" >&2
    exit 1
fi

# Treat first arg as the video; everything after as extra subtitle.py args.
if video=$(resolve_video "$1"); then
    shift
    exec "${CMD[@]}" "$video" "${DEFAULTS[@]}" "$@"
fi

# First arg isn't a file; pass everything through unchanged (e.g. --help).
exec "${CMD[@]}" "$@"

"""Translate Arabic lines in an .srt file to Hebrew (in place).

Reads the .srt, finds subtitle entries whose text contains Arabic characters
(Unicode U+0600..U+06FF), translates each to Hebrew via Google Translate,
and rewrites the file. Hebrew-only entries are left untouched.

Uses the OS certificate trust store (via `truststore`) so it works through
corporate / antivirus TLS-inspection proxies that inject their own root CA.

Usage:
    python translate_srt.py <path.srt> [--batch 25]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Enable OS trust store BEFORE any TLS-using imports happen elsewhere.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception as exc:  # noqa: BLE001
    print(f"WARNING: truststore not active ({exc!s}); SSL may fail through MITM proxies",
          file=sys.stderr)

from deep_translator import GoogleTranslator

ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def parse_srt(text: str) -> list[dict]:
    """Return a list of {index, timing, lines: [str]}."""
    blocks: list[dict] = []
    raw = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    for block in raw.split("\n\n"):
        lines = block.split("\n")
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        timing = lines[1].strip()
        body = lines[2:]
        blocks.append({"index": idx, "timing": timing, "lines": body})
    return blocks


def render_srt(blocks: list[dict]) -> str:
    out: list[str] = []
    for b in blocks:
        body = "\n".join(b["lines"]).rstrip()
        out.append(f"{b['index']}\n{b['timing']}\n{body}\n")
    return "\n".join(out) + "\n"


def is_arabic_text(text: str) -> bool:
    return bool(ARABIC_RE.search(text))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("srt", type=Path)
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--out", type=Path, default=None,
                    help="Output path (default: overwrite input)")
    args = ap.parse_args()

    src = args.srt.resolve()
    if not src.exists():
        print(f"ERROR: {src} not found", file=sys.stderr)
        return 2
    dest = (args.out or src).resolve()

    text = src.read_text(encoding="utf-8")
    blocks = parse_srt(text)
    print(f"Parsed {len(blocks)} subtitle blocks from {src.name}", flush=True)

    ar_targets: list[tuple[int, str]] = []  # (block-idx, joined-text)
    for i, b in enumerate(blocks):
        joined = " ".join(b["lines"]).strip()
        if joined and is_arabic_text(joined):
            ar_targets.append((i, joined))

    if not ar_targets:
        print("No Arabic-containing blocks found; nothing to translate.")
        return 0

    print(f"Translating {len(ar_targets)} Arabic blocks -> Hebrew...", flush=True)
    translator = GoogleTranslator(source="ar", target="iw")

    done = 0
    for chunk_start in range(0, len(ar_targets), args.batch):
        chunk = ar_targets[chunk_start : chunk_start + args.batch]
        texts = [t for _, t in chunk]
        try:
            results = translator.translate_batch(texts)
        except Exception as exc:
            print(f"  batch starting at {chunk_start} failed ({exc!s}); per-line fallback",
                  flush=True)
            results = []
            for t in texts:
                try:
                    results.append(translator.translate(t) or t)
                except Exception as e2:
                    print(f"    line failed: {e2!s}", file=sys.stderr)
                    results.append(t)
        for (block_idx, _), translated in zip(chunk, results):
            translated = (translated or "").strip()
            blocks[block_idx]["lines"] = (translated or " ").split("\n")
        done += len(chunk)
        print(f"  {done}/{len(ar_targets)}", flush=True)

    dest.write_text(render_srt(blocks), encoding="utf-8")
    print(f"Wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

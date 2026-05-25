"""Make an .srt explicitly right-to-left by prefixing every subtitle line
with U+200F (RIGHT-TO-LEFT MARK).

This forces the Unicode bidi algorithm into RTL paragraph direction, fixing
edge cases (mixed-language lines, leading punctuation, numbers) that
otherwise render with confusing word order.

Usage:
    python rtl_srt.py <srt_path> [<srt_path> ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

RLM = "‏"


def add_rlm_to_srt(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    raw = text.replace("\r\n", "\n").replace("\r", "\n")
    changed = 0
    out_blocks: list[str] = []
    for block in raw.split("\n\n"):
        lines = block.split("\n")
        if len(lines) < 3:
            out_blocks.append(block)
            continue
        # lines[0] = index, lines[1] = timing, lines[2:] = text
        head = lines[:2]
        body = lines[2:]
        new_body: list[str] = []
        for ln in body:
            if ln and not ln.startswith(RLM):
                new_body.append(RLM + ln)
                changed += 1
            else:
                new_body.append(ln)
        out_blocks.append("\n".join(head + new_body))
    path.write_text("\n\n".join(out_blocks).rstrip() + "\n", encoding="utf-8")
    return changed


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python rtl_srt.py <srt_path> [<srt_path> ...]")
        return 2
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print(f"skip (missing): {p}")
            continue
        n = add_rlm_to_srt(p)
        print(f"{p.name}: prefixed {n} subtitle lines with RLM")
    return 0


if __name__ == "__main__":
    sys.exit(main())

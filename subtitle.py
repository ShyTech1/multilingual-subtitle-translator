"""Bilingual (Hebrew + Arabic) transcription pipeline that produces Hebrew subtitles.

Strategy for a Fauda-style show:
  1. Pre-extract audio to a small mono 16 kHz wav (skips PyAV OOM on huge MKVs).
  2. Run Whisper twice on the wav: once forced to Hebrew, once forced to Arabic.
     Both passes use anti-hallucination guards (no prompt-conditioning, repetition
     penalty, no-speech threshold, temperature fallback).
  3. Build a unified timeline by merging all unique segment intervals from both
     passes, then for each interval pick the transcription with the higher
     avg_logprob (better confidence). A small penalty is applied to known
     Whisper hallucination phrases like "Subscribe to the channel".
  4. For each Arabic-picked segment, translate to Hebrew via Google Translate.
     Hebrew-picked segments are written as-is.

Outputs (next to the input video):
  <basename>.he.srt          Final Hebrew subtitles (Hebrew speech + Arabic translated)
  <basename>.he.raw.srt      Raw Hebrew-pass output (for comparison)
  <basename>.ar.raw.srt      Raw Arabic-pass output (for comparison)
"""
from __future__ import annotations

import argparse
import os
import re
import site
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def _register_cuda_dlls() -> None:
    if sys.platform != "win32":
        return
    seen: set[str] = set()
    roots: list[str] = list(site.getsitepackages())
    user_site = site.getusersitepackages()
    if user_site:
        roots.append(user_site)
    for sp in roots:
        nvidia_dir = os.path.join(sp, "nvidia")
        if not os.path.isdir(nvidia_dir):
            continue
        for sub in os.listdir(nvidia_dir):
            bin_dir = os.path.join(nvidia_dir, sub, "bin")
            if os.path.isdir(bin_dir) and bin_dir not in seen:
                try:
                    os.add_dll_directory(bin_dir)
                    seen.add(bin_dir)
                except (OSError, FileNotFoundError):
                    pass


_register_cuda_dlls()

# Use the OS certificate trust store so translation works through corporate /
# antivirus TLS-inspection proxies that inject their own root CA.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception as _exc:  # noqa: BLE001
    print(f"WARNING: truststore not active ({_exc!s}); translation may fail through MITM proxies",
          file=sys.stderr)

from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator


HALLUCINATION_PHRASES = [
    "اشتركوا في القناة",
    "اشترك في القناة",
    "ترجمة",
    "subscribe to the channel",
    "subtitles by",
    "תרגום",
    "כתוביות על ידי",
]

HEBREW_RANGE = (0x0590, 0x05FF)
ARABIC_RANGE = (0x0600, 0x06FF)


@dataclass
class Seg:
    start: float
    end: float
    text: str
    lang: str          # "he" or "ar"
    avg_logprob: float


def _locate_ffmpeg() -> str:
    """Prefer a system-installed ffmpeg (Docker/Linux); fall back to the
    binary bundled with imageio-ffmpeg (Windows)."""
    import shutil
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        return sys_ff
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError(
            "ffmpeg not found on PATH and imageio-ffmpeg is not installed"
        ) from exc


def extract_audio(video: Path, out_wav: Path) -> None:
    ffmpeg = _locate_ffmpeg()
    cmd = [
        ffmpeg, "-y", "-nostdin", "-loglevel", "error",
        "-i", str(video),
        "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(out_wav),
    ]
    subprocess.run(cmd, check=True)


def fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


RLM = "‏"  # Right-to-Left Mark, forces RTL paragraph direction


def write_srt(segments: list[tuple[float, float, str]], path: Path,
              rtl: bool = False) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(segments, 1):
            body = text.strip()
            if rtl and body and not body.startswith(RLM):
                body = RLM + body
            f.write(f"{i}\n{fmt_ts(start)} --> {fmt_ts(end)}\n{body}\n\n")


def hallucination_penalty(text: str) -> float:
    t = text.strip().lower()
    for phrase in HALLUCINATION_PHRASES:
        if phrase.lower() in t:
            return 2.0
    # Repetitive single-token output (e.g. "ok ok ok ok") penalty
    words = re.findall(r"\S+", t)
    if len(words) >= 4 and len(set(words)) <= max(1, len(words) // 4):
        return 1.0
    return 0.0


def transcribe_pass(model: WhisperModel, wav_path: Path, lang: str,
                    beam_size: int = 2) -> list[Seg]:
    print(f"  -> pass language={lang}", flush=True)
    t0 = time.time()
    segs_iter, info = model.transcribe(
        str(wav_path),
        language=lang,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        beam_size=beam_size,
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        repetition_penalty=1.15,
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    )
    out: list[Seg] = []
    for s in segs_iter:
        out.append(Seg(start=s.start, end=s.end, text=s.text.strip(),
                       lang=lang, avg_logprob=s.avg_logprob))
    print(f"  -> {lang}: {len(out)} segments in {time.time()-t0:.1f}s "
          f"({info.duration/max(time.time()-t0,1):.2f}x realtime)", flush=True)
    return out


def merge_by_confidence_multi(passes: list[list[Seg]]) -> list[Seg]:
    """Walk a unified timeline and pick the higher-scoring transcription per slot
    across any number of language passes."""
    all_segs: list[Seg] = [s for p in passes for s in p]
    events: list[tuple[float, float, Seg]] = [(s.start, s.end, s) for s in all_segs]
    events.sort(key=lambda x: x[0])
    if not events:
        return []

    boundaries: set[float] = set()
    for s, e, _ in events:
        boundaries.add(s)
        boundaries.add(e)
    bs = sorted(boundaries)

    picked: list[Seg] = []
    for i in range(len(bs) - 1):
        lo, hi = bs[i], bs[i + 1]
        if hi - lo < 0.2:
            continue
        mid = (lo + hi) / 2
        candidates: list[Seg] = []
        for s, e, seg in events:
            if s <= mid < e:
                candidates.append(seg)
        if not candidates:
            continue
        candidates.sort(
            key=lambda c: c.avg_logprob - hallucination_penalty(c.text),
            reverse=True,
        )
        best = candidates[0]
        if not best.text:
            continue
        # Coalesce with previous picked segment if same language and same source text
        if picked and picked[-1].lang == best.lang and picked[-1].text == best.text \
                and abs(picked[-1].end - lo) < 0.5:
            picked[-1].end = hi
        else:
            picked.append(Seg(start=lo, end=hi, text=best.text,
                              lang=best.lang, avg_logprob=best.avg_logprob))
    return picked


def translate_to_hebrew(segments: list[Seg], batch: int = 25) -> list[Seg]:
    """Translate every non-Hebrew picked segment to Hebrew, grouped by source language."""
    by_lang: dict[str, list[int]] = {}
    for i, s in enumerate(segments):
        if s.lang != "he" and s.text:
            by_lang.setdefault(s.lang, []).append(i)
    out = list(segments)
    if not by_lang:
        print("Nothing to translate (no non-Hebrew picked segments).", flush=True)
        return out

    # Google Translate uses 'iw' (legacy) for Hebrew target.
    target = "iw"
    for src_lang, indices in by_lang.items():
        print(f"Translating {len(indices)} {src_lang} segments -> Hebrew", flush=True)
        translator = GoogleTranslator(source=src_lang, target=target)
        for i in range(0, len(indices), batch):
            chunk_idx = indices[i : i + batch]
            chunk_text = [segments[k].text for k in chunk_idx]
            try:
                translated = translator.translate_batch(chunk_text)
            except Exception as exc:
                print(f"  {src_lang} batch failed ({exc!s}); per-line fallback", flush=True)
                translated = []
                for t in chunk_text:
                    try:
                        translated.append(translator.translate(t) or "")
                    except Exception as e2:
                        print(f"    line failed: {e2!s}", flush=True)
                        translated.append(t)
            for k, ht in zip(chunk_idx, translated):
                seg = segments[k]
                out[k] = Seg(start=seg.start, end=seg.end, text=ht or seg.text,
                             lang="he", avg_logprob=seg.avg_logprob)
            print(f"  {src_lang}: {min(i+batch, len(indices))}/{len(indices)}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--model", default="medium")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu", "auto"])
    ap.add_argument("--compute-type", default="int8_float16",
                    help="ctranslate2 compute type. int8_float16 uses ~half the VRAM "
                         "of float16 with minimal quality loss (default).")
    ap.add_argument("--beam-size", type=int, default=2,
                    help="Beam search width. Lower = less VRAM (default: 2)")
    ap.add_argument("--languages", default="he,ar,fr",
                    help="Comma-separated list of language codes to run passes for "
                         "(any non-Hebrew picked segments get translated to Hebrew)")
    ap.add_argument("--out-suffix", default="",
                    help="Extra infix inserted before .he.srt / .he.raw.srt / .ar.raw.srt "
                         "in output filenames (e.g. '.large-v3' -> base.large-v3.he.srt). "
                         "Useful for keeping multiple runs side-by-side.")
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        print(f"ERROR: file not found: {video}", file=sys.stderr)
        return 2

    out_dir = video.parent
    base = video.stem
    wav_path = out_dir / f"{base}.audio16k.wav"
    suffix = args.out_suffix
    he_path = out_dir / f"{base}{suffix}.he.srt"
    he_raw_path = out_dir / f"{base}{suffix}.he.raw.srt"
    ar_raw_path = out_dir / f"{base}{suffix}.ar.raw.srt"

    if not wav_path.exists():
        print(f"Extracting audio -> {wav_path.name}", flush=True)
        t0 = time.time()
        extract_audio(video, wav_path)
        print(f"  audio extracted in {time.time()-t0:.1f}s "
              f"({wav_path.stat().st_size/1024/1024:.1f} MB)", flush=True)
    else:
        print(f"Reusing existing {wav_path.name}", flush=True)

    print(f"Loading Whisper model '{args.model}' on {args.device} "
          f"(compute_type={args.compute_type})...", flush=True)
    t0 = time.time()
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    print(f"Model loaded in {time.time()-t0:.1f}s", flush=True)

    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    print(f"Transcribing with languages: {langs}", flush=True)
    pass_results: dict[str, list[Seg]] = {}
    for lang in langs:
        pass_results[lang] = transcribe_pass(model, wav_path, lang, beam_size=args.beam_size)

    # Free GPU memory before translation step
    del model

    if "he" in pass_results:
        write_srt([(s.start, s.end, s.text) for s in pass_results["he"]], he_raw_path)
        print(f"Wrote {he_raw_path.name}", flush=True)
    if "ar" in pass_results:
        write_srt([(s.start, s.end, s.text) for s in pass_results["ar"]], ar_raw_path)
        print(f"Wrote {ar_raw_path.name}", flush=True)

    if len(pass_results) == 1:
        _only_lang, segs = next(iter(pass_results.items()))
        segs = translate_to_hebrew(segs)
        write_srt([(s.start, s.end, s.text) for s in segs], he_path, rtl=True)
    else:
        all_passes = list(pass_results.values())
        print(f"Merging {len(all_passes)} language passes by confidence...", flush=True)
        merged = merge_by_confidence_multi(all_passes)
        breakdown = ", ".join(
            f"{lang}-picked: {sum(1 for s in merged if s.lang == lang)}"
            for lang in pass_results
        )
        print(f"  merged into {len(merged)} segments ({breakdown})", flush=True)
        merged = translate_to_hebrew(merged)
        write_srt([(s.start, s.end, s.text) for s in merged], he_path, rtl=True)

    print(f"Wrote {he_path.name}", flush=True)
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# LinkedIn post drafts

Pick whichever one feels closer to your voice and tweak. I've kept all of them
under LinkedIn's 3,000-char limit. Add 1-2 screenshots of subtitles overlaid on
a video frame — those drive the most engagement on this kind of post.

---

## Draft A — "the story" (recommended)

I wanted to watch a bilingual Israeli show with my partner, but the only
subtitles available covered just half the dialog. The other half — the Arabic
scenes — had nothing. So I built an auto-subtitle pipeline. A weekend later
it's on GitHub.

The interesting part wasn't running Whisper. The interesting part was that
running Whisper *naively* on a bilingual video produces hallucinations:
forcing language="ar" on a Hebrew scene gives you "اشتركوا في القناة"
("Subscribe to the channel") repeated for 17 minutes straight. That phrase
is a known artifact of YouTube-trained data leaking through when the model
is fed audio that doesn't match the forced language.

The fix I settled on:
→ Pre-extract 16 kHz mono audio with ffmpeg (PyAV OOMs on large MKVs)
→ Run Whisper N times — one pass per candidate language — each with strong
   anti-hallucination guards (condition_on_previous_text off, repetition
   penalty, temperature fallback ladder, VAD)
→ Walk the union of segment boundaries and pick the highest-confidence
   transcription per slice, with a penalty for known hallucination phrases
→ Translate non-Hebrew picks to Hebrew via Google Translate
→ Emit RTL-marked .srt (U+200F prefix) so bidi rendering doesn't shuffle
   punctuation

Hardware-wise: medium model on an RTX 3060 → ~5-8 min for a 45-min episode.
CPU-only works too, just much slower.

Packaged with two Docker images (CPU + CUDA), a launcher that auto-picks
based on `nvidia-smi`, and a shared HuggingFace cache volume so the 1.5 GB
model only ever downloads once.

A few rabbit holes worth flagging if you're building similar things:
• PyAV's AudioFifo buffers the whole stream → OOM on large files. Decode to
  WAV first.
• ctranslate2 reports cuDNN init failures as "out of memory" even when you
  have 9 GB free. Don't chase a phantom VRAM leak; drop to int8_float16 and
  beam_size=2.
• Corporate networks MITM HTTPS with their own root CA, breaking
  `certifi`. Use `truststore` to fall back to the OS cert store.

Code, Dockerfiles, and a writeup of the design choices:
https://github.com/ShyTech1/multilingual-subtitle-translator

#opensource #whisper #python #docker #speechtotext #machinelearning

---

## Draft B — "shorter / punchier"

Spent the weekend solving a small problem that turned out to be more
interesting than expected: auto-generating Hebrew subtitles for a show with
mixed Hebrew, Arabic and French dialog.

Forcing Whisper to one language hallucinates on the other-language stretches
("Subscribe to the channel", on loop, for 17 minutes). The fix is to run a
pass per candidate language and merge by per-segment confidence.

Code, Docker images (CPU + CUDA), full writeup:
https://github.com/ShyTech1/multilingual-subtitle-translator

Tech: faster-whisper + ctranslate2 (GPU), deep-translator (Google), ffmpeg,
truststore (for corporate TLS interception), Docker compose.

Things I learned the hard way:
→ PyAV decodes the whole audio stream into memory. Pre-extract WAV.
→ "CUDA out of memory" can mean cuDNN init failed, not actual VRAM
   shortage. Try int8_float16 before assuming a leak.
→ A small RLM prefix (U+200F) fixes 90% of "the question mark is on the
   wrong side" issues in Hebrew/Arabic subtitles.

#opensource #python #whisper #docker

---

## Draft C — "technical deep-dive" (for an engineering audience)

How do you generate good Hebrew subtitles for a show that code-switches
between Hebrew and Arabic mid-scene?

Naive approach: run Whisper with `language="ar"`. Result: 17 straight
minutes of `اشتركوا في القناة` ("Subscribe to the channel"), the famous
YouTube-data artifact that surfaces when the audio doesn't match the
forced language.

The approach I landed on:

1. ffmpeg → 16 kHz mono WAV. Necessary because PyAV (used internally by
   faster-whisper) tries to buffer the full audio stream and OOMs on
   typical episode-sized MKVs.

2. N independent Whisper passes — one per candidate language — each with
   anti-hallucination guards:
     - condition_on_previous_text=False (stops poisoning loops)
     - repetition_penalty=1.15
     - no_speech_threshold=0.6, log_prob_threshold=-1.0
     - temperature fallback [0.0, 0.2, …, 1.0]
     - silero VAD with min_silence_duration_ms=500

3. Boundary-walked merge: take the union of all segment intervals across
   passes, split into atomic sub-intervals, and per sub-interval pick the
   candidate with the highest `avg_logprob − hallucination_penalty`.

4. Non-Hebrew picks → Google Translate → Hebrew.

5. RTL-mark the output (U+200F prefix on each line) for clean bidi.

Packaged as two Docker images (CPU + CUDA) sharing 95% of the same
content, with a launcher that auto-picks based on nvidia-smi and a shared
HF cache volume so the 1.5 GB Whisper model is downloaded once and shared
between containers and native runs.

A few surprises:
• ctranslate2 reports cuDNN initialization failures as
  `RuntimeError: CUDA failed with error out of memory`, even with 9 GB
  VRAM free. Drop to int8_float16 + beam_size=2.
• Corporate / antivirus TLS interception breaks certifi. truststore
  redirects to the OS cert store and Just Works.
• Google Translate's free endpoint occasionally returns "no translation
  found" for short fragments — handle with a per-line fallback.

Code, writeup, and Docker setup:
https://github.com/ShyTech1/multilingual-subtitle-translator

#whisper #faster_whisper #ctranslate2 #docker #python #speechtotext #opensource

---

## Draft D — "selling, hook-led" (recommended for engagement)

Ever tried watching a show in a language you only half-speak?
Or worse — a show that code-switches between two languages mid-scene, with
subtitles for only one of them?

That was me on Friday night. By Sunday I had a working pipeline. It's now
open source — drag a video onto it, get clean Hebrew subtitles back.

The naive approach (run Whisper, force a language) fails spectacularly: on
the wrong-language stretches the model hallucinates "Subscribe to the
channel" — on loop — for 17 minutes straight. A famous artifact of
YouTube-trained data leaking through.

The fix:
→ Run Whisper N times — one pass per candidate language — with strong
   anti-hallucination guards.
→ Walk the union of segment boundaries and pick the highest-confidence
   slice per timestamp.
→ Translate the non-Hebrew picks to Hebrew. Emit RTL-marked .srt.

Result: ~6 minutes to subtitle a 45-minute episode on an RTX 3060. CPU
works too, just slower. One command on Windows, Linux, or macOS — Docker
auto-picks the right image based on whether you have a GPU.

→ Code & Dockerfiles: https://github.com/ShyTech1/multilingual-subtitle-translator

Three things I learned the hard way:

1. PyAV (used inside faster-whisper) buffers the whole audio stream in
   memory → OOM on episode-sized MKVs. Pre-extract a 16 kHz mono WAV with
   ffmpeg and the problem disappears.

2. "CUDA out of memory" from ctranslate2 can actually mean cuDNN failed to
   initialize — even with 9 GB of VRAM free. Don't chase a phantom leak;
   try int8_float16 + beam_size=2.

3. A single U+200F (RTL mark) at the start of each line fixes 90% of "the
   question mark is on the wrong side" issues in Hebrew/Arabic subtitles
   across every player I tested.

If you've hit similar problems with multilingual ASR — or have ideas to
improve the merge — open an issue, I'd love to compare notes.

#opensource #python #whisper #docker #speechtotext #machinelearning

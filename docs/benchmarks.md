# Dictation benchmark: 5 seconds to 2 minutes

2026-10-18. 94 measured recording-level trials, including the thread sweep, plus warmups and installation checks. Intel Core i5-8350U (4 cores / 8 logical CPUs), 15 GiB RAM, AVX2 CPU inference, AC power, powersave governor, normal Ryoku desktop session. No compiler or competing benchmark ran during timings.

## Selected setup

Stock `/usr/bin/voxtype` 1.1.0, its existing CLI backend, and a resident standard-library Python adapter using unmodified parakeet.cpp. The native pool has two backend slots, each with four compute threads; requests are sequential. Audio longer than 30 seconds is split at quiet frames near each 30-second boundary. This is tuning in the adapter, not a patch to Voxtype. The GGUF model stays loaded.

Full stock-Voxtype adapter medians (three runs for the 5/30/120-second cases): **0.95 s / 5.06 s / 21.11 s**. On the 119.7-second recording, normalized WER was **5.23% (15 word edits / 287 reference words)** and sampled peak backend RSS was **672 MiB**.

The official Photon adapter was slightly faster at **19.13 s** for that recording, with **5.57% WER (16/287)** and **1742 MiB** peak backend RSS. A one-word difference on one sample is not evidence that one runtime is generally more accurate. The selected C++ adapter trades about two seconds at two minutes for much lower memory use, faster worker startup, and no Photon/PyTorch dependency.

Original Parakeet INT8 was stronger on the added-noise sample (7.35% WER versus 11.76% for both Redux adapters), so it remains a candidate if noise accuracy outweighs memory and latency. Moonshine with chunking was fastest at two minutes but lost accuracy in noise; unsplit Moonshine is unsuitable for this tested range.

## Actual packaged Whisper controls

The packaged Whisper build outperformed the helper build. These control measurements therefore use the real stock `/usr/bin/voxtype` 1.1.0, rather than the helper numbers. Each file invocation loads Whisper afresh: the wall times below include that load (roughly 0.1–0.2 s), while the raw JSON also records the logged inference interval. Treat these as conservative comparisons with a resident Whisper daemon, not exact warm-daemon timings. Accuracy matched the helper on these cases.

| Packaged model | ~5 s | ~15 s | ~30 s | ~60 s | ~120 s | WER at ~120 s | Noisy ~30 s WER |
|---|---:|---:|---:|---:|---:|---:|---:|
| Packaged Whisper tiny.en (includes model load) | 1.66 | 1.99 | 2.37 | 6.39 | 11.56 | 10.5% | 19.1% |
| Packaged Whisper base.en (includes model load) | 3.43 | 3.84 | 4.34 | 12.95 | 22.15 | 8.4% | 17.6% |

The helper Whisper timings remain in the raw files for transparency; they are not used as the production Whisper speed comparison below.

## Warm latency and accuracy

Times are seconds to finish transcription after the complete WAV is available. Approximate input labels correspond to exact durations 5.015, 14.470, 29.400, 59.565 and 119.705 seconds. Model loading and microphone recording time are excluded. Adapter times include the real packaged Voxtype CLI process, temporary-WAV conversion, client startup, socket round trip and JSON handling. Direct helper times include file decode and request handling. They do not measure typing text into an application.

| Configuration | ~5 s | ~15 s | ~30 s | ~60 s | ~120 s | WER at ~120 s | Noisy ~30 s WER | Peak backend RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Stock Voxtype + tuned C++ adapter (selected) | 0.95 | 2.55 | 5.06 | 10.95 | 21.11 | 5.2% | 11.8% | 672 MiB |
| Stock Voxtype + official Photon adapter | 0.92 | 2.30 | 4.57 | 9.72 | 19.13 | 5.6% | 11.8% | 1742 MiB |
| Official Photon, direct | 0.76 | 2.15 | 4.47 | 9.58 | 19.26 | 5.6% | 11.8% | 1693 MiB |
| Original Parakeet v3 INT8, native Voxtype backend | 0.79 | 2.17 | 4.30 | 9.75 | 23.49 | 5.6% | 7.4% | 2328 MiB |
| Custom Voxtype Redux/C++, original defaults | 1.52 | 4.01 | 7.61 | 16.83 | 39.46 | 5.6% | 11.8% | 1666 MiB |
| Moonshine base, unsplit | 0.45 | 1.38 | 3.04 | 5.74 | 29.22 | 126.5% | 11.8% | 1951 MiB |
| Moonshine base + experimental 15s quiet splits | 0.42 | 1.41 | 2.68 | 5.02 | 10.22 | 7.3% | 29.4% | 649 MiB |
| C++ four-thread team, unsplit | — | — | 4.90 | — | 36.65 | 5.6% | — | 1675 MiB |
| C++ four-thread team, 30s quiet splits, direct | 0.80 | 2.48 | 4.97 | 10.68 | 20.63 | 5.2% | 11.8% | 670 MiB |

Most rows are single-pass screening results after one separate five-second warmup. The two stock adapters repeat the 5/30/120-second cases three times; those table cells are medians. The 15/60-second and noise cells remain single trials. Peak RSS is sampled from each inference process, including its loaded libraries and workspace; it excludes the separate stock Voxtype daemon/client for adapter rows. The helper was built from Voxtype 1.1.1 public backend code using an optimized development profile; Whisper C++ used RelWithDebInfo. The production daemon is packaged stock 1.1.0, and the adapter runs were measured through that exact stock binary.

## Repeated adapter trials

| Adapter | Input | Median | Min–max | Repeats |
|---|---:|---:|---:|---:|
| stock-cpp-adapter | ~5 s | 0.952 s | 0.945–0.992 s | 3 |
| stock-cpp-adapter | ~30 s | 5.057 s | 5.027–5.338 s | 3 |
| stock-cpp-adapter | ~120 s | 21.107 s | 20.478–21.120 s | 3 |
| stock-photon-adapter | ~5 s | 0.924 s | 0.902–0.929 s | 3 |
| stock-photon-adapter | ~30 s | 4.566 s | 4.419–5.145 s | 3 |
| stock-photon-adapter | ~120 s | 19.132 s | 18.643–19.448 s | 3 |

## Tuning

| Native CPP compute setting | Median for 14.47 s audio | Trials |
|---|---:|---:|
| Native default (8 compute threads) | 4.299 s | 2 |
| Two backend slots, 1 compute threads per slot; sequential calls | 5.794 s | 2 |
| Two backend slots, 2 compute threads per slot; sequential calls | 3.293 s | 2 |
| Two backend slots, 4 compute threads per slot; sequential calls | 2.444 s | 2 |

Splitting long CPP audio near 30 seconds reduced the 119.7-second result from 36.65 s unsplit at the selected thread setting to 20.64 s direct. Peak backend RSS fell from 1675 MiB to 670 MiB. This is the main reason the final adapter improves on the original custom Voxtype integration; an adapter alone is not intrinsically faster than in-process inference.

## Accuracy limits

The corpus is a small public LibriSpeech validation subset with one speaker, not microphone dictation or a meeting. Complete utterances are assembled with 0.2-second gaps; some utterances recur across duration cases. The noisy case adds deterministic white noise at 20dB SNR; it does not simulate competing speakers or room reverberation. No unseen-data or general production-accuracy claim is made. WER is token edit distance after lowercasing, punctuation removal and Mr./Mrs. expansion; raw references/transcripts are preserved. WER can exceed 100% when a model inserts or repeats many words, as unsplit Moonshine did at two minutes.

## Data and reproduction notes

- `audio-manifest.json`: exact references, utterance IDs, WAV hashes and durations; recordings are not bundled.
- `measurements.csv`: per-run recording latency, word error counts and transcripts.
- `thread-sweep.json`: the eight measured thread-sweep trials.
- `benchmark-metadata.json`: source revisions, model/library hashes and hardware settings.
- Portable versions of the screening harnesses and complete archived per-run JSON are now included under [`../benchmarks/`](../benchmarks/). The original native Voxtype fork is pinned as `custom-voxtype/`; its helper source and standalone patch are included. See the benchmark README for path overrides, corpus preparation and reproduction limits.
- Native validation also exercised installed stock transcription, wrong-model rejection, duplicate-worker protection, stale-socket recovery after SIGKILL, permissions and graceful cleanup.

Source corpus: [Hugging Face LibriSpeech dummy validation](https://huggingface.co/datasets/hf-internal-testing/librispeech_asr_dummy). Model/runtime: [Redux model card](https://huggingface.co/moondream/parakeet-redux), [parakeet.cpp](https://github.com/mudler/parakeet.cpp). Photon measured with `moondream==2.6.1`, CPU PyTorch `2.14.1+cpu`; ONNX helper used `onnxruntime==1.31.0`.

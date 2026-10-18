# Voxtype Redux Adapter

[![CI](https://github.com/Sipper1236/voxtype-redux-adapter/actions/workflows/ci.yml/badge.svg)](https://github.com/Sipper1236/voxtype-redux-adapter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Local Parakeet Redux dictation for **stock Voxtype**, using its existing CLI backend and a resident **parakeet.cpp** worker. The model stays loaded between recordings. This adapter uses Python's standard library; its default runtime requires neither Photon nor PyTorch.

```text
Compositor shortcut → stock Voxtype → temporary WAV → adapter CLI
                                                  ↓ private Unix socket
                                           resident parakeet.cpp
                                                  ↓
                                           transcript → Voxtype → typing
```

Tested on Linux with packaged Voxtype 1.1.0 and parakeet.cpp C API ABI 10. This is an experimental initial release; API compatibility and performance on other systems need validation. It does not require Ryoku.

## Native fork and reproducible benchmarks

The original in-process implementation is now included as the pinned [`custom-voxtype/`](custom-voxtype) submodule, backed by the actual [Voxtype native fork](https://github.com/Sipper1236/voxtype-redux-native). [`custom/`](custom/) also contains its standalone patch, parent revision and build notes.

[`benchmarks/`](benchmarks/) includes the portable runners, corpus preparation, raw per-run results, thread/chunk experiments and earlier short-clip history. Clone with `--recurse-submodules` to get the full fork source, or run `git submodule update --init custom-voxtype` later. The submodule is optional for using the stock adapter.

## Requirements

- Python 3.11+ and stock [Voxtype](https://github.com/peteonrails/voxtype) with its CLI backend.
- A recent [parakeet.cpp](https://github.com/mudler/parakeet.cpp) shared library, **C API ABI 10 or newer**, including `parakeet_capi_set_concurrency` for the installed tuning.
- A [Parakeet Redux GGUF](https://huggingface.co/mudler/parakeet-cpp-gguf/tree/main) compatible with that runtime. The original model is [moondream/parakeet-redux](https://huggingface.co/moondream/parakeet-redux). Model weights are downloaded separately.
- A Linux user session with `XDG_RUNTIME_DIR`. The installer uses user systemd services and expects the stock `voxtype.service` to exist (use upstream Voxtype's systemd setup if necessary).

To build a CPU shared library from upstream source:

```sh
git clone --recurse-submodules https://github.com/mudler/parakeet.cpp.git
cmake -S parakeet.cpp -B parakeet.cpp/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DPARAKEET_SHARED=ON -DBUILD_SHARED_LIBS=ON \
  -DPARAKEET_BUILD_CLI=OFF -DPARAKEET_BUILD_SERVER=OFF \
  -DPARAKEET_WITH_CED=OFF -DPARAKEET_WITH_VOICEDETECT=OFF
cmake --build parakeet.cpp/build --target parakeet -j 4
```

Keep the build directory, including its ggml libraries, available. Pass the absolute path to `build/libparakeet.so` below. The benchmark used upstream commit `5c9b0fbbd8e611d88e47d7e1ebae9bca9b447e8f`; see [benchmark metadata](docs/benchmark-metadata.json).

## Install

```sh
git clone https://github.com/Sipper1236/voxtype-redux-adapter.git
cd voxtype-redux-adapter
python3 install.py \
  --model /absolute/path/to/redux-packed.gguf \
  --library /absolute/path/to/parakeet.cpp/build/libparakeet.so
```

The installer writes user-owned files and prints activation commands. **It does not reload or start services unless you pass `--activate`.** It refuses existing generated files unless `--force` is supplied; that option creates timestamped backups before replacement. `--prefix DIR` stages a separate home layout for inspection and cannot activate services. `--voxtype PATH` selects a different stock executable.

Installed files:

| File | Purpose |
|---|---|
| `~/.local/bin/voxtype-redux` | whisper-cli-compatible command |
| `~/.local/share/voxtype-redux/adapter.py` | Resident worker |
| `~/.config/voxtype/redux-adapter.toml` | Dedicated stock Voxtype profile |
| `~/.config/systemd/user/voxtype-redux.service` | Worker with systemd readiness notification |
| `~/.config/systemd/user/voxtype.service.d/redux-adapter.conf` | Orders Voxtype after the worker and selects the profile |

`XDG_CONFIG_HOME` and `XDG_DATA_HOME` are respected for normal installation. Your original Voxtype config is preserved. Existing compositor bindings can continue calling `voxtype record toggle`; the installer does not change desktop keybindings. The generated profile enables typing into the focused application, disables Voxtype's built-in hotkey/OSD, and permits up to 120 seconds of recording. Customize its audio device, output settings, and any desktop integration before activation.

Activate after reviewing the files:

```sh
systemctl --user daemon-reload
systemctl --user enable voxtype-redux.service
systemctl --user restart voxtype-redux.service
systemctl --user restart voxtype.service
~/.local/bin/voxtype-redux status
```

If another drop-in also changes Voxtype's `ExecStart`, inspect `systemctl --user cat voxtype.service` and resolve the conflicting override. Restarting this service switches the daemon's backend.

## How it works

Stock Voxtype's `[whisper] mode = "cli"` launches a whisper-cli-compatible command. The profile's `engine = "whisper"` selects that existing protocol; recognition is performed by Redux. The adapter writes the expected `OUTPUT_BASE.json` with `{"transcription":[{"text":"..."}]}`.

The worker loads one native context and serves requests sequentially over a user-private Unix socket (directory 0700, socket 0600). It rejects mismatched model paths, leaves live workers alone, and recovers an owned stale socket after a crash. Requests complete before Voxtype deletes the temporary WAV. Client waits are bounded to 180 seconds.

The generated service uses `--pool-threads 4 --chunk-seconds 30`, selected on one i5-8350U laptop:

- `--pool-threads N` creates two native backend slots with N compute threads per slot. Requests remain sequential, so one compute team is active at a time. Zero leaves the native default unchanged.
- `--chunk-seconds N` splits long input at a quiet 20ms frame near each boundary. Chunks do not overlap; this can split words and must be evaluated on your audio. Zero disables splitting.
- Voxtype's per-call `--threads` flag is a compatibility argument and does not retune the resident worker.
- Input must be mono, 16-bit PCM WAV at 16 kHz. Voxtype supplies this format.
- Translation, prompts, and forced languages other than English/auto are rejected. The model detects language; `--language en` is compatibility input, not a hard language constraint.

For a manual worker, use `python3 redux_adapter.py serve --model /absolute/model.gguf --library /absolute/libparakeet.so`. Set `VOXTYPE_REDUX_SOCKET` on both client and worker to choose another socket, or pass `serve --socket PATH` on the worker.

## Measured performance

94 recording-level trials on an **Intel Core i5-8350U, 4 cores / 8 logical CPUs, AVX2, 15 GiB RAM**, using a small single-speaker LibriSpeech subset. The stock adapters repeat the ~5/~30/~120-second cases three times; the figures below are medians, with the model resident.

| Setup | ~5 s audio | ~30 s audio | ~120 s audio | ~120 s WER | Peak worker RSS |
|---|---:|---:|---:|---:|---:|
| Stock Voxtype + tuned C++ adapter | 0.95 s | 5.06 s | 21.11 s | 5.23% | 672 MiB |
| Stock Voxtype + optional Photon adapter | 0.92 s | 4.57 s | 19.13 s | 5.57% | 1742 MiB |

These measurements include the stock Voxtype CLI process, WAV conversion, adapter startup and socket round trip. They exclude microphone recording and typing. The accuracy difference is one word edit in a 287-word sample, not evidence of generally better accuracy. The C++ settings trade a small latency increase for lower memory and fewer dependencies. Results are not a microphone, meeting, or multi-speaker accuracy guarantee.

[Full comparison and limitations](docs/benchmarks.md) · [Raw measurements](docs/measurements.csv) · [Hardware/model metadata](docs/benchmark-metadata.json)

## Optional Photon backend

The source retains `serve --backend photon` for comparison with the official Moondream runtime. It is **not used by the default installer** and is imported only when explicitly selected. Install and license that runtime separately; no Photon/native kernel packages are bundled here. Its Python wrapper availability should not be taken as verification that every native/kernel component has matching open-source licensing. For the stock CLI model-identity check, this experimental backend defaults to the compatibility GGUF at `~/.local/share/voxtype/models/redux-packed.gguf`; `serve --compat-model PATH` selects a different alias path for the same canonical Redux model.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The portable tests exercise the CLI/socket protocol, error handling, validation and installer in a temporary prefix, without downloading models or touching desktop services. For a native smoke test after installing real dependencies, run:

```sh
/usr/bin/voxtype --config ~/.config/voxtype/redux-adapter.toml transcribe /absolute/speech.wav
```

## Uninstall or restore

Remove the generated `voxtype.service.d/redux-adapter.conf` drop-in, reload systemd, and restart `voxtype.service` to return to its previous configuration. Then disable and stop `voxtype-redux.service`. Remove the generated adapter files/profile/unit when no longer needed. If files were replaced with `--force`, restore their timestamped backups instead of deleting them. Check for other existing Voxtype overrides before restarting.

## Licenses and credits

Adapter code: [MIT](LICENSE). No model weights, personal recordings, native libraries, or Photon packages are bundled. The optional Voxtype fork retains its upstream license and public test fixtures.

- [Voxtype](https://github.com/peteonrails/voxtype) and [parakeet.cpp](https://github.com/mudler/parakeet.cpp) are separate MIT-licensed projects. parakeet.cpp uses [ggml](https://github.com/ggml-org/ggml).
- [Parakeet Redux](https://huggingface.co/moondream/parakeet-redux) weights are CC BY 4.0, derived by Moondream from NVIDIA's [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3). Converted GGUF weights retain their model licensing and attribution requirements.
- Benchmark audio/references came from [hf-internal-testing/librispeech_asr_dummy](https://huggingface.co/datasets/hf-internal-testing/librispeech_asr_dummy), a LibriSpeech validation subset. Audio is not redistributed here; measurement CSVs contain model-generated transcripts of those public benchmark recordings.

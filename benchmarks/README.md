# Benchmark runners and archived results

These are portable versions of the harnesses used for the published 5–120-second comparison. They run locally and do not install a daemon, change compositor bindings, or type into an application. CPU inference is sequential. Do not run the different scripts concurrently if comparing their timings.

## What is included

- `reference-results/`: complete per-recording JSON from the 94 measured trials, plus four packaged-binary sanity checks. The four extra checks are not included in the published 94-trial count.
- `legacy/`: earlier 1–24-second measurements and the original short-clip runners, adapted to configurable paths.
- `prepare_audio.py`: downloads the public LibriSpeech dummy Parquet and reconstructs the exact whole-utterance clean/noisy WAVs.
- `bench_worker.rs`: resident Voxtype backend helper; also committed in the pinned custom fork as `examples/bench_worker.rs`.
- `run_suite.py`: warm backend screening through the resident helper or official Photon.
- `run_optimizations.py`: CPP thread sweep, CPP chunking comparison and Moonshine 15s chunking experiment.
- `run_adapters.py`: actual stock Voxtype CLI calls through private benchmark-only adapter workers; repeats ~5/~30/~120-second cases three times.
- `run_stock_whisper.py`: packaged Whisper controls, including per-command model loading.
- `verify_stock.py`: additional ~30-second packaged-binary checks.
- `summarize.py`: dynamic Markdown/CSV aggregation of available records, without a hardcoded winner.

Model weights, audio, generated configs, new results and logs are ignored by Git. Archived JSON paths use `~` or `$MODELS_DIR` as descriptive placeholders; they are historical records, not executable configs. The original timings, transcripts and accuracy calculations are retained.

## Prepare dependencies and audio

From the repository root:

```sh
git submodule update --init custom-voxtype
python3 -m venv .venv-bench
. .venv-bench/bin/activate
python -m pip install -r benchmarks/requirements.txt onnxruntime
python benchmarks/prepare_audio.py --verify-reference
```

The benchmark was measured using Python 3.12, NumPy 2.5.4, SoundFile 0.14.0 and PyArrow 26.0.0. Other versions may change the encoded WAV hash. Verification compares hashes and durations against `docs/audio-manifest.json`; inspect any mismatch before comparing results. No model inference is involved in preparation.

Provide the existing native runtime and model locations:

```sh
export VOXTYPE_REDUX_MODEL=/absolute/path/to/redux-packed.gguf
export VOXTYPE_REDUX_LIBRARY=/absolute/path/to/libparakeet.so
export VOXTYPE_MODELS_DIR="$HOME/.local/share/voxtype/models"
export VOXTYPE_STOCK_BINARY=/usr/bin/voxtype
export VOXTYPE_BENCH_PYTHON="$PWD/.venv-bench/bin/python"
```

The model directory must also contain `ggml-tiny.en.bin`, `ggml-base.en.bin`, `parakeet-tdt-0.6b-v3-int8/`, and `moonshine-base/` for the corresponding comparisons. Download them separately using upstream Voxtype's model tooling. The runners never download models automatically.

Build the resident backend helper:

```sh
cargo build --manifest-path custom-voxtype/Cargo.toml \
  --release --features parakeet-cpp,moonshine --example bench_worker
```

See [the custom fork build notes](../custom/README.md), including the original laptop's OpenVINO-fetch/bindgen workarounds and scope of validation. A clean full-manifest build was not the original laptop verification. The Rust ONNX backends require a compatible dynamic runtime exposing API 24+; `onnxruntime==1.31.0` was used in the measurements. `backend_env()` discovers the library from the current Python environment, or you can set `ORT_DYLIB_PATH` explicitly.

## Run the comparison

```sh
python benchmarks/run_suite.py
python benchmarks/run_optimizations.py
python benchmarks/run_adapters.py cpp
python benchmarks/run_stock_whisper.py
python benchmarks/summarize.py
```

The default suite excludes Photon. It screens tiny.en, base.en, custom Redux/C++, original Parakeet INT8 and Moonshine. You can pass individual model names to `run_suite.py`. Completed successful suite results are skipped; move/remove the corresponding file in the generated results directory to rerun. Failed suite results are retried. Other runners replace their own generated result files. Keep archived references separate from new runs.

The adapter benchmark needs `XDG_RUNTIME_DIR` and uses a unique private socket; it does not connect to or restart your production worker. It uses the fastest thread setting from a prior `cpp-thread-sweep.json`, or four when no sweep exists.

Optional native packaged verification:

```sh
export VOXTYPE_ONNX_BINARY=/absolute/path/to/a/stock/onnx-enabled/voxtype
python benchmarks/verify_stock.py
```

The ordinary stock executable may only compile Whisper. The resident helper and the ONNX-enabled stock binary are distinct measurements; their runtime/build versions can differ. Packaged Whisper was faster than the locally built helper in the original tests, so the published production Whisper comparison uses the actual packaged executable.

## Optional Photon comparisons

Photon is installed separately and may ship native/kernel binary components whose complete source/licensing has not been verified here. The default adapter and default benchmark suite do not load it. To reproduce that optional baseline, install the runtime in your chosen benchmark environment. On CPU-only hardware, install a CPU PyTorch wheel before Moondream to avoid a CUDA dependency download:

```sh
python -m pip install --index-url https://download.pytorch.org/whl/cpu 'torch>=2.8'
python -m pip install 'moondream==2.6.1'
python benchmarks/run_suite.py vanilla-photon
python benchmarks/run_adapters.py photon
python benchmarks/summarize.py
```

These commands may download the original packed Redux weights through Photon on first use. The Photon adapter benchmark passes an explicit `--compat-model` alias for the same Redux model when the GGUF compatibility path is customized.

## Path overrides

| Environment variable | Default |
|---|---|
| `VOXTYPE_BENCH_AUDIO_DIR` | `benchmarks/audio` |
| `VOXTYPE_BENCH_RESULTS_DIR` | `benchmarks/results` |
| `VOXTYPE_BENCH_CONFIG_DIR` | `benchmarks/configs` |
| `VOXTYPE_BENCH_PYTHON` | Current Python executable |
| `VOXTYPE_BENCH_WORKER` | `custom-voxtype/target/release/examples/bench_worker` |
| `VOXTYPE_STOCK_BINARY` | `/usr/bin/voxtype` |
| `VOXTYPE_ONNX_BINARY` | Same as the stock binary; override for verification |
| `VOXTYPE_MODELS_DIR` | `~/.local/share/voxtype/models` |
| `VOXTYPE_REDUX_MODEL` | Models directory + `redux-packed.gguf` |
| `VOXTYPE_REDUX_LIBRARY` | `~/.local/lib/voxtype-parakeet/libparakeet.so` |
| `ORT_DYLIB_PATH` | Explicit override or discovered from Python ONNX Runtime |

The Rust C API library override is automatically set from `VOXTYPE_REDUX_LIBRARY` for benchmark children. TOML configs are generated in the benchmark config directory, not in your production config. The runtime manifest resolves relative filenames under the audio directory; a custom `manifest.json` there can select other cases.

Summarize archived references without changing them:

```sh
python benchmarks/summarize.py benchmarks/reference-results \
  --output-dir benchmarks/results/reference-summary
```

## Earlier short-clip experiment

`legacy/redux-2026-10-18/` and `legacy/model-comparison-2026-10-18/` retain the earlier raw JSON/JSONL. The direct C API runner is `legacy/benchmark_cpp.py`; it uses fixtures in the custom fork and a parakeet.cpp checkout. Set `VOXTYPE_PARAKEET_SOURCE` to that checkout, and optionally `VOXTYPE_CUSTOM_BINARY` to a built native Voxtype executable. It writes under the generated results directory.

For the original four-clip native helper, copy `legacy/compare_models.rs` into the custom fork's `examples/`, build it with `parakeet-cpp`, and set `VOXTYPE_LEGACY_WORKER` to the resulting executable. Set `VOXTYPE_VAD_FIXTURES` to the fork's `tests/fixtures/vad`, `VOXTYPE_PARAKEET_SOURCE` to the parakeet.cpp checkout, and `VOXTYPE_REDUX_MODEL` to the GGUF; `legacy/run_compare.py` launches each model sequentially. The original API-only C++ timing excludes WAV read/conversion; the later suite uses full warm request time. Do not combine the two timing boundaries as if identical.

## Interpretation

All public accuracy numbers are for a small single-speaker validation subset with repeated utterances across duration cases and one deterministic 20dB white-noise test. WER normalization lowercases, removes punctuation and expands Mr./Mrs. A one-word difference in the two-minute sample is not a general accuracy ranking. Chunking can cut words; Moonshine's chunked noise result demonstrates that speed improvements can reduce accuracy. The dynamic summarizer reports available measurements rather than choosing a universal winner.

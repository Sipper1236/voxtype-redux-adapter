# Changelog

## 0.2.0 — 2026-10-18

- Add the actual custom Voxtype native fork as a pinned optional submodule, with a standalone patch and upstream provenance.
- Publish portable benchmark runners, corpus reconstruction, dynamic result summaries and complete archived JSON, including earlier short-clip experiments.
- Make runtime/model/helper paths configurable for benchmark reproduction.
- Add an explicit Photon compatibility-model alias for nondefault GGUF paths.

## 0.1.0 — 2026-10-18

- Resident parakeet.cpp C API worker with a whisper-cli-compatible adapter for stock Voxtype.
- Private Unix socket, model identity checks, stale-socket recovery and systemd readiness.
- Optional quiet-point chunking and native backend-pool thread tuning.
- Portable user-level installer with a dedicated profile, backups and opt-in activation.
- Optional Photon comparison backend, separate from the default runtime.
- Hardware measurements across 5–120-second recordings, noisy speech and multiple backends.

"""Machine-local benchmark paths. No production services or configs are modified."""
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
AUDIO = Path(os.environ.get('VOXTYPE_BENCH_AUDIO_DIR', ROOT / 'audio')).expanduser().absolute()
OUT = Path(os.environ.get('VOXTYPE_BENCH_RESULTS_DIR', ROOT / 'results')).expanduser().absolute()
CONFIGS = Path(os.environ.get('VOXTYPE_BENCH_CONFIG_DIR', ROOT / 'configs')).expanduser().absolute()
PYTHON = os.environ.get('VOXTYPE_BENCH_PYTHON', sys.executable)
RUST = os.environ.get('VOXTYPE_BENCH_WORKER', str(REPO / 'custom-voxtype/target/release/examples/bench_worker'))
STOCK = os.environ.get('VOXTYPE_STOCK_BINARY', '/usr/bin/voxtype')
ONNX = os.environ.get('VOXTYPE_ONNX_BINARY', STOCK)
MODELS = Path(os.environ.get('VOXTYPE_MODELS_DIR', Path.home() / '.local/share/voxtype/models')).expanduser().absolute()
MODEL = Path(os.environ.get('VOXTYPE_REDUX_MODEL', MODELS / 'redux-packed.gguf')).expanduser().absolute()
LIBRARY = Path(os.environ.get('VOXTYPE_REDUX_LIBRARY', Path.home() / '.local/lib/voxtype-parakeet/libparakeet.so')).expanduser().absolute()


def manifest():
    path = AUDIO / 'manifest.json'
    if not path.exists():
        path = REPO / 'docs/audio-manifest.json'
    rows = json.loads(path.read_text())
    for row in rows:
        p = Path(row['file'])
        row['file'] = str(p if p.is_absolute() else AUDIO / p)
    return rows


def backend_env():
    env = os.environ.copy()
    env['VOXTYPE_PARAKEET_CPP_LIBRARY'] = str(LIBRARY)
    if 'ORT_DYLIB_PATH' not in env:
        spec = importlib.util.find_spec('onnxruntime')
        if spec and spec.origin:
            candidates = sorted((Path(spec.origin).parent / 'capi').glob('libonnxruntime.so*'))
            if candidates:
                env['ORT_DYLIB_PATH'] = str(candidates[0])
    return env


def generate_configs():
    CONFIGS.mkdir(parents=True, exist_ok=True)
    q = lambda value: json.dumps(str(value), ensure_ascii=False)
    files = {
        'tiny.en': f'engine="whisper"\n[whisper]\nmodel={q(MODELS / "ggml-tiny.en.bin")}\nlanguage="en"\n',
        'base.en': f'engine="whisper"\n[whisper]\nmodel={q(MODELS / "ggml-base.en.bin")}\nlanguage="en"\n',
        'custom-redux': f'engine="parakeet"\n[parakeet]\nmodel={q(MODEL)}\n',
        'parakeet-int8': f'engine="parakeet"\n[parakeet]\nmodel={q(MODELS / "parakeet-tdt-0.6b-v3-int8")}\n',
        'moonshine-base': f'engine="moonshine"\n[moonshine]\nmodel={q(MODELS / "moonshine-base")}\n',
        'adapter': f'engine="whisper"\n[hotkey]\nenabled=false\n[whisper]\nmode="cli"\nmodel={q(MODEL)}\nwhisper_cli_path={q(REPO / "redux_adapter.py")}\nlanguage="en"\n',
    }
    for name, text in files.items():
        (CONFIGS / (name + '.toml')).write_text(text)

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / 'benchmarks'


class BenchmarkTests(unittest.TestCase):
    def test_config_overrides_manifest_and_wer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / 'audio'; audio.mkdir()
            (audio / 'manifest.json').write_text(json.dumps([{'id': 'test', 'file': 'input.wav'}]))
            env = dict(os.environ, PYTHONPATH=str(BENCH),
                       VOXTYPE_BENCH_AUDIO_DIR=str(audio), VOXTYPE_BENCH_CONFIG_DIR=str(root/'configs'),
                       VOXTYPE_BENCH_RESULTS_DIR=str(root/'results'), VOXTYPE_MODELS_DIR=str(root/'models'),
                       VOXTYPE_REDUX_MODEL=str(root/'custom.gguf'), VOXTYPE_REDUX_LIBRARY=str(root/'custom.so'))
            code = '''import json,tomllib
import bench_config as c
from run_suite import wer
print(json.dumps({'file':c.manifest()[0]['file'],
'library':c.backend_env()['VOXTYPE_PARAKEET_CPP_LIBRARY'],
'model':tomllib.loads((c.CONFIGS/'custom-redux.toml').read_text())['parakeet']['model'],
'wer':wer('mister quilter is here','Mr. Quilter here')['wer']}))'''
            p = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, check=True)
            result = json.loads(p.stdout)
            self.assertEqual(result['file'], str(audio/'input.wav'))
            self.assertEqual(result['library'], str(root/'custom.so'))
            self.assertEqual(result['model'], str(root/'custom.gguf'))
            self.assertEqual(result['wer'], 0.25)

    def test_summarizer_preserves_inputs_and_deduplicates_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); inputs = root/'input'; inputs.mkdir(); output = root/'out'
            row = {'id': 'sample', 'audio_seconds': 5, 'inference_seconds': 1, 'wer': .2, 'text': 'hello'}
            result = {'name': 'test-model', 'sampled_peak_rss_mib': 123, 'cases': [row, dict(row,inference_seconds=3)]}
            (inputs/'run.json').write_text(json.dumps(result))
            (inputs/'run.partial.json').write_text(json.dumps(result))
            (inputs/'failed.json').write_text(json.dumps([dict(row, exit_code=1, name='failed')]))
            (inputs/'sweep.json').write_text(json.dumps([{'pool_threads': 2, 'seconds':[1,2]}]))
            subprocess.run([sys.executable, str(BENCH/'summarize.py'), str(inputs), '--output-dir', str(output)], check=True, capture_output=True)
            with (output/'summary.csv').open() as f:
                rows=list(csv.DictReader(f))
            self.assertFalse(any(r['configuration']=='failed' for r in rows))
            model = next(r for r in rows if r['configuration']=='test-model')
            self.assertEqual(model['runs'], '2')
            self.assertEqual(float(model['latency_seconds_median']), 2.0)
            self.assertEqual(float(model['peak_rss_mib']), 123.0)
            self.assertFalse((inputs/'REPORT.md').exists())

    def test_benchmark_help_does_not_start_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=dict(os.environ,VOXTYPE_BENCH_CONFIG_DIR=str(Path(tmp)/'config'),VOXTYPE_BENCH_RESULTS_DIR=str(Path(tmp)/'results'))
            for name in ['run_suite.py','run_adapters.py','run_optimizations.py','run_stock_whisper.py','verify_stock.py','prepare_audio.py','summarize.py']:
                with self.subTest(name=name):
                    p=subprocess.run([sys.executable,str(BENCH/name),'--help'],env=env,capture_output=True,text=True,timeout=10)
                    self.assertEqual(p.returncode,0,p.stderr)
                    self.assertIn('usage:',p.stdout)


if __name__=='__main__':
    unittest.main()

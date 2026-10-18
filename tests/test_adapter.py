import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import tomllib
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import redux_adapter
import install as installer


class ProtocolTests(unittest.TestCase):
    def invoke(self, response):
        with tempfile.TemporaryDirectory(prefix='redux-test-') as tmp:
            root = Path(tmp)
            audio = root / 'input.wav'
            audio.write_bytes(b'protocol-only fixture; fake worker does not decode it')
            path = root / 'worker.sock'
            received = []
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(path))
                server.listen(1)
                server.settimeout(10)
                def serve():
                    conn, _ = server.accept()
                    with conn, conn.makefile('rb') as stream:
                        received.append(json.loads(stream.readline()))
                        conn.sendall(json.dumps(response).encode() + b'\n')
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                env = dict(os.environ, VOXTYPE_REDUX_SOCKET=str(path))
                env.pop('XDG_RUNTIME_DIR', None)
                process = subprocess.run([
                    sys.executable, str(ROOT / 'redux_adapter.py'),
                    '--model', str(root / 'redux.gguf'), '--file', str(audio),
                    '--output-json', '--output-file', str(root / 'result'),
                    '--threads', '4', '--no-prints', '--language', 'en',
                ], env=env, capture_output=True, text=True, timeout=10)
                thread.join(10)
                self.assertFalse(thread.is_alive())
            result = root / 'result.json'
            return process, json.loads(result.read_text()) if result.exists() else None, received, audio

    def test_stock_cli_protocol_and_unicode(self):
        process, result, received, audio = self.invoke({'ok': True, 'text': 'Hello, café 世界.'})
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(result, {'transcription': [{'text': 'Hello, café 世界.'}]})
        self.assertEqual(received[0]['command'], 'transcribe')
        self.assertEqual(received[0]['audio'], str(audio.resolve()))
        self.assertTrue(received[0]['model'].endswith('redux.gguf'))

    def test_worker_failure_is_nonzero_without_success_json(self):
        process, result, _, _ = self.invoke({'ok': False, 'error': 'native model failed'})
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('native model failed', process.stderr)
        self.assertIsNone(result)

    def test_invalid_worker_options_fail_before_loading_model(self):
        for options in [
            ['--chunk-seconds', '-1'], ['--chunk-seconds', 'nan'],
            ['--chunk-seconds', 'inf'], ['--chunk-seconds', '1'],
            ['--backend', 'photon', '--model', 'other/model'],
        ]:
            with self.subTest(options=options):
                process = subprocess.run([sys.executable, str(ROOT / 'redux_adapter.py'), 'serve'] + options,
                                         capture_output=True, text=True, timeout=10)
                self.assertEqual(process.returncode, 2)

    def test_unsupported_cli_features_fail_explicitly(self):
        for option in [['--translate'], ['--prompt', 'names']]:
            p = subprocess.run([sys.executable, str(ROOT / 'redux_adapter.py'),
                '--model', '/unused/model', '--file', '/unused/input', '--output-json',
                '--output-file', '/unused/output'] + option, capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertIn('unsupported', p.stderr)

    def test_truncated_and_oversized_frames_are_rejected(self):
        import io
        for value in [b'{}', b'x' * (redux_adapter.MAX_MESSAGE + 1) + b'\n']:
            with self.assertRaises(ValueError):
                redux_adapter.read_message(io.BytesIO(value))


class InstallTests(unittest.TestCase):
    def test_staging_is_portable_preserves_config_and_requires_force(self):
        with tempfile.TemporaryDirectory(prefix='redux-install-') as tmp:
            root = Path(tmp)
            prefix = root / 'home with spaces $VAR %suffix 🐦'
            model = root / 'test model.gguf'; model.touch()
            library = root / 'test lib.so'; library.touch()
            original = prefix / '.config/voxtype/config.toml'
            original.parent.mkdir(parents=True)
            original.write_text('# preserve original\n')
            command = [sys.executable, str(ROOT / 'install.py'), '--prefix', str(prefix),
                       '--model', str(model), '--library', str(library), '--voxtype', '/usr/bin/true']
            process = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            profile = prefix / '.config/voxtype/redux-adapter.toml'
            cfg = tomllib.loads(profile.read_text())
            self.assertEqual(cfg['whisper']['model'], str(model))
            self.assertEqual(cfg['audio']['max_duration_secs'], 120)
            self.assertEqual(original.read_text(), '# preserve original\n')
            worker = prefix / '.local/share/voxtype-redux/adapter.py'
            self.assertTrue(os.access(worker, os.X_OK))
            unit = (prefix / '.config/systemd/user/voxtype-redux.service').read_text()
            self.assertIn('Type=notify', unit)
            self.assertIn('home with spaces $$VAR %%suffix 🐦', unit)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(subprocess.run(command + ['--force'], capture_output=True).returncode, 0)
            self.assertTrue(list(profile.parent.glob('redux-adapter.toml.bak-*')))
            self.assertNotEqual(subprocess.run(command + ['--activate'], capture_output=True).returncode, 0)

    def test_activation_restarts_the_worker_before_voxtype(self):
        with tempfile.TemporaryDirectory(prefix='redux-activate-') as tmp:
            root = Path(tmp)
            model = root / 'model.gguf'; model.touch()
            library = root / 'lib.so'; library.touch()
            argv = ['install.py', '--model', str(model), '--library', str(library),
                    '--voxtype', '/usr/bin/true', '--activate']
            with mock.patch.object(installer.Path, 'home', return_value=root), \
                 mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': str(root / '.config'),
                                              'XDG_DATA_HOME': str(root / '.local/share')}), \
                 mock.patch.object(sys, 'argv', argv), \
                 mock.patch.object(installer.subprocess, 'run') as run:
                installer.main()
            commands = [call.args[0] for call in run.call_args_list]
            worker_restart = ['systemctl', '--user', 'restart', 'voxtype-redux.service']
            voxtype_restart = ['systemctl', '--user', 'restart', 'voxtype.service']
            self.assertLess(commands.index(worker_restart), commands.index(voxtype_restart))


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""Install user-owned files; activate systemd services only with --activate."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def unit_arg(value):
    # systemd performs its own specifier and environment expansion, even in quotes.
    return json.dumps(str(value).replace('%', '%%').replace('$', '$$'), ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True, help='Existing Redux GGUF file')
    parser.add_argument('--library', type=Path, required=True, help='Existing libparakeet.so (ABI >=10)')
    parser.add_argument('--voxtype', type=Path, default=Path('/usr/bin/voxtype'), help='Stock Voxtype executable')
    parser.add_argument('--prefix', type=Path, help='Alternate home layout for staging; cannot activate')
    parser.add_argument('--force', action='store_true', help='Back up and replace existing generated files')
    parser.add_argument('--activate', action='store_true', help='Reload systemd, enable worker and restart Voxtype')
    args = parser.parse_args()
    if args.activate and args.prefix is not None:
        parser.error('--activate cannot be combined with --prefix')
    for label, path in [('model', args.model), ('library', args.library), ('voxtype', args.voxtype)]:
        if not path.is_file():
            parser.error(f'{label} file does not exist: {path}')
    if not os.access(args.voxtype, os.X_OK):
        parser.error('Voxtype must be executable')
    model, library, voxtype = (p.absolute() for p in [args.model, args.library, args.voxtype])
    base = args.prefix.absolute() if args.prefix else Path.home()
    config = base / '.config' if args.prefix else Path(os.environ.get('XDG_CONFIG_HOME', str(base / '.config')))
    data = base / '.local/share' if args.prefix else Path(os.environ.get('XDG_DATA_HOME', str(base / '.local/share')))
    config, data = config.absolute(), data.absolute()
    worker = data / 'voxtype-redux/adapter.py'
    client = base / '.local/bin/voxtype-redux'
    profile = config / 'voxtype/redux-adapter.toml'
    unit = config / 'systemd/user/voxtype-redux.service'
    override = config / 'systemd/user/voxtype.service.d/redux-adapter.conf'
    source = Path(__file__).with_name('redux_adapter.py').read_text()
    q = lambda value: json.dumps(value, ensure_ascii=False)
    profile_text = f'''# User-owned stock Voxtype + Redux adapter profile.
engine = "whisper"
state_file = "auto"
[hotkey]
enabled = false
[audio]
device = "default"
sample_rate = 16000
max_duration_secs = 120
[whisper]
mode = "cli"
model = {q(str(model))}
whisper_cli_path = {q(str(client))}
language = "en"
translate = false
[output]
mode = "type"
fallback_to_clipboard = true
[osd]
enabled = false
'''
    unit_text = f'''[Unit]
Description=Resident Parakeet Redux worker for stock Voxtype
[Service]
Type=notify
NotifyAccess=main
ExecStart={unit_arg(sys.executable)} {unit_arg(worker)} serve --backend cpp --model {unit_arg(model)} --library {unit_arg(library)} --pool-threads 4 --chunk-seconds 30
RuntimeDirectory=voxtype-redux
RuntimeDirectoryMode=0700
UMask=0077
Restart=on-failure
RestartSec=2
TimeoutStartSec=180
TimeoutStopSec=15
Environment=PYTHONUNBUFFERED=1
[Install]
WantedBy=default.target
'''
    override_text = f'''[Unit]
Requires=voxtype-redux.service
After=voxtype-redux.service
[Service]
ExecStart=
ExecStart={unit_arg(voxtype)} --config {unit_arg(profile)} daemon
'''
    targets = {worker: (source, 0o755), client: (source, 0o755), profile: (profile_text, 0o644),
               unit: (unit_text, 0o644), override: (override_text, 0o644)}
    conflicts = [p for p in targets if p.exists() or p.is_symlink()]
    if any(p.is_dir() for p in conflicts):
        parser.error('a generated file path is an existing directory')
    if conflicts and not args.force:
        parser.error('files already exist; inspect them and use --force to back up/replace: ' + ', '.join(map(str, conflicts)))
    if args.activate:
        subprocess.run(['systemctl', '--user', 'cat', 'voxtype.service'], check=True, stdout=subprocess.DEVNULL)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    for path, (content, mode) in targets.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path in conflicts:
            backup = path.with_name(path.name + '.bak-' + stamp)
            shutil.copy2(path, backup, follow_symlinks=True)
        # Replace a destination symlink itself, never write through it.
        if path.is_symlink():
            path.unlink()
        path.write_text(content)
        path.chmod(mode)
        print('Installed', path)
    if args.activate:
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', '--user', 'enable', 'voxtype-redux.service'], check=True)
        subprocess.run(['systemctl', '--user', 'restart', 'voxtype-redux.service'], check=True)
        subprocess.run(['systemctl', '--user', 'restart', 'voxtype.service'], check=True)
    else:
        print('\nFiles installed; services have not been reloaded or started.')
        print('To activate: systemctl --user daemon-reload')
        print('Then: systemctl --user enable voxtype-redux.service')
        print('Then: systemctl --user restart voxtype-redux.service')
        print('Then: systemctl --user restart voxtype.service')


if __name__ == '__main__':
    main()

"""Installed outside /opt/airnode so interrupted updates can recover at boot."""
import json
from pathlib import Path
import re

def recover(record=Path('/etc/airnode/update-transaction.json'), live=Path('/opt/airnode'), unit_dir=Path('/etc/systemd/system')):
    if not record.exists(): return
    state = json.loads(record.read_text())
    backup = Path(state['backup'])
    if backup.parent != live.parent or not re.fullmatch('airnode-backup-[a-f0-9]{32}', backup.name) or backup.is_symlink():
        raise SystemExit('Invalid recovery location')
    if backup.exists():
        if live.exists():
            failed = live.parent / ('airnode-failed-' + backup.name.removeprefix('airnode-backup-'))
            live.rename(failed)
        backup.rename(live)
    for name, content in state['units'].items():
        if not re.fullmatch(r'airnode-[a-z@-]+\.(?:service|timer)', name): raise SystemExit('Invalid recovery unit')
        target = unit_dir / name
        if content is None: target.unlink(missing_ok=True)
        else: target.write_text(content); target.chmod(0o644)
    record.unlink()
    print('AirNode restored the previous application after an interrupted update.')

if __name__ == '__main__': recover()

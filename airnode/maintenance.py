"""Allowlisted, asynchronous feeder software maintenance on the local appliance."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
from . import aggregators as ag

ROOT = Path('/etc/airnode')
LOCK = '/run/lock/airnode-maintenance.lock'
PACKAGES = {'flightaware': 'piaware', 'flightradar24': 'fr24feed'}
BOOTSTRAPS = {
    'flightaware': ('https://www.flightaware.com/adsb/piaware/files/packages/pool/piaware/f/flightaware-apt-repository/flightaware-apt-repository_1.3_all.deb',
                   '20bdb73536845d9d95bc4659973e7ed07bc0fbdda7491045b82a66d5361046cc'),
    'flightradar24': ('https://repo-feed.flightradar24.com/flightradar24.2026.pub',
                    '3ab6f369d283b8caea09dac2c3aebf5e60aca81bb9ec8ebce758d3e81360aad2'),
}

def job_unit(key):
    ag.provider(key)
    return 'airnode-provider-software@' + key

@contextmanager
def exclusive(wait=False):
    import fcntl
    with open(LOCK, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            raise ValueError('Software maintenance is running. Try again when it finishes.') from None
        yield

def software_status(command, key):
    unit = job_unit(key)
    raw = command(['systemctl', 'show', unit + '.service', '--property=ActiveState,Result,ExecMainStatus', '--no-pager'], check=False)
    state = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
    auto = command(['systemctl', 'is-enabled', unit + '.timer'], check=False) == 'enabled'
    if key in PACKAGES:
        version = command(['dpkg-query', '-W', '-f=${Status}|${Version}', PACKAGES[key]], check=False)
        version = version.split('|', 1)[1] if version.startswith('install ok installed|') else ''
    else:
        path = Path('/usr/local/share/airnode/third-party/readsb.commit')
        version = path.read_text().strip()[:12] if path.exists() else ''
    running = state.get('ActiveState') in ('activating', 'active', 'deactivating')
    result = 'Working' if running else 'Failed' if state.get('Result') not in (None, '', 'success') else 'Ready'
    return {'busy': running, 'result': result, 'automatic': auto, 'version': version}

def operate(command, key, action):
    unit = job_unit(key)
    if action in ('install', 'update'):
        command(['systemctl', 'start', '--no-block', unit + '.service'])
        return {'accepted': True, 'message': 'Software job started on your Pi. Follow its progress and installation log.'}
    if action in ('auto-on', 'auto-off'):
        command(['systemctl', 'enable' if action == 'auto-on' else 'disable', '--now', unit + '.timer'])
        return {'accepted': True, 'message': 'Daily software updates ' + ('enabled.' if action == 'auto-on' else 'disabled.')}
    if action == 'install-logs':
        text = command(['journalctl', '-u', unit + '.service', '-n', '120', '--no-pager', '-o', 'short-iso'])
        return {'text': ag.redact(text, ag.load(ROOT / 'aggregators.json'))[-24000:]}
    raise ValueError('Unknown software action')

def run(args, timeout=1800, check=True):
    # Package output stays in the local system journal, never in error messages.
    result = subprocess.run(args, timeout=timeout, stdin=subprocess.DEVNULL,
                            env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive', 'NEEDRESTART_MODE': 'l'})
    if check and result.returncode:
        raise ValueError('Software step failed; inspect the installation log.')
    return result.returncode

def download(key, target):
    url, expected = BOOTSTRAPS[key]
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 AirNode'})
    with urllib.request.urlopen(request, timeout=60) as response:
        if not response.url.startswith('https://'):
            raise ValueError('An insecure download redirect was rejected.')
        data = response.read(2_000_001)
    if len(data) > 2_000_000 or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Provider bootstrap changed. An AirNode compatibility update is required.')
    Path(target).write_bytes(data)

def check_platform():
    values = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    arch = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    if arch != 'arm64' or values.get('VERSION_CODENAME', '').strip('"') not in ('bookworm', 'trixie') or values.get('ID', '').strip('"') not in ('debian', 'raspbian'):
        raise ValueError('Automatic setup supports Debian / Raspberry Pi OS Bookworm or Trixie arm64.')

def repository(key):
    with tempfile.TemporaryDirectory(prefix='airnode-provider-') as temp:
        target = Path(temp) / ('repository.deb' if key == 'flightaware' else 'repository.asc')
        download(key, target)
        if key == 'flightaware':
            run(['dpkg', '-i', str(target)])
        else:
            keyring = Path('/etc/apt/keyrings/airnode-fr24.gpg')
            keyring.parent.mkdir(parents=True, exist_ok=True)
            keyring.parent.chmod(0o755)
            run(['gpg', '--batch', '--yes', '--dearmor', '--output', str(keyring), str(target)])
            keyring.chmod(0o644)
            ag.atomic_text('/etc/apt/sources.list.d/airnode-fr24.list',
                'deb [arch=arm64 signed-by=/etc/apt/keyrings/airnode-fr24.gpg] https://repo-feed.flightradar24.com flightradar24 raspberrypi-stable\n', 0o644)

def harden_native():
    """APT hook also covers OS upgrades, including failed package configuration."""
    if Path('/etc/systemd/system/fr24feed.service.d/airnode.conf').exists():
        target = Path('/etc/fr24feed.ini')
        if target.exists():
            import grp
            try:
                gid = grp.getgrnam('fr24').gr_gid
            except KeyError:
                gid = 0
            os.chown(target, 0, gid)
            target.chmod(0o640 if gid else 0o600)

def guard_native(key):
    """Persistent boot-safe gate: package scripts cannot start a feed without consent."""
    path = Path('/etc/systemd/system') / (ag.service(key) + '.service.d') / 'airnode.conf'
    text = '[Unit]\nConditionPathExists=/etc/airnode/providers/' + key + '.enabled\n'
    if key == 'flightradar24':
        # Avoid bundled SDR installers, driver changes and network signup pre-start hooks.
        text += '[Service]\nExecStartPre=\nExecStartPre=/usr/bin/fr24feed --validate-config --config-file=/etc/fr24feed.ini\n'
    ag.atomic_text(path, text, 0o644)
    run(['systemctl', 'daemon-reload'])
    if key == 'flightradar24':
        # A diversion survives later package updates; never leave the vendor cron job live.
        run(['dpkg-divert', '--local', '--add', '--rename', '--divert',
             '/etc/airnode/fr24feed_updater.vendor', '/etc/cron.d/fr24feed_updater'])

def native_job(key):
    from .aggregator_control import Manager
    from .broker import command
    manager = Manager(command)
    marker = ROOT / 'providers' / (key + '.enabled')
    marker.unlink(missing_ok=True)
    guard_native(key)
    if manager.state(key).get('LoadState') == 'loaded':
        run(['systemctl', 'stop', ag.service(key) + '.service'])
    # Native package scripts must never see an SDR receiver mode or overwrite a saved key.
    target = manager.target_path(key)
    entry = ag.load(manager.path).get(key, {'enabled': False, 'credential': ''})
    previous = target.read_text() if target.exists() else ''
    if target.exists() and not Path(str(target) + '.airnode-backup').exists():
        ag.atomic_text(str(target) + '.airnode-backup', previous)
    ag.atomic_text(target, ag.native_config(key, entry, previous), 0o600 if key == 'flightradar24' else 0o644)
    try:
        print('Preparing the official provider repository.', flush=True)
        repository(key)
        run(['apt-get', '-o', 'APT::Update::Error-Mode=any', 'update'])
        print('Installing the latest signed provider package and dependencies.', flush=True)
        run(['apt-get', '-o', 'DPkg::Lock::Timeout=120', '-o', 'Dpkg::Options::=--force-confold',
             '--no-install-recommends', '--no-remove', '-y', 'install', PACKAGES[key]])
    finally:
        # FR24's postinst makes its config writable; restore private permissions even on failure.
        harden_native()
        run(['systemctl', 'daemon-reload'])
    if not manager.available(key):
        raise ValueError('Package finished but the provider client or service is missing.')
    if entry['enabled']:
        manager.configure({'provider': key, 'enabled': True, 'consent': True})
    else:
        run(['systemctl', 'disable', '--now', ag.service(key) + '.service'])
    print('Software ready. ' + ('Sharing restored.' if entry['enabled'] else 'Sharing stays off until you enable it.'), flush=True)

def readsb_job():
    expected = Path('/opt/airnode/deploy/readsb.commit').read_text().strip()
    installed = Path('/usr/local/share/airnode/third-party/readsb.commit')
    if Path('/usr/local/bin/readsb').exists() and installed.exists() and installed.read_text().strip() == expected:
        print('Included feeder is current for this AirNode release. Newer revisions arrive with AirNode releases.', flush=True)
        return
    run(['bash', '/opt/airnode/scripts/build-readsb.sh'])
    from .broker import command, units
    for unit in units() + [ag.service(key) for key in ag.PROVIDERS if key not in PACKAGES]:
        if command(['systemctl', 'is-active', unit + '.service'], check=False) == 'active':
            run(['systemctl', 'restart', unit + '.service'])
    print('Included feeder updated to the revision approved for this AirNode release.', flush=True)

def main():
    if sys.argv[1:] == ['--harden']:
        harden_native()
        return
    key = sys.argv[1] if len(sys.argv) == 2 else None
    ag.provider(key)
    try:
        with exclusive(wait=True):
            check_platform()
            print('Starting AirNode software maintenance for ' + ag.provider(key)['name'], flush=True)
            native_job(key) if key in PACKAGES else readsb_job()
    except Exception as exc:
        # Exceptions may embed package URLs/output; display a fixed recovery message only.
        if isinstance(exc, ValueError):
            print(str(exc), flush=True)
        print('Software maintenance failed (' + type(exc).__name__ + '). Sharing may be stopped. Review the preceding steps, resolve the cause, then retry from AirNode.', flush=True)
        raise SystemExit(1) from None

if __name__ == '__main__':
    main()

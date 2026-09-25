"""Signed, opt-in AirNode application releases from the fixed GitHub repository."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from . import __version__
from .aggregators import atomic_text
from .maintenance import exclusive

REPOSITORY = 'TaxiwayBravo/airnode'
ROOT = Path('/etc/airnode')
STATE = ROOT / 'release-status.json'
SETTINGS = ROOT / 'releases.json'
TRUST = ROOT / 'update-public.pem'
LIVE = Path('/opt/airnode')
UNIT_DIR = Path('/etc/systemd/system')
MAX_ARCHIVE = 50 * 1024 * 1024
VERSION = re.compile(r'^(?:v)?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$')

def version(value):
    found = VERSION.fullmatch(value) if isinstance(value, str) else None
    if not found: raise ValueError('Unsupported release version')
    major, minor, patch, beta = found.groups()
    return int(major), int(minor), int(patch), beta is None, int(beta or 0)

def policy():
    result = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {'channel': 'stable'}
    if result.get('channel') not in ('stable', 'beta'): raise ValueError('Invalid update channel')
    return result

def status():
    result = json.loads(STATE.read_text()) if STATE.exists() else {'state': 'Not checked', 'message': 'Check GitHub for an AirNode release.'}
    return {**result, 'current': __version__, 'channel': policy()['channel'], 'repository': REPOSITORY, 'demo': False}

def set_state(state, message, **extra):
    atomic_text(STATE, json.dumps({'state': state, 'message': message, 'checked_at': int(time.time()), **extra}))

def trusted_url(url):
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ''
    return parsed.scheme == 'https' and not parsed.username and not parsed.password and parsed.port in (None, 443) and (host in ('api.github.com', 'github.com') or host.endswith('.githubusercontent.com'))

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        if not trusted_url(newurl): raise ValueError('Untrusted release download redirect')
        return super().redirect_request(request, fp, code, message, headers, newurl)

def fetch(url, maximum):
    if not trusted_url(url): raise ValueError('Untrusted release download URL')
    request = urllib.request.Request(url, headers={'User-Agent': 'AirNode/' + __version__, 'Accept': 'application/vnd.github+json'})
    with urllib.request.build_opener(Redirect()).open(request, timeout=30) as response:
        data = response.read(maximum + 1)
    if len(data) > maximum: raise ValueError('Release download exceeds its size limit')
    return data

def choose(releases, channel, current=__version__):
    candidates = []
    for release in releases:
        try:
            key = version(release.get('tag_name'))
            if release.get('draft') or key <= version(current): continue
            if channel == 'stable' and (release.get('prerelease') or not key[3]): continue
            names = {a['name'] for a in release.get('assets', [])}
            if not {'airnode-update.tar.gz', 'airnode-release.json', 'airnode-release.sig'} <= names: continue
            candidates.append((key, release))
        except (ValueError, KeyError, TypeError): continue
    return max(candidates, key=lambda item: item[0])[1] if candidates else None

def assets(release):
    prefix = 'https://github.com/' + REPOSITORY + '/releases/download/' + release['tag_name'] + '/'
    result = {}
    for name in ('airnode-update.tar.gz', 'airnode-release.json', 'airnode-release.sig'):
        matches = [a for a in release['assets'] if a.get('name') == name]
        if len(matches) != 1 or matches[0].get('browser_download_url') != prefix + name:
            raise ValueError('Unexpected release asset location')
        result[name] = matches[0]['browser_download_url']
    return result

def verify_manifest(data, signature, tag, directory):
    manifest_path, sig_path = Path(directory) / 'manifest.json', Path(directory) / 'manifest.sig'
    manifest_path.write_bytes(data); sig_path.write_bytes(signature)
    result = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(TRUST), '-signature', str(sig_path), str(manifest_path)], capture_output=True, timeout=15)
    if result.returncode: raise ValueError('Release signature could not be verified with this Pi’s trusted key.')
    manifest = json.loads(data)
    if manifest.get('repository') != REPOSITORY or 'v' + manifest.get('version', '') != tag:
        raise ValueError('Release identity mismatch')
    version(manifest['version'])
    if not re.fullmatch('[a-f0-9]{64}', manifest.get('sha256', '')) or manifest.get('format') != 1:
        raise ValueError('Invalid release manifest')
    if manifest.get('readsb_commit') != (LIVE / 'deploy/readsb.commit').read_text().strip():
        raise ValueError('This release changes the receiver runtime. Use the full Pi installer for this upgrade.')
    return manifest

def unpack(archive, destination):
    total, seen = 0, set()
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        if len(members) > 1500: raise ValueError('Too many release files')
        for item in members:
            path = PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or '\\' in item.name or not path.parts or path.parts[0] != 'AirNode' or str(path) in seen:
                raise ValueError('Unsafe release path')
            if not (item.isfile() or item.isdir()): raise ValueError('Release links and special files are forbidden')
            seen.add(str(path)); total += item.size
            if total > 100 * 1024 * 1024: raise ValueError('Expanded release is too large')
        for item in members:
            target = Path(destination).joinpath(*PurePosixPath(item.name).parts[1:])
            if item.isdir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(item) as incoming, target.open('wb') as output:
                shutil.copyfileobj(incoming, output)
            target.chmod(0o755 if target.suffix == '.sh' else 0o644)
    for required in ('airnode/server.py', 'web/index.html', 'scripts/install.sh', 'deploy/readsb.commit'):
        if not (Path(destination) / required).is_file(): raise ValueError('Release is incomplete')

def run(args):
    subprocess.run(args, check=True, timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def activate(stage, manifest):
    live = LIVE
    backup = live.parent / ('airnode-backup-' + uuid.uuid4().hex)
    unit_dir = UNIT_DIR
    units = list((stage / 'deploy').glob('airnode-*.service')) + list((stage / 'deploy').glob('airnode-*.timer'))
    old_units = {p.name: (unit_dir / p.name).read_text() if (unit_dir / p.name).exists() else None for p in units}
    journal = ROOT / 'update-transaction.json'
    atomic_text(journal, json.dumps({'backup': str(backup), 'stage': str(stage), 'units': old_units}))
    try:
        run(['systemctl', 'stop', 'airnode-api', 'airnode-control', 'airnode-wifi'])
        live.rename(backup)
        stage.rename(live)
        for unit in units:
            atomic_text(unit_dir / unit.name, (live / 'deploy' / unit.name).read_text(), 0o644)
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'enable', 'airnode-wifi', 'airnode-release-recovery'])
        run(['systemctl', 'start', 'airnode-control', 'airnode-api', 'airnode-wifi'])
        healthy = False
        for _ in range(20):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3) as response:
                    data = json.load(response)
                    if data.get('ok') and data.get('version') == manifest['version']:
                        healthy = True; break
            except Exception: pass
            time.sleep(1)
        if not healthy: raise ValueError('Updated application did not become healthy.')
        journal.unlink()
        set_state('Updated', 'AirNode was updated. Refresh this page.', installed=manifest['version'])
    except Exception:
        run(['python3', '/usr/local/lib/airnode-recovery.py'])
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'restart', 'airnode-control', 'airnode-api', 'airnode-wifi'])
        raise ValueError('Update failed. The previous application was restored; check local service logs.') from None

def operate(command, action, channel=None):
    if action == 'channel':
        if channel not in ('stable', 'beta'): raise ValueError('Choose stable or beta')
        atomic_text(SETTINGS, json.dumps({'channel': channel}))
        set_state('Not checked', 'Update channel changed. Check for a release.')
    elif action in ('check', 'install'):
        command(['systemctl', 'start', '--no-block', 'airnode-release@' + action + '.service'])
    else: raise ValueError('Unknown AirNode update action')
    return {'accepted': True, 'message': 'AirNode update request accepted.'}

def main():
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    if action not in ('check', 'install'): raise SystemExit('Invalid release job')
    try:
        with exclusive(wait=True):
            channel = policy()['channel']
            set_state('Checking', 'Checking GitHub releases…')
            release = choose(json.loads(fetch('https://api.github.com/repos/' + REPOSITORY + '/releases?per_page=100', 2_000_000)), channel)
            if not release:
                set_state('Up to date', 'No newer compatible published release is available in this channel.')
                return
            urls = assets(release)
            with tempfile.TemporaryDirectory(prefix='airnode-release-') as temp:
                manifest = verify_manifest(fetch(urls['airnode-release.json'], 16384), fetch(urls['airnode-release.sig'], 8192), release['tag_name'], temp)
                if action == 'check':
                    set_state('Available', 'A verified AirNode release is available.', available=manifest['version'])
                    return
                set_state('Installing', 'Downloading and verifying the AirNode update. The dashboard will briefly disconnect.', available=manifest['version'])
                payload = fetch(urls['airnode-update.tar.gz'], MAX_ARCHIVE)
                if hashlib.sha256(payload).hexdigest() != manifest['sha256']: raise ValueError('Release archive checksum mismatch')
                if shutil.disk_usage('/opt').free < 500 * 1024 * 1024: raise ValueError('At least 500 MB free space is required to stage an update.')
                archive = Path(temp) / 'release.tar.gz'; archive.write_bytes(payload)
                stage = Path(tempfile.mkdtemp(prefix='airnode-stage-', dir='/opt'))
                unpack(archive, stage)
                run(['python3', '-m', 'compileall', '-q', str(stage / 'airnode')])
                activate(stage, manifest)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else 'Could not complete the GitHub update. Check internet access, release availability and the local release service log.'
        set_state('Failed', message)
        raise SystemExit(1) from None

if __name__ == '__main__': main()

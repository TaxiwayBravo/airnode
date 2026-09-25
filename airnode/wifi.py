"""NetworkManager Wi-Fi onboarding and offline recovery; no secrets in command lines."""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
import uuid
from .aggregators import atomic_text

ROOT = Path('/etc/airnode')
PROFILES = Path('/etc/NetworkManager/system-connections')
STATE = Path('/run/airnode-wifi.json')
REQUEST = Path('/run/airnode-wifi-request.json')
AP_ID = 'AirNode Setup'

def command(args, timeout=15, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                            env={**os.environ, 'LC_ALL': 'C'})
    if check and result.returncode:
        raise ValueError('Wi-Fi operation failed. Check the country, network name and password.')
    return result.stdout.strip()

def fields(line):
    """Parse nmcli's escaped terse fields, including colons/backslashes in SSIDs."""
    result, part, escaped = [], '', False
    for char in line:
        if escaped:
            part += char
            escaped = False
        elif char == '\\': escaped = True
        elif char == ':': result.append(part); part = ''
        else: part += char
    result.append(part)
    return result

def validate(value):
    if not isinstance(value, dict) or set(value) != {'ssid', 'password', 'country'}:
        raise ValueError('Supply network name, Wi-Fi password and two-letter country code.')
    ssid, password, country = value['ssid'], value['password'], value['country']
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode('utf-8')) <= 32 or any(ord(c) < 32 for c in ssid):
        raise ValueError('Network name must contain 1–32 UTF-8 bytes without control characters.')
    if not isinstance(password, str) or not (8 <= len(password) <= 63 and all(32 <= ord(c) <= 126 for c in password) or re.fullmatch('[a-fA-F0-9]{64}', password)):
        raise ValueError('Use a WPA2/WPA3 personal password: 8–63 printable ASCII characters or 64 hexadecimal digits.')
    if not isinstance(country, str) or not re.fullmatch('[A-Z]{2}', country):
        raise ValueError('Enter your two-letter Wi-Fi country code, for example GB.')
    return dict(value)

def escaped(value):
    return value.replace('\\', '\\\\').replace(' ', '\\s')

def profile(ssid, password, identifier, hotspot=False):
    # Inputs are validated before calling; escape keyfile values rather than interpolate shell code.
    return (f'[connection]\nid={AP_ID if hotspot else "AirNode Home"}\nuuid={identifier}\ntype=wifi\n'
            f'autoconnect={"false" if hotspot else "true"}\nautoconnect-priority=100\n'
            f'\n[wifi]\nssid={escaped(ssid)}\nmode={"ap" if hotspot else "infrastructure"}\n'
            + ('band=bg\n' if hotspot else 'hidden=true\n') +
            ('' if hotspot else f'\n[wifi-security]\nkey-mgmt=wpa-psk\npsk={escaped(password)}\n') +
            ('' if hotspot else '') +
            ('\n[ipv4]\nmethod=shared\naddress1=10.42.0.1/24\nnever-default=true\n\n[ipv6]\nmethod=disabled\n'
             if hotspot else '\n[ipv4]\nmethod=auto\nmay-fail=false\n\n[ipv6]\nmethod=auto\n'))

def initialize():
    path = ROOT / 'hotspot.json'
    created = not path.exists()
    boot = Path('/boot/firmware/airnode-wifi-setup.json')
    if not created:
        config = json.loads(path.read_text())
    elif boot.exists():
        config = validate(json.loads(boot.read_text()))
    else:
        config = {'ssid': 'AirNode-Setup-' + secrets.token_hex(3).upper(),
                  'password': secrets.token_urlsafe(15), 'country': ''}
    if created:
        config['uuid'] = str(uuid.uuid4())
        atomic_text(path, json.dumps(config))
    PROFILES.mkdir(parents=True, exist_ok=True)
    atomic_text(PROFILES / 'airnode-hotspot.nmconnection', profile(config['ssid'], config['password'], config['uuid'], True))
    boot.unlink(missing_ok=True)
    if not created: return
    token = Path('/var/lib/airnode/setup-token')
    # Physical access to the boot partition supplies per-device credentials, not a global default.
    text = ('AirNode setup details — the setup Wi-Fi is open and local-only.\n\nWi-Fi: ' + config['ssid'] +
            '\nWi-Fi password: none\nSetup: https://10.42.0.1/ or https://' +
            command(['hostname']) + '.local/\nPairing token: ' + (token.read_text().strip() if token.exists() else 'Already paired') +
            '\n\nCountry must be configured with Raspberry Pi Imager or scripts/prepare-sd.py before wireless use.\n')
    atomic_text('/boot/firmware/AIRNODE-SETUP.txt', text)

def snapshot(message=None):
    rows = [fields(line) for line in command(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status']).splitlines()]
    wifi = next((r for r in rows if len(r) == 4 and r[1] == 'wifi'), None)
    active = wifi is not None and wifi[2] == 'connected' and wifi[3] == AP_ID
    uplink = any(len(r) == 4 and r[1] in ('wifi', 'ethernet') and r[2] == 'connected' and r[3] != AP_ID for r in rows)
    config_path = ROOT / 'hotspot.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    result = {'available': bool(wifi), 'hotspot': active, 'connected': uplink,
              'interface': wifi[0] if wifi else None, 'connection': wifi[3] if wifi and wifi[2] == 'connected' else '',
              'hotspot_ssid': config.get('ssid', ''), 'setup_url': 'https://10.42.0.1/',
              'message': message or ('Setup hotspot is ready.' if active else 'Connected to your local network.' if uplink else 'Waiting for a network connection.'), 'demo': False}
    atomic_text(STATE, json.dumps(result), 0o644)
    return result

def public_status():
    if not STATE.exists(): return {'available': False, 'message': 'Wi-Fi service is starting.', 'networks': [], 'demo': False}
    result = json.loads(STATE.read_text())
    return result

def scan():
    rows = command(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list', '--rescan', 'no'])
    networks = []
    for line in rows.splitlines():
        row = fields(line)
        if len(row) == 3 and row[0] and not any(n['ssid'] == row[0] for n in networks):
            networks.append({'ssid': row[0], 'signal': row[1], 'security': row[2]})
    return {**public_status(), 'networks': networks}

def queue(value):
    value = validate(value)
    if REQUEST.exists(): raise ValueError('A Wi-Fi connection attempt is already queued.')
    atomic_text(REQUEST, json.dumps(value))
    return {'accepted': True, 'message': 'Connecting shortly. The setup Wi-Fi will disconnect. Join your home Wi-Fi and open the Pi hostname. If connection fails, the setup hotspot returns within two minutes.'}

def hotspot_up():
    config = json.loads((ROOT / 'hotspot.json').read_text())
    if config.get('country'): command(['iw', 'reg', 'set', config['country']])
    command(['rfkill', 'unblock', 'wlan'])
    command(['nmcli', 'radio', 'wifi', 'on'])
    command(['nmcli', 'connection', 'load', str(PROFILES / 'airnode-hotspot.nmconnection')])
    command(['nmcli', '--wait', '25', 'connection', 'up', 'uuid', config['uuid']], timeout=30)

def country_codes():
    codes = json.loads(Path('/usr/share/iso-codes/json/iso_3166-1.json').read_text())['3166-1']
    return {item['alpha_2'] for item in codes}

def connect(value):
    value = validate(value)
    if value['country'] not in country_codes():
        raise ValueError('Unknown Wi-Fi country code.')
    config_path = ROOT / 'hotspot.json'
    config = json.loads(config_path.read_text())
    config['country'] = value['country']
    atomic_text(config_path, json.dumps(config))
    command(['iw', 'reg', 'set', value['country']])
    command(['rfkill', 'unblock', 'wlan'])
    command(['nmcli', 'radio', 'wifi', 'on'])
    identifier = str(uuid.uuid4())
    candidate = PROFILES / ('airnode-home-' + identifier + '.nmconnection')
    atomic_text(candidate, profile(value['ssid'], value['password'], identifier))
    try:
        command(['nmcli', 'connection', 'load', str(candidate)])
        command(['nmcli', '--wait', '45', 'connection', 'up', 'uuid', identifier], timeout=50)
        current = snapshot()
        if not current['connected'] or current['hotspot']: raise ValueError('No local network address received.')
    except Exception:
        command(['nmcli', 'connection', 'delete', 'uuid', identifier], check=False)
        candidate.unlink(missing_ok=True)
        hotspot_up()
        snapshot('Connection failed. Check the Wi-Fi details and try again. Your setup hotspot has been restored.')
        return
    for old in PROFILES.glob('airnode-home-*.nmconnection'):
        if old != candidate:
            old_id = old.stem.removeprefix('airnode-home-')
            command(['nmcli', 'connection', 'delete', 'uuid', old_id], check=False)
            old.unlink(missing_ok=True)
    snapshot('Wi-Fi connected. Open this Pi from your home network.')

def main():
    if sys.argv[1:] == ['init']:
        initialize()
        return
    initialize()
    offline_since = time.monotonic()
    while True:
        try:
            if REQUEST.exists():
                value = json.loads(REQUEST.read_text())
                # Give the browser time to receive the accepted response before switching radios.
                time.sleep(5)
                try: connect(value)
                finally: REQUEST.unlink(missing_ok=True)
                offline_since = time.monotonic()
            state = snapshot()
            if state['connected']:
                offline_since = time.monotonic()
                if state['hotspot']:
                    command(['nmcli', 'connection', 'down', 'id', AP_ID])
            elif state['available'] and not state['hotspot'] and time.monotonic() - offline_since >= 90:
                hotspot_up()
        except Exception:
            # Never log command output or submitted credentials.
            atomic_text(STATE, json.dumps({'available': True, 'message': 'Wi-Fi setup needs attention. Check radio/country settings on the Pi.', 'demo': False}), 0o644)
        time.sleep(15)

if __name__ == '__main__': main()

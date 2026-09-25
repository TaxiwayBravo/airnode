"""Run on your own computer after flashing, before first boot: prepare-sd.py BOOT GB."""
import json
from pathlib import Path
import re
import secrets
import sys

if len(sys.argv) != 3 or not re.fullmatch('[A-Z]{2}', sys.argv[2]):
    raise SystemExit('Usage: python prepare-sd.py BOOT_PARTITION TWO_LETTER_COUNTRY')
boot = Path(sys.argv[1]).resolve()
if not (boot / 'config.txt').is_file(): raise SystemExit('Select the Raspberry Pi boot partition (contains config.txt).')
paths = [boot / 'airnode-wifi-setup.json', boot / 'airnode-setup-token.txt', boot / 'AIRNODE-SETUP.txt']
if any(p.exists() for p in paths): raise SystemExit('Private setup files already exist. Keep them or remove them deliberately before creating replacements.')
config = {'ssid': 'AirNode-Setup-' + secrets.token_hex(3).upper(), 'password': secrets.token_urlsafe(15), 'country': sys.argv[2]}
token = secrets.token_urlsafe(24)
paths[0].write_text(json.dumps(config), encoding='utf-8')
paths[1].write_text(token, encoding='utf-8')
paths[2].write_text('Keep these unique setup details private.\nWi-Fi: ' + config['ssid'] + '\nWi-Fi password: ' + config['password'] + '\nOpen: https://10.42.0.1/\nPairing token: ' + token + '\n', encoding='utf-8')
print('Prepared. Save the private details from AIRNODE-SETUP.txt before inserting the card in your Pi.')

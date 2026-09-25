#!/bin/bash
# Read-only checks on the installed Pi. Never prints passwords or pairing tokens.
set -uo pipefail
failed=0
check() {
    if "$@" >/dev/null 2>&1; then printf 'PASS  %s\n' "$*";
    else printf 'FAIL  %s\n' "$*"; failed=1; fi
}
check systemctl is-active NetworkManager avahi-daemon nginx airnode-api airnode-control
check systemctl is-enabled airnode-network airnode-firstboot airnode-api airnode-control nginx avahi-daemon
check nginx -t
check test -s /etc/airnode/tls/cert.pem
check test -x /usr/local/bin/readsb
cd /opt/airnode || exit 1
python3 - <<'PY' || failed=1
import json, socket, subprocess, urllib.request
from airnode.network import access_info
data = access_info(socket.gethostname(), subprocess.check_output(['ip','-j','address','show'], text=True))
print('\nOpen from another computer on the same LAN:')
print(data['hostname_url'] or 'Hostname unavailable')
for item in data['addresses']: print(item['url'] + ' (' + item['interface'] + ')')
if not data['addresses']: raise SystemExit('No LAN address yet. Check Ethernet / Wi-Fi and router DHCP.')
with urllib.request.urlopen('http://127.0.0.1:8080/', timeout=5) as response:
    if response.status != 200: raise SystemExit('Local API is not ready')
print('PASS  Local dashboard responds')
PY
printf '\nVerify this certificate fingerprint on your other computer before trusting HTTPS:\n'
openssl x509 -in /etc/airnode/tls/cert.pem -noout -fingerprint -sha256 || failed=1
printf '\nReceiver status (requires connected SDR):\n'
systemctl is-active airnode-receiver || failed=1
exit "$failed"

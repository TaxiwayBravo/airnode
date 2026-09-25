#!/bin/bash
set -euo pipefail
umask 077
install -d -m 700 -o airnode -g airnode /var/lib/airnode
status=/var/lib/airnode/installation.json
write_status() { printf '{"state":"%s","step":"%s","progress":%s}\n' "$1" "$2" "$3" > "$status"; chmod 644 "$status"; }
write_status running 'Preparing AirNode identity' 10
install -d -m 700 /etc/airnode/tls
if [[ ! -f /etc/airnode/tls/key.pem ]]; then
    host=$(hostname)
    openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 825 \
      -keyout /etc/airnode/tls/key.pem -out /etc/airnode/tls/cert.pem \
      -subj "/CN=$host.local" -addext "subjectAltName=DNS:$host.local,DNS:$host,IP:10.42.0.1"
fi
# A private owner-selected token can be put on the boot partition before first boot.
# It is consumed as plain data, never sourced as shell code. No default credentials.
token=/boot/firmware/airnode-setup-token.txt
if [[ -f "$token" ]]; then
    python3 - "$token" <<'PY'
import pathlib, sys
value = pathlib.Path(sys.argv[1]).read_text().strip()
if not 24 <= len(value) <= 128 or not value.isascii() or any(c.isspace() for c in value):
    raise SystemExit('AirNode setup token must be 24–128 ASCII non-whitespace characters')
pathlib.Path('/var/lib/airnode/setup-token').write_text(value)
PY
    rm -- "$token"
elif [[ ! -f /var/lib/airnode/setup-token && ! -f /var/lib/airnode/auth.db ]]; then
    openssl rand -hex 24 > /var/lib/airnode/setup-token
fi
chown -R airnode:airnode /var/lib/airnode
chmod 700 /var/lib/airnode
if [[ -f /var/lib/airnode/setup-token ]]; then chmod 600 /var/lib/airnode/setup-token; fi
write_status running 'Preparing Wi-Fi recovery' 70
(cd /opt/airnode && python3 -m airnode.wifi init)
write_status ready 'AirNode is ready for pairing' 100
touch /var/lib/airnode/initialized
chown airnode:airnode /var/lib/airnode/initialized
echo 'AirNode first boot complete. Pairing token is available to the local administrator in /var/lib/airnode/setup-token.'

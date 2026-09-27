#!/bin/bash
# Install on a dedicated Raspberry Pi OS Lite / Debian arm64 host.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run this installer as root.'; exit 1; }
[[ $(dpkg --print-architecture) == arm64 ]] || { echo 'AirNode production targets Debian arm64.'; exit 1; }
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3 nginx openssl avahi-daemon usbutils iproute2 \
  network-manager dnsmasq-base iw rfkill iso-codes ca-certificates gnupg iputils-ping git build-essential pkg-config libusb-1.0-0-dev librtlsdr-dev \
  libncurses-dev zlib1g-dev libzstd-dev libbrotli-dev
getent group airnode >/dev/null || groupadd --system airnode
getent group plugdev >/dev/null || groupadd --system plugdev
id airnode >/dev/null 2>&1 || useradd --system --gid airnode --home-dir /var/lib/airnode --shell /usr/sbin/nologin airnode
id airnode-radio >/dev/null 2>&1 || useradd --system --gid airnode --groups plugdev --no-create-home --shell /usr/sbin/nologin airnode-radio
install -d -m 755 /opt/airnode
if [[ "$root" != /opt/airnode ]]; then
    cp -a "$root/airnode" "$root/web" "$root/scripts" "$root/deploy" /opt/airnode/
fi
chown -R root:root /opt/airnode
find /opt/airnode -type d -exec chmod 755 {} +
find /opt/airnode -type f -exec chmod 644 {} +
chmod 755 /opt/airnode/scripts/*.sh
install -d -m 750 -o root -g airnode /etc/airnode
install -d -m 750 -o root -g airnode /etc/airnode/providers
install -d -m 755 /usr/local/lib
install -m 644 /opt/airnode/scripts/release-recovery.py /usr/local/lib/airnode-recovery.py
if [[ ! -e /etc/airnode/update-public.pem ]]; then
    install -m 644 /opt/airnode/deploy/update-public.pem /etc/airnode/update-public.pem
fi
if [[ ! -f /etc/airnode/config.json ]]; then
    (cd /opt/airnode && python3 -c 'from airnode.config import DEFAULT,write; write("/etc/airnode/config.json", DEFAULT)')
fi
chown root:airnode /etc/airnode/config.json
chmod 640 /etc/airnode/config.json
bash /opt/airnode/scripts/build-readsb.sh
bash /opt/airnode/scripts/install-tar1090.sh
install -m 644 /opt/airnode/deploy/airnode-*.service /etc/systemd/system/
install -m 644 /opt/airnode/deploy/airnode-*.timer /etc/systemd/system/
install -m 644 /opt/airnode/deploy/99airnode-provider-permissions /etc/apt/apt.conf.d/
install -m 644 /opt/airnode/deploy/airnode.avahi.service /etc/avahi/services/
install -m 644 /opt/airnode/deploy/99-airnode-sdr.rules /etc/udev/rules.d/
install -m 644 /opt/airnode/deploy/airnode-sdr.conf /etc/modprobe.d/
# This installer owns the dedicated appliance's default web virtual host.
install -m 644 /opt/airnode/deploy/nginx.conf /etc/nginx/sites-available/airnode
rm -f /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/airnode /etc/nginx/sites-enabled/airnode
install -d /etc/systemd/system/nginx.service.d
printf '[Unit]\nRequires=airnode-firstboot.service\nAfter=airnode-firstboot.service\n' > /etc/systemd/system/nginx.service.d/airnode.conf
systemctl enable airnode-release-recovery airnode-wifi airnode-network airnode-firstboot airnode-control airnode-api airnode-receiver avahi-daemon nginx NetworkManager
if [[ ${AIRNODE_IMAGE_BUILD:-0} != 1 ]]; then
    systemctl daemon-reload
    bash /opt/airnode/scripts/network-setup.sh
    systemctl start NetworkManager
    nmcli connection reload
    if [[ ! -f /var/lib/airnode/initialized ]]; then
        station_host=${AIRNODE_HOSTNAME:-$(hostname)}
        if [[ "$station_host" == raspberrypi || "$station_host" == debian ]]; then station_host=airnode; fi
        [[ "$station_host" =~ ^[a-z][a-z0-9-]{0,61}[a-z0-9]$ || "$station_host" =~ ^[a-z]$ ]] || { echo 'Invalid AirNode hostname'; exit 1; }
        hostnamectl set-hostname "$station_host"
        python3 - "$station_host" <<'PYHOST'
from pathlib import Path
import sys
path = Path('/etc/hosts')
lines = [line for line in path.read_text().splitlines() if not line.startswith('127.0.1.1')]
path.write_text('\n'.join(lines) + '\n127.0.1.1\t' + sys.argv[1] + '\n')
PYHOST
    fi
    systemctl start airnode-firstboot
    nginx -t
    udevadm control --reload-rules
    udevadm trigger --subsystem-match=usb
    systemctl restart airnode-control airnode-api airnode-receiver airnode-wifi avahi-daemon nginx
    echo 'AirNode installed. Reboot to release DVB kernel drivers if needed.'
    echo 'Pairing token: sudo cat /var/lib/airnode/setup-token'
    echo "Open https://$(hostname).local/ from another computer on your LAN."
    echo 'Run sudo bash /opt/airnode/scripts/deployment-check.sh to see addresses and readiness checks.'
fi

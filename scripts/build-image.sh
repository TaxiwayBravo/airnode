#!/bin/bash
# Customize a verified, pristine Raspberry Pi OS Lite arm64 raw image.
# Native arm64 Debian Linux build host only. Never writes a physical disk.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run as root on an arm64 Linux build host.'; exit 1; }
[[ $(uname -m) == aarch64 ]] || { echo 'Native arm64 host required (Pi 4/5 or arm64 VM).'; exit 1; }
[[ $# == 3 ]] || { echo 'Usage: build-image.sh BASE.img EXPECTED_SHA256 OUTPUT.img'; exit 1; }
base=$(realpath -- "$1")
expected=$2
output=$(realpath -m -- "$3")
[[ -f "$base" && "$expected" =~ ^[a-fA-F0-9]{64}$ ]] || exit 1
[[ "$output" == *.img && ! -e "$output" && ! -L "$output" ]] || { echo 'Output must be a new .img file.'; exit 1; }
[[ $(sha256sum "$base" | cut -d ' ' -f 1) == "${expected,,}" ]] || { echo 'Base checksum mismatch'; exit 1; }
for tool in losetup mount umount parted e2fsck resize2fs chroot xz; do command -v "$tool" >/dev/null; done
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p -- "$(dirname -- "$output")"
cp --sparse=always --reflink=auto -- "$base" "$output"
truncate -s +3G -- "$output"
parted -s "$output" resizepart 2 100%
loop=$(losetup --find --show --partscan "$output")
mountpoint=$(mktemp -d)
cleanup() {
    for part in dev/pts dev proc sys run boot/firmware ''; do
        if mountpoint -q "$mountpoint/$part"; then umount "$mountpoint/$part"; fi
    done
    losetup -d "$loop"
    rmdir "$mountpoint"
}
trap cleanup EXIT
udevadm settle
[[ -b "${loop}p1" && -b "${loop}p2" ]] || { echo 'Expected standard two-partition Raspberry Pi OS image'; exit 1; }
set +e
e2fsck -f -p "${loop}p2"
fsck_status=$?
set -e
[[ $fsck_status -le 1 ]] || exit "$fsck_status"
resize2fs "${loop}p2"
mount "${loop}p2" "$mountpoint"
[[ -f "$mountpoint/etc/rpi-issue" ]] || { echo 'Use pristine Raspberry Pi OS Lite arm64.'; exit 1; }
mkdir -p "$mountpoint/boot/firmware"
mount "${loop}p1" "$mountpoint/boot/firmware"
for part in dev proc sys run; do
    mount --bind "/$part" "$mountpoint/$part"
done
mount --bind /dev/pts "$mountpoint/dev/pts"
# Block package maintainer scripts from starting services inside the image.
[[ ! -e "$mountpoint/usr/sbin/policy-rc.d" ]] || { echo 'Unexpected service policy in base image'; exit 1; }
printf '#!/bin/sh\nexit 101\n' > "$mountpoint/usr/sbin/policy-rc.d"
chmod 755 "$mountpoint/usr/sbin/policy-rc.d"
cp -a "$mountpoint/etc/resolv.conf" "$mountpoint/etc/resolv.conf.airnode-backup"
rm -f "$mountpoint/etc/resolv.conf"
cp -L /etc/resolv.conf "$mountpoint/etc/resolv.conf"
mkdir -p "$mountpoint/opt/airnode"
cp -a "$root/airnode" "$root/web" "$root/scripts" "$root/deploy" "$mountpoint/opt/airnode/"
chroot "$mountpoint" /usr/bin/env AIRNODE_IMAGE_BUILD=1 /bin/bash /opt/airnode/scripts/install.sh
rm -f "$mountpoint/usr/sbin/policy-rc.d" "$mountpoint/etc/resolv.conf"
mv "$mountpoint/etc/resolv.conf.airnode-backup" "$mountpoint/etc/resolv.conf"
printf 'airnode\n' > "$mountpoint/etc/hostname"
sed -i 's/^127\.0\.1\.1.*/127.0.1.1\tairnode/' "$mountpoint/etc/hosts"
# A pristine image has no AirNode credentials or TLS identity. Never clone a provisioned Pi.
[[ ! -e "$mountpoint/var/lib/airnode/auth.db" && ! -e "$mountpoint/etc/airnode/tls/key.pem" ]] || { echo 'Unexpected provisioned identity'; exit 1; }
: > "$mountpoint/etc/machine-id"
rm -f "$mountpoint/var/lib/dbus/machine-id"
ln -s /etc/machine-id "$mountpoint/var/lib/dbus/machine-id"
rm -f "$mountpoint"/etc/ssh/ssh_host_*
chroot "$mountpoint" apt-get clean
mkdir -p "$mountpoint/usr/local/share/airnode"
chroot "$mountpoint" dpkg-query -W > "$mountpoint/usr/local/share/airnode/packages.txt"
cp "$root/deploy/readsb.commit" "$output.readsb.commit"
airnode_version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$root/airnode/__init__.py")
printf 'base_sha256=%s\nairnode=%s\narchitecture=arm64\n' "$expected" "$airnode_version" > "$output.manifest"
sync
cleanup
trap - EXIT
xz -T2 -k "$output"
sha256sum "$output.xz" > "$output.xz.sha256"
echo "AirNode image created: $output.xz"
echo 'Hardware boot and SDR acceptance testing are required before release.'

#!/bin/bash
# Install a pinned Tar1090 web map against AirNode's readsb JSON feed.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ref=$(tr -d '[:space:]' < "$root/deploy/tar1090.commit")
[[ "$ref" =~ ^[a-f0-9]{40}$ ]] || { echo 'A full Tar1090 commit SHA is required'; exit 1; }
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
git init "$work/tar1090"
git -C "$work/tar1090" remote add origin https://github.com/wiedehopf/tar1090.git
git -C "$work/tar1090" fetch --depth 1 origin "$ref"
git -C "$work/tar1090" checkout --detach FETCH_HEAD
[[ $(git -C "$work/tar1090" rev-parse HEAD) == "$ref" ]]
# Tar1090's installer creates its generator service and static web assets. The
# source directory is AirNode's private readsb runtime directory.
TAR1090_UPDATE_DIR=/usr/local/share/tar1090 AIRNODE_TAR1090=1 \
  bash "$work/tar1090/install.sh" /run/airnode-readsb tar1090 /usr/local/share/tar1090 "$work/tar1090"
usermod -a -G airnode tar1090
# Run the generator with the same locked-down account that owns readsb's JSON
# runtime directory. This avoids a first-boot supplementary-group race.
if [[ -f /lib/systemd/system/tar1090.service ]]; then
  sed -i 's/^User=tar1090$/User=airnode-radio/' /lib/systemd/system/tar1090.service
fi
install -d -m 755 /usr/local/share/airnode/third-party
git -C "$work/tar1090" archive --format=tar HEAD | gzip -n > /usr/local/share/airnode/third-party/tar1090-source.tar.gz
cp "$work/tar1090/LICENSE" /usr/local/share/airnode/third-party/tar1090-LICENSE
printf '%s\n' "$ref" > /usr/local/share/airnode/third-party/tar1090.commit
if [[ -f /usr/local/share/tar1090/nginx-tar1090.conf ]]; then
  install -m 644 /usr/local/share/tar1090/nginx-tar1090.conf /etc/nginx/snippets/airnode-tar1090.conf
fi

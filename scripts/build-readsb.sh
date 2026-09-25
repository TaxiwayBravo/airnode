#!/bin/bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ref=$(cat "$root/deploy/readsb.commit")
[[ "$ref" =~ ^[a-f0-9]{40}$ ]] || { echo 'A full readsb commit SHA is required'; exit 1; }
build=$(mktemp -d)
trap 'rm -rf -- "$build"' EXIT
git init "$build/readsb"
git -C "$build/readsb" remote add origin https://github.com/wiedehopf/readsb.git
git -C "$build/readsb" fetch --depth 1 origin "$ref"
git -C "$build/readsb" checkout --detach FETCH_HEAD
[[ $(git -C "$build/readsb" rev-parse HEAD) == "$ref" ]]
make -C "$build/readsb" -j"${AIRNODE_BUILD_JOBS:-2}" RTLSDR=yes
install -m 755 "$build/readsb/readsb" /usr/local/bin/readsb.airnode-new
mv -f /usr/local/bin/readsb.airnode-new /usr/local/bin/readsb
install -d /usr/local/share/airnode/third-party
# Preserve corresponding source and licensing alongside the binary for image distribution.
git -C "$build/readsb" archive --format=tar HEAD | gzip -n > /usr/local/share/airnode/third-party/readsb-source.tar.gz
cp "$build/readsb/COPYING" /usr/local/share/airnode/third-party/readsb-COPYING
printf '%s\n' "$ref" > /usr/local/share/airnode/third-party/readsb.commit

#!/bin/bash
# Low-priority wired DHCP fallback. Existing Imager/Wi-Fi/static profiles win.
set -euo pipefail
install -d -m 700 /etc/NetworkManager/system-connections
profile=/etc/NetworkManager/system-connections/airnode-ethernet.nmconnection
if [[ ! -e "$profile" ]]; then
    umask 077
    uuid=$(python3 -c 'import uuid; print(uuid.uuid4())')
    cat > "$profile" <<EOF
[connection]
id=AirNode Ethernet
uuid=$uuid
type=ethernet
autoconnect=true
autoconnect-priority=-999

[ethernet]

[ipv4]
method=auto
dhcp-send-hostname=true

[ipv6]
method=auto
EOF
    chmod 600 "$profile"
fi

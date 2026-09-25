# Deploy AirNode on your local network

AirNode runs on the Pi. Your laptop/desktop only needs a browser on the same network. The Pi obtains its own address from the router using DHCP; AirNode does not invent a fixed IP or require cloud hosting. The image uses `airnode` as its hostname, so start with **https://airnode.local/**. The installer also changes a fresh default `raspberrypi`/`debian` hostname to `airnode`, preserving other custom hostnames. Set `AIRNODE_HOSTNAME` during a first installation to choose a unique name.

## Deploy the source package

1. Flash Raspberry Pi OS Lite **64-bit Bookworm or Trixie** for Pi 4/5. In Raspberry Pi Imager set a local administrator and your Wi-Fi/country if needed. Ethernet to your router is the simplest setup. Set a unique hostname if you have several stations.
2. Copy the AirNode folder from the ZIP to the Pi. From that folder run `sudo bash scripts/install.sh`. Keep it powered and online while it installs dependencies and builds readsb. Reboot after installation, then attach the SDR/antenna.
3. Run `sudo bash /opt/airnode/scripts/deployment-check.sh` on the Pi. This prints its current browser addresses, service readiness and HTTPS certificate fingerprint. It does not reveal the pairing token. An absent SDR can make the receiver check fail even if the website works.
4. On your **other computer**, open `https://airnode.local/` (or your chosen hostname), or the Pi's IP address printed by the check, such as `https://192.168.1.42/`. This number is an example, not a preassigned address. Port 8086 / localhost is only the development preview on your computer.
5. AirNode generates a unique self-signed HTTPS certificate. Compare its fingerprint with the Pi's deployment-check output before trusting it on your computer, or provision a certificate trusted by your devices. IP access may also show a hostname mismatch; prefer the `.local` name. AirNode does not disable browser certificate validation.
6. Read your private first-use token on the Pi with `sudo cat /var/lib/airnode/setup-token`, pair in the browser, and choose an owner password. You can instead provision a private token on the flashed boot partition as described in the README. Then configure the receiver and optional aggregators.

Under **System → Open AirNode on another device**, the dashboard lists the hostname and observed active IP addresses. Save the hostname as a bookmark. If you want the same numeric IP after reboot, create a DHCP reservation for the Pi in your router. There is no need to expose the API, forward router ports, or install software on your desktop.

## Network behavior

At boot, `airnode-network.service` creates a private, per-device NetworkManager Ethernet profile with automatic IPv4 DHCP and IPv6 configuration. Its priority is -999, allowing existing standard-priority Imager, Wi-Fi and static profiles to take precedence. It never forcibly disconnects a working interface; the profile is loaded during installation and selected automatically at boot where needed. Wi-Fi credentials are not bundled or guessed.

Nginx listens on the Pi's interfaces on ports 80/443, redirects HTTP to HTTPS, and proxies to the private API on 127.0.0.1:8080. Avahi advertises the HTTPS service and hostname over mDNS. Raw radio feed ports remain loopback-only unless deliberately enabled. A router with client isolation, guest Wi-Fi, VLAN separation, host firewall, or blocked multicast may prevent access; use the same normal LAN and check the router's client list for the Pi's IP if `.local` does not resolve. Multiple devices need unique hostnames. If neither Wi-Fi nor Ethernet provides a connection for 90 seconds, AirNode starts its protected setup hotspot. See [Wi-Fi onboarding](WIFI.md). There is no direct-cable Ethernet DHCP server.

## Flashable image and release gate

The source package includes the [image builder](IMAGE.md), which must run on native arm64 Linux with a verified pristine Raspberry Pi OS image. It prepares first-boot identities, networking and services; credentials and TLS keys are generated per Pi. The development Windows machine has not built or boot-tested a flashable image. The local hardware preview uses no synthetic aircraft and cannot stand in for a connected Pi/SDR. Do not distribute a hardware-ready release until Pi 4 and Pi 5 pass the [acceptance checklist](VALIDATION.md), including access from a second machine, reboot reconnection, SDR reception and feeder updates.

References: [Raspberry Pi network configuration](https://www.raspberrypi.com/documentation/computers/configuration.html), [finding your Pi on the network](https://www.raspberrypi.com/documentation/computers/remote-access.html).

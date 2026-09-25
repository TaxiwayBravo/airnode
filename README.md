# AirNode

**Your sky, connected.** An original Raspberry Pi ADS-B appliance MVP with an AirNode control panel, authenticated API and Linux orchestration. Built for Pi 4/5, Raspberry Pi OS Lite / Debian arm64, and a supported 1090 MHz RTL-SDR.

This is a runnable development repository, **not a hardware-certified image release**. The demo and API tests run without a Pi. Installation, systemd integration and image boot must pass the hardware acceptance checklist before distributing a release.

## Try the dashboard

Python 3.11+ is the only runtime dependency for the demo. No npm install, hosted fonts, tracking, map SDK or CDN is required.

```sh
python -m airnode.server --local-preview
```

Open **http://127.0.0.1:8080**. Copy the pairing token printed in the terminal, choose an owner password of at least 12 characters, and claim the local preview. Hardware-preview state lives in `.preview/`. It binds only to loopback, shows no synthetic aircraft, and disables Pi management actions until you use the installed Pi. The explicit developer-only `--demo` flag remains available for automated UI tests; no production service uses it.

## What is implemented

| Area | MVP behavior |
| --- | --- |
| Original UI | Responsive overview, live local radar, searchable aircraft list, receiver, aggregators, feeds, system and logs |
| Receiver | readsb with RTL-SDR, serial/index selection, gain, PPM, optional coordinates, start/stop/restart |
| Data | readsb-compatible authenticated aircraft JSON, freshness detection, aircraft counts and sampled message rate |
| Map links | AirNode-owned receiver-centred 200 NM radar; per-aircraft OpenStreetMap links |
| Aggregators | Five provider integrations with local settings, explicit sharing consent, dashboard installation, optional daily updates, software status, logs and restart |
| Custom feeds | Up to eight optional Beast TCP destinations, individual systemd processes and journal logs |
| Device health | Service states, USB inventory, CPU temperature, load API field, storage and network addresses |
| System | Hostname setting, signed OS package upgrades, update journal, password-confirmed reboot/shutdown |
| Authentication | One owner, pairing token, scrypt password hash, expiring sessions, CSRF protection, throttled login |
| Deployment | Dedicated-host installer, systemd units, nginx HTTPS, mDNS, udev permissions and first-boot identity |
| Image pipeline | Verified base-image customization, pinned readsb commit, source archive, compressed image + checksum |

Network setup includes DHCP, authenticated home Wi-Fi configuration and a unique protected setup hotspot when no usable uplink exists. See [Wi-Fi onboarding](docs/WIFI.md). Static IP changes remain router/local-administrator operations. The Aggregators page manages ADSB.lol, airplanes.live, ADS-B Exchange, FlightAware and Flightradar24. AirNode installs PiAware/FR24 from official repositories and offers daily updates. Users still complete provider registration/claiming; MLAT stays off. See [aggregator setup](docs/AGGREGATORS.md). OS updates use APT. Signed AirNode application updates use stable/beta GitHub releases with application rollback; receiver-runtime changes still require the full installer. See [release publishing](docs/RELEASES.md). The radar is not a geographic basemap. See [scope and release gates](docs/ROADMAP.md).

## Install on a Pi

Follow the [local deployment guide](docs/DEPLOYMENT.md) to install on the Pi and open it from another computer. For a card-flashing walkthrough, see [put AirNode on a microSD card](docs/FLASHING.md). The Pi receives its own router-assigned IP; the default image is reachable at `https://airnode.local/`.

Use a **dedicated** Raspberry Pi OS Lite 64-bit installation (Bookworm or Trixie candidate), Pi 4/5, quality power supply, 16 GB+ microSD, 1090 MHz antenna and compatible RTL-SDR. The installer owns the default nginx site and DVB blacklist. Back up an existing installation first.

1. Flash the AirNode image with Raspberry Pi Imager. Choose **Use custom**, select the image, select the SD card and click **Write**. Leave the optional Imager customisation at its defaults; AirNode handles first-boot pairing and Wi-Fi setup.
2. Copy this repository onto the Pi. Run `sudo bash scripts/install.sh` from its root. It fetches the exact readsb revision recorded in `deploy/readsb.commit` and builds locally.
3. Reboot to release any DVB drivers, then attach the SDR and antenna.
4. Open `https://airnode.local/` or `https://<Pi-IP>/` from another LAN device. A unique self-signed certificate is generated locally. Verify the SHA-256 fingerprint from a trusted console (`sudo openssl x509 -in /etc/airnode/tls/cert.pem -noout -fingerprint -sha256`) before trusting it, or install your own trusted certificate.
5. Read the pairing token using `sudo cat /var/lib/airnode/setup-token`. Claim the station, set its location if desired, and inspect receiver health. The token is deleted after ownership is claimed.

No global admin password is included. SSH is not enabled by AirNode. Internet feeder connections are off by default. No router port forwarding is needed.

For headless image pairing without SSH, place a random, privately generated 24â€“128 character token in `airnode-setup-token.txt` on the boot partition **after flashing, before first boot**. Save a private copy for the pairing form. The first-boot service consumes and removes that file. Without it, a local administrator must retrieve the generated token. Never publish an image containing owner credentials or a shared pairing token.

## Build a flashable image

See [image build guide](docs/IMAGE.md). The script takes a pristine Raspberry Pi OS Lite arm64 `.img`, its verified SHA-256 and a new output filename. It adds AirNode to a copy and produces `.img.xz`, checksum and manifest. Run on a native arm64 Linux host with root/mount access. It does not write a physical SD card.

```sh
sudo bash scripts/build-image.sh base-raspios-lite-arm64.img VERIFIED_64_HEX_SHA256 build/airnode-0.4.0-beta.1.img
```

## Repository

```text
airnode/       Python API, auth, schema, privileged broker, receiver and feeder launchers
web/           Original HTML, CSS and JavaScript interface (no frontend build step)
deploy/        systemd, nginx, mDNS, udev and readsb revision lock
scripts/       Install, first boot, decoder build, image build and diagnostics
tests/         Authentication, API, configuration and stale-data regression tests
docs/          Architecture, API, image build, operations, security and release gates
```

Run `python -m unittest discover -s tests -v` and `node --check web/app.js`. Linux CI additionally runs Bash syntax checks and ShellCheck. [Validation notes](docs/VALIDATION.md) distinguish executed checks from hardware gates.

## Design and attribution

AirNode's name, interface and orchestration in this repository are original. The general headless-appliance workflow is the inspiration; no adsb.im code, UI assets or branding is included. The receiver uses [wiedehopf/readsb](https://github.com/wiedehopf/readsb), an independently maintained open-source decoder. Its [upstream build and networking documentation](https://github.com/wiedehopf/readsb/blob/dev/README.md) informs the integration. The image base remains Raspberry Pi OS; it is not rebranded in a way that obscures OS provenance.

AirNode code is MIT licensed. Third-party packages retain their own licenses. See [THIRD_PARTY.md](THIRD_PARTY.md), especially source distribution obligations before shipping images.


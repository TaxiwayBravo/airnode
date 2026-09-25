# Aggregators — AirNode 0.3

AirNode is hosted by each user's Raspberry Pi. The browser connects to that Pi over the LAN. The Pi stores the owner password, aggregator settings and provider keys, and selected clients make outbound connections directly to their providers. There is no AirNode cloud account, central relay, remote hosting requirement or incoming router port forward. Offline LAN administration remains available when the internet is down; internet feeds reconnect through their clients.

Open **Aggregators** in the dashboard. All five providers start unconfigured and disabled. Set up a provider, choose an existing ID or allow a new one where supported, and explicitly enable sharing. Each provider has its own enabled state, status, restart action, redacted local journal and official setup/status links. Disabled settings survive reboot; blank credential fields keep a previously saved credential. No actual provider is enabled in the development preview.

| Provider | Local adapter | What the owner supplies |
| --- | --- | --- |
| ADSB.lol | Dedicated network-only readsb service; `feed.adsb.lol:30004`, fallback `in.adsb.lol:1337` | A locally generated UUID, or an existing station UUID |
| airplanes.live | Dedicated network-only readsb service; `feed.airplanes.live:30004` | A locally generated UUID, or an existing station UUID |
| ADS-B Exchange | Dedicated network-only readsb service; `feed1.adsbexchange.com:30004`, fallback `feed2.adsbexchange.com:64004` | A locally generated UUID, or an existing station UUID |
| FlightAware | Installed `piaware.service`, configured for `127.0.0.1:30005` | Optional existing feeder ID; new installations register through PiAware and are claimed on FlightAware |
| Flightradar24 | Installed `fr24feed.service`, configured for Beast TCP at `127.0.0.1:30005` | A valid 16-character sharing key obtained through FR24 registration |

The readsb adapters use `beast_reduce_plus_out` with per-provider UUIDs. They never open a second USB receiver or incoming feed port. The existing AirNode receiver remains the only decoder. LAN raw-feed exposure can remain off because every adapter reads the loopback Beast port.

## Install and maintain from the dashboard

1. For FlightAware or Flightradar24, choose **Install software**. AirNode downloads the official repository bootstrap, checks its pinned SHA-256, installs the client and dependencies with signed APT packages, and configures a local Beast input. ADSB.lol, airplanes.live and ADS-B Exchange already have their client included.
2. Wait for the software job to finish. The card displays working/failed state and the installed version. **Installation log** shows the local, redacted journal. Downloads run in the background; the dashboard remains available. A failed install leaves sharing stopped and the saved credentials intact. Resolve the logged cause and retry.
3. Open **Set up**, supply an existing ID/key where needed, and explicitly enable sharing. FlightAware owners claim their receiver through the provider link. Flightradar24 owners obtain a sharing key through provider registration. AirNode does not create accounts or accept provider terms on the owner's behalf.
4. Choose **Keep updated daily** to opt into a persistent daily update timer (04:00–05:00 Pi local time, with catch-up after downtime). **Check & update** runs immediately. Turn off daily updates to cancel future scheduled runs; an already-running job finishes. Explicit system-wide OS updates may still upgrade installed provider packages.

Native automatic setup targets Debian / Raspberry Pi OS Bookworm and Trixie arm64. It uses the stable provider repositories, never beta feeds, unsigned packages or downloaded shell scripts. Bootstrap hashes are pinned in `airnode/maintenance.py`; a changed repository package/key fails closed until an AirNode compatibility update approves it. Provider package versions remain controlled by their signed stable repositories. Existing conflicting provider repository definitions may need administrator cleanup before APT can run.

The first three networks share the bundled readsb binary. Their update controls check/build only the revision pinned by the installed AirNode release, preserving its source archive. They do not track arbitrary upstream Git commits. Installing a new AirNode release is still required to approve a newer readsb revision. Builds publish the binary by an atomic rename; active receiver/custom-feed/readsb-aggregator services restart after a successful replacement.

AirNode installs systemd service gates so package scripts cannot start native clients before sharing is enabled. The FR24 service override skips its SDR installer/driver hooks; its vendor updater cron file is diverted outside cron, leaving scheduling to AirNode. An APT hook restores private FR24 key permissions after package operations, including OS upgrades. The first original configuration is backed up privately. AirNode preserves unrelated configuration entries. Existing PiAware boot configuration overrides must be removed before AirNode can enable it.

Software jobs and native settings mutations share a local lock; simultaneous jobs queue. OS package updates use the same lock. No feed is enabled by installing software. Updates resume only feeds previously enabled in AirNode. Failure can leave a feed stopped; inspect the job log and retry. Package rollback and recovery from interrupted dpkg transactions are not automatic: keep local console/SSH recovery access during hardware testing.

Official sources checked 2026-09-22: [PiAware installation](https://www.flightaware.com/adsb/piaware/install.rvt), [FR24 registration and installation](https://www.flightradar24.com/share-your-data), [FR24 stable repository](https://repo-feed.flightradar24.com/), and [FR24 signing-key rotation](https://forum.flightradar24.com/forum/radar-forums/flightradar24-feeding-data-to-flightradar24/230581-fr24-repo-feed-signing-key-uses-sha1-trixie-will-stop-supporting-it-by-february). The current FR24 arm64 package was inspected for its service, updater and installation hooks; it was not executed on the development computer.

## What status means

- **Not configured / Disabled:** nothing selected for sharing, or sharing deliberately disabled.
- **Client required:** install the local client or repair its missing service.
- **Starting / Connecting:** the process is starting or its upstream TCP connection has not been detected.
- **TCP connected:** a readsb process owns an established socket to the expected upstream port. This does **not** prove provider ingestion or account credit.
- **Running · unverified:** PiAware/FR24 is active. AirNode does not claim provider acknowledgement from process status.
- **Stopped:** settings are enabled but the service is inactive/failed.
- **Running outside settings:** a local client is active although AirNode has not enabled it; another administrator/tool may have started it.
- **Demo enabled:** settings are simulated locally; no clients, accounts or network feeds are started.

Provider status links open the provider directly in the user's browser. They may depend on the public IP or provider account of the user. AirNode does not proxy those account pages or poll their APIs. No remote-provider availability is needed to load the catalog.

## Security and storage

`/etc/airnode/aggregators.json` is root-only (0600). FR24 sharing keys are never returned by the API; only a `credential_set` flag is returned. UUIDs are visible to the authenticated owner. Readsb instance configuration lives in `/etc/airnode/providers/` and is readable by the radio group; those instance files contain only their respective UUID, not other providers' keys. Native FR24 settings are private to root or the packaged service's group. Journals served through AirNode redact known identifiers/keys and common UUID/key patterns. Root administrators can still access raw system journals/configs.

Updates to this feature preserve the original receiver/custom feeder config schema: existing installations require no migration. To upgrade, stop the API/control services, install the new AirNode source and unit template through the installer, then restart. The new readsb aggregator template is installed but no instance is enabled automatically. Keep provider state/credentials out of distributable images and source archives.

## Current limits

ADS-B only: MLAT remains off for all five integrations. Provider-specific statistics upload, account benefits, station credit, MLAT enrolment and status-API integrations are not implemented or guaranteed. Community network feed transports are unencrypted TCP. Provider/client/package compatibility and real data acceptance must be validated on a Pi; local tests use mocked service operations and demo traffic, not public collectors. Automated native package installation and scheduled maintenance are implemented but require Pi integration testing before release.

Protocol/configuration references: [ADSB.lol manual feeding](https://github.com/adsblol/feed), [readsb connector/UUID format](https://github.com/wiedehopf/readsb), [ADS-B Exchange endpoint configuration](https://github.com/ADSBexchange/feedclient/blob/master/configure.sh), [Ultrafeeder's readsb ADS-B Exchange integration](https://github.com/sdr-enthusiasts/docker-adsb-ultrafeeder/blob/main/docker-compose.yml), [PiAware configuration](https://www.flightaware.com/adsb/piaware/advanced_configuration). Checked 2026-09-20; validate again before an image release.

# Operations

## Daily use

Fresh data and an active receiver service should agree. A plugged-in USB device alone does not prove readsb can open it or decode transmissions. No aircraft with an otherwise healthy decoder can simply mean insufficient antenna coverage. Default gain is automatic. Do not enable bias tee without checking your antenna/LNA; this MVP does not control it.

Saving receiver settings briefly restarts readsb and feeds. Feeder start/stop/restart affects current state. Use the enabled switch to persist behavior after boot. Feeds start disabled and send no data until explicitly enabled. Review connection logs for each collector; running process state alone does not mean the collector accepts your feed.

## Diagnostics

```sh
sudo bash scripts/diagnose.sh
sudo journalctl -u airnode-api -u airnode-control -n 100 --no-pager
sudo journalctl -u airnode-receiver -f
sudo journalctl -u airnode-feeder@my-collector -f
```

If SDR is missing, inspect `lsusb`, power, cable and udev permissions. If the DVB driver owns it, reboot after installing the blacklist. Additional SDR USB product IDs need explicit udev rules. Stop other dump1090/readsb processes that might already own the radio or ports. Restarting does not reset a physically wedged USB device.

If the UI cannot connect, check `systemctl status airnode-firstboot nginx airnode-api airnode-control`. Malformed boot pairing tokens fail first-boot provisioning deliberately; correct/remove the token from a trusted local console and restart the firstboot unit. Verify nginx certificate paths and `sudo nginx -t`. Production cookies require HTTPS. The API health endpoint only checks the API process.

## OS and application updates

The dashboard starts `airnode-update.service`, which runs signed APT index refresh and `apt-get upgrade`. It uses current configured repositories and keeps modified config files. It does not run a distribution upgrade, change feed providers or install new AirNode source. Read the update journal for completion and failures; reboot separately when required. Power loss during package upgrades can require local `dpkg --configure -a` recovery.

For an AirNode/readsb release, first take a backup, review the source/version and its pinned decoder revision, stop API/control/receiver/feeders, preserve the old `/opt/airnode` and `/usr/local/bin/readsb`, then install the new source release with `sudo bash scripts/install.sh`. Reboot and check service/data health. Config and auth state are preserved by the installer. This MVP has no schema migration framework: only upgrade after reviewing schema compatibility. For recovery restore the old code/decoder and matching backup while services are stopped, reload systemd, and restart. Rollback is manual, not transactional OTA. Use a spare SD card for first production trials.

## Backups and recovery

Stop `airnode-api` briefly before copying SQLite state. Back up `/etc/airnode`, `/var/lib/airnode` and any custom network/SSH configuration to private storage. Backups contain password hashes and TLS private keys: protect them. Do not distribute a backup as an image.

If the owner password is lost, use a trusted local administrator console. Stop the API, archive `/var/lib/airnode/auth.db` into a root-only recovery directory, create a new private `/var/lib/airnode/setup-token` owned by airnode with mode 0600, and restart the API. Claim a new owner account. Removing the old auth database invalidates sessions; configuration is unchanged. This recovery path requires local root, not a web endpoint.

Hostname changes update OS identity and mDNS, but the self-signed certificate retains the original SAN. Prefer a certificate provisioned for your chosen name, or regenerate it locally with the new name and restart nginx. The IPv4 address can change under DHCP; reserve a lease on your router if desired.

## Network settings

Use NetworkManager from the local console (`nmtui`) for Wi-Fi/static addressing after initial Imager provisioning. Changes can disconnect remote management. The MVP exposes read-only network details and hostname changes; remote transactional IP editing with automatic rollback is planned. Never forward the owner API or unauthenticated raw feeds from your router to the internet. For remote access, use a properly configured private VPN.

## Storage

Aircraft output is in `/run` and disappears at reboot. Authentication/configuration are small persistent files. Journals follow the OS defaults; set a bounded `SystemMaxUse`/`RuntimeMaxUse` in journald for your SD card size. No unbounded aircraft history is enabled. Keep free space for APT upgrades.

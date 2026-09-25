# Architecture

```mermaid
flowchart LR
  SDR[USB RTL-SDR] --> R[readsb / airnode-radio]
  R --> J[/run/airnode-readsb aircraft.json]
  R --> B[Loopback Beast :30005]
  B --> F[Optional feeder instances]
  F --> C[User-selected collectors]
  J --> API[AirNode API / airnode user]
  Browser[LAN browser] --> TLS[nginx HTTPS :443]
  TLS --> API
  API --> IPC[Restricted Unix socket broker / root]
  IPC --> Units[Allowlisted systemd services]
  IPC --> Config[/etc/airnode/config.json]
```

**Decode plane:** readsb is a separate executable, not linked into AirNode. It owns the USB SDR and emits aircraft JSON once per second into a runtime directory on tmpfs. No high-volume aircraft history is written to the SD card. RTL-SDR is the initial supported hardware family; UAT, remote input and non-RTL devices need dedicated adapters.

**Control plane:** Python 3.11+ standard library, ThreadingHTTPServer behind nginx, SQLite authentication and an allowlisted Unix socket broker. There is no package registry dependency for the API. The API listens on `127.0.0.1:8080` and runs as an unprivileged user; nginx owns LAN HTTP/HTTPS. Keep nginx enabled in production: direct HTTP is a loopback-only service, not a supported LAN deployment. systemd restarts crashed processes.

**Privileges:** configuration belongs to `root:airnode` mode 0640. The API can read it but only the root broker can write it. Receiver and feeder processes run as `airnode-radio`, distinct from the API user. Socket permissions allow the group to connect, but Linux SO_PEERCRED additionally requires the exact API UID. A compromised radio process cannot invoke control actions merely by joining the group. The broker only accepts fixed operations, known service names, bounded hostname/feeder values and validated configuration. No request text reaches a shell. The broker remains security-sensitive and should receive review before public release.

**Storage:** `/etc/airnode/config.json` is atomically replaced; `/var/lib/airnode/auth.db` stores one owner, hashed session tokens, CSRF values and login throttles. `/var/lib/airnode/setup-token` is private and deleted on setup. `/etc/airnode/tls` contains a per-device certificate/key generated on first boot. `/run/airnode-readsb` and `/run/airnode-control` are transient. `journalctl` supplies bounded service logs; OS journal retention should be capped for long-lived SD deployments.

**Settings lifecycle:** full configuration is validated in the API and broker. Saving restarts readsb, then reconciles feeder enablement. A synchronous systemctl error triggers an attempted config and unit rollback. A process can fail after systemctl returns; the dashboard reports that failure rather than claiming reception is guaranteed. Stop/start controls affect current process state; feeder enable/disable in configuration controls persistence across boot. The receiver is enabled by default and a manual stop ends at reboot.

**Feed plane:** Beast :30005 and SBS :30003 bind loopback by default. The LAN-output setting binds them to all IPv4 interfaces with no protocol-level authentication. Users must explicitly opt in. Optional feeder instances forward the unmodified Beast stream to configured collectors with reconnect/backpressure timeouts. A running relay can be retrying; its journal is the authoritative connection diagnostic. DNS/collector IPs are administrator-selected, not untrusted public input.

**UI:** static first-party files, no remote scripts/fonts, five-second authenticated API polling. Stale aircraft (more than 15 seconds since readsb's JSON timestamp) are not displayed as live. Aircraft/position freshness uses `seen`/`seen_pos`. Callsigns and receiver-controlled strings are escaped. Position plotting uses great-circle distance and bearing; it is a 200 NM radar rather than a navigational map. OpenStreetMap links are optional user navigation; no tiles load automatically.

The MVP uses single-owner administration. TLS trust provisioning, fleet management, scoped API tokens, transactional network edits and signed app-release updates are separate release milestones.

## Aggregator extension (0.2)

The dedicated Aggregators page uses a root-only store separate from receiver config. Three network-only readsb instances consume the loopback Beast stream; PiAware and FR24 use their installed native services. The owner must opt into each provider. No AirNode cloud service is involved. See [AGGREGATORS.md](AGGREGATORS.md) for status semantics, credential handling, native client prerequisites and scope.

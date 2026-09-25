# API v0.3

All routes are same-origin under `/api`. JSON bodies only, up to 32 KiB. No CORS. Errors use `{"error":"description"}` with an appropriate HTTP status. Sessions use an HttpOnly, SameSite=Strict cookie, Secure in production, and an eight-hour fixed expiry. Every authenticated POST also requires the `X-CSRF-Token` returned by setup/login/session. Never place session tokens in query strings.

| Method / route | Auth | Purpose |
| --- | --- | --- |
| GET `/health` | Public | API liveness and version; does not prove RF reception |
| GET `/session` | Optional | configured/authenticated flags, current CSRF token, demo flag |
| POST `/setup` | Pairing token | `{token,password}`; exactly one owner |
| POST `/login` | Password | `{password}`; creates cookie and returns CSRF |
| POST `/logout` | Session + CSRF | Empty object; invalidates current session |
| POST `/password` | Session + CSRF + current password | `{current,password}`; invalidates all sessions |
| GET `/status` | Session | Decoder/service/USB/system/network health and aircraft counters |
| GET `/aircraft` | Session | readsb-compatible aircraft JSON plus `stale`, `age`, `demo` |
| GET `/config` | Session | Entire station configuration |
| POST `/config` | Session + CSRF | Validate, atomically save, restart receiver and reconcile feeders |
| POST `/service` | Session + CSRF | `{unit,action}`; start/stop/restart managed unit |
| GET `/logs?unit=...` | Session | Last 120 lines, max 24,000 characters |
| POST `/hostname` | Session + CSRF | `{hostname}`; changes LAN identity |
| POST `/update` | Session + CSRF + password | `{password}`; asynchronously runs OS APT upgrade |
| POST `/power` | Session + CSRF + password | `{action:"reboot" or "poweroff",password}`; schedule in one minute |

Managed unit keys are `airnode-receiver` and configured `airnode-feeder@<id>` instances. Logs also accept `airnode-update`. Arbitrary services, executable paths and commands are rejected. Mutating routes are POST only.

Default config:

```json
{
  "name": "AirNode",
  "receiver": {
    "device": "0", "gain": "auto", "ppm": 0,
    "latitude": null, "longitude": null, "lan_output": false
  },
  "feeders": []
}
```

A feed object is `{"id":"my-collector","host":"collector.example.org","port":30004,"enabled":false}`. Maximum eight; unique lowercase alphanumeric/hyphen IDs. Hosts are DNS names or IPv4; IPv6 literals are not supported by this UI schema yet. Coordinates must both be null or both finite and in range. Gain accepts `"auto"` or a numeric value 0–58 dB; the SDR driver determines supported physical gain steps.

Machine clients can authenticate using a cookie jar and session CSRF token. Independent long-lived API keys are not yet implemented. Do not expose this owner API directly to the internet.

## Aggregators

`GET /api/aggregators` returns the offline provider catalog with authenticated local settings, client installation and service/connection state. FR24 secrets are never returned.

`POST /api/aggregators/config` accepts `{provider, enabled, credential?, consent?}`. Valid IDs are `adsblol`, `airplaneslive`, `adsbexchange`, `flightaware`, `flightradar24`. Enabling requires boolean `consent: true` plus an installed client on production. Blank credentials preserve saved values; readsb-provider UUIDs are generated locally when absent. State persists separately from `/api/config`.

`POST /api/aggregators/action` accepts `{provider, action}` where action is `restart`, `logs`, `install`, `update`, `auto-on`, `auto-off`, or `install-logs`. Disabled providers cannot restart through this endpoint. Logs are redacted. All three endpoints require owner authentication; POST also requires CSRF and passes the origin check. Install/update actions enqueue allowlisted systemd jobs and return immediately. Software state is polled from GET `/api/aggregators` in each provider’s `software` object (`busy`, `result`, `automatic`, `version`). Daily update timers persist across reboot. No API accepts package names, executable paths or download URLs. No call creates provider accounts or contacts provider status APIs.

## Wi-Fi and AirNode releases

Authenticated GET `/api/wifi` returns radio/uplink/hotspot state and cached network names; it never returns Wi-Fi passwords. POST `/api/wifi/connect` accepts `{ssid,password,country}` with owner session, CSRF and same-origin checks. It queues the root Wi-Fi worker and returns before changing radios. Only personal WPA networks are supported.

Authenticated GET `/api/releases` returns installed version, stable/beta channel, the fixed GitHub repository and last job result. POST `/api/releases/action` accepts `{action:"check"}`, `{action:"channel",channel:"stable"|"beta"}`, or `{action:"install",password}`. Installing requires owner-password confirmation. All mutations require CSRF. The root worker downloads only allowlisted GitHub assets and verifies the signed manifest/checksum against the per-install trusted public key.

Production units omit both development flags. `--local-preview` shows real empty/stale receiver state without a Pi and refuses hardware/software mutations; `--demo` is an explicit test-only simulator.

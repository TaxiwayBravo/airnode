# Validation record

Development host: Windows, Python 3.14.5, Node.js 24.15.0. Production target: Python 3.11+ on Debian/Raspberry Pi OS arm64. Date: 2026-09-20.

## Executed successfully

- 29 Python unit/API tests via `python -m unittest discover -s tests -q`.
- Python module compilation and JavaScript syntax check.
- Bash syntax checks of every installer/build/diagnostic script using Git Bash.
- Live browser demo login and session restoration after reload.
- Overview updates showing 18 synthetic aircraft and sampled message rate.
- Receiver stop hides live aircraft and changes health to attention; start restores reception.
- Receiver settings and USB inventory screen loads.
- Journal screen displays clearly identified demo logs.
- Callsign search filters to the expected single aircraft; authenticated JSON and per-aircraft map links are present.
- Desktop (1440 px) and mobile (390 px) viewport inspection; mobile document width stays within viewport. No browser errors/warnings observed during tested flows.

The tests cover: configuration bounds/unknown keys, nonfinite values, argument injection attempts, default loopback outputs, atomic config persistence, password verification, duplicate setup rejection, hashed/expired/revoked sessions, password rotation, persistent throttling, authenticated data access, CSRF/origin rejection, POST-only system mutations, asset security headers, path traversal, invalid config preservation, power reauthentication, demo stop/start, consumed setup tokens, missing/corrupt/stale receiver files, broker unit/action/hostname allowlists, fixed argument vectors, delayed power actions and feeder reconciliation.

Testing uncovered and fixed a SQLite connection lifetime leak and a Windows connection-reset edge case when rejecting cross-origin POSTs before consuming their bounded body. The final suite passes.

## Not executed on this host

ShellCheck is configured in Linux CI but was not available locally. CI workflow has not run on a remote repository. Real systemd/nginx/udev/NetworkManager operations, readsb compilation, Unix socket peer-credential checks, Linux service sandbox behavior, TLS first-boot generation, APT upgrades, disk-image mounting/building, SD flashing and Pi boot/radio reception are not verified by the Windows demo. Broker unit tests mock system commands and do not replace integration testing.

## Hardware acceptance suite

Before release, record the exact OS image and readsb revision and pass these cases on Pi 4 and Pi 5:

1. Build from a verified pristine base and compare output checksum; flash using Imager.
2. Confirm DHCP, `.local` discovery, boot filesystem expansion, private per-device TLS identity and absence of shared credentials.
3. Pair from an independent LAN client using a per-device token; reject wrong token/password; verify Secure cookie and CSRF enforcement through nginx.
4. Decode a supported RTL-SDR using non-root radio user; verify healthy data timestamps and actual aircraft counts.
5. Unplug SDR and stop receiver; show stale/unavailable data within 15 seconds; reconnect/restart recovers.
6. Save coordinates/gain/PPM and verify actual readsb invocation, config ownership and reboot persistence.
7. Connect an operator-controlled Beast listener; enable/disable/remove feeds; verify byte delivery, reconnect and boot behavior. Never use an unrelated public collector for tests.
8. Verify raw outputs are loopback-only by default; opt-in exposes only intended ports. Incoming Beast/raw decoder ports stay disabled.
9. Try broker requests from the radio UID and reject them; unknown units/actions and malformed config must not execute commands.
10. Inspect logs, change hostname, apply a controlled OS update, reboot and shutdown; verify recovery with local console access.
11. Run 24–72 hours, including power/USB/network interruptions; check memory, temperature, disk/journal growth and session behavior.
12. Review source/license artifacts and package manifest before publishing.

## Aggregators update — 2026-09-21

The v0.2 suite passes 60 tests (including API security regressions on a separate aggregator test server). New coverage includes provider allowlists, sharing consent, identity generation/persistence, invalid credentials, secret redaction, missing-client rejection, native configuration merging, failed-service rollback, independent service state, and correct process/port matching for upstream TCP status. Python compilation and JavaScript syntax checks pass.

Browser checks verified all five cards, a simulated ADSB.lol setup with explicit consent, save/enable and disable, and mobile layout at 390 px with no page overflow. Sharing was left disabled. No real provider was contacted by a feeder during testing. The preview is simulated and cannot verify native client installation or acceptance by aggregators. Those remain Pi hardware integration gates.

## Software maintenance update — 2026-09-22

76 unit/API tests pass, including new checks for fixed provider/job allowlists, asynchronous dispatch, timer control, missing-client scheduling rejection, software job state/version reporting, bootstrap digest mismatch and insecure redirect rejection, secret redaction, preserving disabled feeds, stopping enabled feeds throughout package operations, failed-install behavior, and authenticated/CSRF-protected demo software actions. Tests mock native commands; they do not run APT or systemd.

Before release on both Pi models and each supported OS: test first install, repeated install, signed package upgrade, daily timer/reboot catch-up, offline repository, bad signature/bootstrap digest, concurrent OS update, power interruption/recovery, preservation of FR24 key mode/group, diversion of vendor cron updates, service gate enforcement, absence of extra SDR processes, and actual provider reception after explicit enablement. Verify FR24's packaged post-install hooks and PiAware's service dependencies for each approved package release. No native package install or update has been executed on this Windows host.

The updated browser preview was checked for simulated FlightAware installation and daily-update enablement, with sharing left off. The narrow layout displays the software controls without horizontal clipping. Python compilation, JavaScript syntax and all Bash script syntax checks pass.

## Desktop and LAN deployment update

80 tests pass, including observed-address formatting, IPv6 browser URLs, filtering inactive/loopback/container addresses, malformed network input, and keeping demo addresses separate from real Pi addresses. JavaScript and every Bash script pass syntax checks. Browser DOM layout checks at 3840 and 1920 px confirm the dashboard reaches the right edge without horizontal document overflow; the 1920 px aggregator view uses three columns. Temporary viewport overrides were reset. The production network profile, hostname initialization, deployment checker and second-device connectivity still require execution on a Raspberry Pi.

# Security model

AirNode is a single-owner, trusted-LAN appliance MVP. It has not undergone an independent security audit. The privileged broker and update path are the highest-value review surfaces.

Implemented controls:

- No default owner credential. First owner must possess the per-device pairing token. No setup secret is sent by public APIs or logged by production services.
- scrypt password hashing with random salts; 12–128 character passwords; constant-time comparisons.
- Random session tokens stored only as hashes, fixed eight-hour expiry, session invalidation on password change/logout. Secure, HttpOnly, SameSite=Strict cookies in production.
- Persistent eight-attempt/five-minute per-client setup/login throttling. nginx overwrites the client-IP header; the API binds loopback. This is a small-appliance control, not a distributed denial-of-service defense.
- CSRF tokens on authenticated writes, same-origin check for browser POSTs, JSON-only bounded bodies, no CORS and no GET mutations.
- First-party-only CSP, frame embedding denied, output escaping, no external scripts/fonts or default map requests.
- Unprivileged API and radio processes; root-owned code/config, systemd restrictions, peer-UID-checked local broker.
- Fixed executable argument lists without a shell; service/action allowlists; validated hostnames and configuration.
- Default loopback raw feeds; network sharing is explicit. API aircraft JSON requires authentication.
- Unique TLS identity generated on first boot. The initial self-signed certificate needs out-of-band fingerprint verification or replacement with a trusted certificate.

Limits and assumptions:

- Root/local administrator access can reset the owner; this is required for appliance recovery. Physical access to an unencrypted SD card exposes persistent state.
- Authenticated owner access intentionally permits service changes, data sharing, OS updates and scheduled power operations. Updates and power actions additionally require password confirmation. Hostname/settings changes can disrupt connectivity.
- A compromised API user can invoke the broker's allowed operations; the socket boundary restricts arbitrary execution, not the authority the owner API intentionally holds. The receiver UID is explicitly rejected at the broker.
- An administrator may direct feeders to arbitrary reachable DNS/IPv4 targets. No public unauthenticated feeder registration is supported. Feed streams are plaintext TCP; transport/security requirements depend on the destination.
- The API's standard-library HTTP server is protected by nginx's connection/body handling. Do not bind it to a public interface. Add firewall/VPN policy appropriate to the LAN.
- Application updates are reviewed source installations; no signed OTA or A/B rollback is claimed. APT validates its configured package repositories, which an administrator can change.
- Pairing tokens on FAT boot storage are only as private as the SD card and setup process. They are removed after consumption but flash deletion is not secure erasure. Use a fresh random token for each device and claim it promptly.
- TLS SANs cover the initial hostname and `.local` name, not dynamic IP addresses. Install trusted LAN certificates if seamless IP-based browser trust is required.

Before broader deployment add security review, release signing, bounded global connection limits, audit history, scoped API credentials and a recoverable network configuration workflow.

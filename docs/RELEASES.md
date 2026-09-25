# AirNode stable and beta releases

The appliance checks **https://github.com/TaxiwayBravo/airnode**. It selects a newer semantic version with all three release assets; stable excludes prereleases, while beta allows stable releases and `-beta.N` versions. It never silently downgrades. Selecting stable while running a newer beta waits for a newer stable release.

The dashboard offers channel selection, **Check GitHub**, and password-confirmed **Install AirNode update**. Beta application installation is manual; there is no unattended application auto-update. Daily aggregator package updates and OS updates remain separate operations. No private GitHub token is installed on user devices; the release repository and downloadable assets must remain public.

## Trust and packaging

Assets are `airnode-update.tar.gz`, `airnode-release.json`, and `airnode-release.sig`. The manifest identifies the repository, version, pinned readsb commit and archive SHA-256. It is signed with the project release private key (RSA/SHA-256). The Pi verifies against `/etc/airnode/update-public.pem`, copied from the source during the initial install only; updates do not silently replace this trusted key. All download redirects require HTTPS and GitHub-controlled hosts. Changing signing keys requires a deliberate trust migration.

Keep the private signing key outside the repository. The prepared development key is held separately under the local workspace's `work/release-signing/`; it is not in the source ZIP or release archive. Back it up securely. Do not regenerate the key for each release. Only the public key belongs in `deploy/update-public.pem`.

## Connect and publish

1. Authenticate GitHub CLI with the TaxiwayBravo account and connect the local source repository to `https://github.com/TaxiwayBravo/airnode.git` (the remote is already configured in this workspace).
2. Create a GitHub Actions environment named `releases`, restrict it to release tags/maintainers, and add the private PEM as environment secret **AIRNODE_RELEASE_SIGNING_KEY**. Configure required human review for that environment if available. Never paste the key into an issue, commit or workflow file.
3. Push reviewed source to `main`. CI runs Python/API tests, JavaScript/Bash syntax checks and ShellCheck.
4. Update `airnode/__init__.py` to the desired version and tag the exact commit, for example `v0.4.0-beta.1`. Push the tag. `.github/workflows/release.yml` verifies the version/tag, tests, packages, signs and publishes; beta tags are GitHub prereleases.
5. Verify the release assets and test update/recovery on a spare Pi before promoting a stable release. A signed package authenticates its publisher; it is not proof of hardware qualification.

Local packaging: `python scripts/package-release.py dist v0.4.0-beta.1`. Sign `dist/airnode-release.json` with the private key using `openssl dgst -sha256 -sign PRIVATE_KEY -out dist/airnode-release.sig dist/airnode-release.json`. Verify it with `openssl dgst -sha256 -verify deploy/update-public.pem -signature dist/airnode-release.sig dist/airnode-release.json`. The prepared workflow performs these steps automatically once its secret and GitHub authentication are configured.

## Installation and recovery scope

The Pi serializes update jobs against package maintenance, downloads and verifies the manifest/archive, rejects unsafe archive entries, checks free space and Python syntax, and stages the application under `/opt`. Settings, credentials and NetworkManager profiles live outside the application directory and are preserved. It backs up the prior application and managed systemd units, stops API/control/Wi-Fi briefly, switches the application, restarts, and checks the new API version/health.

A failed health check restores the previous application. A persistent transaction journal plus the recovery helper outside `/opt/airnode` handles interruption on the next boot. Old and failed application directories are retained under `/opt/airnode-backup-*` / `/opt/airnode-failed-*` for inspection and must be pruned deliberately by an administrator when no longer needed. This is application rollback, not whole-OS A/B recovery. Future releases must keep settings backward-compatible; database/config migrations and changes to the pinned readsb runtime are not supported by this updater. Such releases require the full installer and a backup.

At preparation time the GitHub repository was reachable publicly, but the saved GitHub CLI sign-in was invalid. No push, repository secret configuration, tag publication or GitHub Actions execution has been completed from this environment. Those are explicit remaining deployment steps, alongside real Pi hotspot/update acceptance tests.

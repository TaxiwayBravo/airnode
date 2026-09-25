# Image build and first boot

The MVP customizes an existing Raspberry Pi OS Lite arm64 image. This preserves Raspberry Pi firmware, Pi 4/5 kernel support, partition layout and first-boot disk expansion. It is a practical image pipeline; it is not yet bit-for-bit reproducible because APT repository contents change over time.

## Build host

If you do not have Linux, the repository includes a GitHub Actions workflow at `.github/workflows/image.yml`. After the repository is pushed, open **Actions → Build Raspberry Pi image → Run workflow**, provide the direct Raspberry Pi OS Lite 64-bit `.img.xz` URL and the SHA-256 of its decompressed `.img`, then download the `airnode-image` artifact. This uses a native arm64 GitHub runner and produces the same verified image artifacts described below. The repository must be public or have Actions enabled for the account, and the base URL/checksum must come from Raspberry Pi's official download page.

Use a dedicated native arm64 Debian/Raspberry Pi OS host (Pi 4/5 with sufficient cooling/RAM, or an arm64 Linux VM). Allow at least 15 GB of free disk and a reliable network. Root is needed for loop devices, mounts and chroot. Windows and x86 Linux are not supported build hosts for this initial script. A future pipeline can add tested qemu/binfmt integration.

Install host tools:

```sh
sudo apt-get update
sudo apt-get install -y parted e2fsprogs util-linux xz-utils coreutils udev
```

Obtain an official [Raspberry Pi OS Lite 64-bit image](https://www.raspberrypi.com/software/operating-systems/). Verify the downloaded compressed file against the official published checksum, decompress it, then record the SHA-256 of the resulting raw `.img`. The builder's checksum argument applies to the **raw image**, not the compressed download. Use a pristine, never-booted base; do not use an image copied from a provisioned Pi.

```sh
xz -dk raspios-lite-arm64.img.xz
sha256sum raspios-lite-arm64.img
sudo bash scripts/build-image.sh raspios-lite-arm64.img RAW_IMAGE_SHA256 build/airnode-0.4.0-beta.1.img
```

The build fails unless the input is a regular file, output is a new `.img`, checksum matches and host is arm64. It copies the base, adds 3 GiB, grows partition 2/ext4, mounts the standard boot/root layout and runs the installer inside chroot. It blocks package auto-starts, restores DNS setup, sets default hostname, clears machine/SSH identity, and leaves AirNode TLS/owner provisioning for first boot. It never passes a physical disk as output. The cleanup trap releases mounts and loop devices on ordinary exit/failure; if a host crash interrupts the build, inspect remaining mounts before manual cleanup. Delete a failed output before retrying with the same filename.

Artifacts:

- `airnode-0.4.0-beta.1.img.xz`: flashable compressed image.
- `.img.xz.sha256`: checksum for the compressed image.
- `.img.manifest`: AirNode version, architecture and base checksum.
- `.img.readsb.commit`: exact decoder source revision.
- Inside the image: installed-package manifest and matching readsb source archive under `/usr/local/share/airnode/`.

Builds use [readsb commit d9a4c62655490e70d07704e207738bb9c6cffde1](https://github.com/wiedehopf/readsb/commit/d9a4c62655490e70d07704e207738bb9c6cffde1). Update the lock only after reviewing and validating a candidate. There is no `curl | sh` remote installer and no automatic tracking of a moving branch.

## Flash and provision

1. Use Raspberry Pi Imager's custom-image option to flash the compressed artifact. Configure your own administrator, SSH key if needed, hostname and network where the Imager/base-image combination supports customization. If custom-image OS customization is unavailable, use Ethernet and local console provisioning. AirNode does not create a shared OS user/password.
2. Optionally write `airnode-setup-token.txt` onto the FAT boot partition with a freshly generated private token (e.g. `openssl rand -hex 24`). Do this per device after flashing. Do not put a token in a distributable image.
3. Attach Ethernet, antenna and SDR, then power the Pi. DHCP and mDNS provide IP discovery. Wi-Fi needs the correct regulatory country and credentials through the underlying OS provisioning flow.
4. First boot creates a unique TLS key/certificate and consumes or creates the pairing token. The API and nginx start after provisioning. From another device open `https://airnode.local/` or the DHCP address. `.local` resolution depends on client/LAN mDNS support; use the router lease table if necessary.
5. Verify certificate trust, claim the owner account, set receiver coordinates, and inspect receiver logs/aircraft activity.

This repository has not produced a hardware-tested `.img.xz` in the development session. First-boot compatibility with the exact chosen Bookworm/Trixie base is a release gate, not an asserted result. See [VALIDATION.md](VALIDATION.md).

## Image release checklist

Test both Pi 4 and Pi 5 with the intended base image. Keep a clean source manifest, record base URL/checksum and APT package versions, scan for credentials and unique device identifiers, verify checksum after download, include license/source materials, and only publish after the hardware acceptance suite passes. Subsequent hardening should snapshot APT repositories and sign release manifests.


# Put AirNode on a microSD card

The current AirNode package is the source and installer bundle. A flashable `.img.xz` is produced from a verified Raspberry Pi OS Lite 64-bit base on a native arm64 Linux build host; this Windows computer should not write the image builder directly to a physical disk.

## Easiest route: Raspberry Pi Imager

1. Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Insert a good-quality 16 GB or larger microSD card.
3. Choose **Use custom** and select the AirNode `.img.xz` image.
4. Select the microSD card and click **Write**. Imager erases the selected card.
5. Let Imager verify the write, then eject the card.

You can leave Imager's operating-system customisation screen alone. Do not create an extra AirNode user or shared AirNode password there; AirNode handles its own owner pairing on first boot.

For the headless setup network, run `python scripts/prepare-sd.py E:/ GB` while the card's boot partition is mounted as `E:` (replace `E:/` and `GB`). This is a one-time step that creates the private Wi-Fi name, password and pairing token for that card. Keep the generated `AIRNODE-SETUP.txt` private.

Put the card in the Pi, connect the RTL-SDR and antenna, and power it on. From a phone or laptop, join the printed `AirNode-Setup-XXXXXX` Wi-Fi network and open `https://10.42.0.1/` to claim the station and configure home Wi-Fi. No monitor, keyboard or Ethernet cable is required.

If you already configured home Wi-Fi in Imager, the Pi should join it directly. Open `https://airnode.local/` or find the DHCP address in your router. The first certificate is self-signed; verify its fingerprint before accepting it.

## If you only have the ZIP

The ZIP is not itself a bootable image. Use it to install on a fresh Raspberry Pi OS Lite 64-bit card:

```sh
scp -r AirNode pi@airnode.local:/tmp/
ssh pi@airnode.local
cd /tmp/AirNode
sudo bash scripts/install.sh
sudo reboot
```

The installer builds the pinned readsb decoder and installs AirNode services. This route requires temporary network access and an existing administrator account on the Pi.

## Important safety checks

- Confirm the card letter/device before writing; Imager permanently erases it.
- Use a verified AirNode image checksum and the matching release manifest.
- Never distribute a card after first boot: it contains a device certificate and setup identity.
- Do not put owner passwords, Wi-Fi passwords or pairing tokens into the repository or release archive.
- Hardware acceptance is still required on both Pi 4 and Pi 5 before calling an image production-ready.

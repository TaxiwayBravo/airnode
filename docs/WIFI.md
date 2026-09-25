# Wi-Fi setup and recovery

AirNode uses the Pi's built-in Wi-Fi through NetworkManager. A normal Wi-Fi or Ethernet connection takes priority. After 90 seconds without either, it starts an **open, local-only setup network** named **AirNode-Setup-XXXXXX**, with a setup page at **https://10.42.0.1/**. The network has no internet route; first setup asks only for a new owner password. A working Ethernet connection keeps the hotspot off.

## Before the first boot

1. Flash the AirNode image (or provision Raspberry Pi OS for the source installation). Set your actual Wi-Fi country in Raspberry Pi Imager. Regulatory restrictions can prevent wireless/AP operation until this is set.
2. For an AirNode image, while the flashed boot partition is attached to your computer, run `python scripts/prepare-sd.py E:/ GB`, replacing `E:/` with that partition and `GB` with your country. It generates private per-device setup files; it refuses to overwrite existing ones.
3. Save the network name, password and pairing token from `AIRNODE-SETUP.txt` privately, then eject the card and boot the Pi. These files are for one device only and must never be included in a distributed image or Git repository.
4. If you did not prepare the files, first boot creates them. Retrieve `AIRNODE-SETUP.txt` from the boot partition using physical access, or read it with your local administrator account. A source installation also creates the file. If already paired, use the existing owner password.

## Connect from your computer or phone

No monitor, keyboard or Ethernet cable is required for first setup: power the Pi, wait for the setup network to appear, and use a phone or laptop to complete pairing. Keep the printed setup details with the device; AirNode never displays the hotspot password through its authenticated API.

Join the named setup Wi-Fi with no password. Stay connected even if your device reports **no internet**. Open `https://10.42.0.1/` or the Pi's `.local` hostname; automatic captive-portal pop-ups are not implemented. Verify/trust the Pi's per-device certificate as described in [deployment](DEPLOYMENT.md). Choose an owner password, then open **System → Wi-Fi connection**.

Enter the exact home SSID, its WPA2/WPA3 personal password and your two-letter country code. The network list uses NetworkManager's cached scan results; an unseen/hidden SSID can be entered manually. Enterprise/802.1X, open networks and Wi-Fi 6-only authentication modes are outside this MVP; use Ethernet or local NetworkManager provisioning for those networks.

The Pi saves credentials privately in NetworkManager keyfiles, never command-line arguments or API responses. After accepting the request it waits five seconds, switches its radio, and waits up to 45 seconds for activation and DHCP. A failed attempt removes only the new candidate and restores the setup hotspot; previously saved AirNode profiles remain. A successful attempt retains the new home profile, removes old AirNode-managed home profiles, and leaves unrelated administrator/Imager profiles intact. Country is retained for future hotspot recovery.

The browser disconnects during a successful switch. Rejoin your home Wi-Fi and open `https://airnode.local/` (or your chosen hostname). The router assigns the Pi a new IP; the old hotspot address no longer applies. Home Wi-Fi profiles reconnect through NetworkManager after reboot. If the router is unavailable later, the recovery hotspot returns; submit the home-network details again when it is ready. This MVP does not periodically drop an active setup session to retry home Wi-Fi.

`AIRNODE-SETUP.txt` is removed after successful first owner setup where the root broker is reachable. Retain your private copy of hotspot credentials for recovery. Root administrators can inspect `/etc/airnode/hotspot.json`; the authenticated web API deliberately does not disclose its password. The boot partition cannot enforce Unix permissions on all filesystems, so keep the physical card and pre-boot files private.

## Hardware acceptance still required

Test Pi 4 and Pi 5 with the deployed OS/firmware: radio country and rfkill, AP capability, phone/laptop joining, DHCP at 10.42.0.1, HTTPS ownership setup, correct and incorrect home passwords, hidden SSIDs, reboot, lost router, Ethernet present/absent and no credential leakage in process lists or journals. Desktop unit tests cannot verify radio firmware, host firewall rules or DHCP behavior. The setup subnet must not overlap another active network on the Pi.

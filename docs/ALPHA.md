# AirNode alpha test checklist

This alpha is ready for first hardware testing, not general distribution.

Use the GitHub image workflow to build the image, flash it to a spare 16 GB or larger card, and test on a Pi 4 and Pi 5 with a supported RTL-SDR and antenna.

Acceptance checks:

- First boot creates the TLS identity and shows first-boot progress before pairing.
- Ethernet receives a DHCP address and the dashboard opens from another device.
- With Ethernet disconnected, the private AirNode setup Wi-Fi appears and `https://10.42.0.1/` opens from a phone or laptop.
- Pairing accepts the private token and owner password, then removes the token.
- Home Wi-Fi can be saved, a failed join restores the setup hotspot, and a successful join exposes the hostname/IP.
- Receiver status is honest when the SDR is absent and shows live aircraft only after readsb receives data.
- Aggregator installation and update actions remain disabled until explicitly enabled.
- A signed GitHub AirNode release can be checked and rolled back after an interrupted update.
- Reboot, shutdown, logs, OS updates and password changes work from the dashboard.

Do not use the alpha on an important receiver or publish its generated setup files. Record the Pi model, OS image, SDR, network path and any failed step with the service log.

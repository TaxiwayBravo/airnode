# MVP boundaries and next release gates

This repository implements a working control-plane MVP and image build candidate. It should not be described as a tested production Raspberry Pi distribution yet.

## Required before first image release

1. Run the installer and image pipeline on native arm64; verify pinned readsb builds and its help/options match this integration.
2. Boot the image on Pi 4 and Pi 5 using the exact base release; test Imager customization, filesystem expansion and first-boot ordering.
3. Validate USB reception, permissions, reconnect after unplug/reboot and multi-day stability with real aircraft data.
4. Exercise HTTPS pairing, independent browser access, services, feeder reconnect, OS updates and power actions on hardware.
5. Review root broker, TLS/credential handling, default open ports and license/source distribution.

## Next product increments

- Extend the five local aggregator adapters with actual ingestion/bytes metrics, provider status APIs and MLAT. Validate the new automated PiAware/FR24 installer and scheduled updates on hardware.
- MLAT support with accurate surveyed station coordinates, UAT and additional SDR families.
- Geographic map with deliberate tile/data provider choice, offline assets and attribution.
- Hardware-test the Wi-Fi onboarding/hotspot recovery and add enterprise Wi-Fi/static IP editing.
- Hardware-test signed AirNode application updates and recovery; add readsb-runtime migrations and recovery partitions/A-B updates.
- Historical reception/range statistics with bounded retention, hardware undervoltage/throttling alerts and backup/export UI.
- Scoped API keys, multi-user roles, access audit and fleet provisioning.

No placeholder provider integration or fake production hardware status is presented as implemented. Demo mode is conspicuously identified and all its system actions are simulated.

# Third-party software and provenance

AirNode's original code is MIT licensed. A Linux image contains many independently licensed components; the MIT license does not replace their terms.

| Component | Integration / source |
| --- | --- |
| readsb | Separate executable built from https://github.com/wiedehopf/readsb at `deploy/readsb.commit`; upstream GPL license and individual file notices apply |
| librtlsdr and libusb | System libraries installed through Debian/Raspberry Pi repositories; retain package copyright/license material |
| Python, nginx, OpenSSL, Avahi, systemd, NetworkManager | OS packages; package-specific terms in `/usr/share/doc/<package>/copyright` |
| Raspberry Pi OS / Debian / Linux kernel / firmware | Unmodified upstream base plus AirNode configuration; mixed package licenses and firmware terms |
| OpenStreetMap | Optional external links only; no tiles, geographic datasets or map libraries are bundled |

The readsb builder preserves an exact source tarball, revision and upstream COPYING file under `/usr/local/share/airnode/third-party/`. [readsb's COPYING](https://github.com/wiedehopf/readsb/blob/dev/COPYING) contains the GPL text; consult the pinned tree's file headers for applicable version and notices. Do not strip these materials from a redistributed image. Provide corresponding source for included GPL components and any changes using a compliant distribution method; retaining only copyright text is not sufficient. Review obligations for the entire OS package set, not just readsb, before publishing an image.

No adsb.im UI, source, marks or assets were used. No tar1090 code/assets are bundled in this MVP. AirNode's dashboard and local radar are first-party code, using system fonts and browser canvas. The source link above is for attribution and build provenance, not an endorsement.

## Optional native aggregator clients

FlightAware PiAware and Flightradar24 fr24feed are optional locally installed clients, not binaries bundled in AirNode. Their original licenses/terms apply; obtain them through their official channels. AirNode can install and update these clients from official repositories on user request, writes validated integration settings, and controls their local services. Repository bootstraps are pinned by SHA-256; package downloads are verified by APT. They are not redistributed in this source archive. Provider names identify interoperability and do not imply endorsement.

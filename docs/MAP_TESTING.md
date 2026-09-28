# Map and Tar1090 testing

The map views can be tested without an SDR by generating a readsb-compatible
feed. On a Linux/QEMU test environment, run:

```sh
python3 scripts/simulate-readsb.py --directory /run/readsb
```

The generator writes moving aircraft atomically to `aircraft.json`, matching the
file Tar1090 and the Your Sky dashboard consume. This isolates map rendering and
Tar1090 backend failures from USB and radio hardware. Stop it with Ctrl-C before
testing the real receiver.

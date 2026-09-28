#!/usr/bin/env python3
"""Generate a moving readsb-compatible aircraft.json for map testing."""
import argparse, json, math, time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--directory', default='work/sim-readsb')
parser.add_argument('--interval', type=float, default=1.0)
args = parser.parse_args()
out = Path(args.directory); out.mkdir(parents=True, exist_ok=True)
started = time.time()
while True:
    now = time.time(); age = now - started
    aircraft = []
    for i, (hexid, flight) in enumerate((('400001','YSK101'),('400002','YSK202'),('400003','YSK303'))):
        angle = age / 55 + i * 2.1
        aircraft.append({'hex': hexid, 'flight': flight, 'lat': 51.5 + math.cos(angle) * (0.3 + i*.15),
                         'lon': -0.12 + math.sin(angle) * (0.5 + i*.2), 'alt_baro': 18000+i*4000,
                         'gs': 220+i*35, 'track': (angle*57.3+90)%360, 'seen': .2, 'seen_pos': .2,
                         'messages': 100+i*10, 'rssi': -12-i})
    tmp = out / 'aircraft.json.tmp'
    tmp.write_text(json.dumps({'now': now, 'messages': int(age*120), 'aircraft': aircraft})+'\n')
    tmp.replace(out / 'aircraft.json')
    time.sleep(args.interval)

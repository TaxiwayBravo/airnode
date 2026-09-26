"""Strict, shared configuration schema; never accept shell fragments."""
import copy
import json
import math
import os
import re
import tempfile
from pathlib import Path

DEFAULT = {"name": "AirNode", "receiver": {"device": "0", "gain": "auto", "ppm": 0,
    "latitude": None, "longitude": None, "lan_output": False}, "feeders": []}

def validate(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT):
        raise ValueError("Expected name, receiver and feeders")
    if not isinstance(value["name"], str) or not 1 <= len(value["name"].strip()) <= 48:
        raise ValueError("Station name must contain 1–48 characters")
    r = value["receiver"]
    if not isinstance(r, dict) or set(r) != set(DEFAULT["receiver"]):
        raise ValueError("Invalid receiver fields")
    if not isinstance(r["device"], str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", r["device"]):
        raise ValueError("SDR must be an index or alphanumeric serial")
    if r["gain"] != "auto":
        number(r["gain"], 0, 58, "gain")
    number(r["ppm"], -200, 200, "ppm")
    if (r["latitude"] is None) != (r["longitude"] is None):
        raise ValueError("Set both coordinates or neither")
    if r["latitude"] is not None:
        number(r["latitude"], -90, 90, "latitude")
        number(r["longitude"], -180, 180, "longitude")
    if type(r["lan_output"]) is not bool:
        raise ValueError("lan_output must be boolean")
    feeds = value["feeders"]
    if not isinstance(feeds, list) or len(feeds) > 8:
        raise ValueError("Maximum eight feeders")
    ids = set()
    for f in feeds:
        if not isinstance(f, dict) or set(f) != {"id", "host", "port", "enabled"}:
            raise ValueError("Invalid feeder fields")
        if not isinstance(f["id"], str) or not re.fullmatch(r"[a-z0-9-]{1,24}", f["id"]) or f["id"] in ids:
            raise ValueError("Feeder IDs must be unique lowercase names")
        ids.add(f["id"])
        if not isinstance(f["host"], str) or len(f["host"]) > 253 or not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", f["host"]):
            raise ValueError("Feeder host must be an IPv4 address or DNS name")
        if type(f["port"]) is not int or not 1 <= f["port"] <= 65535 or type(f["enabled"]) is not bool:
            raise ValueError("Invalid feeder port or enabled state")
    return copy.deepcopy(value)

def number(value, low, high, label):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be a number between {low} and {high}")

def read(path):
    return validate(json.loads(Path(path).read_text()))

def write(path, value):
    value = validate(value)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o640)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def receiver_args(config):
    r = validate(config)["receiver"]
    args = ["/usr/local/bin/readsb", "--device-type=rtlsdr", f"--device={r['device']}",
        f"--gain={r['gain']}", f"--ppm={r['ppm']}", "--net", "--quiet",
        "--write-json=/run/airnode-readsb", "--write-json-every=1", "--write-json-globe-index", "--json-location-accuracy=0",
        "--net-bind-address=" + ("0.0.0.0" if r["lan_output"] else "127.0.0.1"),
        "--net-bo-port=30005", "--net-sbs-port=30003", "--net-bi-port=0", "--net-ri-port=0", "--net-ro-port=0"]
    if r["latitude"] is not None:
        args += [f"--lat={r['latitude']}", f"--lon={r['longitude']}"]
    return args

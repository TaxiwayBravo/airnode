"""Provider catalog and local-only configuration. No requests to provider APIs."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

PROVIDERS = {
    "adsblol": {"name": "ADSB.lol", "mark": "lol", "kind": "readsb", "host": "feed.adsb.lol", "port": 30004,
        "description": "Contribute your local reception to ADSB.lol.",
        "setup_url": "https://www.adsb.lol/docs/get-started/", "status_url": "https://my.adsb.lol/", "credential_label": "Station UUID"},
    "airplaneslive": {"name": "airplanes.live", "mark": "AL", "kind": "readsb", "host": "feed.airplanes.live", "port": 30004,
        "description": "Share your station’s ADS-B reception with airplanes.live.",
        "setup_url": "https://airplanes.live/get-started/", "status_url": "https://airplanes.live/myfeed/", "credential_label": "Station UUID"},
    "adsbexchange": {"name": "ADS-B Exchange", "mark": "AX", "kind": "readsb", "host": "feed1.adsbexchange.com", "port": 30004,
        "description": "Send your received aircraft data to ADS-B Exchange.",
        "setup_url": "https://www.adsbexchange.com/how-to-feed/", "status_url": "https://www.adsbexchange.com/myip/", "credential_label": "Station UUID"},
    "flightaware": {"name": "FlightAware", "mark": "FA", "kind": "native", "binary": "/usr/bin/piaware", "unit": "piaware",
        "description": "Use the PiAware client on this Pi and claim your receiver with FlightAware.",
        "setup_url": "https://www.flightaware.com/adsb/piaware/install", "status_url": "https://www.flightaware.com/adsb/stats/",
        "claim_url": "https://www.flightaware.com/adsb/piaware/claim", "credential_label": "Existing feeder ID (optional)"},
    "flightradar24": {"name": "Flightradar24", "mark": "24", "kind": "native", "binary": "/usr/bin/fr24feed", "unit": "fr24feed",
        "description": "Connect the local FR24 client using your own receiver sharing key.",
        "setup_url": "https://www.flightradar24.com/share-your-data", "status_url": "https://www.flightradar24.com/account/data-sharing",
        "credential_label": "Sharing key"},
}

def provider(key):
    if not isinstance(key, str) or key not in PROVIDERS:
        raise ValueError("Unknown aggregator")
    return PROVIDERS[key]

def service(key):
    p = provider(key)
    return p.get("unit", "airnode-aggregator@" + key)

def load(path):
    path = Path(path)
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not set(value) <= set(PROVIDERS):
        raise ValueError("Invalid aggregator storage")
    for key, entry in value.items():
        validate_entry(key, entry)
    return value

def validate_entry(key, value):
    provider(key)
    if not isinstance(value, dict) or set(value) != {"enabled", "credential"} or type(value["enabled"]) is not bool:
        raise ValueError("Invalid aggregator settings")
    token = value["credential"]
    if not isinstance(token, str):
        raise ValueError("Invalid station identifier")
    if token:
        if key == "flightradar24":
            if not re.fullmatch(r"[a-fA-F0-9]{16}", token):
                raise ValueError("Flightradar24 sharing key must be 16 hexadecimal characters")
        else:
            try:
                parsed = uuid.UUID(token)
            except ValueError:
                raise ValueError("Station identifier must be a valid UUID") from None
            if str(parsed) != token.lower() or parsed.int == 0:
                raise ValueError("Station identifier must be a non-zero UUID")
    if value["enabled"] and not token and key != "flightaware":
        raise ValueError("Set a station identifier before enabling")
    return copy.deepcopy(value)

def updated(old, request):
    if not isinstance(request, dict) or set(request) - {"provider", "enabled", "credential", "consent"}:
        raise ValueError("Invalid aggregator request")
    key = request.get("provider")
    p = provider(key)
    enabled = request.get("enabled")
    if type(enabled) is not bool:
        raise ValueError("Enabled must be boolean")
    if enabled and request.get("consent") is not True:
        raise ValueError("Confirm sharing with this provider")
    entry = copy.deepcopy(old.get(key, {"enabled": False, "credential": ""}))
    supplied = request.get("credential", "")
    if not isinstance(supplied, str):
        raise ValueError("Invalid credential")
    # Blank means keep an existing key. Secrets are never sent back to the browser.
    if supplied:
        entry["credential"] = supplied.strip()
    if not entry["credential"] and p["kind"] == "readsb":
        entry["credential"] = str(uuid.uuid4())
    entry["enabled"] = enabled
    validate_entry(key, entry)
    result = copy.deepcopy(old)
    result[key] = entry
    return result

def atomic_text(path, text, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def save(path, value):
    for key, entry in value.items():
        validate_entry(key, entry)
    atomic_text(path, json.dumps(value, indent=2))

def public_settings(key, entry):
    return {"configured": entry is not None, "enabled": bool(entry and entry["enabled"]),
        "credential_set": bool(entry and entry["credential"]),
        "identifier": entry["credential"] if entry and key != "flightradar24" else ""}

def relay_args(key, entry):
    p = provider(key)
    validate_entry(key, entry)
    if p["kind"] != "readsb" or not entry["enabled"]:
        raise ValueError("Aggregator is not an enabled readsb feed")
    target = f"{p['host']},{p['port']},beast_reduce_plus_out"
    if key == "adsblol":
        target += ",in.adsb.lol,1337"
    if key == "adsbexchange":
        target += ",feed2.adsbexchange.com,64004"
    target += ",uuid=" + entry["credential"]
    return ["/usr/local/bin/readsb", "--net-only", "--quiet", "--net-heartbeat=60",
        "--net-bind-address=127.0.0.1", "--net-bi-port=0", "--net-bo-port=0", "--net-ri-port=0", "--net-ro-port=0", "--net-sbs-port=0",
        "--net-connector=127.0.0.1,30005,beast_in", "--net-connector=" + target,
        "--net-beast-reduce-interval=0.5", "--json-location-accuracy=0"]

def merge_settings(existing, values, ini=False):
    """Replace only managed keys, retaining unrelated provider configuration."""
    lines = []
    for line in existing.splitlines():
        stripped = line.strip()
        key = re.split(r"[=\s]", stripped, maxsplit=1)[0]
        if key not in values:
            lines.append(line)
    lines += [f'{key}="{value}"' if ini else f"{key} {value}" for key, value in values.items()]
    return "\n".join(lines) + "\n"

def native_config(key, entry, existing):
    validate_entry(key, entry)
    if key == "flightaware":
        values = {"receiver-type": "other", "receiver-host": "127.0.0.1", "receiver-port": "30005",
            "allow-auto-updates": "no", "allow-manual-updates": "no", "allow-mlat": "no", "mlat-results": "no"}
        if entry["credential"]:
            values["feeder-id"] = entry["credential"]
        return merge_settings(existing, values)
    if key == "flightradar24":
        return merge_settings(existing, {"receiver":"beast-tcp", "host":"127.0.0.1:30005", "fr24key":entry["credential"],
            "bs":"no", "raw":"no", "mlat":"no", "mlat-without-gps":"no", "bind-interface":"127.0.0.1", "logmode":"0"}, ini=True)
    raise ValueError("Not a native client")

def redact(text, settings):
    for entry in settings.values():
        if entry["credential"]:
            text = re.sub(re.escape(entry["credential"]), "[redacted]", text, flags=re.I)
    # Catch other IDs/keys emitted by native clients (including auto-generated PiAware ID).
    text = re.sub(r"\b[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}\b", "[station-id]", text)
    return re.sub(r"\b[a-fA-F0-9]{16}\b", "[key]", text)

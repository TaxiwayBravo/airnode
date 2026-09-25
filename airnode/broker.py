"""Root broker. Only fixed operations, unit allowlists, and validated config cross IPC."""
import json
import os
from pathlib import Path
import re
import socket
import socketserver
import struct
import subprocess
import threading
from .config import read, validate, write
from .aggregator_control import Manager
from .maintenance import exclusive
from . import wifi, releases

CONFIG = Path("/etc/airnode/config.json")
SOCKET = "/run/airnode-control/control.sock"
LOCK = threading.Lock()

def command(args, timeout=15, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise ValueError((result.stderr or result.stdout or "Command failed")[-2000:])
    return result.stdout.strip()

def units():
    return ["airnode-receiver"] + ["airnode-feeder@" + f["id"] for f in read(CONFIG)["feeders"]]

def unit(value):
    if value not in units():
        raise ValueError("Unknown managed service")
    return value + ".service"

def apply_config(value):
    import grp
    value = validate(value)
    old = read(CONFIG)
    # Only AirNode-owned paths are writable. Preserve group access for reader services.
    write(CONFIG, value)
    os.chown(CONFIG, 0, grp.getgrnam("airnode").gr_gid)
    try:
        command(["systemctl", "restart", "airnode-receiver.service"])
        reconcile(old, value)
    except Exception:
        write(CONFIG, old)
        os.chown(CONFIG, 0, grp.getgrnam("airnode").gr_gid)
        command(["systemctl", "restart", "airnode-receiver.service"], check=False)
        reconcile(value, old)
        raise
    return {"saved": True, "message": "Configuration applied; inspect receiver status for SDR availability."}

def reconcile(old, new):
    enabled = {f["id"] for f in new["feeders"] if f["enabled"]}
    for f in old["feeders"]:
        if f["id"] not in enabled:
            command(["systemctl", "disable", "--now", f"airnode-feeder@{f['id']}.service"])
    for name in sorted(enabled):
        service = f"airnode-feeder@{name}.service"
        command(["systemctl", "enable", service])
        command(["systemctl", "restart", service])

def dispatch(request):
    op = request.get("op")
    if op == "wifi-status":
        return wifi.scan()
    if op == "wifi-connect":
        with LOCK:
            return wifi.queue(request.get("settings"))
    if op == "release-status":
        return releases.status()
    if op == "release-action":
        with LOCK, exclusive():
            return releases.operate(command, request.get("action"), request.get("channel"))
    if op == "onboarding-complete":
        Path('/boot/firmware/AIRNODE-SETUP.txt').unlink(missing_ok=True)
        return {"ok": True}
    if op == "aggregators":
        return Manager(command).status()
    if op == "aggregator-config":
        with LOCK, exclusive():
            return Manager(command).configure(request.get("settings"))
    if op == "aggregator-action":
        with LOCK:
            if request.get("action") in ("restart",):
                with exclusive():
                    return Manager(command).operate(request.get("provider"), request.get("action"))
            return Manager(command).operate(request.get("provider"), request.get("action"))
    if op == "status":
        result = {}
        for name in units():
            state = command(["systemctl", "show", name + ".service", "--property=ActiveState,SubState,UnitFileState", "--no-pager"])
            result[name] = dict(line.split("=", 1) for line in state.splitlines() if "=" in line)
        return {"services": result,
            "network": command(["ip", "-j", "address", "show"], check=False),
            "usb": command(["lsusb"], check=False),
            "hostname": command(["hostname"]),
            "update": command(["systemctl", "show", "airnode-update.service", "--property=ActiveState,Result,ExecMainStatus"], check=False)}
    if op == "config":
        with LOCK:
            return apply_config(request.get("config"))
    if op == "service":
        name = unit(request.get("unit"))
        action = request.get("action")
        if action not in ("start", "stop", "restart"):
            raise ValueError("Unknown service action")
        command(["systemctl", action, name])
        return {"accepted": True}
    if op == "logs":
        name = request.get("unit")
        service = "airnode-update.service" if name == "airnode-update" else unit(name)
        return {"text": command(["journalctl", "-u", service, "-n", "120", "--no-pager", "-o", "short-iso"])[-24000:]}
    if op == "hostname":
        value = request.get("hostname", "")
        if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,61}[a-z0-9]|[a-z]", value):
            raise ValueError("Use a lowercase hostname, 1–63 characters")
        command(["hostnamectl", "set-hostname", value])
        # Keep sudo/name resolution healthy on Debian.
        hosts = Path("/etc/hosts")
        lines = [line for line in hosts.read_text().splitlines() if not line.startswith("127.0.1.1")]
        hosts.write_text("\n".join(lines) + f"\n127.0.1.1\t{value}\n")
        command(["systemctl", "restart", "avahi-daemon"])
        return {"hostname": value, "message": "Hostname updated. HTTPS certificate retains original name; use its fingerprint or provision a new certificate."}
    if op == "update":
        command(["systemctl", "start", "--no-block", "airnode-update.service"])
        return {"accepted": True, "message": "OS update started. Follow the update log; AirNode/readsb releases are updated separately."}
    if op == "power":
        action = request.get("action")
        if action not in ("reboot", "poweroff"):
            raise ValueError("Unknown power action")
        command(["shutdown", "-r" if action == "reboot" else "-h", "+1"])
        return {"accepted": True, "message": "Scheduled in one minute."}
    raise ValueError("Unknown operation")

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        import pwd
        self.connection.settimeout(20)
        _, uid, _ = struct.unpack("3i", self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != pwd.getpwnam("airnode").pw_uid:
            return
        try:
            raw = self.rfile.readline(65537)
            if len(raw) > 65536:
                raise ValueError("Request too large")
            result = {"ok": True, "data": dispatch(json.loads(raw))}
        except Exception as exc:
            result = {"ok": False, "error": str(exc)[:2000]}
        self.wfile.write(json.dumps(result).encode() + b"\n")

def main():
    import grp
    Path(SOCKET).parent.mkdir(parents=True, exist_ok=True)
    Path(SOCKET).unlink(missing_ok=True)
    with socketserver.UnixStreamServer(SOCKET, Handler) as server:
        os.chown(SOCKET, 0, grp.getgrnam("airnode").gr_gid)
        os.chmod(SOCKET, 0o660)
        server.serve_forever()

if __name__ == "__main__":
    main()

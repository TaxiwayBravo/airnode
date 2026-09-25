"""Dependency-free AirNode HTTP API. Production binds loopback behind nginx TLS."""
import argparse
import copy
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import socket
import time
from urllib.parse import urlsplit, parse_qs
from . import __version__
from .auth import Auth
from .config import DEFAULT, read, validate, write
from . import aggregators as ag
from .network import access_info

WEB = Path(__file__).resolve().parent.parent / "web"

class APIError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message

class App:
    def __init__(self, state, demo=False, data="/run/airnode-readsb", config="/etc/airnode/config.json", local_preview=False):
        self.state = Path(state)
        self.state.mkdir(parents=True, exist_ok=True)
        self.demo, self.data = demo, Path(data)
        self.local_preview = local_preview
        self.config = self.state / "config.json" if demo or local_preview else Path(config)
        if (demo or local_preview) and not self.config.exists():
            value = copy.deepcopy(DEFAULT)
            if demo: value["receiver"].update(latitude=51.5, longitude=-0.12)
            write(self.config, value)
        self.auth = Auth(self.state / "auth.db")
        self.started = time.time()
        self.setup_path = self.state / "setup-token"
        if not self.auth.configured() and not self.setup_path.exists():
            self.setup_path.write_text(secrets.token_urlsafe(24))
            os.chmod(self.setup_path, 0o600)
        self.demo_software = {key: {"busy": False, "result": "Demo ready", "automatic": False, "version": "Demo", "installed": ag.PROVIDERS[key]["kind"] == "readsb"} for key in ag.PROVIDERS}
        self.demo_services = {"airnode-receiver": "active"}
        if demo:
            self.demo_services.update({"airnode-feeder@" + f["id"]: "active" if f["enabled"] else "inactive" for f in read(self.config)["feeders"]})

    def broker(self, request):
        if self.local_preview:
            op = request.get("op")
            if op == "status":
                return {"services": {}, "network": "[]", "usb": "No Pi connected. USB inventory comes from the installed Pi.", "hostname": "No Pi connected", "update": "Available on the Pi", "error": "No Raspberry Pi connected. Waiting for real receiver data."}
            if op == "aggregators":
                return {"providers": [{"id":key, **p, **ag.public_settings(key,None), "installed":False, "state":"No Pi connected", "detail":"Install AirNode on your Pi to manage this provider.", "demo":False} for key,p in ag.PROVIDERS.items()]}
            if op == "wifi-status": return {"available":False,"message":"Wi-Fi setup is available on the installed Pi.","networks":[],"demo":False}
            if op == "release-status": return {"current":__version__,"repository":"TaxiwayBravo/airnode","channel":"stable","state":"No Pi connected","message":"GitHub release installation runs on your Pi.","demo":False}
            if op == "onboarding-complete": return {"ok":True}
            raise APIError(503, "This computer is a hardware preview. Open AirNode on your Pi to change device settings.")
        if self.demo:
            op = request["op"]
            ag_path = self.state / "aggregators.json"
            if op == "wifi-status": return {"available":True,"message":"Demo: Wi-Fi changes are simulated.","networks":[],"demo":True}
            if op == "wifi-connect":
                from .wifi import validate as validate_wifi
                validate_wifi(request.get("settings"))
                return {"accepted":True,"message":"Demo only. No Wi-Fi settings changed."}
            if op == "release-status": return {"current":__version__,"repository":"TaxiwayBravo/airnode","channel":"stable","state":"Demo","message":"Demo: updates are simulated.","demo":True}
            if op == "release-action":
                if request.get("action") not in ("check","install","channel") or (request.get("action") == "channel" and request.get("channel") not in ("stable","beta")):
                    raise ValueError("Invalid release request")
                return {"accepted":True,"message":"Demo only. No release downloaded or installed."}
            if op == "aggregators":
                settings = ag.load(ag_path)
                return {"local_only": True, "mlat_supported": False, "providers": [
                    {"id": key, **p, **ag.public_settings(key, settings.get(key)), "installed": self.demo_software[key]["installed"],
                     "state": "Demo enabled" if settings.get(key, {}).get("enabled") else "Disabled" if key in settings else "Not configured",
                     "detail": "Simulation only. No data leaves this computer; real clients must be installed on the Pi.",
                     "service": ag.service(key), "service_state": "simulated", "demo": True, "software": self.demo_software[key]} for key, p in ag.PROVIDERS.items()]}
            if op == "aggregator-config":
                ag.save(ag_path, ag.updated(ag.load(ag_path), request["settings"]))
                return {"saved": True, "message": "Demo settings saved. No provider connection was made."}
            if op == "aggregator-action":
                ag.provider(request.get("provider"))
                if request.get("action") in ("logs", "install-logs"):
                    return {"text": "DEMO · Aggregator simulation. No upstream connection or data transmission.\n"}
                if request.get("action") in ("install", "update", "auto-on", "auto-off"):
                    item = self.demo_software[request["provider"]]
                    if request["action"].startswith("auto-"):
                        item["automatic"] = request["action"] == "auto-on"
                    else:
                        item["result"] = "Demo complete"
                        item["installed"] = True
                    return {"accepted": True, "message": "Demo software action simulated. No packages or schedules changed on this computer."}
                if request.get("action") != "restart":
                    raise ValueError("Unknown aggregator action")
                if not ag.load(ag_path).get(request["provider"], {}).get("enabled"):
                    raise ValueError("Enable this provider before restarting")
                return {"accepted": True, "message": "Demo restart simulated."}
            if op == "config":
                write(self.config, request["config"])
                self.demo_services = {"airnode-receiver": "active", **{"airnode-feeder@" + f["id"]: "active" if f["enabled"] else "inactive" for f in request["config"]["feeders"]}}
            elif op == "service":
                if request.get("unit") not in self.demo_services or request.get("action") not in ("start", "stop", "restart"):
                    raise ValueError("Unknown service/action")
                self.demo_services[request["unit"]] = "inactive" if request["action"] == "stop" else "active"
            elif op == "logs":
                return {"text": "DEMO · Synthetic data. No radio or system commands are running.\nAirNode receiver simulator ready.\n"}
            elif op == "status":
                return {"services": {k: {"ActiveState": v, "SubState": "running" if v == "active" else "dead"} for k, v in self.demo_services.items()},
                    "network": "[]", "usb": "DEMO · Simulated RTL2832U / R820T2", "hostname": "airnode-demo", "update": "Demo mode: updates are simulated"}
            return {"accepted": True, "message": "Demo only: simulated action; host unchanged."}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(45)
            conn.connect("/run/airnode-control/control.sock")
            conn.sendall(json.dumps(request).encode() + b"\n")
            response = json.loads(conn.makefile("rb").readline(131072))
        if not response["ok"]:
            raise APIError(503, response["error"])
        return response["data"]

    def aircraft(self):
        if self.demo:
            now = time.time()
            active = self.demo_services["airnode-receiver"] == "active"
            aircraft = []
            if active:
                for i in range(18):
                    angle = now / 450 + i * 2.399
                    distance = 0.5 + (i % 7) * 0.43
                    aircraft.append({"hex": f"{0x400001+i:06x}", "flight": ["BAW", "EZY", "RYR", "KLM"][i % 4] + str(102 + i * 37),
                        "lat": 51.5 + math.cos(angle) * distance, "lon": -0.12 + math.sin(angle) * distance * 1.6,
                        "alt_baro": 18000 + i * 1000, "gs": 320 + i * 8, "track": (angle * 180 / math.pi + 90) % 360,
                        "seen": i % 3, "seen_pos": i % 3, "messages": 800 + i * 90, "rssi": -15.2 - i / 2})
            return {"now": now, "messages": int((now - self.started) * 840), "aircraft": aircraft, "stale": not active, "age": 0, "demo": True}
        try:
            path = self.data / "aircraft.json"
            value = json.loads(path.read_text())
            age = max(0, time.time() - float(value.get("now", path.stat().st_mtime)))
            return {**value, "age": round(age, 1), "stale": age > 15, "demo": False}
        except (OSError, ValueError, TypeError):
            return {"now": time.time(), "messages": 0, "aircraft": [], "stale": True, "age": None, "demo": False}

    def status(self):
        data = self.aircraft()
        aircraft = [a for a in data["aircraft"] if a.get("seen", 999) < 60] if not data["stale"] else []
        total, used, _ = shutil.disk_usage(self.state)
        temp = None
        try:
            temp = round(float(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
        except (OSError, ValueError):
            pass
        try:
            system = self.broker({"op": "status"})
        except (OSError, APIError) as exc:
            system = {"services": {}, "error": str(exc), "network": "[]", "usb": "Unavailable", "hostname": socket.gethostname()}
        return {"version": __version__, "demo": self.demo, "local_preview": self.local_preview, "station": read(self.config)["name"],
            "aircraft": len(aircraft), "positioned": sum("lat" in a and a.get("seen_pos", 999) < 60 for a in aircraft),
            "messages": data.get("messages", 0), "stale": data["stale"], "data_age": data["age"],
            "access": access_info(system.get("hostname"), system.get("network", "[]"), self.demo or self.local_preview),
            "temperature": None if self.local_preview else temp, "load": os.getloadavg()[0] if hasattr(os, "getloadavg") and not self.local_preview else None,
            "disk_percent": None if self.local_preview else round(used / total * 100, 1), "api_uptime": int(time.time() - self.started), **system}

class Handler(BaseHTTPRequestHandler):
    server_version = "AirNode"

    @property
    def app(self):
        return self.server.app

    def log_message(self, fmt, *args):
        # Never log request bodies, credentials or cookies.
        print(f"AirNode {self.client_address[0]} {fmt % args}", flush=True)

    def send(self, code, body, kind="application/json", cookie=None):
        raw = json.dumps(body, allow_nan=False).encode() if kind == "application/json" else body
        self.send_response(code)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def token(self):
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            return cookies["airnode_session"].value if "airnode_session" in cookies else ""
        except Exception:
            return ""

    def cookie(self, token, age=28800):
        return f"airnode_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={age}" + ("" if self.app.demo or self.app.local_preview else "; Secure")

    def authenticated(self, mutate=False):
        csrf = self.app.auth.lookup(self.token())
        if not csrf:
            raise APIError(401, "Please sign in")
        if mutate and not secrets.compare_digest(csrf, self.headers.get("X-CSRF-Token", "")):
            raise APIError(403, "Invalid CSRF token")
        return csrf

    def body(self):
        if self.headers.get_content_type() != "application/json":
            raise APIError(415, "Expected application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise APIError(400, "Invalid content length")
        if not 0 < length <= 32768:
            raise APIError(413, "Request must be 1–32768 bytes")
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError("Expected JSON object")
        return value

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)

    def handle_request(self, mutate):
        self.connection.settimeout(15)
        try:
            path = urlsplit(self.path).path
            if mutate:
                body = self.body()
                # Reject cross-site browser mutations, including setup/login.
                origin = self.headers.get("Origin")
                if origin and origin != ("http" if self.app.demo or self.app.local_preview else "https") + "://" + self.headers.get("Host", ""):
                    raise APIError(403, "Origin rejected")
                if path in ("/api/login", "/api/setup"):
                    ip = self.client_address[0] if self.app.demo else self.headers.get("X-Real-IP", self.client_address[0])
                    if not self.app.auth.throttle(ip):
                        raise APIError(429, "Too many attempts. Try again in five minutes.")
                    if path == "/api/setup":
                        if self.app.auth.configured():
                            raise APIError(409, "AirNode already has an owner")
                        token = str(body.get("token", ""))
                        if not secrets.compare_digest(token, self.app.setup_path.read_text().strip()):
                            raise APIError(403, "Invalid pairing token")
                        self.app.auth.password(body.get("password"), initial=True)
                        self.app.setup_path.unlink(missing_ok=True)
                        try: self.app.broker({"op":"onboarding-complete"})
                        except Exception: pass
                    elif not self.app.auth.verify(body.get("password")):
                        raise APIError(401, "Incorrect password")
                    token, csrf = self.app.auth.session()
                    return self.send(200, {"csrf": csrf}, cookie=self.cookie(token))
                self.authenticated(True)
                if path == "/api/logout":
                    self.app.auth.logout(self.token())
                    return self.send(200, {"ok": True}, cookie=self.cookie("", 0))
                if path == "/api/password":
                    if not self.app.auth.verify(body.get("current")):
                        raise APIError(403, "Current password is incorrect")
                    self.app.auth.password(body.get("password"))
                    return self.send(200, {"message": "Password changed; sign in again."}, cookie=self.cookie("", 0))
                if path == "/api/wifi/connect":
                    return self.send(200, self.app.broker({"op":"wifi-connect","settings":body}))
                if path == "/api/releases/action":
                    if body.get("action") == "install" and not self.app.auth.verify(body.get("password")):
                        raise APIError(403, "Confirm your password")
                    return self.send(200, self.app.broker({"op":"release-action","action":body.get("action"),"channel":body.get("channel")}))
                if path == "/api/config":
                    return self.send(200, self.app.broker({"op": "config", "config": validate(body)}))
                if path == "/api/aggregators/config":
                    return self.send(200, self.app.broker({"op": "aggregator-config", "settings": body}))
                if path == "/api/aggregators/action":
                    return self.send(200, self.app.broker({"op": "aggregator-action", "provider": body.get("provider"), "action": body.get("action")}))
                operations = {"/api/service": "service", "/api/hostname": "hostname", "/api/update": "update", "/api/power": "power"}
                if path in operations:
                    if path in ("/api/update", "/api/power") and not self.app.auth.verify(body.get("password")):
                        raise APIError(403, "Confirm your password")
                    request = {k: v for k, v in body.items() if k != "password"}
                    request["op"] = operations[path]
                    return self.send(200, self.app.broker(request))
            else:
                if path == "/api/health":
                    return self.send(200, {"ok": True, "version": __version__})
                if path == "/api/session":
                    csrf = self.app.auth.lookup(self.token())
                    return self.send(200, {"configured": self.app.auth.configured(), "authenticated": bool(csrf), "csrf": csrf, "demo": self.app.demo, "local_preview": self.app.local_preview})
                if path.startswith("/api/"):
                    self.authenticated()
                    if path == "/api/wifi":
                        return self.send(200, self.app.broker({"op":"wifi-status"}))
                    if path == "/api/releases":
                        return self.send(200, self.app.broker({"op":"release-status"}))
                    if path == "/api/status":
                        return self.send(200, self.app.status())
                    if path == "/api/config":
                        return self.send(200, read(self.app.config))
                    if path == "/api/aggregators":
                        return self.send(200, self.app.broker({"op": "aggregators"}))
                    if path == "/api/aircraft":
                        return self.send(200, self.app.aircraft())
                    if path == "/api/logs":
                        name = parse_qs(urlsplit(self.path).query).get("unit", ["airnode-receiver"])[0]
                        return self.send(200, self.app.broker({"op": "logs", "unit": name}))
                assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
                if path in assets:
                    name, kind = assets[path]
                    return self.send(200, (WEB / name).read_bytes(), kind)
            raise APIError(404, "Not found")
        except APIError as exc:
            self.send(exc.code, {"error": exc.message})
        except (ValueError, TypeError, KeyError) as exc:
            self.send(400, {"error": str(exc)[:500]})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            import traceback
            traceback.print_exc()
            self.send(503, {"error": "Service unavailable; inspect AirNode service logs"})

def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--demo", action="store_true")
    modes.add_argument("--local-preview", action="store_true", help="Read-only hardware preview: no simulated data or system control")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--state")
    args = parser.parse_args()
    os.umask(0o077)
    app = App(args.state or (".demo" if args.demo else ".preview" if args.local_preview else "/var/lib/airnode"), args.demo, local_preview=args.local_preview)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.app = app
    if (args.demo or args.local_preview) and app.setup_path.exists():
        print("Local preview pairing token: " + app.setup_path.read_text(), flush=True)
    print(f"AirNode {'DEMO' if args.demo else 'API'}: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()

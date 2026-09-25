"""Root-side provider operations; callers pass only catalog IDs and validated data."""
import json
import os
from pathlib import Path
import re
from . import aggregators as ag
from . import maintenance

class Manager:
    def __init__(self, command, root="/etc/airnode", etc="/etc"):
        self.command, self.root, self.etc = command, Path(root), Path(etc)
        self.path = self.root / "aggregators.json"

    def state(self, key):
        text = self.command(["systemctl", "show", ag.service(key) + ".service", "--property=LoadState,ActiveState,SubState,MainPID,UnitFileState", "--no-pager"], check=False)
        return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)

    def available(self, key, state=None):
        p = ag.provider(key)
        binary = "/usr/local/bin/readsb" if p["kind"] == "readsb" else p["binary"]
        state = state if state is not None else self.state(key)
        return Path(binary).is_file() and state.get("LoadState") == "loaded"

    def status(self):
        settings = ag.load(self.path)
        sockets = self.command(["ss", "-Htnp", "state", "established"], check=False)
        items = []
        for key, p in ag.PROVIDERS.items():
            entry = settings.get(key)
            state = self.state(key)
            installed = self.available(key, state)
            active = state.get("ActiveState") == "active"
            label, detail = "Not configured", "Choose a provider and configure sharing from this Pi."
            if active and (not entry or not entry["enabled"]):
                label, detail = "Running outside settings", "A client is running although AirNode sharing is off. Inspect its local service."
            elif entry and not entry["enabled"]:
                label, detail = "Disabled", "Sharing is switched off in AirNode."
            elif entry and not installed:
                label, detail = "Client required", "Select Install software to let AirNode prepare this client."
            elif entry and state.get("ActiveState") in ("failed", "inactive"):
                label, detail = "Stopped", "Sharing is enabled, but the client is stopped. Check its logs or restart."
            elif entry:
                label, detail = "Starting", "Waiting for the provider client."
                if active:
                    label, detail = "Running · unverified", "Client is running. Check the provider status page to confirm reception."
                    if p["kind"] == "readsb":
                        ports = {30004, 1337} if key == "adsblol" else {30004, 64004} if key == "adsbexchange" else {30004}
                        if upstream_connected(sockets, state.get("MainPID", "0"), ports):
                            label, detail = "TCP connected", "Upstream TCP connection is established. Provider acceptance is not independently verified."
                        else:
                            label, detail = "Connecting", "Client is running without a detected upstream TCP connection. It retries automatically."
            if not installed and not entry:
                label, detail = "Client required", "Select Install software, then configure sharing."
            items.append({"id":key, **p, **ag.public_settings(key, entry), "installed":installed,
                "state":label, "detail":detail, "service":ag.service(key), "service_state":state.get("ActiveState", "unknown"), "demo":False, "software":maintenance.software_status(self.command, key)})
        return {"providers":items, "local_only":True, "mlat_supported":False}

    def target_path(self, key):
        if key == "flightaware":
            return self.etc / "piaware.conf"
        if key == "flightradar24":
            return self.etc / "fr24feed.ini"
        return self.root / "providers" / (key + ".json")

    def configure(self, request):
        old = ag.load(self.path)
        new = ag.updated(old, request)
        key, p = request["provider"], ag.provider(request["provider"])
        entry = new[key]
        state = self.state(key)
        installed = self.available(key, state)
        if entry["enabled"] and not installed:
            raise ValueError("Install the provider client on this Pi before enabling. Settings were not changed.")
        # PiAware package installs use /etc/piaware.conf; image/boot overrides would defeat these settings.
        if key == "flightaware" and entry["enabled"]:
            for boot in (Path("/boot/piaware-config.txt"), Path("/boot/firmware/piaware-config.txt")):
                if boot.exists() and any(line.strip() and not line.lstrip().startswith("#") for line in boot.read_text().splitlines()):
                    raise ValueError("PiAware boot configuration overrides are present. Move to package-only configuration before enabling in AirNode.")
        unit = ag.service(key) + ".service"
        target = self.target_path(key)
        previous = target.read_bytes() if target.exists() else None
        previous_stat = target.stat() if target.exists() else None
        marker = self.root / "providers" / (key + ".enabled")
        marker_existed = marker.exists()
        changed = False
        service_touched = False
        try:
            if not entry['enabled']:
                marker.unlink(missing_ok=True)
            if installed and (entry["enabled"] or key in old):
                self.command(["systemctl", "stop", unit])
                service_touched = True
            if entry["enabled"]:
                if p["kind"] == "readsb":
                    ag.atomic_text(target, json.dumps(entry), 0o640)
                    changed = True
                    import grp
                    os.chown(target, 0, grp.getgrnam("airnode").gr_gid)
                else:
                    if previous is not None and not Path(str(target) + ".airnode-backup").exists():
                        ag.atomic_text(str(target) + ".airnode-backup", previous.decode(), 0o600)
                    mode = (previous_stat.st_mode & 0o777) if previous_stat and key == "flightaware" else 0o644 if key == "flightaware" else 0o600
                    ag.atomic_text(target, ag.native_config(key, entry, previous.decode() if previous else ""), mode)
                    changed = True
                    # Respect a packaged non-root FR24 service without making its key world-readable.
                    if key == "flightradar24":
                        user = self.command(["systemctl", "show", unit, "--property=User", "--value"])
                        if user and user != "root":
                            import pwd
                            os.chown(target, 0, pwd.getpwnam(user).pw_gid)
                            os.chmod(target, 0o640)
                ag.atomic_text(marker, "enabled\n", 0o644)
                self.command(["systemctl", "enable", unit])
                self.command(["systemctl", "start", unit])
            elif installed and key in old:
                marker.unlink(missing_ok=True)
                self.command(["systemctl", "disable", "--now", unit])
            ag.save(self.path, new)
        except Exception:
            rollback_ok = True
            try:
                if marker_existed:
                    ag.atomic_text(marker, "enabled\n", 0o644)
                else:
                    marker.unlink(missing_ok=True)
                if changed:
                    if previous is None:
                        target.unlink(missing_ok=True)
                    else:
                        ag.atomic_text(target, previous.decode(), previous_stat.st_mode & 0o777)
                        os.chown(target, previous_stat.st_uid, previous_stat.st_gid)
                if service_touched:
                    self.command(["systemctl", "enable" if state.get("UnitFileState") == "enabled" else "disable", unit])
                    self.command(["systemctl", "restart" if state.get("ActiveState") == "active" else "stop", unit])
            except Exception:
                rollback_ok = False
            # Native command errors can contain credentials. Do not echo their output through the API.
            raise ValueError("Provider setup failed. " + ("Previous configuration restored; inspect local service logs." if rollback_ok else "Recovery was incomplete; inspect the client from a local console before retrying.")) from None
        return {"saved":True, "message": "Sharing enabled. Verify reception on the provider’s status page." if entry["enabled"] else "Settings saved with sharing disabled."}

    def operate(self, key, action):
        ag.provider(key)
        if action in ("install", "update", "auto-on", "auto-off", "install-logs"):
            if action == "auto-on" and not self.available(key):
                raise ValueError("Install the client before enabling daily updates")
            return maintenance.operate(self.command, key, action)
        settings = ag.load(self.path)
        if action not in ("restart", "logs"):
            raise ValueError("Unknown aggregator action")
        if action == "logs":
            raw = self.command(["journalctl", "-u", ag.service(key) + ".service", "-n", "120", "--no-pager", "-o", "short-iso"])
            return {"text":ag.redact(raw, settings)[-24000:]}
        if key not in settings or not settings[key]["enabled"]:
            raise ValueError("Enable this provider before restarting")
        if not self.available(key):
            raise ValueError("Provider client is not installed")
        try:
            self.command(["systemctl", "restart", ag.service(key) + ".service"])
        except Exception:
            raise ValueError("Client restart failed; inspect its local logs") from None
        return {"accepted":True, "message":"Client restarted; check provider reception."}

def upstream_connected(text, pid, ports):
    if not str(pid).isdigit() or int(pid) <= 0:
        return False
    for line in text.splitlines():
        if not re.search(r"\bpid=" + re.escape(str(pid)) + r",", line):
            continue
        columns = line.split()
        # ss with 'state established' omits the state column: Recv-Q Send-Q Local Peer Process.
        if len(columns) >= 5:
            peer = columns[3]
            port = peer.rsplit(":", 1)[-1]
            if port.isdigit() and int(port) in ports:
                return True
    return False

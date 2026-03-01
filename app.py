"""
app.py — MultiMachine Controller
Flask web server + PCConnection + PCManager
"""

import os
import sys
import ssl
import json
import hmac
import uuid
import socket
import hashlib
import threading
import webbrowser
import time

from flask import Flask, request, jsonify, send_from_directory


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def resource_path(relative_path: str) -> str:
    """Return absolute path to *bundled* resources (templates/static).
    When frozen by PyInstaller, files live under sys._MEIPASS.
    During development they live next to this script.
    """
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


def config_path(filename: str) -> str:
    """Return absolute path to *writable* config files.
    When frozen the writable directory is next to the .exe.
    During development it is next to this script.
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, filename)


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

template_folder = resource_path("templates")
static_folder = resource_path("static")
app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)


# ---------------------------------------------------------------------------
# PCConnection
# ---------------------------------------------------------------------------

class PCConnection:
    """Manages a single TLS + HMAC-authenticated connection to one remote PC."""

    def __init__(self, pc_id: str, name: str, ip: str, port: int, password: str):
        self.id = pc_id
        self.name = name
        self.ip = ip
        self.port = port
        self.password = password

        self.connected = False
        self.error: str = ""
        self.hostname: str = ""
        self.os_info: str = ""

        self._ssl_sock = None
        self._lock = threading.Lock()
        self._file = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            context.minimum_version = ssl.TLSVersion.TLSv1_2

            raw = socket.create_connection((self.ip, self.port), timeout=10)
            self._ssl_sock = context.wrap_socket(raw, server_hostname=self.ip)
            self._file = self._ssl_sock.makefile("r", encoding="utf-8")

            # Read welcome message from agent
            welcome_line = self._file.readline()
            if not welcome_line:
                raise ConnectionError("Agent did not send welcome message")
            welcome = json.loads(welcome_line)

            self.hostname = welcome.get("hostname", "")
            self.os_info = welcome.get("os", "")

            if welcome.get("requires_auth"):
                nonce = welcome.get("nonce", "")
                proof = hmac.new(
                    self.password.encode("utf-8"),
                    nonce.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                self._send_raw({"command": "AUTH", "proof": proof})

                auth_response_line = self._file.readline()
                if not auth_response_line:
                    raise ConnectionError("No auth response from agent")
                auth_response = json.loads(auth_response_line)
                if auth_response.get("status") != "ok":
                    raise PermissionError(
                        auth_response.get("message", "Authentication failed")
                    )

            self.connected = True
            self.error = ""
            return True

        except Exception as exc:
            self.connected = False
            self.error = str(exc)
            self._cleanup()
            return False

    def disconnect(self):
        self.connected = False
        self._cleanup()

    def _cleanup(self):
        try:
            if self._ssl_sock:
                self._ssl_sock.close()
        except Exception:
            pass
        self._ssl_sock = None
        self._file = None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _send_raw(self, payload: dict):
        """Send a JSON payload (no lock — caller holds it or it is init)."""
        line = json.dumps(payload) + "\n"
        self._ssl_sock.sendall(line.encode("utf-8"))

    def send_command(self, command: dict) -> dict:
        """Thread-safe command send + response receive."""
        with self._lock:
            if not self.connected or self._ssl_sock is None:
                return {"error": "Not connected"}
            try:
                self._send_raw(command)
                response_line = self._file.readline()
                if not response_line:
                    self.connected = False
                    self.error = "Connection lost"
                    return {"error": "Connection lost"}
                return json.loads(response_line)
            except Exception as exc:
                self.connected = False
                self.error = str(exc)
                self._cleanup()
                return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "ip": self.ip,
            "port": self.port,
            "connected": self.connected,
            "error": self.error,
            "hostname": self.hostname,
            "os": self.os_info,
        }


# ---------------------------------------------------------------------------
# PCManager
# ---------------------------------------------------------------------------

CONFIG_FILE = config_path("pcs_config.json")


class PCManager:
    """Loads/saves pcs_config.json and manages all PCConnection objects."""

    def __init__(self):
        self._pcs: dict[str, PCConnection] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for entry in data.get("pcs", []):
                pc_id = entry.get("id") or str(uuid.uuid4())
                pc = PCConnection(
                    pc_id=pc_id,
                    name=entry["name"],
                    ip=entry["ip"],
                    port=int(entry["port"]),
                    password=entry.get("password", ""),
                )
                self._pcs[pc_id] = pc
        except Exception as exc:
            print(f"[PCManager] Error loading config: {exc}")

    def _save(self):
        data = {
            "pcs": [
                {
                    "id": pc.id,
                    "name": pc.name,
                    "ip": pc.ip,
                    "port": pc.port,
                    "password": pc.password,
                }
                for pc in self._pcs.values()
            ]
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=4)
        except Exception as exc:
            print(f"[PCManager] Error saving config: {exc}")

    # ------------------------------------------------------------------
    # PC management
    # ------------------------------------------------------------------

    def connect_all(self):
        """Connect to all PCs in parallel background threads."""
        threads = []
        for pc in list(self._pcs.values()):
            t = threading.Thread(target=pc.connect, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

    def add_pc(self, name: str, ip: str, port: int, password: str) -> PCConnection:
        pc_id = str(uuid.uuid4())
        pc = PCConnection(pc_id, name, ip, port, password)
        self._pcs[pc_id] = pc
        self._save()
        threading.Thread(target=pc.connect, daemon=True).start()
        return pc

    def remove_pc(self, pc_id: str) -> bool:
        pc = self._pcs.pop(pc_id, None)
        if pc is None:
            return False
        pc.disconnect()
        self._save()
        return True

    def get_pc(self, pc_id: str) -> PCConnection | None:
        return self._pcs.get(pc_id)

    def all_pcs(self) -> list[PCConnection]:
        return list(self._pcs.values())


# ---------------------------------------------------------------------------
# Singleton manager
# ---------------------------------------------------------------------------

manager = PCManager()


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(template_folder, "index.html")


@app.route("/api/status")
def api_status():
    return jsonify([pc.to_dict() for pc in manager.all_pcs()])


@app.route("/api/command", methods=["POST"])
def api_command():
    body = request.get_json(force=True)
    pc_id = body.get("pc_id")
    command = body.get("command")
    if not pc_id or not command:
        return jsonify({"error": "pc_id and command are required"}), 400
    pc = manager.get_pc(pc_id)
    if pc is None:
        return jsonify({"error": "PC not found"}), 404
    result = pc.send_command(command)
    return jsonify(result)


@app.route("/api/command/all", methods=["POST"])
def api_command_all():
    body = request.get_json(force=True)
    command = body.get("command")
    if not command:
        return jsonify({"error": "command is required"}), 400
    results = {}
    threads = []

    def _send(pc):
        results[pc.id] = {"name": pc.name, "result": pc.send_command(command)}

    for pc in manager.all_pcs():
        if pc.connected:
            t = threading.Thread(target=_send, args=(pc,), daemon=True)
            t.start()
            threads.append(t)
    for t in threads:
        t.join()
    return jsonify(results)


@app.route("/api/reconnect", methods=["POST"])
def api_reconnect():
    body = request.get_json(force=True) or {}
    pc_id = body.get("pc_id")
    if pc_id:
        pc = manager.get_pc(pc_id)
        if pc is None:
            return jsonify({"error": "PC not found"}), 404
        pc.disconnect()
        threading.Thread(target=pc.connect, daemon=True).start()
        return jsonify({"status": "reconnecting", "pc_id": pc_id})
    # Reconnect all
    for pc in manager.all_pcs():
        pc.disconnect()
    threading.Thread(target=manager.connect_all, daemon=True).start()
    return jsonify({"status": "reconnecting_all"})


@app.route("/api/reconnect/all", methods=["POST"])
def api_reconnect_all():
    offline = [pc for pc in manager.all_pcs() if not pc.connected]
    for pc in offline:
        pc.disconnect()
        threading.Thread(target=pc.connect, daemon=True).start()
    return jsonify({"status": "reconnecting", "count": len(offline)})


@app.route("/api/pcs", methods=["POST"])
def api_add_pc():
    body = request.get_json(force=True)
    name = body.get("name", "").strip()
    ip = body.get("ip", "").strip()
    port = int(body.get("port", 6666))
    password = body.get("password", "")
    if not name or not ip:
        return jsonify({"error": "name and ip are required"}), 400
    pc = manager.add_pc(name, ip, port, password)
    return jsonify(pc.to_dict()), 201


@app.route("/api/pcs/<pc_id>", methods=["DELETE"])
def api_remove_pc(pc_id: str):
    if manager.remove_pc(pc_id):
        return jsonify({"status": "removed"})
    return jsonify({"error": "PC not found"}), 404


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _open_browser():
    time.sleep(1.5)
    webbrowser.open("http://localhost:5000")


if __name__ == "__main__":
    # Connect all PCs in background
    threading.Thread(target=manager.connect_all, daemon=True).start()

    # Open browser after short delay
    threading.Thread(target=_open_browser, daemon=True).start()

    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

"""
agente.py — MultiMachine Agent
TLS server with HMAC-SHA256 authentication.
Runs on each remote Red Hat VM.
"""

import os
import sys
import ssl
import json
import hmac
import hashlib
import shlex
import socket
import threading
import subprocess
import uuid

import psutil


# ---------------------------------------------------------------------------
# Path helper
# ---------------------------------------------------------------------------

def exe_path(filename: str) -> str:
    """Resolve path for cert/key files relative to the executable or script."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, filename)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def handle_command(data: dict) -> dict:
    cmd = data.get("command", "").upper()

    if cmd == "PING":
        return {"status": "ok", "message": "pong"}

    if cmd == "INFO":
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "status": "ok",
            "cpu_percent": cpu,
            "memory": {
                "total": mem.total,
                "available": mem.available,
                "percent": mem.percent,
            },
            "disk": {
                "total": disk.total,
                "free": disk.free,
                "percent": disk.percent,
            },
        }

    if cmd == "LIST_PROCESSES":
        procs = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return {"status": "ok", "processes": procs}

    if cmd == "LAUNCH_APP":
        app_name = data.get("app", "")
        if not app_name:
            return {"status": "error", "message": "app parameter required"}
        try:
            args = shlex.split(app_name)
            subprocess.Popen(args, shell=False)
            return {"status": "ok", "message": f"Launched: {app_name}"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    if cmd == "CLOSE_APP":
        target = data.get("target", "")
        if not target:
            return {"status": "error", "message": "target parameter required"}
        killed = []
        try:
            pid = int(target)
            proc = psutil.Process(pid)
            proc.terminate()
            killed.append(pid)
        except ValueError:
            # target is a name
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if proc.info["name"] and target.lower() in proc.info["name"].lower():
                        proc.terminate()
                        killed.append(proc.info["pid"])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            return {"status": "error", "message": str(exc)}
        return {"status": "ok", "killed": killed}

    if cmd == "OPEN_URL":
        url = data.get("url", "")
        if not url:
            return {"status": "error", "message": "url parameter required"}
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if not url.lower().startswith(("http://", "https://")):
            return {"status": "error", "message": "Only http/https URLs are allowed"}
        try:
            subprocess.Popen(["xdg-open", url])
            return {"status": "ok", "message": f"Opening: {url}"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    if cmd == "LOCK_PC":
        try:
            subprocess.Popen(["loginctl", "lock-session"])
            return {"status": "ok", "message": "Session locked"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    if cmd == "SHUTDOWN":
        delay = int(data.get("delay", 0))
        try:
            subprocess.Popen(["shutdown", "-h", str(delay)])
            return {"status": "ok", "message": f"Shutdown in {delay} minutes"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    if cmd == "CANCEL_SHUTDOWN":
        try:
            subprocess.Popen(["shutdown", "-c"])
            return {"status": "ok", "message": "Shutdown cancelled"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    if cmd == "WRITE_FILE":
        filename = data.get("filename", "")
        content = data.get("content", "")
        if not filename:
            return {"status": "error", "message": "filename parameter required"}
        try:
            with open(filename, "w", encoding="utf-8") as fh:
                fh.write(content)
            return {"status": "ok", "message": f"File written: {filename}"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    return {"status": "error", "message": f"Unknown command: {cmd}"}


# ---------------------------------------------------------------------------
# Client handler
# ---------------------------------------------------------------------------

def handle_client(conn: ssl.SSLSocket, password: str):
    """Handle one connected controller client."""
    try:
        nonce = str(uuid.uuid4())
        welcome = {
            "type": "agent_ready",
            "hostname": socket.gethostname(),
            "os": _get_os_info(),
            "requires_auth": bool(password),
            "nonce": nonce,
        }
        _send(conn, welcome)

        fileobj = conn.makefile("r", encoding="utf-8")

        # Authentication
        if password:
            line = fileobj.readline()
            if not line:
                return
            auth_msg = json.loads(line)
            if auth_msg.get("command") != "AUTH":
                _send(conn, {"status": "error", "message": "Authentication required"})
                return
            proof = auth_msg.get("proof", "")
            expected = hmac.new(
                password.encode("utf-8"),
                nonce.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(proof, expected):
                _send(conn, {"status": "error", "message": "Invalid password"})
                return
            _send(conn, {"status": "ok", "message": "Authenticated"})

        # Command loop
        for line in fileobj:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                result = handle_command(data)
                _send(conn, result)
            except json.JSONDecodeError:
                _send(conn, {"status": "error", "message": "Invalid JSON"})

    except (ConnectionResetError, BrokenPipeError):
        pass
    except Exception as exc:
        print(f"[Agent] Client error: {exc}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _send(conn: ssl.SSLSocket, payload: dict):
    line = json.dumps(payload) + "\n"
    conn.sendall(line.encode("utf-8"))


def _get_os_info() -> str:
    try:
        with open("/etc/os-release") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    import platform
    return platform.platform()


# ---------------------------------------------------------------------------
# TLS server
# ---------------------------------------------------------------------------

def run_server(port: int, password: str, certfile: str, keyfile: str):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=certfile, keyfile=keyfile)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as raw_srv:
        raw_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raw_srv.bind(("0.0.0.0", port))
        raw_srv.listen(10)
        print(f"[Agent] Listening on port {port} (TLS)")

        with context.wrap_socket(raw_srv, server_side=True) as srv:
            while True:
                try:
                    conn, addr = srv.accept()
                    print(f"[Agent] Connection from {addr}")
                    t = threading.Thread(
                        target=handle_client, args=(conn, password), daemon=True
                    )
                    t.start()
                except Exception as exc:
                    print(f"[Agent] Accept error: {exc}")


# ---------------------------------------------------------------------------
# Interactive startup
# ---------------------------------------------------------------------------

def main():
    print("=== MultiMachine Agent ===")

    port_str = input("Puerto de escucha [6666]: ").strip()
    port = int(port_str) if port_str else 6666

    password = input("Contraseña (vacío = sin autenticación): ").strip()

    default_cert = exe_path("agent.crt")
    default_key = exe_path("agent.key")

    cert_input = input(f"Ruta certificado TLS [{default_cert}]: ").strip()
    certfile = cert_input if cert_input else default_cert

    key_input = input(f"Ruta clave privada TLS [{default_key}]: ").strip()
    keyfile = key_input if key_input else default_key

    if not os.path.exists(certfile) or not os.path.exists(keyfile):
        print("[Agent] Cert/key not found. Generating self-signed certificate...")
        try:
            subprocess.run(
                [
                    "openssl", "req", "-x509", "-newkey", "rsa:4096",
                    "-keyout", keyfile,
                    "-out", certfile,
                    "-days", "3650",
                    "-nodes",
                    "-subj", "/CN=multimachine-agent",
                ],
                check=True,
            )
            print(f"[Agent] Certificate generated: {certfile}")
        except Exception as exc:
            print(f"[Agent] Error generating certificate: {exc}")
            sys.exit(1)

    run_server(port, password, certfile, keyfile)


if __name__ == "__main__":
    main()

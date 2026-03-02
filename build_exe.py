"""
build_exe.py — Build script for MultiMachine Controller
Compiles app.py and agente.py into standalone .exe files using PyInstaller.
"""

import os
import sys
import shutil
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT, "dist")
RELEASE_DIR = os.path.join(ROOT, "release")
CONTROLLER_DIR = os.path.join(RELEASE_DIR, "Controlador")
AGENT_DIR = os.path.join(RELEASE_DIR, "Agente")


def run(cmd: list[str]):
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def build_controller():
    print("\n[1/2] Building MultiMachine_Controller.exe ...")
    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "MultiMachine_Controller",
        "--add-data", f"templates{os.pathsep}templates",
        "--add-data", f"static{os.pathsep}static",
        os.path.join(ROOT, "app.py"),
    ])


def build_agent():
    print("\n[2/2] Building MultiMachine_Agent.exe ...")
    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "MultiMachine_Agent",
        os.path.join(ROOT, "agente.py"),
    ])


def organise_release():
    print("\nOrganising release folders ...")
    os.makedirs(CONTROLLER_DIR, exist_ok=True)
    os.makedirs(AGENT_DIR, exist_ok=True)

    # Copy executables
    for exe_name, dest_dir in [
        ("MultiMachine_Controller", CONTROLLER_DIR),
        ("MultiMachine_Agent", AGENT_DIR),
    ]:
        for suffix in [".exe", ""]:
            src = os.path.join(DIST_DIR, exe_name + suffix)
            if os.path.exists(src):
                shutil.copy2(src, dest_dir)
                break

    # Copy default config next to controller
    config_src = os.path.join(ROOT, "pcs_config.json")
    if os.path.exists(config_src):
        shutil.copy2(config_src, CONTROLLER_DIR)

    # Copy deploy scripts
    deploy_src = os.path.join(ROOT, "deploy")
    deploy_dst = os.path.join(RELEASE_DIR, "deploy")
    if os.path.exists(deploy_src):
        if os.path.exists(deploy_dst):
            shutil.rmtree(deploy_dst)
        shutil.copytree(deploy_src, deploy_dst)
        print(f"  deploy/ copied to: {deploy_dst}")

    # Write README
    readme_path = os.path.join(RELEASE_DIR, "README.txt")
    with open(readme_path, "w", encoding="utf-8") as fh:
        fh.write(README_CONTENT)
    print(f"  README written: {readme_path}")


README_CONTENT = """\
======================================================
 MultiMachine Controller — Instrucciones de instalación
======================================================

CONTROLADOR (PC del administrador)
-----------------------------------
1. Copie la carpeta Controlador/ a su PC.
2. Edite pcs_config.json con las IPs de sus VMs.
3. Ejecute MultiMachine_Controller.exe
4. Se abrirá automáticamente el navegador en http://localhost:5000

AGENTE (cada VM Red Hat)
--------------------------
1. Copie MultiMachine_Agent.exe a la VM.
2. Ejecute el agente:
       ./MultiMachine_Agent.exe
3. Siga las instrucciones interactivas (puerto, contraseña, certificado).

FIREWALL (Red Hat / CentOS)
----------------------------
   firewall-cmd --add-port=6666/tcp --permanent
   firewall-cmd --reload

GENERAR CERTIFICADO TLS MANUALMENTE
-------------------------------------
   openssl req -x509 -newkey rsa:4096 -keyout agent.key -out agent.crt \\
       -days 3650 -nodes -subj "/CN=multimachine-agent"

NOTAS DE RED
-------------
- Use modo Bridge en VirtualBox/VMware, NO NAT.
- El controlador debe poder alcanzar la IP de cada VM directamente.

CONFIGURACIÓN CON VMs EN MODO NAT (TÚNEL SSH)
----------------------------------------------
Si las VMs corren en modo NAT dentro de un host intermedio (SteamOS, otra
PC Linux, etc.), use los scripts de la carpeta deploy/ incluida en este release:

  Arquitectura:
    Windows (PC1) → socat en PC2 (:SOCAT_PORT) → túnel SSH reverse → VM (:AGENT_PORT)

  Paso 1 — En el host intermedio (PC2):
    chmod +x deploy/setup_socat.sh
    ./deploy/setup_socat.sh [SOCAT_PORT] [TUNNEL_PORT]
    Ejemplo: ./deploy/setup_socat.sh 6667 6666

  Paso 2 — En la VM:
    chmod +x deploy/setup_tunnel.sh
    ./deploy/setup_tunnel.sh REMOTE_USER REMOTE_HOST [AGENT_PORT] [TUNNEL_PORT]
    Ejemplo: ./deploy/setup_tunnel.sh deck 192.168.1.83 6666 6666

  Paso 3 — En pcs_config.json apunte a IP_PC2:SOCAT_PORT:
    {"name": "VM-RedHat-1", "ip": "192.168.1.83", "port": 6667, "password": ""}

  Verificar desde Windows:
    Test-NetConnection -ComputerName 192.168.1.83 -Port 6667

  Consulte el README.md del proyecto para más detalles.
"""


def print_summary():
    print("\n=== Build Summary ===")
    for folder, label in [(CONTROLLER_DIR, "Controlador"), (AGENT_DIR, "Agente")]:
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            size = os.path.getsize(fpath)
            print(f"  [{label}] {fname}  ({size / 1_048_576:.1f} MB)")
    print("\nDone! Release files are in:", RELEASE_DIR)


if __name__ == "__main__":
    build_controller()
    build_agent()
    organise_release()
    print_summary()

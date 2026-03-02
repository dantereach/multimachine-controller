# MultiMachine Controller

Sistema de control remoto para gestionar múltiples VMs Red Hat desde un único panel web.

## Descripción

**MultiMachine Controller** es una aplicación que permite administrar múltiples máquinas virtuales Red Hat desde una interfaz web moderna con tema oscuro. Consta de dos componentes:

1. **Controlador (`app.py`)** — Servidor Flask con dashboard web. Se ejecuta en el PC del administrador y se accede en `http://localhost:5000`.
2. **Agente (`agente.py`)** — Servidor TLS que se ejecuta en cada VM remota. Recibe y ejecuta comandos del controlador.

La comunicación está cifrada con **TLS** y autenticada con **HMAC-SHA256**.

## Arquitectura

```
┌─────────────────────────────┐
│   PC Administrador          │
│   app.py (Flask :5000)      │
│   Browser → localhost:5000  │
└────────────┬────────────────┘
             │ TLS + HMAC-SHA256
    ┌────────┴─────────────────────┐
    │                              │
┌───▼──────────────┐  ┌───────────▼──────────────┐
│  VM-RedHat-1     │  │  VM-RedHat-2             │
│  agente.py :6666 │  │  agente.py :6666         │
└──────────────────┘  └──────────────────────────┘
```

## Estructura del proyecto

```
multimachine-controller/
├── app.py                 # Controlador Flask
├── agente.py              # Agente TLS para VMs
├── build_exe.py           # Script de compilación PyInstaller
├── pcs_config.json        # Configuración de VMs
├── requirements.txt       # Dependencias Python
├── deploy/
│   ├── setup_tunnel.sh    # Configura túnel SSH reverse en la VM
│   └── setup_socat.sh     # Configura socat en el host intermedio
├── templates/
│   └── index.html         # Dashboard principal
└── static/
    ├── css/
    │   └── styles.css     # Estilos CSS
    └── js/
        └── app.js         # Lógica frontend
```

## Requisitos

- Python 3.10+
- pip

## Instalación y uso

### Controlador (PC del administrador)

```bash
# Instalar dependencias
pip install -r requirements.txt

# Editar VMs en pcs_config.json
# Iniciar controlador
python app.py
```

El navegador se abrirá automáticamente en `http://localhost:5000`.

### Agente (cada VM Red Hat)

```bash
# Copiar agente.py a la VM
# Instalar dependencias
pip install psutil

# Ejecutar agente
python agente.py
# Seguir las instrucciones interactivas:
#   - Puerto de escucha (por defecto 6666)
#   - Contraseña (vacío = sin autenticación)
#   - Rutas de certificado TLS
```

## Compilar a .exe con PyInstaller

```bash
pip install pyinstaller
python build_exe.py
```

Los ejecutables se generarán en:
- `release/Controlador/MultiMachine_Controller.exe`
- `release/Agente/MultiMachine_Agent.exe`

## Configuración del firewall (Red Hat / CentOS)

```bash
firewall-cmd --add-port=6666/tcp --permanent
firewall-cmd --reload
```

## Generar certificado TLS autofirmado

```bash
openssl req -x509 -newkey rsa:4096 -keyout agent.key -out agent.crt \
    -days 3650 -nodes -subj "/CN=multimachine-agent"
```

## Requisitos de red

- Usar **modo Bridge** en VirtualBox/VMware (NO NAT).
- El PC administrador debe poder alcanzar la IP de cada VM directamente.
- Verificar conectividad: `ping <IP_VM>` y `telnet <IP_VM> 6666`.

## Configuración con VMs en modo NAT (túnel SSH)

Cuando las VMs corren en modo **NAT** dentro de un host intermedio (por ejemplo SteamOS, otra PC Linux), el controlador no puede alcanzar directamente la IP de la VM. La solución es un **túnel SSH reverse** combinado con **socat**:

```
Windows (PC1)              Host intermedio (PC2)              VM (NAT dentro de PC2)
IP_PC1                     IP_PC2                             IP_VM
     │                          │                                 │
     │  TLS :SOCAT_PORT         │                                 │
     ├─────────────────────────►│ socat :SOCAT_PORT → :TUNNEL_PORT│
     │                          ├──── túnel SSH reverse ─────────►│
     │                          │                           agente :AGENT_PORT
```

### Paso 1 — Configurar el host intermedio (PC2)

Ejecutar en **PC2** (SteamOS / Arch Linux / cualquier Linux):

```bash
chmod +x deploy/setup_socat.sh
./deploy/setup_socat.sh [SOCAT_PORT] [TUNNEL_PORT]
# Ejemplo con puertos por defecto:
./deploy/setup_socat.sh 6667 6666
```

Esto instala el servicio `multimachine-socat` que reenvía `0.0.0.0:6667 → 127.0.0.1:6666`.

### Paso 2 — Configurar la VM

Ejecutar en la **VM** (RHEL 9/10):

```bash
chmod +x deploy/setup_tunnel.sh
./deploy/setup_tunnel.sh REMOTE_USER REMOTE_HOST [AGENT_PORT] [TUNNEL_PORT]
# Ejemplo:
./deploy/setup_tunnel.sh deck 192.168.1.83 6666 6666
```

Esto instala el servicio `multimachine-tunnel` que mantiene el túnel SSH reverse activo.

### Paso 3 — Configurar `pcs_config.json`

Apuntar el controlador a **IP_PC2:SOCAT_PORT** en lugar de la IP de la VM:

```json
{
    "pcs": [
        {"name": "VM-RedHat-1", "ip": "192.168.1.83", "port": 6667, "password": ""},
        {"name": "VM-RedHat-2", "ip": "192.168.1.101", "port": 6666, "password": ""}
    ]
}
```

### Verificar desde Windows

```powershell
Test-NetConnection -ComputerName 192.168.1.83 -Port 6667
```

### Variables de configuración

| Variable      | Descripción                                      | Valor por defecto |
|---------------|--------------------------------------------------|-------------------|
| `REMOTE_USER` | Usuario SSH en el host intermedio (PC2)          | —                 |
| `REMOTE_HOST` | IP o hostname del host intermedio (PC2)          | —                 |
| `AGENT_PORT`  | Puerto del agente TLS en la VM                   | `6666`            |
| `TUNNEL_PORT` | Puerto local del túnel SSH en PC2                | `6666`            |
| `SOCAT_PORT`  | Puerto externo de socat en PC2 (apuntado por el controlador) | `6667` |

> **Nota:** Asegúrese de que `GatewayPorts yes` esté en `/etc/ssh/sshd_config` de PC2 y de que el puerto `SOCAT_PORT` esté abierto en el firewall de PC2.

## Comandos disponibles

| Comando           | Descripción                          |
|-------------------|--------------------------------------|
| `PING`            | Verificar conectividad               |
| `INFO`            | CPU, memoria y disco                 |
| `LIST_PROCESSES`  | Listar procesos en ejecución         |
| `LAUNCH_APP`      | Lanzar aplicación por nombre/ruta    |
| `CLOSE_APP`       | Cerrar proceso por nombre o PID      |
| `OPEN_URL`        | Abrir URL en el navegador de la VM   |
| `LOCK_PC`         | Bloquear sesión                      |
| `SHUTDOWN`        | Apagar equipo (con retraso opcional) |
| `CANCEL_SHUTDOWN` | Cancelar apagado programado          |
| `WRITE_FILE`      | Escribir contenido en un archivo     |

## Protocolo de autenticación

1. Agente envía: `{"type":"agent_ready","hostname":...,"requires_auth":true,"nonce":"<uuid>"}`
2. Controlador envía: `{"command":"AUTH","proof":"<HMAC-SHA256(password, nonce)>"}`
3. Agente responde: `{"status":"ok","message":"Authenticated"}` o error.

## Licencia

MIT
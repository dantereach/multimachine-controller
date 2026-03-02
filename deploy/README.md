# 🚀 Guía de Despliegue: MultiMachine Controller con VMs en NAT

## El problema

Cuando las VMs corren en **modo NAT** (VirtualBox/VMware), cada VM tiene una IP interna (p.ej. `10.0.2.15`) que **no es accesible directamente** desde otro equipo de la red. El controlador en Windows no puede conectarse a esa IP.

## La solución

Usar un **host intermedio (PC2)** que sí es accesible desde Windows, combinando:

1. **Túnel SSH reverse** — la VM abre un túnel hacia PC2, exponiendo su puerto `6666` en PC2.
2. **socat** — en PC2 reenvía el tráfico del puerto externo (`6667`) al túnel local (`6666`).
3. El **controlador** en Windows apunta a `IP_PC2:6667`.

## 🗺️ Diagrama de arquitectura

```
Windows (PC1)                Host intermedio (PC2)              VM (dentro de PC2)
Controlador Flask            SSH + socat                        Agente TLS
IP_PC1                       IP_PC2                             IP_VM (NAT)
     │                            │                                 │
     │  TLS :6667                 │                                 │
     ├───────────────────────────►│ socat :6667 → :6666             │
     │                            ├──── túnel SSH reverse ─────────►│
     │                            │                           agente :6666
```

---

## 📋 Paso 0: Identificar tus datos de red

Anota estos valores antes de empezar:

| Variable      | Descripción                              | Cómo obtenerla                    | Ejemplo          |
|---------------|------------------------------------------|-----------------------------------|------------------|
| `IP_PC2`      | IP del host intermedio en la red local   | `ip -4 addr show wlan0`           | `192.168.1.83`   |
| `IP_VM`       | IP interna de la VM en modo NAT          | `hostname -I`                     | `10.0.2.15`      |
| `USUARIO_PC2` | Usuario SSH del host intermedio          | —                                 | `deck`           |
| `USUARIO_VM`  | Usuario de la VM                         | —                                 | `dr`             |

---

## 🔧 Paso 1: Preparar la VM (agente)

Conéctate a la VM (por consola de VirtualBox o SSH desde PC2 si ya tienes acceso).

### 1.1 Instalar dependencias

```bash
pip install psutil
```

### 1.2 Copiar y ejecutar el agente

```bash
# Copiar agente.py a la VM (desde PC2 si tienes acceso SSH a la VM)
scp agente.py USUARIO_VM@IP_VM:~/

# Ejecutar el agente en la VM
python agente.py
# Seguir las instrucciones:
#   - Puerto: 6666
#   - Contraseña: (vacío = sin autenticación)
#   - Certificado TLS: generar o indicar rutas
```

### 1.3 Confirmar que el agente escucha

```bash
ss -tlnp | grep :6666
```

Deberías ver algo como:
```
LISTEN  0  128  0.0.0.0:6666  0.0.0.0:*  users:(("python",pid=1234,fd=4))
```

### 1.4 Abrir puerto en el firewall de la VM

```bash
sudo firewall-cmd --add-port=6666/tcp --permanent && sudo firewall-cmd --reload
```

### 1.5 Anotar la IP interna de la VM

```bash
hostname -I
# Ejemplo: 10.0.2.15
```

---

## 🖥️ Paso 2: Preparar el host intermedio (PC2)

### 2.1 Instalar y habilitar SSH

```bash
# Arch / SteamOS
sudo pacman -S openssh
sudo systemctl enable --now sshd

# Fedora / Red Hat
sudo dnf install openssh-server
sudo systemctl enable --now sshd

# Debian / Ubuntu
sudo apt install openssh-server
sudo systemctl enable --now ssh
```

### 2.2 Configurar GatewayPorts en sshd

Edita `/etc/ssh/sshd_config` y añade o modifica:

```ini
GatewayPorts yes
```

Luego reinicia el servicio:

```bash
sudo systemctl restart sshd
```

> **¿Por qué?** Sin `GatewayPorts yes`, el túnel reverse SSH solo escucha en `127.0.0.1`, no en la IP externa de PC2. Con esta opción el túnel escucha en `0.0.0.0`.

### 2.3 Instalar socat

```bash
# Arch / SteamOS
sudo pacman -S socat

# Fedora / Red Hat
sudo dnf install socat

# Debian / Ubuntu
sudo apt install socat
```

### 2.4 Anotar la IP de PC2

```bash
ip -4 addr show wlan0
# o
ip -4 addr show eth0
```

---

## 🔑 Paso 3: Configurar SSH keys

Esto permite que la VM abra el túnel SSH hacia PC2 **sin pedir contraseña**, necesario para el servicio systemd.

### 3.1 Generar clave SSH en la VM

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
```

### 3.2 Copiar la clave pública al host intermedio

```bash
ssh-copy-id USUARIO_PC2@IP_PC2
# Ejemplo: ssh-copy-id deck@192.168.1.83
```

### 3.3 Verificar que funciona sin contraseña

```bash
ssh USUARIO_PC2@IP_PC2 echo "OK"
# Debe imprimir: OK
```

---

## 🚇 Paso 4: Crear el túnel SSH reverse (en la VM)

### 4.1 Prueba manual del túnel

Antes de crear el servicio, verifica que el túnel funciona:

```bash
ssh -N -R 0.0.0.0:6666:IP_VM:6666 USUARIO_PC2@IP_PC2
# Ejemplo: ssh -N -R 0.0.0.0:6666:10.0.2.15:6666 deck@192.168.1.83
```

Mientras este comando corra, el puerto `6666` de PC2 debería estar activo. Prueba desde PC2:

```bash
ss -tlnp | grep :6666
```

Cuando confirmes que funciona, cancela con `Ctrl+C` y crea el servicio.

### 4.2 Crear el servicio systemd del túnel

Crea el archivo `/etc/systemd/system/multimachine-tunnel.service`:

```ini
[Unit]
Description=MultiMachine Reverse SSH Tunnel
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/ssh -N \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=accept-new \
    -R 0.0.0.0:6666:IP_VM:6666 USUARIO_PC2@IP_PC2
Restart=always
RestartSec=10
User=USUARIO_VM

[Install]
WantedBy=multi-user.target
```

**Ejemplo real** (con los valores del diagrama):

```ini
[Unit]
Description=MultiMachine Reverse SSH Tunnel
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/ssh -N \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=accept-new \
    -R 0.0.0.0:6666:10.0.2.15:6666 deck@192.168.1.83
Restart=always
RestartSec=10
User=dr

[Install]
WantedBy=multi-user.target
```

### 4.3 Habilitar y arrancar el servicio

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now multimachine-tunnel.service
```

### 4.4 Verificar el estado del servicio

```bash
sudo systemctl status multimachine-tunnel.service
```

---

## 📡 Paso 5: Crear el servicio socat (en PC2)

### 5.1 Prueba manual de socat

Antes de crear el servicio, verifica que socat reenvía correctamente:

```bash
socat TCP-LISTEN:6667,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:6666 &
```

Prueba desde Windows:
```powershell
Test-NetConnection -ComputerName IP_PC2 -Port 6667
```

Cuando confirmes que funciona, mata el proceso con `kill %1` o `fg` + `Ctrl+C`, y crea el servicio.

### 5.2 Crear el servicio systemd de socat

Crea el archivo `/etc/systemd/system/multimachine-socat.service`:

```ini
[Unit]
Description=MultiMachine socat forwarding (external port to SSH tunnel)
After=network-online.target

[Service]
ExecStart=/usr/bin/socat TCP-LISTEN:6667,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:6666
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 5.3 Habilitar y arrancar el servicio

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now multimachine-socat.service
```

### 5.4 Abrir el puerto 6667 en el firewall de PC2

```bash
# firewalld (Fedora / Red Hat / SteamOS)
sudo firewall-cmd --add-port=6667/tcp --permanent
sudo firewall-cmd --reload

# ufw (Debian / Ubuntu)
sudo ufw allow 6667/tcp
```

---

## ✅ Paso 6: Verificar que todo funciona

### En PC2 — comprobar puertos activos

```bash
# El túnel SSH reverse debe estar escuchando en 6666
ss -tlnp | grep :6666

# socat debe estar escuchando en 6667
ss -tlnp | grep :6667
```

### En PC2 — probar TLS contra el agente

```bash
openssl s_client -connect 127.0.0.1:6667 -servername localhost -brief
```

Si el agente responde, verás `CONNECTION ESTABLISHED` y los datos del certificado.

### Desde Windows (PC1) — probar conectividad

```powershell
Test-NetConnection -ComputerName IP_PC2 -Port 6667
# TcpTestSucceeded debe ser True
```

---

## 🖱️ Paso 7: Configurar el controlador en Windows

### 7.1 Editar `pcs_config.json`

Apunta el controlador a `IP_PC2` con el puerto de socat (`6667`):

```json
{
    "pcs": [
        {
            "id": "5149dbe9-8ae2-4ebc-852c-ef79fd26790f",
            "name": "VM-RedHat-1",
            "ip": "192.168.1.83",
            "port": 6667,
            "password": ""
        }
    ]
}
```

> El campo `ip` es la IP de **PC2** (no de la VM), y el puerto es el de **socat** (`6667`), no el del agente.

### 7.2 Ejecutar el controlador

```bash
python app.py
```

El navegador se abrirá en `http://localhost:5000`. La VM debería aparecer como **conectada**.

---

## ➕ Paso 8: Agregar más VMs

Cada VM adicional necesita un par de puertos únicos en PC2.

| VM   | Puerto agente | Puerto túnel en PC2 | Puerto socat en PC2 |
|------|---------------|---------------------|---------------------|
| VM-1 | 6666          | 6666                | 6667                |
| VM-2 | 6666          | 6668                | 6669                |
| VM-3 | 6666          | 6670                | 6671                |

### Para VM-2: túnel en la VM

Ajusta el servicio `multimachine-tunnel.service` de VM-2 (o crea `multimachine-tunnel-vm2.service`):

```ini
ExecStart=/usr/bin/ssh -N \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o StrictHostKeyChecking=accept-new \
    -R 0.0.0.0:6668:IP_VM2:6666 USUARIO_PC2@IP_PC2
```

### Para VM-2: socat en PC2

Crea `/etc/systemd/system/multimachine-socat-vm2.service`:

```ini
[Unit]
Description=MultiMachine socat forwarding VM-2
After=network-online.target

[Service]
ExecStart=/usr/bin/socat TCP-LISTEN:6669,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:6668
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now multimachine-socat-vm2.service
sudo firewall-cmd --add-port=6669/tcp --permanent && sudo firewall-cmd --reload
```

### En `pcs_config.json`

```json
{
    "pcs": [
        {
            "id": "5149dbe9-8ae2-4ebc-852c-ef79fd26790f",
            "name": "VM-RedHat-1",
            "ip": "192.168.1.83",
            "port": 6667,
            "password": ""
        },
        {
            "id": "7a3f2c1d-0e4b-4d8a-9f1c-2b3e5d6a7890",
            "name": "VM-RedHat-2",
            "ip": "192.168.1.83",
            "port": 6669,
            "password": ""
        }
    ]
}
```

---

## 📝 Checklist rápido para nueva red

| # | Dónde   | Qué hacer                                                          |
|---|---------|--------------------------------------------------------------------|
| 1 | VM      | Ejecutar `agente.py` y confirmar con `ss -tlnp \| grep :6666`      |
| 2 | VM      | Abrir puerto `6666` en firewall                                    |
| 3 | PC2     | Instalar y habilitar `sshd` con `GatewayPorts yes`                 |
| 4 | PC2     | Instalar `socat`                                                   |
| 5 | VM      | Generar SSH key y copiarla a PC2 con `ssh-copy-id`                 |
| 6 | VM      | Crear y habilitar `multimachine-tunnel.service`                    |
| 7 | PC2     | Crear y habilitar `multimachine-socat.service`, abrir puerto `6667`|
| 8 | Windows | Actualizar `pcs_config.json` con `IP_PC2` y puerto `6667`          |

---

## 🩺 Troubleshooting

| Síntoma                          | Causa probable                              | Solución                                              |
|----------------------------------|---------------------------------------------|-------------------------------------------------------|
| `TcpTestSucceeded: False`        | Firewall bloqueando el puerto en PC2        | Abrir puerto `6667` (ver Paso 5.4)                    |
| Túnel se cae frecuentemente      | Conexión inestable                          | systemd lo reinicia automáticamente (normal)          |
| `Connection refused` en puerto   | Agente no está corriendo en la VM           | Revisar `systemctl status multimachine-tunnel.service` y arrancar `agente.py` |
| Error TLS / certificado          | El controlador no verifica cert (correcto)  | El controlador ya usa `CERT_NONE`; no requiere acción |
| Puerto no accesible desde Windows| nftables bloqueando tráfico en PC2          | `sudo nft flush ruleset` (temporal, para diagnóstico) |
| Túnel activo pero socat falla    | socat no encontrado en `/usr/bin/socat`     | Verificar ruta con `which socat` y ajustar en el servicio |

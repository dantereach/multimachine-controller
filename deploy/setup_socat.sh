#!/usr/bin/env bash
# setup_socat.sh — Run on the intermediate host (PC2, e.g. SteamOS / Arch Linux)
# Sets up a systemd service that uses socat to forward external traffic to the
# local SSH reverse-tunnel listener, allowing the Windows controller to reach
# the VM agent through the tunnel.
#
# Usage:
#   ./setup_socat.sh [SOCAT_PORT] [TUNNEL_PORT]
#
# Parameters:
#   SOCAT_PORT    External port socat listens on (default: 6667)
#   TUNNEL_PORT   Local port bound by the SSH reverse tunnel  (default: 6666)
#
# Example:
#   ./setup_socat.sh 6667 6666

set -euo pipefail

# ── Parameters ────────────────────────────────────────────────────────────────
SOCAT_PORT="${1:-6667}"
TUNNEL_PORT="${2:-6666}"

SERVICE_NAME="multimachine-socat"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# ── Check socat is installed ──────────────────────────────────────────────────
if ! command -v socat &>/dev/null; then
    echo "[ERROR] socat is not installed."
    echo "        Install it with:"
    echo "          Arch/SteamOS : sudo pacman -S socat"
    echo "          Debian/Ubuntu: sudo apt install socat"
    echo "          RHEL/CentOS  : sudo dnf install socat"
    exit 1
fi
echo "[INFO] socat found: $(command -v socat)"

# ── Check GatewayPorts in sshd_config ────────────────────────────────────────
SSHD_CONFIG="/etc/ssh/sshd_config"
if [[ -f "$SSHD_CONFIG" ]]; then
    if grep -qE '^\s*GatewayPorts\s+yes' "$SSHD_CONFIG"; then
        echo "[INFO] GatewayPorts yes — found in sshd_config."
    else
        echo "[WARN] GatewayPorts yes not found in ${SSHD_CONFIG}."
        echo "       The SSH tunnel may not accept connections from external hosts."
        echo "       Add the following line to ${SSHD_CONFIG} and restart sshd:"
        echo "         GatewayPorts yes"
        echo "       Then run: sudo systemctl restart sshd"
    fi
fi

# ── Write systemd service file ────────────────────────────────────────────────
echo "[INFO] Writing service file: $SERVICE_FILE"
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=MultiMachine socat forwarding (external port to SSH tunnel)
After=network-online.target

[Service]
ExecStart=/usr/bin/socat TCP-LISTEN:${SOCAT_PORT},fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:${TUNNEL_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# ── Enable and start service ──────────────────────────────────────────────────
echo "[INFO] Reloading systemd and enabling ${SERVICE_NAME} ..."
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

# ── Open firewall port (firewalld) ────────────────────────────────────────────
if command -v firewall-cmd &>/dev/null; then
    echo "[INFO] Opening port ${SOCAT_PORT}/tcp in firewalld ..."
    sudo firewall-cmd --add-port="${SOCAT_PORT}/tcp" --permanent
    sudo firewall-cmd --reload
    echo "[INFO] Firewall port ${SOCAT_PORT}/tcp opened."
else
    echo "[INFO] firewalld not found — skipping firewall rule."
    echo "       If you use iptables/nftables, open port ${SOCAT_PORT}/tcp manually."
    echo "       WARNING: ensure only trusted hosts can reach port ${SOCAT_PORT}/tcp."
fi

echo ""
echo "[OK] socat service installed and started."
echo "     Check status : sudo systemctl status ${SERVICE_NAME}"
echo "     View logs    : sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "     Forwarding   : 0.0.0.0:${SOCAT_PORT} → 127.0.0.1:${TUNNEL_PORT}"
echo "     Controller should point to <IP_PC2>:${SOCAT_PORT}"

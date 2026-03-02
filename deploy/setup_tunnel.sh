#!/usr/bin/env bash
# setup_tunnel.sh — Run on the VM (agent host)
# Sets up a systemd service that maintains a reverse SSH tunnel to the
# intermediate host (PC2), forwarding the agent TLS port so the controller
# on Windows can reach it via socat on PC2.
#
# Usage:
#   ./setup_tunnel.sh REMOTE_USER REMOTE_HOST [AGENT_PORT] [TUNNEL_PORT]
#
# Parameters:
#   REMOTE_USER   Username on the intermediate host (PC2)
#   REMOTE_HOST   IP or hostname of the intermediate host (PC2)
#   AGENT_PORT    Port the agent listens on in this VM  (default: 6666)
#   TUNNEL_PORT   Port exposed on the intermediate host (default: 6666)
#
# Example:
#   ./setup_tunnel.sh deck 192.168.1.83 6666 6666

set -euo pipefail

# ── Parameters ────────────────────────────────────────────────────────────────
REMOTE_USER="${1:-}"
REMOTE_HOST="${2:-}"
AGENT_PORT="${3:-6666}"
TUNNEL_PORT="${4:-6666}"

if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
    echo "Usage: $0 REMOTE_USER REMOTE_HOST [AGENT_PORT] [TUNNEL_PORT]"
    exit 1
fi

CURRENT_USER="$(whoami)"
SSH_KEY="$HOME/.ssh/id_ed25519_multimachine"
SERVICE_NAME="multimachine-tunnel"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# ── Detect VM IP ──────────────────────────────────────────────────────────────
VM_IP="$(hostname -I | awk '{print $1}')"
echo "[INFO] VM IP detected: $VM_IP"

# ── Generate SSH key (idempotent) ─────────────────────────────────────────────
if [[ ! -f "$SSH_KEY" ]]; then
    echo "[INFO] Generating SSH key: $SSH_KEY"
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -C "multimachine-tunnel@$(hostname)"
else
    echo "[INFO] SSH key already exists: $SSH_KEY"
fi

# ── Copy public key to intermediate host ─────────────────────────────────────
echo "[INFO] Copying public key to ${REMOTE_USER}@${REMOTE_HOST} ..."
ssh-copy-id -i "${SSH_KEY}.pub" "${REMOTE_USER}@${REMOTE_HOST}"

# ── Write systemd service file ────────────────────────────────────────────────
echo "[INFO] Writing service file: $SERVICE_FILE"
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
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
  -i ${SSH_KEY} \
  -R 127.0.0.1:${TUNNEL_PORT}:${VM_IP}:${AGENT_PORT} \
  ${REMOTE_USER}@${REMOTE_HOST}
Restart=always
RestartSec=10
User=${CURRENT_USER}

[Install]
WantedBy=multi-user.target
EOF

# ── Enable and start service ──────────────────────────────────────────────────
echo "[INFO] Reloading systemd and enabling ${SERVICE_NAME} ..."
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"

echo ""
echo "[OK] Tunnel service installed and started."
echo "     Check status : sudo systemctl status ${SERVICE_NAME}"
echo "     View logs    : sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "     Tunnel route : ${VM_IP}:${AGENT_PORT} → ${REMOTE_HOST}:${TUNNEL_PORT}"
echo "     Controller should point to ${REMOTE_HOST}:<socat_port>"

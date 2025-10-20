#!/usr/bin/env bash
set -euo pipefail

# Re-run as root if needed
if [[ $EUID -ne 0 ]]; then
  exec sudo -E bash "$0" "$@"
fi

echo "[1/6] Apt packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3-pip python3-venv python3-picamera2 \
  libatlas-base-dev bluetooth bluez \
  python3-opencv python3-numpy \
  git

echo "[2/6] Create system user 'picarx' ..."
if ! id -u picarx >/dev/null 2>&1; then
  adduser --system --group --home /opt/picarx-ble picarx
fi
usermod -aG video,bluetooth,spi,i2c,gpio picarx || true

echo "[3/6] Install app into /opt/picarx-ble ..."
install -d -o picarx -g picarx /opt/picarx-ble
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp -f "$SCRIPT_DIR/picarx_ble.py" /opt/picarx-ble/
cp -f "$SCRIPT_DIR/requirements.txt" /opt/picarx-ble/
chown -R picarx:picarx /opt/picarx-ble

echo "[4/6] Python venv + requirements ..."
sudo -u picarx python3 -m venv /opt/picarx-ble/venv
/opt/picarx-ble/venv/bin/pip install --upgrade pip
/opt/picarx-ble/venv/bin/pip install -r /opt/picarx-ble/requirements.txt

echo "[5/6] Install systemd service ..."
install -D -m 0644 "$SCRIPT_DIR/service/picarx-ble.service" 
/etc/systemd/system/picarx-ble.service

echo "[6/6] Enable + start ..."
systemctl daemon-reload
systemctl enable picarx-ble.service
systemctl restart picarx-ble.service

echo "Done. Check:  sudo systemctl status picarx-ble"
echo "Logs:         journalctl -u picarx-ble -f"


#!/bin/sh
# One-time system setup for Mängukogu on the Pi. Run with: sudo sh ~/mangukogu/deploy/setup.sh
# Safe to run again.
set -eu

# The account that runs `sudo` owns the app (it lives in that user's home folder).
USER_NAME=${SUDO_USER:-}
APP_DIR=/home/$USER_NAME/mangukogu

if [ "$(id -u)" -ne 0 ] || [ -z "$USER_NAME" ]; then
    echo "Run this with sudo." >&2
    exit 1
fi

echo "== Mängukogu service (port 8020)"
cat > /etc/systemd/system/mangukogu.service <<UNIT
[Unit]
Description=Mängukogu (games for the kindergarten)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER_NAME
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8020
Restart=on-failure
# The Pi has 1 GB of RAM shared with the other apps.
MemoryMax=200M

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now mangukogu.service
systemctl restart mangukogu.service
echo "Done: http://$(hostname).local:8020"

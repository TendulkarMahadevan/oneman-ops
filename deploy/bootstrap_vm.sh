#!/usr/bin/env bash
# Run once as root on a fresh Ubuntu 22.04/24.04 Vultr Cloud Compute VM:
#   sudo bash deploy/bootstrap_vm.sh
# Installs Docker, enables a host firewall that allows only SSH/HTTP/HTTPS, and turns on unattended upgrades.
# It does not touch your .env or any secrets.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }

apt-get update -y
apt-get install -y ca-certificates curl ufw unattended-upgrades git

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status verbose

dpkg-reconfigure -f noninteractive unattended-upgrades
echo "Bootstrap done. Next: clone the repo, create .env from .env.example, then 'docker compose up -d --build'."
echo "NOTE: Docker-published ports bypass ufw. Only Caddy publishes ports in docker-compose.yml (80/443), by design."

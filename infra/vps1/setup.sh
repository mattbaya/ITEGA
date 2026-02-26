#!/usr/bin/env bash
# ============================================================
# VPS 1 Setup — Keycloak + Newshare Profiles
# Target: DigitalOcean 4 GB Droplet, Ubuntu 22.04+
#
# Usage:
#   chmod +x setup.sh
#   sudo ./setup.sh
# ============================================================

set -euo pipefail

# ---- Configuration ----
DOMAIN="auth.newshare.example"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-admin@newshare.example}"
SWAP_SIZE="2G"

# ---- Preflight checks ----
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root." >&2
    exit 1
fi

echo "==> Starting VPS 1 setup for ${DOMAIN}"

# ---- 1. System updates ----
echo "==> Updating system packages..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq

# ---- 2. Swap (essential for 4 GB VPS running Keycloak + PG) ----
if ! swapon --show | grep -q '/swapfile'; then
    echo "==> Creating ${SWAP_SIZE} swap file..."
    fallocate -l "${SWAP_SIZE}" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    # Guard against duplicate fstab/sysctl entries on re-run
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    sysctl vm.swappiness=10
    grep -q 'vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
else
    echo "==> Swap already configured, skipping."
fi

# ---- 3. Install required packages ----
echo "==> Installing dependencies..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    ufw \
    nginx \
    certbot \
    python3-certbot-nginx \
    fail2ban

# ---- 4. Install Docker Engine ----
if ! command -v docker &>/dev/null; then
    echo "==> Installing Docker..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --yes --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin

    systemctl enable --now docker
else
    echo "==> Docker already installed, skipping."
fi

# ---- 5. Firewall ----
echo "==> Configuring UFW firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ---- 6. Fail2Ban ----
echo "==> Configuring Fail2Ban..."
systemctl enable --now fail2ban

# ---- 7. TLS certificates ----
echo "==> Obtaining TLS certificate for ${DOMAIN}..."
if [[ ! -d "/etc/letsencrypt/live/${DOMAIN}" ]]; then
    # Stop Nginx briefly so certbot can bind to port 80
    systemctl stop nginx || true
    certbot certonly \
        --standalone \
        --non-interactive \
        --agree-tos \
        --email "${CERTBOT_EMAIL}" \
        -d "${DOMAIN}"
    systemctl start nginx
else
    echo "==> Certificate already exists, skipping."
fi

# ---- 8. Deploy Nginx configuration ----
echo "==> Installing Nginx configuration..."
cp nginx.conf "/etc/nginx/sites-available/${DOMAIN}"
ln -sf "/etc/nginx/sites-available/${DOMAIN}" "/etc/nginx/sites-enabled/${DOMAIN}"
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ---- 9. Create providers directory for Keycloak SPI JARs ----
mkdir -p ./providers

# ---- 10. Prepare .env ----
if [[ ! -f .env ]]; then
    echo "==> No .env file found. Copying from .env.example..."
    cp .env.example .env
    chmod 600 .env
    echo "WARNING: Edit .env and set real passwords before starting Docker."
else
    echo "==> .env already exists, leaving it untouched."
fi

# ---- 11. Set secure permissions ----
chmod 600 .env 2>/dev/null || true
chmod 755 init-db.sh

# ---- 12. Certbot auto-renewal ----
echo "==> Verifying certbot renewal timer..."
systemctl enable --now certbot.timer

echo ""
echo "============================================================"
echo "  VPS 1 setup complete."
echo ""
echo "  Next steps:"
echo "    1. Edit .env with real passwords"
echo "    2. Run: docker compose up -d"
echo "    3. Apply SQL migration:"
echo "       docker exec -i newshare-postgres psql -U keycloak -d newshare_profiles < ../sql/001_newshare_profiles.sql"
echo "============================================================"

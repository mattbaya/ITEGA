#!/usr/bin/env bash
# ============================================================
# VPS 2 Setup — ALS Services (Auth, Logging, Settlement)
# Target: DigitalOcean 4 GB Droplet, Ubuntu 22.04+
#
# Usage:
#   chmod +x setup.sh
#   sudo ./setup.sh
# ============================================================

set -euo pipefail

# ---- Configuration ----
DOMAINS=("als.newshare.example" "network.newshare.example" "dashboard.newshare.example")
CERTBOT_EMAIL="${CERTBOT_EMAIL:-admin@newshare.example}"
SWAP_SIZE="2G"

# ---- Preflight checks ----
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root." >&2
    exit 1
fi

echo "==> Starting VPS 2 setup for ALS services"

# ---- 1. System updates ----
echo "==> Updating system packages..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq

# ---- 2. Swap (essential for 4 GB VPS) ----
if ! swapon --show | grep -q '/swapfile'; then
    echo "==> Creating ${SWAP_SIZE} swap file..."
    fallocate -l "${SWAP_SIZE}" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    sysctl vm.swappiness=10
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
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
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
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
echo "==> Obtaining TLS certificates..."
# Stop Nginx briefly so certbot can bind to port 80
systemctl stop nginx || true

for DOMAIN in "${DOMAINS[@]}"; do
    if [[ ! -d "/etc/letsencrypt/live/${DOMAIN}" ]]; then
        echo "==> Requesting certificate for ${DOMAIN}..."
        certbot certonly \
            --standalone \
            --non-interactive \
            --agree-tos \
            --email "${CERTBOT_EMAIL}" \
            -d "${DOMAIN}"
    else
        echo "==> Certificate for ${DOMAIN} already exists, skipping."
    fi
done

systemctl start nginx

# ---- 8. Create web roots ----
echo "==> Creating web root directories..."
mkdir -p /var/www/network-discovery/.well-known
mkdir -p /var/www/dashboard/dist
mkdir -p /var/www/certbot

# Copy network discovery JSON
cp network-discovery/newshare-network.json /var/www/network-discovery/newshare-network.json

# Also serve it as a well-known resource
ln -sf /var/www/network-discovery/newshare-network.json \
       /var/www/network-discovery/.well-known/newshare-network.json

# ---- 9. Deploy Nginx configuration ----
echo "==> Installing Nginx configuration..."
cp nginx.conf /etc/nginx/sites-available/als-services
ln -sf /etc/nginx/sites-available/als-services /etc/nginx/sites-enabled/als-services
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ---- 10. Create secrets directory for JWT keys ----
echo "==> Setting up secrets directory..."
mkdir -p ./secrets
chmod 700 ./secrets

if [[ ! -f ./secrets/jwt_private.pem ]]; then
    echo "==> Generating JWT signing key pair..."
    openssl genpkey -algorithm RSA -out ./secrets/jwt_private.pem -pkeyopt rsa_keygen_bits:2048
    openssl rsa -pubout -in ./secrets/jwt_private.pem -out ./secrets/jwt_public.pem
    chmod 600 ./secrets/jwt_private.pem
    chmod 644 ./secrets/jwt_public.pem
    echo "==> JWT key pair generated."
else
    echo "==> JWT keys already exist, skipping."
fi

# ---- 11. Prepare .env ----
if [[ ! -f .env ]]; then
    echo "==> No .env file found. Copying from .env.example..."
    cp .env.example .env
    chmod 600 .env
    echo "WARNING: Edit .env and set real passwords before starting Docker."
else
    echo "==> .env already exists, leaving it untouched."
fi

# ---- 12. Set secure permissions ----
chmod 600 .env 2>/dev/null || true
chmod 755 init-db.sh

# ---- 13. Certbot auto-renewal ----
echo "==> Verifying certbot renewal timer..."
systemctl enable --now certbot.timer

echo ""
echo "============================================================"
echo "  VPS 2 setup complete."
echo ""
echo "  Next steps:"
echo "    1. Edit .env with real passwords"
echo "    2. Run: docker compose up -d"
echo "    3. Apply SQL migrations:"
echo "       docker exec -i als-postgres psql -U als -d als_logs < ../sql/002_als_logs.sql"
echo "       docker exec -i als-postgres psql -U als -d als_settlement < ../sql/003_als_settlement.sql"
echo "============================================================"

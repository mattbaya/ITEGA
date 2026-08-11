#!/bin/bash
# bootstrap-almalinux.sh — prepare a fresh AlmaLinux 10 host to run Newshare services.
#
# Idempotent: safe to re-run. Handles the parts common to both hosts —
# a non-root deploy user, SSH lockdown, CSF, Apache, Docker, and restic.
#
# Usage:  ./bootstrap-almalinux.sh <role>      where role is vps1 | vps2
#
# Deliberate choices worth knowing:
#
#   CSF rather than firewalld — matches the firewall already in use on the
#   other svaha hosts, so one set of habits covers everything.
#
#   Apache rather than Nginx, for the same reason. It terminates TLS and
#   reverse-proxies to containers bound on 127.0.0.1; no service port is ever
#   exposed to the internet directly.
#
#   Docker for the services themselves, so the stack is identical to what runs
#   locally and nothing depends on the host's Python or Java versions.

set -euo pipefail

ROLE="${1:-}"
if [[ "$ROLE" != "vps1" && "$ROLE" != "vps2" ]]; then
    echo "usage: $0 <vps1|vps2>" >&2
    exit 2
fi

log() { echo -e "\n=== $* ==="; }

# ── Base packages ────────────────────────────────────────────────────
log "Base packages"
dnf -y -q install epel-release
dnf -y -q install curl wget git vim tar policycoreutils-python-utils \
    httpd mod_ssl python3-certbot-apache restic jq perl perl-libwww-perl \
    perl-LWP-Protocol-https perl-GDGraph postgresql16

# ── Deploy user ──────────────────────────────────────────────────────
# Services and the repo live under an unprivileged account; root login is
# disabled below, so this is the only way in.
log "Deploy user"
if ! id deploy &>/dev/null; then
    useradd -m -s /bin/bash deploy
    usermod -aG wheel deploy
fi
install -d -m 0700 -o deploy -g deploy /home/deploy/.ssh
if [[ -f /root/.ssh/authorized_keys ]]; then
    install -m 0600 -o deploy -g deploy /root/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
fi
# Passwordless sudo: there is no password on this account to type.
echo 'deploy ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-deploy
chmod 0440 /etc/sudoers.d/90-deploy

# ── SSH lockdown ─────────────────────────────────────────────────────
log "SSH lockdown"
cat > /etc/ssh/sshd_config.d/50-newshare.conf <<'EOF'
# Key-based access only, and not as root. Applied after the deploy user has a
# working key, so this cannot lock everyone out.
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
EOF
sshd -t && systemctl reload sshd

# ── Docker ───────────────────────────────────────────────────────────
log "Docker"
if ! command -v docker &>/dev/null; then
    dnf -y -q config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    dnf -y -q install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# Alma's minimal cloud image ships without kernel-modules-extra, which holds
# xt_addrtype. Docker's bridge driver needs it to write its NAT rules, and
# without it dockerd dies at startup with an iptables error that reads like a
# firewall problem rather than a missing module. Install it for the running
# kernel and load at every boot.
dnf -y -q install "kernel-modules-extra-$(uname -r)"
printf 'xt_addrtype\nbr_netfilter\niptable_nat\n' > /etc/modules-load.d/docker.conf
modprobe xt_addrtype || true
modprobe br_netfilter || true

systemctl enable --now docker
usermod -aG docker deploy

# ── Apache ───────────────────────────────────────────────────────────
# Reverse proxy only; vhosts are added per host after certificates exist.
log "Apache"
systemctl enable --now httpd
# SELinux is enforcing on Alma by default and blocks outbound proxy
# connections unless told otherwise. Without this, every proxied request
# fails with 503 and the cause is invisible from Apache's error log alone.
setsebool -P httpd_can_network_connect 1

# ── CSF ──────────────────────────────────────────────────────────────
# ConfigServer Ltd shut down on 31 August 2025 and download.configserver.com no
# longer resolves. CSF v15.00 was released under GPLv3 on the way out and is
# continued at configserver.dev (github.com/aetherinox/csf-firewall), which is
# actively maintained -- releases through v15.10 and commits within the week at
# time of writing. Any guide still pointing at the .com is dead.
log "ConfigServer Firewall"
if [[ ! -d /etc/csf ]]; then
    cd /usr/local/src
    rm -rf csf csf.tgz
    # The download sits behind Cloudflare, which serves a challenge page rather
    # than the tarball to a default curl user-agent. Without this the script
    # downloads HTML and the failure surfaces later as a confusing tar error.
    curl -fsSL -A "Mozilla/5.0" https://download.configserver.dev/csf.tgz -o csf.tgz

    # Look before running an installer as root. If what arrived is not a CSF
    # tarball -- a challenge page, a truncated download, something substituted
    # -- find out here rather than after executing it.
    # NOTE: list to a file rather than piping into grep. Under `set -o pipefail`,
    # `tar | grep -q` fails whenever grep matches: grep exits at the first hit,
    # tar takes SIGPIPE, and the pipeline reports failure precisely when the
    # check has succeeded.
    tar -tzf csf.tgz > /tmp/csf-manifest.txt
    file -b csf.tgz | grep -qi gzip || { echo "ERROR: csf.tgz is not gzip — got $(file -b csf.tgz)" >&2; exit 1; }
    grep -qx 'csf/install.generic.sh' /tmp/csf-manifest.txt || {
        echo "ERROR: csf.tgz does not contain csf/install.generic.sh — refusing to run it" >&2; exit 1; }

    tar -xzf csf.tgz
    grep -qi 'configserver' csf/install.generic.sh || { echo "ERROR: unexpected installer" >&2; exit 1; }

    # install.generic.sh, not install.sh: these are plain servers with no
    # control panel, and the generic installer is the one that suits them.
    cd csf && sh install.generic.sh
fi

# Inbound: SSH, HTTP, HTTPS only. Service ports (8000-8004) and the database
# stay closed -- every container binds to 127.0.0.1 and is reached through
# Apache, so there is nothing to open.
csf_set() { sed -i -E "s|^$1 = \".*\"|$1 = \"$2\"|" /etc/csf/csf.conf; }
csf_set TCP_IN  "22,80,443"
csf_set TCP_OUT "20,21,22,25,53,80,110,113,443,587,993,995"
csf_set UDP_IN  "53"
csf_set UDP_OUT "20,21,53,113,123"
csf_set TESTING "0"
# Docker manages its own iptables rules; CSF must not flush them or every
# container loses outbound networking the first time the firewall restarts.
csf_set DOCKER  "1"
systemctl enable --now csf lfd
csf -r >/dev/null

log "Done — $(hostname), role $ROLE"
echo "  docker:  $(docker --version)"
echo "  apache:  $(httpd -v | head -1)"
echo "  csf:     $(csf --version 2>/dev/null | head -1)"
echo "  restic:  $(restic version | head -1)"

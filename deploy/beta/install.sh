#!/usr/bin/env bash
# Run on the Ubuntu staging host only, never on the development machine.
set -euo pipefail
umask 077
[[ $EUID == 0 ]] || { echo 'Run as root on the Ubuntu host' >&2; exit 1; }
REPO=$(cd -- "$(dirname -- "$0")/../.." && pwd)
[[ "$REPO" == /opt/dem-beta ]] || { echo 'Clone the public tag to /opt/dem-beta first' >&2; exit 1; }
source /etc/os-release
[[ "$ID" == ubuntu ]] || { echo 'Ubuntu is required' >&2; exit 1; }
apt-get update
apt-get install -y ca-certificates curl openssl python3 tzdata unattended-upgrades logrotate iproute2 util-linux
install -m 0755 -d /etc/apt/keyrings
curl --fail --silent --show-error https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
    "$(dpkg --print-architecture)" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
if [[ ! -f /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
fi
[[ $(stat -c %s /swapfile) == 2147483648 ]] || { echo 'Existing /swapfile is not 2 GiB; inspect manually' >&2; exit 1; }
if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then swapon /swapfile; fi
if ! grep -q '^/swapfile ' /etc/fstab; then printf '/swapfile none swap sw 0 0\n' >> /etc/fstab; fi
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
ENV_FILE="$REPO/deploy/beta/.env"
if [[ ! -e "$ENV_FILE" ]]; then
    # Hex is URL-safe and shell-safe; stdout never contains credentials.
    temporary=$(mktemp "$REPO/deploy/beta/.env.XXXXXX")
    trap 'rm -f -- "$temporary"' EXIT
    admin_password=$(openssl rand -hex 32)
    owner_password=$(openssl rand -hex 32)
    app_password=$(openssl rand -hex 32)
    {
        printf 'DEM_BETA_DOMAIN=beta.example.invalid\nDEM_BETA_HOME=/var/lib/dem-beta\n'
        printf 'DEM_BETA_ADMIN_PASSWORD=%s\n' "$admin_password"
        printf 'DEM_BETA_OWNER_PASSWORD=%s\n' "$owner_password"
        printf 'DEM_BETA_APP_PASSWORD=%s\n' "$app_password"
        printf 'DEM_BETA_COMMIT=%s\n' "$(git -C "$REPO" rev-parse HEAD)"
        printf "DEM_BETA_RESET_SCHEDULE='Mon 04:00 Asia/Tokyo'\nDEM_BETA_NOINDEX=1\n"
        printf 'DEM_BETA_INTERFACE=%s\n' "$(ip -4 route show default | awk 'NR==1 {print $5}')"
        printf 'DEM_BETA_MONTHLY_TX_LIMIT=2500000000000\n'
        printf 'DEM_BETA_SLACK_WEBHOOK_URL=\n'
    } > "$temporary"
    mv -- "$temporary" "$ENV_FILE"
    trap - EXIT
    unset admin_password owner_password app_password
fi
chmod 600 "$ENV_FILE"
chown root:root "$ENV_FILE"
source "$ENV_FILE"
[[ "$DEM_BETA_HOME" == /var/lib/dem-beta ]] || { echo 'Unexpected runtime directory; inspect manually' >&2; exit 1; }
install -d -m 0755 "$DEM_BETA_HOME"
for directory in flags status state backups; do
    install -d -m 0755 -o 10001 -g 10001 "$DEM_BETA_HOME/$directory"
done
install -d -m 0700 -o 10001 -g 10001 "$DEM_BETA_HOME/contacts"
install -d -m 0700 "$DEM_BETA_HOME/host-state" "$DEM_BETA_HOME/logs"
install -m 0755 "$REPO/deploy/beta/bin/dem-beta" /usr/local/sbin/dem-beta
python3 "$REPO/deploy/beta/host.py" units "$REPO/deploy/beta/systemd" /etc/systemd/system "$DEM_BETA_RESET_SCHEDULE"
cat > /etc/logrotate.d/dem-beta <<'EOF'
/var/lib/dem-beta/logs/access.log {
    daily
    rotate 30
    maxage 30
    missingok
    notifempty
    copytruncate
    compress
    dateext
    dateformat -%Y%m%d
}
EOF
systemctl daemon-reload
# Enable now; start only after the first healthy reset (operations guide).
systemctl enable dem-beta-reset.timer dem-beta-backup.timer dem-beta-watch.timer dem-beta-notify.timer
systemctl enable --now logrotate.timer
echo 'dem-beta: host prepared; configure domain, initialize DB, then start timers'

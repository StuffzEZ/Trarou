#!/usr/bin/env bash
# Trarou install script
# Run as root: sudo bash install.sh
set -e

INSTALL_DIR="/opt/trarou"
ENV_DIR="/etc/trarou"
LOG_DIR="/var/log/trarou"
MEDIA_DIR="/home/${SUDO_USER:-pi}/trarou-media"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
AP_COUNTRY_CODE="GB"

echo "=== Trarou Installer ==="

# ── Cleanup previous install ─────────────────────────────────────────────────
echo "[0/8] Cleaning up any previous install..."

# Stop & disable old services (ignore errors if never installed)
for svc in trarou trarou-frontend; do
    systemctl stop "$svc" 2>/dev/null || true
    systemctl disable "$svc" 2>/dev/null || true
done
systemctl daemon-reload 2>/dev/null || true

# Kill any Trarou-managed dnsmasq/hostapd processes (not the system ones)
pkill -f 'dnsmasq.*trarou' 2>/dev/null || true
pkill -f 'hostapd.*trarou' 2>/dev/null || true

# Clean up stale iptables rules from previous captive portal
# Try all common AP interfaces since AP_INTERFACE isn't known yet
for iface in wlan1 wlan0; do
    iptables -t nat -D PREROUTING -i "$iface" -j TRAROU_PORTAL 2>/dev/null || true
done
iptables -t nat -F TRAROU_PORTAL 2>/dev/null || true
iptables -t nat -X TRAROU_PORTAL 2>/dev/null || true

# Remove old Trarou temp files
rm -f /tmp/trarou-dnsmasq.conf /tmp/trarou-dnsmasq.pid
rm -f /tmp/trarou-hostapd.conf /tmp/trarou-hostapd.pid

# Wipe old installation (preserve env file and media)
rm -rf "$INSTALL_DIR/venv" "$INSTALL_DIR/backend" "$INSTALL_DIR/frontend"
rm -f /etc/systemd/system/trarou.service /etc/systemd/system/trarou-frontend.service
rm -rf "$LOG_DIR"

echo "  Done."

# ── Dependencies ──────────────────────────────────────────────────────────────
echo "[1/8] Installing system packages..."
apt-get update -q
apt-get install -y \
    hostapd dnsmasq iptables wireless-regdb \
    network-manager iw \
    python3 python3-pip python3-venv \
    build-essential python3-dev libffi-dev \
    novnc websockify tigervnc-standalone-server \
    x11vnc xvfb openbox \
    --no-install-recommends

# Stop and mask default services that would conflict
echo "  Disabling system hostapd and dnsmasq (Trarou manages its own)..."
systemctl stop hostapd dnsmasq 2>/dev/null || true
systemctl disable hostapd dnsmasq 2>/dev/null || true
systemctl mask hostapd dnsmasq 2>/dev/null || true

# ── Directories ───────────────────────────────────────────────────────────────
echo "[2/8] Creating directories..."
mkdir -p "$INSTALL_DIR/backend/routers" \
         "$INSTALL_DIR/backend/services" \
         "$INSTALL_DIR/backend/models" \
         "$INSTALL_DIR/frontend" \
         "$ENV_DIR" "$LOG_DIR" "$MEDIA_DIR"
chown -R "${SUDO_USER:-pi}:${SUDO_USER:-pi}" "$MEDIA_DIR"

# ── Copy backend (map flat root files into package structure) ─────────────────
echo "[3/8] Installing backend..."

cp "$SRC_DIR/app.py"              "$INSTALL_DIR/backend/app.py"
cp "$SRC_DIR/config.py"           "$INSTALL_DIR/backend/config.py"
cp "$SRC_DIR/__init__.py"         "$INSTALL_DIR/backend/__init__.py"
cp "$SRC_DIR/requirements.txt"    "$INSTALL_DIR/backend/requirements.txt"

cp "$SRC_DIR/auth.py"             "$INSTALL_DIR/backend/routers/auth.py"
cp "$SRC_DIR/media.py"            "$INSTALL_DIR/backend/routers/media.py"
cp "$SRC_DIR/network.py"          "$INSTALL_DIR/backend/routers/network.py"
cp "$SRC_DIR/system.py"           "$INSTALL_DIR/backend/routers/system.py"
cp "$SRC_DIR/vnc.py"              "$INSTALL_DIR/backend/routers/vnc.py"

cp "$SRC_DIR/captive_portal.py"   "$INSTALL_DIR/backend/services/captive_portal.py"
cp "$SRC_DIR/hostapd.py"          "$INSTALL_DIR/backend/services/hostapd.py"
cp "$SRC_DIR/network_manager.py"  "$INSTALL_DIR/backend/services/network_manager.py"

cp "$SRC_DIR/schemas.py"          "$INSTALL_DIR/backend/models/schemas.py"

touch "$INSTALL_DIR/backend/routers/__init__.py"
touch "$INSTALL_DIR/backend/services/__init__.py"
touch "$INSTALL_DIR/backend/models/__init__.py"

# ── Copy frontend ─────────────────────────────────────────────────────────────
echo "[4/8] Installing frontend..."
cp -r "$SRC_DIR/frontend/"* "$INSTALL_DIR/frontend/"

# ── Python venv ───────────────────────────────────────────────────────────────
echo "[5/8] Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"

# ── Set Wi-Fi country / regulatory domain ────────────────────────────────────
echo "[6/8] Setting Wi-Fi regulatory domain..."
if command -v raspi-config &>/dev/null; then
    raspi-config nonint do_wifi_country "$AP_COUNTRY_CODE" 2>/dev/null || true
fi
iw reg set "$AP_COUNTRY_CODE" 2>/dev/null || echo "  Could not set regulatory domain (ok on headless)."

# ── Detect Wi-Fi interfaces ───────────────────────────────────────────────────
echo "[7/8] Detecting Wi-Fi interfaces and writing environment config..."

if command -v iw &>/dev/null; then
    WIFI_IFACES=($(iw dev 2>/dev/null | awk '/Interface/ {print $2}' | sort))
else
    WIFI_IFACES=()
    echo "  WARNING: 'iw' not found, cannot detect interfaces."
fi

if [ ${#WIFI_IFACES[@]} -eq 0 ]; then
    echo "  No Wi-Fi interfaces detected. Defaulting to wlan0 (AP) / wlan1 (client)."
    echo "  You can edit /etc/trarou/trarou.env later to fix."
    AP_IFACE="wlan0"
    CLIENT_IFACE="wlan1"
elif [ ${#WIFI_IFACES[@]} -eq 1 ]; then
    echo "  WARNING: Only one Wi-Fi interface found (${WIFI_IFACES[0]})."
    echo "  You need two interfaces: one for the AP, one for upstream."
    AP_IFACE="${WIFI_IFACES[0]}"
    CLIENT_IFACE="${WIFI_IFACES[0]}"
else
    echo ""
    echo "  Detected Wi-Fi interfaces:"
    for i in "${!WIFI_IFACES[@]}"; do
        IFACE="${WIFI_IFACES[$i]}"
        MAC=$(cat "/sys/class/net/$IFACE/address" 2>/dev/null || echo "unknown")
        AP_SUPPORT=$(iw phy "$(iw dev "$IFACE" info 2>/dev/null | awk '/wiphy/ {print "phy"$2}')" info 2>/dev/null | grep -c "AP" || echo 0)
        AP_LABEL=""
        [ "$AP_SUPPORT" -gt 0 ] && AP_LABEL=" [AP mode supported]"
        echo "    [$i] $IFACE  (MAC: $MAC)$AP_LABEL"
    done
    echo ""

    DEFAULT_AP="${WIFI_IFACES[0]}"
    DEFAULT_CLIENT="${WIFI_IFACES[1]}"

    echo -n "  Which interface should be the ACCESS POINT (AP)? [default: $DEFAULT_AP]: "
    read -r INPUT_AP
    AP_IFACE="${INPUT_AP:-$DEFAULT_AP}"

    echo -n "  Which interface should be the UPSTREAM CLIENT?  [default: $DEFAULT_CLIENT]: "
    read -r INPUT_CLIENT
    CLIENT_IFACE="${INPUT_CLIENT:-$DEFAULT_CLIENT}"
fi

echo "  AP interface:     $AP_IFACE"
echo "  Client interface: $CLIENT_IFACE"
echo ""

# ── Environment file ─────────────────────────────────────────────────────────
if [ ! -f "$ENV_DIR/trarou.env" ]; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    RANDOM_SUFFIX=$(python3 -c "import random, string; print(''.join(random.choices(string.ascii_lowercase + string.digits, k=6)))")
    DEFAULT_SSID="trarou-${RANDOM_SUFFIX}"

    echo -n "  Set Wi-Fi network name (SSID) [default: $DEFAULT_SSID]: "
    read -r INPUT_SSID
    AP_SSID="${INPUT_SSID:-$DEFAULT_SSID}"
    echo "  SSID will be: $AP_SSID"
    echo ""

    echo -n "  Set 2-letter country code (e.g. US, GB, DE) [default: GB]: "
    read -r INPUT_CC
    AP_COUNTRY_CODE="${INPUT_CC:-GB}"
    echo "  Country code: $AP_COUNTRY_CODE"
    echo ""

    while true; do
        echo -n "  Set admin password (min 8 chars): "
        read -rs ADMIN_PASS
        echo
        if [ ${#ADMIN_PASS} -lt 8 ]; then
            echo "  Password too short -- must be at least 8 characters."
        else
            break
        fi
    done

    HASH=$("$INSTALL_DIR/venv/bin/python3" -c \
        "import bcrypt; print(bcrypt.hashpw('$ADMIN_PASS'.encode(), bcrypt.gensalt()).decode())")

    cat > "$ENV_DIR/trarou.env" <<EOF
SECRET_KEY=$SECRET
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$HASH
AP_INTERFACE=$AP_IFACE
CLIENT_INTERFACE=$CLIENT_IFACE
AP_SSID=$AP_SSID
CAPTIVE_PORTAL_IP=10.0.0.1
AP_COUNTRY_CODE=$AP_COUNTRY_CODE
FRONTEND_URL=http://10.0.0.1:3000
NOVNC_PATH=/usr/share/novnc
EOF
    chmod 600 "$ENV_DIR/trarou.env"
    echo "  Environment written to $ENV_DIR/trarou.env"
else
    echo "  Environment file already exists -- skipping."
    echo "  (Delete $ENV_DIR/trarou.env and re-run to reconfigure.)"
fi

# ── Persistently tell NetworkManager to ignore the AP interface ─────────────
echo "  Configuring NetworkManager to ignore $AP_IFACE..."
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/trarou-ap.conf <<NMCONF
[keyfile]
unmanaged-devices=interface-name:$AP_IFACE
NMCONF
systemctl reload NetworkManager 2>/dev/null || true

# ── Systemd services ─────────────────────────────────────────────────────────
echo "[8/8] Enabling systemd services..."

cp "$SRC_DIR/trarou.service" /etc/systemd/system/trarou.service
cp "$SRC_DIR/frontend/trarou-frontend.service" /etc/systemd/system/trarou-frontend.service
systemctl daemon-reload
systemctl enable trarou.service || echo "  WARNING: could not enable trarou.service"
systemctl start trarou.service  || echo "  WARNING: could not start trarou.service (may need reboot)"
systemctl enable trarou-frontend.service || echo "  WARNING: could not enable trarou-frontend.service"
systemctl start trarou-frontend.service  || echo "  WARNING: could not start trarou-frontend.service"

echo ""
echo "=== Trarou installed and running ==="
echo "  API:      http://10.0.0.1:8000"
echo "  API docs: http://10.0.0.1:8000/docs"
echo "  Frontend: http://10.0.0.1:3000"
echo "  noVNC:    http://10.0.0.1:6080  (start via API)"
echo ""
echo "Done."

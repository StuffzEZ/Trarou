#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Trarou Installer
#  Usage: sudo bash install.sh [--debug]
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── Parse flags ──────────────────────────────────────────────────────────────
DEBUG=0
for arg in "$@"; do
    case "$arg" in
        --debug) DEBUG=1 ;;
    esac
done

# ── Paths ────────────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/trarou"
ENV_DIR="/etc/trarou"
LOG_DIR="/var/log/trarou"
MEDIA_DIR="/home/${SUDO_USER:-pi}/trarou-media"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
AP_COUNTRY_CODE="GB"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

# ── Helpers ──────────────────────────────────────────────────────────────────
step()  { echo -e "\n${BOLD}${CYAN}[$1/$TOTAL]${NC} ${BOLD}$2${NC}"; }
info()  { echo -e "  ${BLUE}●${NC} $1"; }
ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}!${NC} $1"; }
err()   { echo -e "  ${RED}✗${NC} $1"; }
debug() { [ "$DEBUG" -eq 1 ] && echo -e "  ${DIM}$1${NC}" || true; }
hr()    { echo -e "${DIM}$(printf '%.0s─' {1..50})${NC}"; }

TOTAL=9

# ── Run command (hide output unless --debug) ─────────────────────────────────
run() {
    if [ "$DEBUG" -eq 1 ]; then
        "$@"
    else
        "$@" > /dev/null 2>&1
    fi
}

# ── Banner ───────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "  ${BOLD}${CYAN}╔═══════════════════════════════════════╗${NC}"
echo -e "  ${BOLD}${CYAN}║${NC}    ${BOLD}Trarou Installer${NC}                  ${BOLD}${CYAN}║${NC}"
echo -e "  ${BOLD}${CYAN}║${NC}    ${DIM}Travel Router v1.1.0${NC}               ${BOLD}${CYAN}║${NC}"
echo -e "  ${BOLD}${CYAN}╚═══════════════════════════════════════╝${NC}"
echo ""

# ── [0] Cleanup ──────────────────────────────────────────────────────────────
step 0 "Cleaning up previous install"

for svc in trarou trarou-frontend; do
    run systemctl stop "$svc"
    run systemctl disable "$svc"
done
run systemctl daemon-reload

run pkill -f 'dnsmasq.*trarou'
run pkill -f 'hostapd.*trarou'

for iface in wlan1 wlan0; do
    run iptables -t nat -D PREROUTING -i "$iface" -j TRAROU_PORTAL
done
run iptables -t nat -F TRAROU_PORTAL
run iptables -t nat -X TRAROU_PORTAL

rm -f /tmp/trarou-dnsmasq.conf /tmp/trarou-dnsmasq.pid
rm -f /tmp/trarou-hostapd.conf /tmp/trarou-hostapd.pid
rm -rf "$INSTALL_DIR/venv" "$INSTALL_DIR/backend" "$INSTALL_DIR/frontend"
rm -f /etc/systemd/system/trarou.service /etc/systemd/system/trarou-frontend.service
rm -rf "$LOG_DIR"

ok "Previous install removed"

# ── [1] Dependencies ─────────────────────────────────────────────────────────
step 1 "Installing system packages"

if [ "$DEBUG" -eq 1 ]; then
    apt-get update -q
    apt-get install -y \
        hostapd dnsmasq iptables wireless-regdb \
        network-manager iw \
        python3 python3-pip python3-venv \
        build-essential python3-dev libffi-dev \
        novnc websockify tigervnc-standalone-server \
        x11vnc xvfb openbox \
        --no-install-recommends
else
    apt-get update -q > /dev/null 2>&1
    apt-get install -y -q \
        hostapd dnsmasq iptables wireless-regdb \
        network-manager iw \
        python3 python3-pip python3-venv \
        build-essential python3-dev libffi-dev \
        novnc websockify tigervnc-standalone-server \
        x11vnc xvfb openbox \
        --no-install-recommends > /dev/null 2>&1
fi

run systemctl stop hostapd dnsmasq
run systemctl disable hostapd dnsmasq
run systemctl mask hostapd dnsmasq

ok "Packages installed"

# ── [2] Directories ──────────────────────────────────────────────────────────
step 2 "Creating directories"

mkdir -p "$INSTALL_DIR/backend/routers" \
         "$INSTALL_DIR/backend/services" \
         "$INSTALL_DIR/backend/models" \
         "$INSTALL_DIR/frontend" \
         "$ENV_DIR" "$LOG_DIR" "$MEDIA_DIR"
chown -R "${SUDO_USER:-pi}:${SUDO_USER:-pi}" "$MEDIA_DIR"

ok "Directories created"

# ── [3] Backend ──────────────────────────────────────────────────────────────
step 3 "Installing backend"

cp "$SRC_DIR/app.py"              "$INSTALL_DIR/backend/app.py"
cp "$SRC_DIR/config.py"           "$INSTALL_DIR/backend/config.py"
cp "$SRC_DIR/__init__.py"         "$INSTALL_DIR/backend/__init__.py"
cp "$SRC_DIR/requirements.txt"    "$INSTALL_DIR/backend/requirements.txt"

cp "$SRC_DIR/routers/"*.py        "$INSTALL_DIR/backend/routers/"
cp "$SRC_DIR/services/"*.py       "$INSTALL_DIR/backend/services/"
cp "$SRC_DIR/models/"*.py         "$INSTALL_DIR/backend/models/"

touch "$INSTALL_DIR/backend/routers/__init__.py"
touch "$INSTALL_DIR/backend/services/__init__.py"
touch "$INSTALL_DIR/backend/models/__init__.py"

ok "Backend installed"

# ── [4] Frontend ─────────────────────────────────────────────────────────────
step 4 "Installing frontend"

cp -r "$SRC_DIR/frontend/"* "$INSTALL_DIR/frontend/"

ok "Frontend installed"

# ── [5] Version ──────────────────────────────────────────────────────────────
step 5 "Version info"

if [ -f "$SRC_DIR/version.json" ]; then
    cp "$SRC_DIR/version.json" "$INSTALL_DIR/backend/version.json"
    VER=$(grep '"version"' "$SRC_DIR/version.json" | cut -d'"' -f4)
    ok "Version: $VER"
else
    ok "Skipping (dev install)"
fi

# ── [6] Python venv ──────────────────────────────────────────────────────────
step 6 "Setting up Python environment"

python3 -m venv "$INSTALL_DIR/venv" > /dev/null 2>&1
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q > /dev/null 2>&1
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q > /dev/null 2>&1

ok "Python venv ready"

# ── [7] Wi-Fi ────────────────────────────────────────────────────────────────
step 7 "Configuring Wi-Fi"

# Regulatory domain
if command -v raspi-config &>/dev/null; then
    run raspi-config nonint do_wifi_country "$AP_COUNTRY_CODE"
fi
run iw reg set "$AP_COUNTRY_CODE"

# Detect interfaces
if command -v iw &>/dev/null; then
    WIFI_IFACES=($(iw dev 2>/dev/null | awk '/Interface/ {print $2}' | sort))
else
    WIFI_IFACES=()
fi

if [ ${#WIFI_IFACES[@]} -eq 0 ]; then
    warn "No Wi-Fi interfaces found, defaulting to wlan0 (AP) / wlan1 (client)"
    AP_IFACE="wlan0"
    CLIENT_IFACE="wlan1"
elif [ ${#WIFI_IFACES[@]} -eq 1 ]; then
    warn "Only one interface found (${WIFI_IFACES[0]})"
    AP_IFACE="${WIFI_IFACES[0]}"
    CLIENT_IFACE="${WIFI_IFACES[0]}"
else
    echo ""
    info "Detected interfaces:"
    for i in "${!WIFI_IFACES[@]}"; do
        IFACE="${WIFI_IFACES[$i]}"
        MAC=$(cat "/sys/class/net/$IFACE/address" 2>/dev/null || echo "?")
        echo -e "    ${DIM}[$i]${NC} $IFACE  ${DIM}($MAC)${NC}"
    done
    echo ""
    read -r -p "    AP interface [${WIFI_IFACES[0]}]: " INPUT_AP </dev/tty
    read -r -p "    Client interface [${WIFI_IFACES[1]}]: " INPUT_CLIENT </dev/tty
    AP_IFACE="${INPUT_AP:-${WIFI_IFACES[0]}}"
    CLIENT_IFACE="${INPUT_CLIENT:-${WIFI_IFACES[1]}}"
fi

ok "AP: $AP_IFACE, Client: $CLIENT_IFACE"

# ── [7.5] Config ─────────────────────────────────────────────────────────────
if [ ! -f "$ENV_DIR/trarou.env" ]; then
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    SUFFIX=$(python3 -c "import random,string; print(''.join(random.choices(string.ascii_lowercase+string.digits,k=6)))")

    echo ""
    read -r -p "    SSID [trarou-$SUFFIX]: " INPUT_SSID </dev/tty
    AP_SSID="${INPUT_SSID:-trarou-$SUFFIX}"

    read -r -p "    Country code [GB]: " INPUT_CC </dev/tty
    AP_COUNTRY_CODE="${INPUT_CC:-GB}"

    echo ""
    read -r -p "    Wi-Fi password (leave blank for open network): " AP_PASSPHRASE </dev/tty

    echo ""
    while true; do
        read -rs -p "    Admin password (min 8 chars): " ADMIN_PASS </dev/tty
        echo
        if [ ${#ADMIN_PASS} -ge 8 ]; then break; fi
        warn "Too short, try again."
    done

    HASH=$("$INSTALL_DIR/venv/bin/python3" -c \
        'import bcrypt,sys; print(bcrypt.hashpw(sys.stdin.read().strip().encode(), bcrypt.gensalt()).decode())' <<< "$ADMIN_PASS")

    cat > "$ENV_DIR/trarou.env" <<EOF
SECRET_KEY=$SECRET
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=$HASH
AP_INTERFACE=$AP_IFACE
CLIENT_INTERFACE=$CLIENT_IFACE
AP_SSID=$AP_SSID
AP_PASSPHRASE=$AP_PASSPHRASE
CAPTIVE_PORTAL_IP=10.0.0.1
AP_COUNTRY_CODE=$AP_COUNTRY_CODE
FRONTEND_URL=http://10.0.0.1:3000
NOVNC_PATH=/usr/share/novnc
CAPTIVE_PORTAL_TOOLS_ONLY=true
TRAROU_HOSTNAME=tra.rou
TAILSCALE_ENABLED=false
AI_ENABLED=true
EOF
    chmod 600 "$ENV_DIR/trarou.env"
    ok "Config written to $ENV_DIR/trarou.env"
else
    ok "Config exists, skipping"
fi

# NetworkManager
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/trarou-ap.conf <<NMCONF
[keyfile]
unmanaged-devices=interface-name:$AP_IFACE
NMCONF
run systemctl reload NetworkManager
ok "NetworkManager configured"

# ── [8] Services ─────────────────────────────────────────────────────────────
step 8 "Starting services"

cp "$SRC_DIR/trarou.service" /etc/systemd/system/trarou.service
cp "$SRC_DIR/frontend/trarou-frontend.service" /etc/systemd/system/trarou-frontend.service
run systemctl daemon-reload
run systemctl enable trarou.service
run systemctl enable trarou-frontend.service
run systemctl start trarou.service
run systemctl start trarou-frontend.service

ok "Services running"

# ── [9] Tailscale (optional) ─────────────────────────────────────────────────
step 9 "Tailscale VPN"

echo ""
read -r -p "    Install Tailscale? [y/N] " INSTALL_TS </dev/tty
if [[ "$INSTALL_TS" =~ ^[Yy]$ ]]; then
    info "Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | bash > /dev/null 2>&1
    ok "Tailscale installed"
else
    ok "Skipped"
fi

# ── [10] Ollama (optional) ──────────────────────────────────────────────────
step 10 "Ollama AI"

echo ""
read -r -p "    Install Ollama (local AI)? [y/N] " INSTALL_OLLAMA </dev/tty
if [[ "$INSTALL_OLLAMA" =~ ^[Yy]$ ]]; then
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh > /dev/null 2>&1
    ok "Ollama installed"
    info "Pulling recommended model (gemma2:2b)..."
    ollama pull gemma2:2b > /dev/null 2>&1 || warn "Model pull failed — run 'ollama pull gemma2:2b' later"
    ok "AI ready"
else
    ok "Skipped"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
hr
echo ""
echo -e "  ${BOLD}${GREEN}Trarou is installed and running!${NC}"
echo ""
echo -e "  ${BOLD}Web UI:${NC}    http://10.0.0.1:3000"
echo -e "  ${BOLD}API:${NC}       http://10.0.0.1:8000"
echo -e "  ${BOLD}API docs:${NC}  http://10.0.0.1:8000/docs"
echo ""
echo -e "  ${DIM}Connect to the Trarou Wi-Fi network, then open the URL above.${NC}"
echo ""

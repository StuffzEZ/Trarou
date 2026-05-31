#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Trarou — Installer / Uninstaller
#  Install:    curl -fsSL https://trarou.stufy.qzz.io/get.sh | sudo bash -s
#  Uninstall:  curl -fsSL https://trarou.stufy.qzz.io/get.sh | sudo bash -s -- --uninstall
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REPO="StuffzEZ/Trarou"
INSTALL_DIR="/opt/trarou"
ENV_DIR="/etc/trarou"
TMP_DIR="/tmp/trarou-installer-$$"

# ── Parse flags ──────────────────────────────────────────────────────────────
UNINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --uninstall) UNINSTALL=1 ;;
    esac
done

# ── Auto-elevate to root ─────────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    echo -e "  Need root, re-running with sudo..."
    exec sudo bash "$0" "$@"
fi

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
info()  { echo -e "  ${BLUE}●${NC} $1"; }
ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}!${NC} $1"; }
err()   { echo -e "  ${RED}✗${NC} $1"; }
hr()    { echo -e "${DIM}$(printf '%.0s─' {1..50})${NC}"; }

cleanup() { rm -rf "$TMP_DIR" 2>/dev/null; }
trap cleanup EXIT

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  UNINSTALL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if [ "$UNINSTALL" -eq 1 ]; then
    echo ""
    echo -e "  ${BOLD}${RED}╔═══════════════════════════════════════╗${NC}"
    echo -e "  ${BOLD}${RED}║${NC}    ${BOLD}Trarou Uninstaller${NC}                 ${BOLD}${RED}║${NC}"
    echo -e "  ${BOLD}${RED}╚═══════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  This will remove Trarou from your system:"
    echo -e "    ${DIM}• Stop and disable services${NC}"
    echo -e "    ${DIM}• Remove /opt/trarou${NC}"
    echo -e "    ${DIM}• Remove /etc/trarou (config)${NC}"
    echo -e "    ${DIM}• Remove systemd service files${NC}"
    echo -e "    ${DIM}• Clean up iptables rules${NC}"
    echo ""

    read -r -p "  Are you sure? [y/N] " CONFIRM </dev/tty
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo -e "\n  ${DIM}Uninstall cancelled.${NC}"
        exit 0
    fi

    echo ""

    info "Stopping services..."
    systemctl stop trarou 2>/dev/null || true
    systemctl stop trarou-frontend 2>/dev/null || true
    systemctl disable trarou 2>/dev/null || true
    systemctl disable trarou-frontend 2>/dev/null || true
    systemctl daemon-reload 2>/dev/null || true
    ok "Services stopped"

    info "Killing Trarou processes..."
    pkill -f 'dnsmasq.*trarou' 2>/dev/null || true
    pkill -f 'hostapd.*trarou' 2>/dev/null || true
    pkill -f 'uvicorn.*app:app' 2>/dev/null || true
    ok "Processes killed"

    info "Cleaning iptables rules..."
    iptables -t nat -D PREROUTING -i wlan0 -j TRAROU_PORTAL 2>/dev/null || true
    iptables -t nat -D PREROUTING -i wlan1 -j TRAROU_PORTAL 2>/dev/null || true
    iptables -t nat -F TRAROU_PORTAL 2>/dev/null || true
    iptables -t nat -X TRAROU_PORTAL 2>/dev/null || true
    ok "iptables cleaned"

    info "Removing installed files..."
    rm -rf "$INSTALL_DIR"
    rm -rf "$ENV_DIR"
    rm -rf /var/log/trarou
    rm -f /etc/systemd/system/trarou.service
    rm -f /etc/systemd/system/trarou-frontend.service
    rm -f /etc/NetworkManager/conf.d/trarou-ap.conf
    rm -f /tmp/trarou-*
    ok "Files removed"

    info "Restoring system services..."
    systemctl unmask hostapd 2>/dev/null || true
    systemctl unmask dnsmasq 2>/dev/null || true
    systemctl reload NetworkManager 2>/dev/null || true
    ok "System services restored"

    echo ""
    hr
    echo ""
    echo -e "  ${BOLD}${GREEN}Trarou has been uninstalled.${NC}"
    echo -e "  ${DIM}Media files in ~/trarou-media were preserved.${NC}"
    echo ""
    exit 0
fi

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  INSTALL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo ""
echo -e "  ${BOLD}${CYAN}╔═══════════════════════════════════════╗${NC}"
echo -e "  ${BOLD}${CYAN}║${NC}    ${BOLD}Trarou Travel Router${NC}              ${BOLD}${CYAN}║${NC}"
echo -e "  ${BOLD}${CYAN}║${NC}    ${DIM}Smart Wi-Fi on a Raspberry Pi${NC}      ${BOLD}${CYAN}║${NC}"
echo -e "  ${BOLD}${CYAN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo -e "  This will install Trarou to ${BOLD}/opt/trarou${NC}"
echo -e "  and set up two systemd services."
echo ""
read -r -p "  Continue? [Y/n] " CONFIRM </dev/tty
if [[ "$CONFIRM" =~ ^[Nn]$ ]]; then
    echo -e "\n  ${DIM}Installation cancelled.${NC}"
    exit 0
fi
echo ""

# Get latest release
info "Checking latest release..."
LATEST=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" 2>/dev/null | grep '"tag_name"' | cut -d'"' -f4 || true)

if [ -z "$LATEST" ]; then
    err "Could not fetch latest release from GitHub."
    exit 1
fi

ok "Latest release: ${BOLD}$LATEST${NC}"

# Download
ZIP_URL="https://github.com/$REPO/releases/download/$LATEST/trarou-$LATEST.zip"
ZIP_FILE="$TMP_DIR/trarou-$LATEST.zip"

mkdir -p "$TMP_DIR"
info "Downloading trarou-$LATEST.zip ..."
if ! curl -fSL -o "$ZIP_FILE" "$ZIP_URL" 2>/dev/null; then
    err "Download failed."
    exit 1
fi
ok "Downloaded $(du -h "$ZIP_FILE" | cut -f1)"

# Extract
info "Extracting..."
if ! unzip -qo "$ZIP_FILE" -d "$TMP_DIR/extract" 2>/dev/null; then
    err "Extraction failed."
    exit 1
fi
ok "Extracted"

# Find installer
INSTALLER=$(find "$TMP_DIR/extract" -name "install.sh" -type f | head -1)

if [ -z "$INSTALLER" ]; then
    err "Could not find install.sh in the release zip."
    exit 1
fi

# Run installer
echo ""
hr
echo -e "  ${BOLD}Handing off to installer...${NC}"
hr
echo ""

exec bash "$INSTALLER" "$@"

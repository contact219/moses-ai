#!/bin/bash
# ============================================================
#  Moses AI Assistant — Linux Installer
# ============================================================
set -e

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$INSTALL_DIR"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "  M.O.S.E.S  AI Assistant — Installer"
echo "  ====================================="
echo ""

# ── 1. System packages ─────────────────────────────────────
echo -e "${YELLOW}[1/6] Installing system dependencies...${NC}"
sudo apt-get update -qq
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    portaudio19-dev \
    libxcb-xinerama0 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 \
    libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-xfixes0 libxcb-xkb1 \
    libgl1 libglib2.0-0 libdbus-1-3 \
    xdotool scrot wmctrl \
    python3-xlib \
    libpulse0 \
    xclip xdotool \
    2>/dev/null

echo -e "${GREEN}  ✓ System packages installed${NC}"

# ── 2. Python virtual environment ──────────────────────────
echo -e "${YELLOW}[2/6] Creating Python virtual environment...${NC}"
python3 -m venv env
source env/bin/activate
pip install --upgrade pip --quiet
echo -e "${GREEN}  ✓ Virtual environment ready${NC}"

# ── 3. Python dependencies ─────────────────────────────────
echo -e "${YELLOW}[3/6] Installing Python packages (this may take a few minutes)...${NC}"
pip install -r requirements-linux.txt --quiet
echo -e "${GREEN}  ✓ Python packages installed${NC}"

# ── 4. Playwright browsers ─────────────────────────────────
echo -e "${YELLOW}[4/6] Installing Playwright browser (Chromium)...${NC}"
playwright install chromium 2>/dev/null || python3 -m playwright install chromium
playwright install-deps chromium 2>/dev/null || true
echo -e "${GREEN}  ✓ Playwright ready${NC}"

# ── 5. Config setup ────────────────────────────────────────
echo -e "${YELLOW}[5/6] Setting up configuration...${NC}"

if [ ! -f "$INSTALL_DIR/config/api_keys.json" ]; then
    cp "$INSTALL_DIR/config/api_keys.template.json" "$INSTALL_DIR/config/api_keys.json"
    echo -e "${RED}  ⚠  config/api_keys.json created from template.${NC}"
    echo -e "${RED}     Open it and replace YOUR_GEMINI_API_KEY_HERE with your real key.${NC}"
else
    echo -e "${GREEN}  ✓ config/api_keys.json already exists${NC}"
fi

if [ ! -f "$INSTALL_DIR/memory/long_term.json" ]; then
    cat > "$INSTALL_DIR/memory/long_term.json" << 'EOF'
{
  "identity":      {},
  "preferences":   {},
  "projects":      {},
  "relationships": {},
  "wishes":        {},
  "notes":         {}
}
EOF
    echo -e "${GREEN}  ✓ Memory store initialized${NC}"
fi

chmod +x "$INSTALL_DIR/start_jarvis.sh"

# ── 6. Desktop icon ────────────────────────────────────────
echo -e "${YELLOW}[6/6] Creating desktop launcher...${NC}"

DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/Moses.desktop" << EOF
[Desktop Entry]
Version=1.0
Name=Moses
Comment=Launch Moses AI Assistant
Exec=$INSTALL_DIR/start_jarvis.sh
Icon=$INSTALL_DIR/jarvis_1.png
Terminal=false
Type=Application
Categories=Utility;
EOF
chmod +x "$DESKTOP_DIR/Moses.desktop"

# Trust the icon on GNOME desktops (if gio is available)
if command -v gio &>/dev/null; then
    gio set "$DESKTOP_DIR/Moses.desktop" metadata::trusted true 2>/dev/null || true
fi

echo -e "${GREEN}  ✓ Desktop icon created${NC}"

# ── Done ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}  ✅ Moses is installed!${NC}"
echo ""

if grep -q "YOUR_GEMINI_API_KEY_HERE" "$INSTALL_DIR/config/api_keys.json" 2>/dev/null; then
    echo -e "${YELLOW}  ➜  NEXT STEP: Add your Gemini API key:${NC}"
    echo "     nano $INSTALL_DIR/config/api_keys.json"
    echo ""
    echo "     Get a free key at: https://aistudio.google.com/app/apikey"
    echo ""
fi

echo "  Then double-click the Moses icon on your Desktop."
echo ""

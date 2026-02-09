#!/usr/bin/env bash
# Installer for TerminalFormer2
# Installs system deps (apt) and Python deps (apt or pip), sets up launcher + .desktop
set -u

REPO_URL="https://github.com/haxpenguin2/TerminalFormer2.git"
INSTALL_DIR="$HOME/.terminal_former2"
BACKUP_DIR="/tmp/tf2_backup_$(date +%s)"
BIN_NAME="terminalformer2"
DESKTOP_FILE="$HOME/.local/share/applications/terminalformer2.desktop"
LOGFILE="/tmp/tf2_install.log"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; PURPLE='\033[0;35m'; BOLD='\033[1m'; NC='\033[0m'

# Keep track if we changed input group perms
PERMISSIONS_CHANGED=false

# Draw progress bar (reuse your function)
draw_bar() {
    local width=30
    local percent=$1
    local text=$2
    local num_filled=$(( (percent * width) / 100 ))
    local num_empty=$(( width - num_filled ))
    local bar_filled=""
    if [ "$num_filled" -gt 0 ]; then
        bar_filled=$(printf '█%.0s' $(seq 1 $num_filled))
    fi
    local bar_empty=""
    if [ "$num_empty" -gt 0 ]; then
        bar_empty=$(printf '░%.0s' $(seq 1 $num_empty))
    fi
    echo -ne "\r${BOLD}${CYAN}[${CYAN}${bar_filled}${NC}${BOLD}${bar_empty}${CYAN}]${NC} ${percent}% ${PURPLE}::${NC} ${text}\033[K"
}

print_banner() {
    clear
    echo -e "${CYAN}${BOLD}"
    cat << "EOF"
  _______                   _             _   ______                              ___  
 |__   __|                 (_)           | | |  ____|                            |__ \ 
    | | ___ _ __ _ __ ___   _ _ __   __ _| | | |__ ___  _ __ _ __ ___   ___ _ __    ) |
    | |/ _ \ '__| '_ ` _ \ | | '_ \ / _` | | |  __/ _ \| '__| '_ ` _ \ / _ \ '__|  / / 
    | |  __/ |  | | | | | || | | | | (_| | | | | | (_) | |  | | | | | |  __/ |    / /_ 
    |_|\___|_|  |_| |_| |_||_|_| |_|\__,_|_| |_|  \___/|_|  |_| |_| |_|\___|_|   |____|
EOF
    echo -e "${NC}"
    echo -e "${BLUE}  :: High-Performance Terminal Platformer Installer ::${NC}"
    echo -e "${BLUE}  :: v3.3 | Menu Launch | debug-mode enabled        ::${NC}"
    echo ""
}

# cleanup on exit
cleanup() {
    # restore cursor
    tput cnorm 2>/dev/null || true
    # kill sudo refresh loop
    if [ -n "${SUDO_PID-}" ] && ps -p "$SUDO_PID" > /dev/null 2>&1; then
        kill "$SUDO_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

print_banner

# request sudo early
echo -e "${YELLOW}:: Requesting administrative access for installation...${NC}"
sudo -v || { echo -e "${RED}sudo required. Exiting.${NC}"; exit 1; }
# keep sudo alive
( while true; do sudo -v; sleep 60; done; ) &
SUDO_PID=$!

# hide cursor
tput civis 2>/dev/null || true

# Step 1: Preflight
draw_bar 3 "Preflight checks..."
echo ""
echo -e "${BLUE}Checking environment...${NC}" | tee -a "$LOGFILE"

# Detect package manager
PKG_MANAGER=""
if command -v apt-get >/dev/null 2>&1; then
    PKG_MANAGER="apt"
    echo -e "${GREEN}Using apt for package installation.${NC}" | tee -a "$LOGFILE"
else
    echo -e "${YELLOW}apt-get not found — installer will use pip for Python deps where needed.${NC}" | tee -a "$LOGFILE"
fi
draw_bar 8 "Environment detected"

# Step 2: Install system packages (apt preferred)
if [ "$PKG_MANAGER" = "apt" ]; then
    draw_bar 12 "Updating package index..."
    echo -e "\n${BLUE}Running apt-get update (this may take a moment)...${NC}" | tee -a "$LOGFILE"
    sudo apt-get update 2>&1 | tee -a "$LOGFILE"
    draw_bar 20 "Installing system packages..."
    echo -e "${BLUE}Installing system packages (git, python3, pip, SDL libs, X11)...${NC}" | tee -a "$LOGFILE"
    # packages chosen to satisfy pygame + evdev + common build/runtime deps
    sudo apt-get install -y \
        git curl python3 python3-pip python3-venv python3-dev \
        python3-evdev python3-pygame \
        libsdl2-2.0-0 libsdl2-dev libsdl2-image-2.0-0 \
        libx11-6 libx11-dev \
        libasound2 libasound2-dev \
        build-essential pkg-config \
        xterm \
        >/dev/null 2>&1 | tee -a "$LOGFILE"
    if [ "${PIPESTATUS[0]:-0}" -ne 0 ]; then
        echo -e "${YELLOW}apt install may have produced warnings — check $LOGFILE if something went wrong.${NC}" | tee -a "$LOGFILE"
    fi
    draw_bar 35 "System packages installed"
else
    draw_bar 20 "Skipping apt packages (not available)"
fi

# Step 3: Ensure pip packages: pygame + evdev (if apt didn't provide)
draw_bar 40 "Ensuring Python packages..."
echo -e "${BLUE}Verifying Python packages (pygame + evdev)...${NC}" | tee -a "$LOGFILE"
PY_OK=0
python3 - <<'PYCHK' 2>>"$LOGFILE"
import sys
ok=True
try:
    import pygame
except Exception:
    ok=False
try:
    import evdev
except Exception:
    # evdev optional
    pass
sys.exit(0 if ok else 1)
PYCHK
PY_OK=$?

if [ $PY_OK -ne 0 ]; then
    echo -e "${YELLOW}pygame not importable, attempting pip3 install...${NC}" | tee -a "$LOGFILE"
    # try pip install (prefer sudo so system python can import)
    if command -v pip3 >/dev/null 2>&1; then
        sudo pip3 install --upgrade pip setuptools wheel >/dev/null 2>&1 | tee -a "$LOGFILE"
        # Some systems have apt python3-pygame; if not, pip install pygame
        sudo pip3 install pygame evdev --no-cache-dir 2>&1 | tee -a "$LOGFILE" || true
    else
        echo -e "${RED}pip3 not available; please install pip3 and re-run.${NC}" | tee -a "$LOGFILE"
    fi
else
    echo -e "${GREEN}pygame import OK.${NC}" | tee -a "$LOGFILE"
fi
draw_bar 55 "Python packages ready"

# Verify pygame now
python3 - <<'PYCHK' 2>>"$LOGFILE"
try:
    import pygame, sys
    print("pygame ok")
except Exception as e:
    print("pygame fail", e)
    sys.exit(1)
PYCHK
if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: pygame still not importable. Check $LOGFILE and install python3-pygame or pip3 pygame.${NC}" | tee -a "$LOGFILE"
    tput cnorm 2>/dev/null || true
    exit 1
fi
draw_bar 65 "Verified pygame"

# Step 4: Fix input permissions
draw_bar 70 "Verifying Input Permissions..."
echo -e "${BLUE}\nChecking /dev/input group membership for user '${USER}'...${NC}" | tee -a "$LOGFILE"
sleep 0.4
if ! groups "$USER" | grep -E '\binput\b' >/dev/null 2>&1; then
    echo -e "${YELLOW}User not in 'input' group, attempting to add...${NC}" | tee -a "$LOGFILE"
    if sudo usermod -a -G input "$USER" 2>>"$LOGFILE"; then
        PERMISSIONS_CHANGED=true
        echo -e "${GREEN}Added $USER to 'input' group. Reboot required to take effect.${NC}" | tee -a "$LOGFILE"
    else
        echo -e "${YELLOW}Could not add to 'input' group (may be distro-specific). Continuing; pygame mode will still work.${NC}" | tee -a "$LOGFILE"
    fi
else
    echo -e "${GREEN}User already in 'input' group.${NC}" | tee -a "$LOGFILE"
fi
draw_bar 75 "Input permissions checked"

# Step 5: Backup existing install
draw_bar 80 "Backing up previous installation..."
echo -e "${BLUE}\nBacking up existing installation (if any)...${NC}" | tee -a "$LOGFILE"
if [ -d "$INSTALL_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    [ -f "$INSTALL_DIR/scores.json" ] && cp "$INSTALL_DIR/scores.json" "$BACKUP_DIR/" || true
    [ -d "$INSTALL_DIR/levels" ] && cp -r "$INSTALL_DIR/levels" "$BACKUP_DIR/" || true
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}Backed up to $BACKUP_DIR${NC}" | tee -a "$LOGFILE"
else
    echo -e "${YELLOW}No previous install found.${NC}" | tee -a "$LOGFILE"
fi
draw_bar 85 "Backup complete"

# Step 6: Clone repository
draw_bar 88 "Downloading TerminalFormer2..."
echo -e "${BLUE}\nCloning repository to $INSTALL_DIR ...${NC}" | tee -a "$LOGFILE"
git clone "$REPO_URL" "$INSTALL_DIR" 2>&1 | tee -a "$LOGFILE" || true
if [ ! -d "$INSTALL_DIR" ]; then
    tput cnorm 2>/dev/null || true
    echo -e "\n${RED}ERROR: clone failed. Check $LOGFILE${NC}" | tee -a "$LOGFILE"
    exit 1
fi
draw_bar 92 "Repository downloaded"

# Step 7: Restore user data
draw_bar 94 "Restoring user data..."
echo -e "${BLUE}Restoring scores & levels (if any)...${NC}" | tee -a "$LOGFILE"
[ -f "$BACKUP_DIR/scores.json" ] && mv "$BACKUP_DIR/scores.json" "$INSTALL_DIR/" || true
if [ -d "$BACKUP_DIR/levels" ]; then
    mkdir -p "$INSTALL_DIR/levels"
    cp -rn "$BACKUP_DIR/levels/"* "$INSTALL_DIR/levels/" 2>/dev/null || true
fi
rm -rf "$BACKUP_DIR" 2>/dev/null || true
draw_bar 96 "User data restored"

# Step 8: Create launcher (wrapper)
draw_bar 98 "Creating launcher + desktop file..."
echo -e "${BLUE}\nCreating launcher at /usr/local/bin/$BIN_NAME${NC}" | tee -a "$LOGFILE"
LAUNCHER_PATH="/usr/local/bin/$BIN_NAME"
cat <<'EOF' > tf2_launcher.tmp
#!/usr/bin/env bash
# TerminalFormer2 launcher wrapper
INSTALL_DIR="${INSTALL_DIR_PLACEHOLDER}"
cd "$INSTALL_DIR" || exit 1
TARGET="game.py"
if [ -f "menu.py" ]; then
    TARGET="menu.py"
fi
# export a hint env var for prefer_evdev if you want to override later
echo "Launching $TARGET..."
python3 "$TARGET" "$@"
EXIT_CODE=$?
echo ""
echo "=================================================="
echo " Application Exited (Code: $EXIT_CODE)"
echo "=================================================="
read -p "Press ENTER to close this window..."
exit $EXIT_CODE
EOF

# insert right install dir
sed "s|INSTALL_DIR_PLACEHOLDER|$INSTALL_DIR|g" tf2_launcher.tmp > tf2_launcher.sh
chmod +x tf2_launcher.sh
sudo mv tf2_launcher.sh "$LAUNCHER_PATH" 2>/dev/null || sudo mv tf2_launcher.sh "$LAUNCHER_PATH" 2>>"$LOGFILE"
echo -e "${GREEN}Launcher installed to $LAUNCHER_PATH${NC}" | tee -a "$LOGFILE"

# desktop entry
mkdir -p "$HOME/.local/share/applications"
cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Name=TerminalFormer 2
Comment=High-performance terminal platformer
Exec=$LAUNCHER_PATH
Icon=$INSTALL_DIR/icons/icon.png
Terminal=true
Type=Application
Categories=Game;
Keywords=platformer;terminal;game;
EOF
update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true

# final chown and cleanup
draw_bar 100 "Finalizing..."
sudo chown -R "$USER:$USER" "$INSTALL_DIR" 2>/dev/null || true
sleep 0.4
tput cnorm 2>/dev/null || true

echo ""
echo ""
echo -e "${GREEN}${BOLD}==========================================${NC}"
echo -e "${GREEN}${BOLD}       INSTALLATION COMPLETE!             ${NC}"
echo -e "${GREEN}${BOLD}==========================================${NC}"
echo ""
echo -e "${BLUE}Installation directory: ${PURPLE}$INSTALL_DIR${NC}"
echo -e "${BLUE}Launcher command: ${PURPLE}${BIN_NAME}${NC}"
echo ""
if [ "$PERMISSIONS_CHANGED" = true ]; then
    echo -e "${YELLOW}${BOLD}!!! REBOOT REQUIRED !!!${NC}"
    echo -e "${YELLOW}You were added to the 'input' group. Reboot to apply group membership.${NC}"
fi
echo -e "${GREEN}Log file: ${LOGFILE}${NC}"
echo ""

# cleanup background sudo (trap will also handle)
if ps -p "$SUDO_PID" >/dev/null 2>&1; then
    kill "$SUDO_PID" 2>/dev/null || true
fi

exit 0

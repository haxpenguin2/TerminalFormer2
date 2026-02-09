#!/bin/bash

# --- CONFIGURATION ---
REPO_URL="https://github.com/haxpenguin2/TerminalFormer2.git"
INSTALL_DIR="$HOME/.terminal_former2"
BACKUP_DIR="/tmp/tf2_backup_$(date +%s)"
BIN_NAME="terminalformer2"
DESKTOP_FILE="$HOME/.local/share/applications/terminalformer2.desktop"

# --- COLORS ---
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
PURPLE='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

# --- STATE ---
PERMISSIONS_CHANGED=false

# --- CLEANUP ON EXIT ---
cleanup() {
    tput cnorm 2>/dev/null || true
    if [ -n "$SUDO_PID" ]; then
        kill "$SUDO_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# --- HELPER FUNCTIONS ---

print_banner() {
    clear
    echo -e "${CYAN}${BOLD}"
    cat << "EOF"
  _______                   _             _   ______                              ___  
 |__   __|                 (_)           | | |  ____|                            |__ \ 
    | | ___ _ __ _ __ ___   _ _ __   __ _| | | |__ ___  _ __ _ __ ___   ___ _ __    ) |
    | |/ _ \ '__| '_ ` _ \ | | '_ \ / _` | | |  __/ _ \| '__| '_ ` _ \ / _ \ '__|  / / 
    | |  __/ |  | | | | | || | | | | (_| | | | | (_) | |  | | | | | |  __/ |    / /_ 
    |_|\___|_|  |_| |_| |_||_|_| |_|\__,_|_| |_|  \___/|_|  |_| |_| |_|\___|_|   |____|
EOF
    echo -e "${NC}"
    echo -e "${BLUE}  :: High-Performance Terminal Platformer Installer ::${NC}"
    echo -e "${BLUE}  :: v3.3 | Menu Launch | debug-mode enabled        ::${NC}"
    echo ""
}

# $1 = percentage (0-100), $2 = Status text
draw_bar() {
    local width=30
    local percent=$1
    local text=$2

    # Calculate fill width
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

# --- MAIN SCRIPT ---

print_banner

# 0. PRE-FLIGHT CHECK
echo -e "${YELLOW}:: Requesting administrative access for installation...${NC}"
sudo -v
# Keep sudo alive in background so it doesn't timeout during long installs
( while true; do sudo -v; sleep 60; done; ) &
SUDO_PID=$!

# Hide Cursor for a cleaner look
tput civis 2>/dev/null || true

# 1. CHECK DEPENDENCIES (verbose)
draw_bar 5 "Preparing system package installation..."
echo ""
echo -e "${YELLOW}:: Installing system packages (this will be verbose)...${NC}"
if command -v apt-get >/dev/null 2>&1; then
    # update first
    draw_bar 8 "Updating package lists..."
    sudo apt-get update
    draw_bar 12 "Installing required system packages..."
    # core deps + libs for building/pygame
    sudo apt-get install -y \
        python3-evdev git python3 python3-pip curl xterm \
        python3-dev build-essential \
        libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
        libportmidi-dev libfreetype6-dev libavcodec-dev libavformat-dev libswscale-dev \
        libjpeg-dev libpng-dev >/dev/null || {
            # Try again without redirect if apt failed quietly
            echo -e "${YELLOW}:: First attempt redirected - retrying with visible output...${NC}"
            sudo apt-get install -y \
                python3-evdev git python3 python3-pip curl xterm \
                python3-dev build-essential \
                libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
                libportmidi-dev libfreetype6-dev libavcodec-dev libavformat-dev libswscale-dev \
                libjpeg-dev libpng-dev
        }
else
    echo -e "${RED}:: apt-get not found — please install dependencies manually if on a non-Debian distro.${NC}"
fi
draw_bar 25 "System packages installed."

# 2. PIP / PYGAME
draw_bar 30 "Ensuring pip is available..."
# prefer pip3
if command -v pip3 >/dev/null 2>&1; then
    PIP=pip3
elif command -v pip >/dev/null 2>&1; then
    PIP=pip
else
    echo -e "${YELLOW}\n:: Installing pip3 via get-pip.py...${NC}"
    curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    sudo python3 /tmp/get-pip.py
    PIP=pip3
fi

draw_bar 40 "Installing pygame (this may take a moment)..."
echo -e "\n${YELLOW}:: Installing pygame via ${PIP} (verbose output)${NC}"
# Use sudo to ensure system-wide installation (so launcher finds it)
sudo -H "$PIP" install pygame

# Verify pygame
if ! python3 -c "import pygame; print(pygame.ver)" >/dev/null 2>&1; then
    echo -e "${RED}:: Warning: pygame import failed. You may need to install additional libs manually.${NC}"
else
    draw_bar 55 "Pygame installed and verified."
fi

# 3. FIX INPUT PERMISSIONS
draw_bar 60 "Verifying Input Permissions..."
sleep 0.4
if ! groups "$USER" | grep &>/dev/null "\binput\b"; then
    if sudo usermod -a -G input "$USER" > /dev/null 2>&1; then
        PERMISSIONS_CHANGED=true
    else
        PERMISSIONS_CHANGED=false
    fi
fi

# 4. BACKUP
draw_bar 70 "Backing up old data..."
if [ -d "$INSTALL_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    [ -f "$INSTALL_DIR/scores.json" ] && cp "$INSTALL_DIR/scores.json" "$BACKUP_DIR/"
    [ -d "$INSTALL_DIR/levels" ] && cp -r "$INSTALL_DIR/levels" "$BACKUP_DIR/"
    rm -rf "$INSTALL_DIR"
fi

# 5. DOWNLOAD
draw_bar 80 "Downloading TerminalFormer2..."
echo ""
echo -e "${YELLOW}:: Cloning repository (${REPO_URL})...${NC}"
git clone "$REPO_URL" "$INSTALL_DIR"
if [ ! -d "$INSTALL_DIR" ]; then
    tput cnorm
    echo ""
    echo -e "${RED}ERROR: Git clone failed. Check internet connection.${NC}"
    exit 1
fi

# 6. RESTORE
draw_bar 88 "Restoring User Data..."
[ -f "$BACKUP_DIR/scores.json" ] && mv "$BACKUP_DIR/scores.json" "$INSTALL_DIR/"
[ -d "$BACKUP_DIR/levels" ] && mkdir -p "$INSTALL_DIR/levels" && cp -rn "$BACKUP_DIR/levels/"* "$INSTALL_DIR/levels/" 2>/dev/null
rm -rf "$BACKUP_DIR"

# 7. CREATE LAUNCHERS
draw_bar 93 "Creating Shortcuts..."
LAUNCHER_PATH="/usr/local/bin/$BIN_NAME"

# Create wrapper script
cat <<EOF > tf2_launcher.tmp
#!/bin/bash
cd "$INSTALL_DIR"
TARGET="game.py"
if [ -f "menu.py" ]; then
    TARGET="menu.py"
fi
echo "Launching \$TARGET..."
python3 "\$TARGET" "\$@"
EXIT_CODE=\$?
echo ""
echo "=================================================="
echo " Application Exited (Code: \$EXIT_CODE)"
echo "=================================================="
echo "Press ENTER to close this window..."
read
EOF

chmod +x tf2_launcher.tmp
sudo mv tf2_launcher.tmp "$LAUNCHER_PATH"

# Create .desktop file
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

update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1

# 8. FINALIZE
draw_bar 100 "Finalizing..."
sudo chown -R "$USER:$USER" "$INSTALL_DIR" >/dev/null 2>&1
sleep 0.4

# Restore cursor & cleanup (trap will also run)
tput cnorm 2>/dev/null || true

echo ""
echo ""
echo -e "${GREEN}${BOLD}==========================================${NC}"
echo -e "${GREEN}${BOLD}       INSTALLATION COMPLETE!             ${NC}"
echo -e "${GREEN}${BOLD}==========================================${NC}"
echo ""
echo -e "Type 'terminalformer2' to play."
echo ""

if [ "$PERMISSIONS_CHANGED" = true ]; then
    echo -e "${RED}${BOLD}!!! REBOOT REQUIRED !!!${NC}"
    echo -e "${YELLOW}You must reboot for keyboard permissions to work.${NC}"
fi

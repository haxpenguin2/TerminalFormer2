


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
BOLD='\033[1m'
NC='\033[0m'

# --- HELPER FUNCTIONS ---

print_banner() {
    clear
    # We print the color codes first
    echo -e "${CYAN}${BOLD}"
    
    # We use quoted EOF to prevent the shell from eating backslashes
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
    echo -e "${BLUE}  :: v3.2 | Menu Launch | debug-mode enabled        ::${NC}"
    echo ""
}

# $1 = percentage (0-100), $2 = Status text
draw_bar() {
    local width=40
    local percent=$1
    local text=$2
    
    # Calculate how many # and how many .
    local num_filled=$(( (percent * width) / 100 ))
    local num_empty=$(( width - num_filled ))
    
    # Construct the bar
    local bar_filled=$(printf "%0.s#" $(seq 1 $num_filled))
    local bar_empty=$(printf "%0.s." $(seq 1 $num_empty))
    
    # Print using \r to overwrite the line
    echo -ne "\r${BOLD}[${GREEN}${bar_filled}${NC}${bar_empty}${BOLD}] ${percent}% - ${text}${NC}\033[K"
}

# --- MAIN SCRIPT ---

print_banner

# 0. PRE-FLIGHT CHECK
# Refresh sudo credentials upfront so the password prompt doesn't break the loading bar
echo -e "${YELLOW}:: Requesting administrative access for installation...${NC}"
sudo -v
# Keep sudo alive in background
( while true; do sudo -v; sleep 60; done; ) &
SUDO_PID=$!

# Hide Cursor
tput civis

# 1. CHECK DEPENDENCIES
draw_bar 10 "Checking System Libraries..."
if [ -x "$(command -v apt-get)" ]; then
    sudo apt-get update > /dev/null 2>&1
    # We silence the output so it doesn't break the bar
    sudo apt-get install -y python3-evdev git python3 python3-pip curl xterm > /dev/null 2>&1
fi

# 2. FIX INPUT PERMISSIONS
draw_bar 30 "Verifying Input Permissions..."
if ! groups "$USER" | grep &>/dev/null "\binput\b"; then
    if sudo usermod -a -G input "$USER" > /dev/null 2>&1; then
        PERMISSIONS_CHANGED=true
    else
        # If this fails, we can't really stop, but we note it
        PERMISSIONS_CHANGED=false
    fi
fi

# 3. BACKUP
draw_bar 45 "Backing up old data..."
if [ -d "$INSTALL_DIR" ]; then
    mkdir -p "$BACKUP_DIR"
    [ -f "$INSTALL_DIR/scores.json" ] && cp "$INSTALL_DIR/scores.json" "$BACKUP_DIR/"
    [ -d "$INSTALL_DIR/levels" ] && cp -r "$INSTALL_DIR/levels" "$BACKUP_DIR/"
    rm -rf "$INSTALL_DIR"
fi

# 4. DOWNLOAD
draw_bar 60 "Downloading TerminalFormer2..."
git clone "$REPO_URL" "$INSTALL_DIR" > /dev/null 2>&1
if [ ! -d "$INSTALL_DIR" ]; then
    tput cnorm
    echo ""
    echo -e "${RED}ERROR: Git clone failed. Check internet connection.${NC}"
    kill $SUDO_PID
    exit 1
fi

# 5. RESTORE
draw_bar 75 "Restoring User Data..."
[ -f "$BACKUP_DIR/scores.json" ] && mv "$BACKUP_DIR/scores.json" "$INSTALL_DIR/"
[ -d "$BACKUP_DIR/levels" ] && mkdir -p "$INSTALL_DIR/levels" && cp -rn "$BACKUP_DIR/levels/"* "$INSTALL_DIR/levels/" 2>/dev/null
rm -rf "$BACKUP_DIR"

# 6. CREATE LAUNCHERS
draw_bar 90 "Creating Shortcuts..."
LAUNCHER_PATH="/usr/local/bin/$BIN_NAME"

# Create the wrapper script (silently)
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
sudo mv tf2_launcher.tmp "$LAUNCHER_PATH" > /dev/null 2>&1

# Create .desktop file (silently)
mkdir -p "$HOME/.local/share/applications"
cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Name=TerminalFormer 2
Comment=High-performance terminal platformer
Exec=$LAUNCHER_PATH
Icon=utilities-terminal
Terminal=true
Type=Application
Categories=Game;
Keywords=platformer;terminal;game;
EOF

update-desktop-database "$HOME/.local/share/applications" > /dev/null 2>&1

# 7. FINALIZE
draw_bar 100 "Finalizing..."
sudo chown -R "$USER:$USER" "$INSTALL_DIR" > /dev/null 2>&1

# Clean up background sudo
kill $SUDO_PID
# Restore cursor
tput cnorm

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

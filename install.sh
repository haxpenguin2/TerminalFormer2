\#!/bin/bash

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
    echo -e "${CYAN}${BOLD}"
    echo "  _______                   _             _ ______                                  ___  "
    echo " |__   __|                 (_)           | |  ____|                                |__ \ "
    echo "    | | ___ _ __ _ __ ___   _ _ __   __ _| | |__ ___  _ __ _ __ ___   ___ _ __        ) |"
    echo "    | |/ _ \ '__| '_ \` _ \ | | '_ \ / _\` | |  __/ _ \| '__| '_ \` _ \ / _ \ '__|      / / "
    echo "    | |  __/ |  | | | | | | | | | | (_| | | | | (_) | |  | | | | | |  __/ |        / /_ "
    echo "    |_|\___|_|  |_| |_| |_| |_|_| |_|\__,_|_|_|  \___/|_|  |_| |_| |_|\___|_|       |____|"
    echo -e "${NC}"
    echo -e "${BLUE}  :: High-Performance Terminal Platformer Installer ::${NC}"
    echo -e "${BLUE}  :: v3.2 | Menu Launch | debug-mode enabled        ::${NC}"
    echo ""
}

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# --- MAIN SCRIPT ---
print_banner

# 1. CHECK DEPENDENCIES
echo -e "${BOLD}Step 1: Checking System Libraries...${NC}"
if [ -x "$(command -v apt-get)" ]; then
    log_info "Debian/Ubuntu detected."
    sudo apt-get update
    sudo apt-get install -y python3-evdev git python3 python3-pip curl xterm
    log_success "Dependencies installed."
else
    log_warn "Not on Debian/Ubuntu. Assuming dependencies are installed."
fi
echo ""

# 2. FIX INPUT PERMISSIONS
echo -e "${BOLD}Step 2: Verifying Input Permissions...${NC}"
if groups "$USER" | grep &>/dev/null "\binput\b"; then
    log_success "User '$USER' is already in the 'input' group."
else
    log_warn "User '$USER' is NOT in the 'input' group."
    log_info "Attempting to fix permissions..."
    if sudo usermod -a -G input "$USER"; then
        log_success "Permission fix applied!"
        PERMISSIONS_CHANGED=true
    else
        log_error "Failed to fix permissions. Run: sudo usermod -a -G input $USER"
        exit 1
    fi
fi
echo ""

# 3. BACKUP
echo -e "${BOLD}Step 3: Preparing Installation Directory...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    log_info "Backing up data to $BACKUP_DIR..."
    mkdir -p "$BACKUP_DIR"
    [ -f "$INSTALL_DIR/scores.json" ] && cp "$INSTALL_DIR/scores.json" "$BACKUP_DIR/"
    [ -d "$INSTALL_DIR/levels" ] && cp -r "$INSTALL_DIR/levels" "$BACKUP_DIR/"
    rm -rf "$INSTALL_DIR"
fi
echo ""

# 4. DOWNLOAD
echo -e "${BOLD}Step 4: Downloading TerminalFormer2...${NC}"
git clone "$REPO_URL" "$INSTALL_DIR"
if [ ! -d "$INSTALL_DIR" ]; then
    log_error "Git clone failed."
    exit 1
fi
echo ""

# 5. RESTORE
echo -e "${BOLD}Step 5: Restoring User Data...${NC}"
[ -f "$BACKUP_DIR/scores.json" ] && mv "$BACKUP_DIR/scores.json" "$INSTALL_DIR/"
[ -d "$BACKUP_DIR/levels" ] && mkdir -p "$INSTALL_DIR/levels" && cp -rn "$BACKUP_DIR/levels/"* "$INSTALL_DIR/levels/" 2>/dev/null
rm -rf "$BACKUP_DIR"
log_success "Data restored."
echo ""

# 6. CREATE LAUNCHERS (The Important Part)
echo -e "${BOLD}Step 6: Creating Application Shortcuts...${NC}"

LAUNCHER_PATH="/usr/local/bin/$BIN_NAME"
log_info "Creating global command '$BIN_NAME'..."

# We create a robust wrapper that NEVER closes immediately
cat <<EOF > tf2_launcher.tmp
#!/bin/bash
cd "$INSTALL_DIR"

# Logic: Try to run menu.py first. If missing, run game.py
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
echo "If you see an error above, please fix it."
echo "Press ENTER to close this window..."
read
EOF

chmod +x tf2_launcher.tmp
sudo mv tf2_launcher.tmp "$LAUNCHER_PATH"
log_success "Global command updated."

# Create .desktop file
log_info "Creating Desktop Entry..."
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
log_success "Desktop shortcut fixed!"

echo ""

# 7. FINALIZE
echo -e "${BOLD}Step 7: Finalizing...${NC}"
sudo chown -R "$USER:$USER" "$INSTALL_DIR"

echo ""
echo -e "${GREEN}${BOLD}==========================================${NC}"
echo -e "${GREEN}${BOLD}       INSTALLATION COMPLETE!             ${NC}"
echo -e "${GREEN}${BOLD}==========================================${NC}"
echo ""
echo -e "Try opening the app now."
echo -e "It will launch into the MENU (if menu.py exists)."
echo -e "If it crashes, the window will WAIT so you can read the error."
echo ""

if [ "$PERMISSIONS_CHANGED" = true ]; then
    echo -e "${RED}${BOLD}!!! REBOOT REQUIRED !!!${NC}"
    echo -e "${YELLOW}You must reboot for keyboard permissions to work.${NC}"
fi

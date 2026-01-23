#!/bin/bash

# --- CONFIGURATION ---
REPO_URL="https://github.com/haxpenguin2/TerminalFormer2.git"
INSTALL_DIR="$HOME/.terminal_former2"
BACKUP_DIR="/tmp/tf2_backup_$(date +%s)"
BIN_NAME="terminalformer2"
DESKTOP_FILE="$HOME/.local/share/applications/terminalformer2.desktop"

# --- COLORS & STYLES ---
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# --- HELPER FUNCTIONS ---
print_banner() {
    clear
    echo -e "${CYAN}${BOLD}"
    echo "  _______                  _             _   ______                                "
    echo " |__   __|                (_)           | | |  ____|                               "
    echo "    | | ___ _ __ _ __ ___  _ _ __   __ _| | | |__ ___  _ __ _ __ ___   ___ _ __    "
    echo "    | |/ _ \ '__| '_ \` _ \| | '_ \ / _\` | | |  __/ _ \| '__| '_ \` _ \ / _ \ '__|   "
    echo "    | |  __/ |  | | | | | | | | | | (_| | | | | | (_) | |  | | | | | |  __/ |      "
    echo "    |_|\___|_|  |_| |_| |_|_|_| |_|\__,_|_| |_|  \___/|_|  |_| |_| |_|\___|_|      "
    echo -e "${NC}"
    echo -e "${BLUE}  :: High-Performance Terminal Platformer Installer ::${NC}"
    echo -e "${BLUE}  :: v3.0 | Desktop App | Auto-Updater | Perms Fix  ::${NC}"
    echo ""
}

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# --- MAIN SCRIPT ---
print_banner

# 1. CHECK SYSTEM DEPENDENCIES (VISIBLE LOGS)
echo -e "${BOLD}Step 1: Checking System Libraries...${NC}"
if [ -x "$(command -v apt-get)" ]; then
    log_info "Debian/Ubuntu detected. Installing requirements..."
    # We allow the output to be seen now
    sudo apt-get update
    sudo apt-get install -y python3-evdev git python3 python3-pip curl gnome-terminal
    log_success "Dependencies installed."
else
    log_warn "Not on Debian/Ubuntu. Assuming dependencies (python3-evdev, git) are installed manually."
fi

echo ""

# 2. FIX INPUT PERMISSIONS
echo -e "${BOLD}Step 2: Verifying Input Permissions...${NC}"
if groups "$USER" | grep &>/dev/null "\binput\b"; then
    log_success "User '$USER' is already in the 'input' group. Good to go!"
else
    log_warn "User '$USER' is NOT in the 'input' group."
    log_info "Attempting to fix permissions automatically (requires sudo)..."
    
    if sudo usermod -a -G input "$USER"; then
        log_success "Permission fix applied!"
        PERMISSIONS_CHANGED=true
    else
        log_error "Failed to add user to input group. You may need to run: sudo usermod -a -G input $USER"
        exit 1
    fi
fi

echo ""

# 3. BACKUP & PREPARE DIRECTORY
echo -e "${BOLD}Step 3: Preparing Installation Directory...${NC}"

if [ -d "$INSTALL_DIR" ]; then
    log_info "Existing installation found at $INSTALL_DIR"
    log_info "Backing up custom levels and scores to $BACKUP_DIR..."
    
    mkdir -p "$BACKUP_DIR"
    
    # Backup Scores
    if [ -f "$INSTALL_DIR/scores.json" ]; then
        cp "$INSTALL_DIR/scores.json" "$BACKUP_DIR/"
    fi

    # Backup Levels
    if [ -d "$INSTALL_DIR/levels" ]; then
        cp -r "$INSTALL_DIR/levels" "$BACKUP_DIR/"
    fi
    
    log_info "Removing old program files..."
    rm -rf "$INSTALL_DIR"
else
    log_info "Fresh installation. Creating directory..."
fi

echo ""

# 4. CLONE REPOSITORY (VISIBLE LOGS)
echo -e "${BOLD}Step 4: Downloading TerminalFormer2...${NC}"
git clone "$REPO_URL" "$INSTALL_DIR"

if [ -d "$INSTALL_DIR" ]; then
    log_success "Download complete."
else
    log_error "Git clone failed. Check your internet connection."
    exit 1
fi

echo ""

# 5. RESTORE BACKUPS
echo -e "${BOLD}Step 5: Restoring User Data...${NC}"

# Restore Scores
if [ -f "$BACKUP_DIR/scores.json" ]; then
    mv "$BACKUP_DIR/scores.json" "$INSTALL_DIR/"
    log_success "Restored scores."
fi

# Restore Levels
if [ -d "$BACKUP_DIR/levels" ]; then
    mkdir -p "$INSTALL_DIR/levels"
    cp -rn "$BACKUP_DIR/levels/"* "$INSTALL_DIR/levels/" > /dev/null 2>&1
    log_success "Restored custom levels."
fi
rm -rf "$BACKUP_DIR"

echo ""

# 6. CREATE LAUNCHERS & DESKTOP ENTRIES
echo -e "${BOLD}Step 6: Creating Application Shortcuts...${NC}"

# A. Create a global launcher script in /usr/local/bin
LAUNCHER_PATH="/usr/local/bin/$BIN_NAME"
log_info "Creating global command '$BIN_NAME'..."

# Create a temporary launcher file locally first
cat <<EOF > tf2_launcher.tmp
#!/bin/bash
cd "$INSTALL_DIR"
python3 game.py "\$@"
EOF

chmod +x tf2_launcher.tmp
sudo mv tf2_launcher.tmp "$LAUNCHER_PATH"
log_success "Global command installed. You can now type '$BIN_NAME' anywhere!"

# B. Create .desktop file
log_info "Creating Desktop Entry..."
mkdir -p "$HOME/.local/share/applications"

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Name=TerminalFormer 2
Comment=High-performance terminal platformer
Exec=gnome-terminal -- /usr/local/bin/$BIN_NAME
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=Game;
Keywords=platformer;terminal;game;
EOF

# Note: We use "Terminal=false" but "Exec=gnome-terminal" to force a
# FRESH terminal window for the game, ensuring inputs work correctly.

# Update desktop database
update-desktop-database "$HOME/.local/share/applications" > /dev/null 2>&1
log_success "Desktop shortcut created!"

echo ""

# 7. FINALIZE
echo -e "${BOLD}Step 7: Finalizing...${NC}"
sudo chown -R "$USER:$USER" "$INSTALL_DIR"

echo ""
echo -e "${GREEN}${BOLD}==========================================${NC}"
echo -e "${GREEN}${BOLD}       INSTALLATION COMPLETE!             ${NC}"
echo -e "${GREEN}${BOLD}==========================================${NC}"
echo ""
echo -e "You can play the game in three ways:"
echo -e "  1. Type ${CYAN}$BIN_NAME${NC} in any terminal."
echo -e "  2. Search for ${CYAN}TerminalFormer 2${NC} in your Apps menu."
echo -e "  3. Run ${CYAN}python3 $INSTALL_DIR/game.py${NC}"
echo ""

if [ "$PERMISSIONS_CHANGED" = true ]; then
    echo -e "${RED}${BOLD}!!! IMPORTANT REBOOT REQUIRED !!!${NC}"
    echo -e "${YELLOW}We enabled hardware input permissions for your user.${NC}"
    echo -e "${YELLOW}${BOLD}PLEASE REBOOT YOUR COMPUTER NOW.${NC}"
    echo -e "${YELLOW}If you don't, the game will crash with 'Permission Denied'.${NC}"
    echo ""
fi

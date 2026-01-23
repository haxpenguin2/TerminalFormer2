#!/bin/bash

# --- CONFIGURATION ---
REPO_URL="https://github.com/haxpenguin2/TerminalFormer2.git"
INSTALL_DIR="$HOME/.terminal_former2"
BACKUP_DIR="/tmp/tf2_backup_$(date +%s)"
USER_GROUP="input"

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
    echo -e "${BLUE}  :: v2.5 | Auto-Updater | Permission Fixer         ::${NC}"
    echo ""
}

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# --- MAIN SCRIPT ---
print_banner

# 1. CHECK SYSTEM DEPENDENCIES
echo -e "${BOLD}Step 1: Checking System Dependencies...${NC}"
if [ -x "$(command -v apt-get)" ]; then
    log_info "Debian/Ubuntu detected. Installing requirements..."
    sudo apt-get update -qq > /dev/null 2>&1
    sudo apt-get install -y python3-evdev git python3 python3-pip -qq > /dev/null 2>&1 &
    spinner $!
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
    log_info "Backing up custom levels and scores..."
    
    mkdir -p "$BACKUP_DIR"
    
    # Backup Scores
    if [ -f "$INSTALL_DIR/scores.json" ]; then
        cp "$INSTALL_DIR/scores.json" "$BACKUP_DIR/"
        log_info "Backed up scores.json"
    fi

    # Backup Levels (Entire folder to be safe)
    if [ -d "$INSTALL_DIR/levels" ]; then
        cp -r "$INSTALL_DIR/levels" "$BACKUP_DIR/"
        log_info "Backed up custom levels"
    fi
    
    # Remove old installation
    log_info "Removing old program files..."
    rm -rf "$INSTALL_DIR"
else
    log_info "Fresh installation. Creating directory..."
fi

echo ""

# 4. CLONE REPOSITORY
echo -e "${BOLD}Step 4: Downloading TerminalFormer2...${NC}"
git clone "$REPO_URL" "$INSTALL_DIR" -q &
spinner $!

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

# Restore Levels (Merge strategy: Don't overwrite default files if they are newer, but ensure user files exist)
# Actually, safest for custom levels is to copy them back.
if [ -d "$BACKUP_DIR/levels" ]; then
    mkdir -p "$INSTALL_DIR/levels"
    cp -rn "$BACKUP_DIR/levels/"* "$INSTALL_DIR/levels/" > /dev/null 2>&1
    log_success "Restored custom levels."
fi

# Cleanup backup folder
rm -rf "$BACKUP_DIR"

echo ""

# 6. FINALIZE
echo -e "${BOLD}Step 6: Finalizing...${NC}"
# Make sure permissions inside the folder are correct for the user
sudo chown -R "$USER:$USER" "$INSTALL_DIR"

# Create a handy alias instruction
echo "alias tf2='python3 $INSTALL_DIR/game.py'" >> ~/.bash_aliases 2>/dev/null

echo ""
echo -e "${GREEN}${BOLD}==========================================${NC}"
echo -e "${GREEN}${BOLD}       INSTALLATION COMPLETE!             ${NC}"
echo -e "${GREEN}${BOLD}==========================================${NC}"
echo ""
echo -e "To play the game, run:"
echo -e "  ${CYAN}python3 $INSTALL_DIR/game.py${NC}"
echo ""

if [ "$PERMISSIONS_CHANGED" = true ]; then
    echo -e "${RED}${BOLD}!!! IMPORTANT !!!${NC}"
    echo -e "${YELLOW}We changed your user permissions to allow keyboard access.${NC}"
    echo -e "${YELLOW}${BOLD}YOU MUST LOG OUT AND LOG BACK IN (OR REBOOT) FOR THIS TO WORK.${NC}"
    echo -e "${YELLOW}If you don't, the game will crash saying 'Permission Denied'.${NC}"
    echo ""
fi

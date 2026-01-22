#!/bin/bash

# ==========================================
# TerminalFormer2 - Ultimate Installer
# ==========================================

# CONFIGURATION
REPO_URL="https://github.com/haxpenguin2/TerminalFormer2.git"
INSTALL_DIR="$HOME/.terminal_former2"
BIN_DIR="/usr/local/bin"
MENU_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"
APP_NAME="terminalformer2"

# COLORS
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================="
echo -e "   TerminalFormer2 Setup Wizard"
echo -e "==========================================${NC}"

# 1. DEPENDENCY CHECK & INSTALLATION
# This fixes the "evdev not found" issue on bare-bones systems.
echo -e "${BLUE}[+] Checking system libraries...${NC}"

if command -v apt-get &> /dev/null; then
    echo -e "${BLUE}    Debian/Ubuntu system detected.${NC}"
    echo -e "${BLUE}    Installing python3-evdev, git, and python3...${NC}"
    # We update quietly and install required libs
    if sudo apt-get update -qq && sudo apt-get install -y python3-evdev git python3; then
        echo -e "${GREEN}    Dependencies installed successfully.${NC}"
    else
        echo -e "${RED}[!] Error installing dependencies. Check internet connection.${NC}"
        exit 1
    fi
elif command -v pacman &> /dev/null; then
    # Arch Linux support
    echo -e "${BLUE}    Arch Linux detected.${NC}"
    sudo pacman -Sy --noconfirm python-evdev git python
else
    # Fallback for other distros
    echo -e "${RED}[!] Warning: Package manager not detected.${NC}"
    echo -e "    Ensure 'git' and 'python3-evdev' are installed manually."
fi

# 2. CLEANUP OLD INSTALLS
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${BLUE}[+] Removing previous installation...${NC}"
    rm -rf "$INSTALL_DIR"
fi

# 3. CLONE REPOSITORY
echo -e "${BLUE}[+] Downloading TerminalFormer2...${NC}"
if git clone -q "$REPO_URL" "$INSTALL_DIR"; then
    echo -e "${GREEN}    Download complete.${NC}"
else
    echo -e "${RED}[!] Git clone failed. Please check your internet.${NC}"
    exit 1
fi

# 4. CREATE LAUNCHER (AUTO-SUDO)
echo -e "${BLUE}[+] creating smart launcher...${NC}"

# We use a heredoc to write the script.
# We escape \$EUID so it is evaluated at RUNTIME.
# We do NOT escape $INSTALL_DIR so it is evaluated NOW (hardcoded path).
LAUNCHER_CONTENT="#!/bin/bash
# TerminalFormer2 Launcher
# Automatically requests sudo for evdev input access.

if [ \"\$EUID\" -ne 0 ]; then
   echo '-------------------------------------------------------'
   echo ' TERMINALFORMER2 - PERMISSION REQUEST'
   echo '-------------------------------------------------------'
   echo ' This game requires direct access to keyboard hardware'
   echo ' for low-latency input (evdev).'
   echo ''
   echo ' Please enter your password below to play.'
   echo '-------------------------------------------------------'
   exec sudo /bin/bash \"\$0\" \"\$@\"
fi

# Navigate to the exact install folder
cd \"$INSTALL_DIR\" || { echo 'Error: Install directory not found.'; read -p 'Press Enter'; exit 1; }

# Run the game
python3 menu.py

# If the game crashes, keep window open
EXIT_CODE=\$?
if [ \$EXIT_CODE -ne 0 ]; then
    echo ''
    echo 'Game crashed or closed unexpectedly.'
    read -p 'Press Enter to close...'
fi
"

echo "$LAUNCHER_CONTENT" > "$INSTALL_DIR/$APP_NAME"
chmod +x "$INSTALL_DIR/$APP_NAME"

# 5. INSTALL GLOBAL COMMAND
echo -e "${BLUE}[+] Installing global command...${NC}"
if [ -f "$BIN_DIR/$APP_NAME" ]; then
    sudo rm "$BIN_DIR/$APP_NAME"
fi
sudo cp "$INSTALL_DIR/$APP_NAME" "$BIN_DIR/$APP_NAME"

# 6. DESKTOP SHORTCUTS
echo -e "${BLUE}[+] Creating desktop icons...${NC}"
TEMP_DESKTOP="/tmp/terminalformer2.desktop"
cat << EOM > "$TEMP_DESKTOP"
[Desktop Entry]
Version=1.0
Type=Application
Name=TerminalFormer2
Comment=Terminal-based platformer engine
Exec=$BIN_DIR/$APP_NAME
Icon=utilities-terminal
Terminal=true
Categories=Game;ActionGame;
EOM

# Install to standard menu location
mkdir -p "$MENU_DIR"
cp "$TEMP_DESKTOP" "$MENU_DIR/terminalformer2.desktop"
chmod +x "$MENU_DIR/terminalformer2.desktop"

# Install to user Desktop
mkdir -p "$DESKTOP_DIR"
cp "$TEMP_DESKTOP" "$DESKTOP_DIR/terminalformer2.desktop"
chmod +x "$DESKTOP_DIR/terminalformer2.desktop"

# 7. COMPLETION
echo -e "${BLUE}=========================================="
echo -e "${GREEN}   INSTALLATION SUCCESSFUL!${NC}"
echo -e "${BLUE}=========================================="
echo -e " 1. Launch from your Desktop icon."
echo -e " 2. Enter password when prompted."
echo -e " 3. Enjoy low-latency inputs!"
echo -e "${BLUE}=========================================="

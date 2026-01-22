#!/bin/bash

# CONFIGURATION
REPO_URL="https://github.com/haxpenguin2/TerminalFormer2.git"
INSTALL_DIR="$HOME/.terminal_former2"
BIN_DIR="/usr/local/bin"
MENU_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"
APP_NAME="terminalformer2"
CURRENT_USER=$(whoami)

echo "Starting TerminalFormer2 installation..."

# 1. Clean up old installs
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing previous version..."
    rm -rf "$INSTALL_DIR"
fi

# 2. Clone the repository
echo "Cloning repository to $INSTALL_DIR..."
git clone -q "$REPO_URL" "$INSTALL_DIR"

# 3. Create the launcher script (FAIL-SAFE METHOD)
echo "Creating launcher script..."
# We use simple echo commands to hardcode the path safely
echo "#!/bin/bash" > "$INSTALL_DIR/$APP_NAME"
echo "echo 'Launching TerminalFormer2...'" >> "$INSTALL_DIR/$APP_NAME"
echo "cd \"$INSTALL_DIR\" || { echo 'Error: Could not find game folder'; read -p 'Press Enter'; exit 1; }" >> "$INSTALL_DIR/$APP_NAME"
echo "python3 menu.py" >> "$INSTALL_DIR/$APP_NAME"
echo "echo ''" >> "$INSTALL_DIR/$APP_NAME"
echo "read -p 'Press Enter to close...'" >> "$INSTALL_DIR/$APP_NAME"

chmod +x "$INSTALL_DIR/$APP_NAME"

# 4. Install Global Command & Fix Groups
echo "Configuring system permissions..."
sudo rm -f "$BIN_DIR/$APP_NAME"
sudo cp "$INSTALL_DIR/$APP_NAME" "$BIN_DIR/$APP_NAME"

if sudo usermod -aG input "$CURRENT_USER"; then
    echo "User added to 'input' group successfully."
else
    echo "Warning: Failed to add user to input group."
fi

# 5. Generate the Desktop Entry
echo "Generating shortcut file..."
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

# 6. Install to Application Menu & Desktop
mkdir -p "$MENU_DIR"
cp "$TEMP_DESKTOP" "$MENU_DIR/terminalformer2.desktop"
chmod +x "$MENU_DIR/terminalformer2.desktop"

mkdir -p "$DESKTOP_DIR"
cp "$TEMP_DESKTOP" "$DESKTOP_DIR/terminalformer2.desktop"
chmod +x "$DESKTOP_DIR/terminalformer2.desktop"

echo "-------------------------------------------------------"
echo "INSTALLATION COMPLETE"
echo "-------------------------------------------------------"
echo "1. LOG OUT and LOG BACK IN to apply permission changes."
echo "2. The game should now launch correctly from the Desktop."
echo "-------------------------------------------------------"

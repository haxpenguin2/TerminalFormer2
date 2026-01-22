#!/bin/bash

# CONFIGURATION
REPO_URL="https://github.com/haxpenguin2/TerminalFormer2.git"
INSTALL_DIR="$HOME/.terminal_former2"
BIN_DIR="/usr/local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
APP_NAME="terminalformer2"

echo "Starting TerminalFormer2 installation..."

# 1. Clean up old installs
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing previous version..."
    rm -rf "$INSTALL_DIR"
fi

# 2. Clone the repository
echo "Cloning repository to $INSTALL_DIR..."
git clone -q "$REPO_URL" "$INSTALL_DIR"

# 3. Create the launcher script
echo "Creating launcher script..."
echo "#!/bin/bash" > "$INSTALL_DIR/$APP_NAME"
echo "cd \"$INSTALL_DIR\"" >> "$INSTALL_DIR/$APP_NAME"
echo "python3 menu.py" >> "$INSTALL_DIR/$APP_NAME"
chmod +x "$INSTALL_DIR/$APP_NAME"

# 4. Create the global shortcut
echo "Installing global command. Sudo password may be required."
if sudo cp "$INSTALL_DIR/$APP_NAME" "$BIN_DIR/$APP_NAME"; then
    echo "Global command created: $APP_NAME"
else
    echo "Error: Failed to create global command."
fi

# 5. Create Desktop Entry
echo "Creating desktop entry..."
mkdir -p "$DESKTOP_DIR"
cat << EOM > "$DESKTOP_DIR/terminalformer2.desktop"
[Desktop Entry]
Version=1.0
Type=Application
Name=TerminalFormer2
Comment=Terminal-based platformer engine
Exec=terminalformer2
Icon=utilities-terminal
Terminal=true
Categories=Game;ActionGame;
EOM

chmod +x "$DESKTOP_DIR/terminalformer2.desktop"

echo "Installation complete."

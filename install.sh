#!/bin/bash

# CONFIGURATION
REPO_URL="https://github.com/haxpenguin2/TerminalFormer2.git"
INSTALL_DIR="$HOME/.terminal_former2"
BIN_DIR="/usr/local/bin"
APP_NAME="terminalformer2"

echo "Installing TerminalFormer2..."

# 1. Clean up old installs
if [ -d "$INSTALL_DIR" ]; then
    echo "Removing old version..."
    rm -rf "$INSTALL_DIR"
fi

# 2. Clone the repository
echo "Downloading game files..."
git clone -q "$REPO_URL" "$INSTALL_DIR"

# 3. Create the launcher script
echo "#!/bin/bash" > "$INSTALL_DIR/$APP_NAME"
echo "cd \"$INSTALL_DIR\"" >> "$INSTALL_DIR/$APP_NAME"
echo "python3 menu.py" >> "$INSTALL_DIR/$APP_NAME"
chmod +x "$INSTALL_DIR/$APP_NAME"

# 4. Create the global shortcut
echo "Finalizing installation..."
echo "Sudo authentication is required to create the '$APP_NAME' command."

if sudo cp "$INSTALL_DIR/$APP_NAME" "$BIN_DIR/$APP_NAME"; then
    echo "Success. Type '$APP_NAME' in any terminal to play."
else
    echo "Warning: Could not create global command."
    echo "You can still play by running: $INSTALL_DIR/$APP_NAME"
fi

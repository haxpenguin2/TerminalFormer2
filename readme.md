
# TerminalFormer2 (1.5.9 HOTFIX RELEASE)

TerminalFormer2 is a high-performance, physics-based platformer engine and level editor designed for the Linux terminal. It utilizes the curses library for graphics and evdev for low-latency hardware input handling.

## Features

* Physics Engine: Real-time collision detection, gravity, and momentum.
* Low-Latency Input: Direct hardware reading via evdev for precise control.
* Level Editor: Design and test custom levels directly from the game menu.
* System Integration: Installs as a native application with a global command and desktop shortcut.
* Save slot system!
* Plugin types include: moving blocks, jump pads, and jump coins! feel free to design your own plugin! 
---

## Installation (Linux)

To install TerminalFormer2, run the following command in your terminal:


curl -sL https://raw.githubusercontent.com/haxpenguin2/TerminalFormer2/main/install.sh | bash

This will put you into the install. it will install on your system form there. if you alreayd have the game installed in an older version, it will "update" and keep all of your data, just add the new features.

### Note on Permissions
Because the game reads your keyboard directly for maximum responsiveness, it requires elevated privileges. **When you launch the game, you will be asked for your sudo password.** This is required for the input system to function.

---

## Controls

| Key | Action |
| :--- | :--- |
| **Arrow Keys** | Move and Jump |
| **R** | Reset Current Level |
| **Q** | Quit to Main Menu |

---

## Uninstallation

To completely remove TerminalFormer2 and all associated system files, run the following commands:

sudo rm /usr/local/bin/terminalformer2
rm -rf ~/.terminal_former2
rm ~/.local/share/applications/terminalformer2.desktop
rm ~/Desktop/terminalformer2.desktop


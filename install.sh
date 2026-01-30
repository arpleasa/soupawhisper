#!/bin/bash
# Install SoupaWhisper on Linux
# Supports: Ubuntu, Pop!_OS, Debian, Fedora, Arch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/soupawhisper"
SERVICE_DIR="$HOME/.config/systemd/user"

# Detect package manager
detect_package_manager() {
    if command -v apt &> /dev/null; then
        echo "apt"
    elif command -v dnf &> /dev/null; then
        echo "dnf"
    elif command -v pacman &> /dev/null; then
        echo "pacman"
    elif command -v zypper &> /dev/null; then
        echo "zypper"
    else
        echo "unknown"
    fi
}

# Install system dependencies
install_deps() {
    local pm=$(detect_package_manager)

    echo "Detected package manager: $pm"
    echo "Installing system dependencies..."

    case $pm in
        apt)
            sudo apt update
            sudo apt install -y alsa-utils xclip xdotool libnotify-bin
            ;;
        dnf)
            sudo dnf install -y alsa-utils xclip xdotool libnotify
            ;;
        pacman)
            sudo pacman -S --noconfirm alsa-utils xclip xdotool libnotify
            ;;
        zypper)
            sudo zypper install -y alsa-utils xclip xdotool libnotify-tools
            ;;
        *)
            echo "Unknown package manager. Please install manually:"
            echo "  alsa-utils xclip xdotool libnotify"
            ;;
    esac
}

# Install Python dependencies
install_python() {
    echo ""
    echo "Installing Python dependencies..."

    if ! command -v poetry &> /dev/null; then
        echo "Poetry not found. Please install Poetry first:"
        echo "  curl -sSL https://install.python-poetry.org | python3 -"
        exit 1
    fi

    poetry install
}

# Setup config file
setup_config() {
    echo ""
    echo "Setting up config..."
    mkdir -p "$CONFIG_DIR"

    if [ ! -f "$CONFIG_DIR/config.ini" ]; then
        cp "$SCRIPT_DIR/config.example.ini" "$CONFIG_DIR/config.ini"
        echo "Created config at $CONFIG_DIR/config.ini"
    else
        echo "Config already exists at $CONFIG_DIR/config.ini"
    fi
}

# Install control utility
install_ctl() {
    echo ""
    echo "Installing control utility..."

    mkdir -p "$HOME/.local/bin"
    cp "$SCRIPT_DIR/soupawhisper-ctl" "$HOME/.local/bin/soupawhisper-ctl"
    chmod +x "$HOME/.local/bin/soupawhisper-ctl"

    echo "Installed soupawhisper-ctl to ~/.local/bin/"

    # Check if ~/.local/bin is in PATH
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        echo ""
        echo "NOTE: Add ~/.local/bin to your PATH:"
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
    fi
}

# Install desktop file
install_desktop() {
    echo ""
    echo "Installing desktop launcher..."

    local desktop_dir="$HOME/.local/share/applications"
    mkdir -p "$desktop_dir"

    cat > "$desktop_dir/soupawhisper.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SoupaWhisper Control
Comment=Manage SoupaWhisper voice dictation service
Exec=gnome-terminal -- soupawhisper-ctl
Icon=audio-input-microphone
Terminal=false
Categories=Utility;AudioVideo;
EOF

    echo "Installed desktop launcher"

    # Also copy to Desktop if it exists
    if [ -d "$HOME/Desktop" ]; then
        cp "$desktop_dir/soupawhisper.desktop" "$HOME/Desktop/"
        chmod +x "$HOME/Desktop/soupawhisper.desktop"
        echo "Copied launcher to Desktop"
    fi
}

# Install systemd service
install_service() {
    echo ""
    echo "Installing systemd user service..."

    mkdir -p "$SERVICE_DIR"

    # Get current display settings
    local display="${DISPLAY:-:0}"
    local xauthority="${XAUTHORITY:-$HOME/.Xauthority}"
    local venv_path="$SCRIPT_DIR/.venv"

    # Check if venv exists
    if [ ! -d "$venv_path" ]; then
        venv_path=$(poetry env info --path 2>/dev/null || echo "$SCRIPT_DIR/.venv")
    fi

    cat > "$SERVICE_DIR/soupawhisper.service" << EOF
[Unit]
Description=SoupaWhisper Voice Dictation
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$venv_path/bin/python $SCRIPT_DIR/dictate.py
Restart=on-failure
RestartSec=5

# X11 display access
Environment=DISPLAY=$display
Environment=XAUTHORITY=$xauthority

[Install]
WantedBy=default.target
EOF

    echo "Created service at $SERVICE_DIR/soupawhisper.service"

    # Reload and enable
    systemctl --user daemon-reload
    systemctl --user enable soupawhisper

    echo ""
    echo "Service installed! Commands:"
    echo "  systemctl --user start soupawhisper   # Start"
    echo "  systemctl --user stop soupawhisper    # Stop"
    echo "  systemctl --user status soupawhisper  # Status"
    echo "  journalctl --user -u soupawhisper -f  # Logs"
}

# Main
main() {
    echo "==================================="
    echo "  SoupaWhisper Installer"
    echo "==================================="
    echo ""

    install_deps
    install_python
    setup_config
    install_ctl

    echo ""
    read -p "Install desktop launcher? [Y/n] " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        install_desktop
    fi

    echo ""
    read -p "Install as systemd service? [y/N] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        install_service
    fi

    echo ""
    echo "==================================="
    echo "  Installation complete!"
    echo "==================================="
    echo ""
    echo "To run manually:"
    echo "  poetry run python dictate.py"
    echo ""
    echo "Control panel:"
    echo "  soupawhisper-ctl"
    echo ""
    echo "Config: $CONFIG_DIR/config.ini"
    echo "Hotkey: F12 (hold to record)"
}

main "$@"

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
            sudo apt install -y alsa-utils xclip xdotool libnotify-bin python3-gi gir1.2-ayatanaappindicator3-0.1
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

# Install soupawhisper-ctl onto PATH
install_ctl() {
    echo ""
    echo "Installing soupawhisper-ctl..."

    local bin_dir="$HOME/.local/bin"
    mkdir -p "$bin_dir"
    ln -sf "$SCRIPT_DIR/soupawhisper-ctl" "$bin_dir/soupawhisper-ctl"
    chmod +x "$SCRIPT_DIR/soupawhisper-ctl"

    echo "Linked soupawhisper-ctl -> $bin_dir/soupawhisper-ctl"
    case ":$PATH:" in
        *":$bin_dir:"*) ;;
        *) echo "Note: $bin_dir is not on your PATH. Add it in your shell profile, e.g.:"
           echo "  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
    esac
}

# Install the tray icon as a systemd user service
install_tray_service() {
    echo ""
    echo "Installing tray icon service..."

    local display="${DISPLAY:-:0}"
    local xauthority="${XAUTHORITY:-$HOME/.Xauthority}"

    cat > "$SERVICE_DIR/soupawhisper-tray.service" << EOF
[Unit]
Description=SoupaWhisper tray icon
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $SCRIPT_DIR/soupawhisper-tray
Restart=on-failure
RestartSec=5
# Exit 3 means the AppIndicator typelib is missing; retrying will not help
RestartPreventExitStatus=3

Environment=DISPLAY=$display
Environment=XAUTHORITY=$xauthority

[Install]
WantedBy=default.target
EOF

    echo "Created service at $SERVICE_DIR/soupawhisper-tray.service"
    systemctl --user daemon-reload
    systemctl --user enable soupawhisper-tray

    if ! /usr/bin/python3 -c "import gi; gi.require_version('AyatanaAppIndicator3', '0.1')" 2>/dev/null; then
        echo "Note: the tray needs PyGObject and Ayatana AppIndicator for /usr/bin/python3"
        echo "  (Debian/Ubuntu: python3-gi gir1.2-ayatanaappindicator3-0.1)."
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
# Flush print() output so journalctl shows backend status lines
Environment=PYTHONUNBUFFERED=1

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
    read -p "Install as systemd service? [y/N] " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        install_service
        install_tray_service
    fi

    echo ""
    echo "==================================="
    echo "  Installation complete!"
    echo "==================================="
    echo ""
    echo "To run manually:"
    echo "  poetry run python dictate.py"
    echo ""
    echo "Config: $CONFIG_DIR/config.ini"
    echo "Hotkey: F12 (hold to record)"
    echo "Exit:   Ctrl+C"
    echo ""
    echo "Control panel: soupawhisper-ctl (installed to ~/.local/bin)"
    echo "Tray icon:     systemctl --user start soupawhisper-tray"
}

main "$@"

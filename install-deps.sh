#!/usr/bin/env bash
# Install wpeek dependencies on Ubuntu 24.04
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing system packages..."
sudo apt install -y \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    gir1.2-gstreamer-1.0 \
    gstreamer1.0-pipewire \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-plugins-bad \
    ffmpeg \
    libnotify-bin

echo ""
echo "Installing desktop file (enables GNOME window introspection)..."
mkdir -p ~/.local/share/applications
cp "$SCRIPT_DIR/com.github.wpeek.desktop" ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true

echo ""
echo "Done!  Run wpeek with:"
echo "  cd $SCRIPT_DIR && /usr/bin/python3 -m wpeek"
echo ""
echo "Note: If window position detection doesn't work on first run,"
echo "log out and back in so GNOME picks up the new desktop file."

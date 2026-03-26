#!/usr/bin/env bash
# Build a .deb package for wpeek
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="${1:-1.1.0}"
PKG="wpeek"
ARCH="all"
BUILD_DIR="$SCRIPT_DIR/build/${PKG}_${VERSION}_${ARCH}"

echo "Building ${PKG} ${VERSION}..."

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/lib/wpeek/wpeek"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/share/applications"
mkdir -p "$BUILD_DIR/usr/share/doc/wpeek"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps"
for size in 16 32 48 64 128 256 512; do
    mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/${size}x${size}/apps"
done
mkdir -p "$BUILD_DIR/usr/share/pixmaps"

# ── Control file ──────────────────────────────────────────────────
cat > "$BUILD_DIR/DEBIAN/control" << EOF
Package: $PKG
Version: $VERSION
Section: video
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.10),
 python3-gi,
 python3-gi-cairo,
 gir1.2-gtk-4.0,
 gir1.2-adw-1,
 gir1.2-gstreamer-1.0,
 gstreamer1.0-pipewire,
 gstreamer1.0-plugins-base,
 gstreamer1.0-plugins-good,
 gstreamer1.0-plugins-ugly,
 gstreamer1.0-plugins-bad,
 ffmpeg
Recommends: libnotify-bin
Installed-Size: $(du -sk "$SCRIPT_DIR/wpeek" | cut -f1)
Homepage: https://github.com/cryan/wpeek
Maintainer: cryan <cryan@localhost>
Description: Peek-like screen area recorder for GNOME Wayland
 wpeek is a screen area recorder for GNOME on Wayland. It records
 your screen selection as GIF, WebM (VP9), or MP4 (H.264).
 .
 Features:
  - Screenshot-based region selector
  - GIF recording with high-quality palette optimization
  - WebM recording with VP9 encoding
  - MP4 recording with H.264 encoding
  - Multi-monitor support
  - Configurable countdown delay
 .
 wpeek uses the Mutter ScreenCast D-Bus API and PipeWire for
 capture, with a GTK4/libadwaita interface.
EOF

# ── Post-install: update desktop database ─────────────────────────
cat > "$BUILD_DIR/DEBIAN/postinst" << 'POSTINST'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications/ 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
fi
POSTINST
chmod 755 "$BUILD_DIR/DEBIAN/postinst"

# ── Post-remove: update desktop database ──────────────────────────
cat > "$BUILD_DIR/DEBIAN/postrm" << 'POSTRM'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications/ 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
fi
POSTRM
chmod 755 "$BUILD_DIR/DEBIAN/postrm"

# ── Python package ────────────────────────────────────────────────
cp "$SCRIPT_DIR/wpeek/__init__.py"  "$BUILD_DIR/usr/lib/wpeek/wpeek/"
cp "$SCRIPT_DIR/wpeek/__main__.py"  "$BUILD_DIR/usr/lib/wpeek/wpeek/"
cp "$SCRIPT_DIR/wpeek/app.py"       "$BUILD_DIR/usr/lib/wpeek/wpeek/"
cp "$SCRIPT_DIR/wpeek/recorder.py"  "$BUILD_DIR/usr/lib/wpeek/wpeek/"

# ── Launcher script ──────────────────────────────────────────────
cat > "$BUILD_DIR/usr/bin/wpeek" << 'LAUNCHER'
#!/usr/bin/python3
"""Launch wpeek."""
import sys
sys.path.insert(0, '/usr/lib/wpeek')
from wpeek.__main__ import main
sys.exit(main())
LAUNCHER
chmod 755 "$BUILD_DIR/usr/bin/wpeek"

# ── Desktop file ─────────────────────────────────────────────────
cat > "$BUILD_DIR/usr/share/applications/com.github.wpeek.desktop" << 'DESKTOP'
[Desktop Entry]
Name=wpeek
Comment=Screen area recorder for GNOME Wayland
Exec=wpeek
Icon=wpeek
Terminal=false
Type=Application
Categories=AudioVideo;Video;Recorder;
Keywords=screencast;recording;gif;video;
StartupNotify=true
X-GNOME-Introspect=true
DESKTOP

# ── Icons ─────────────────────────────────────────────────────────
cp "$SCRIPT_DIR/wpeek.svg" "$BUILD_DIR/usr/share/icons/hicolor/scalable/apps/wpeek.svg"
for size in 16 32 48 64 128 256 512; do
    cp "$SCRIPT_DIR/icons/wpeek-${size}.png" \
       "$BUILD_DIR/usr/share/icons/hicolor/${size}x${size}/apps/wpeek.png"
done
cp "$SCRIPT_DIR/icons/wpeek-48.png" "$BUILD_DIR/usr/share/pixmaps/wpeek.png"

# ── Copyright ─────────────────────────────────────────────────────
cat > "$BUILD_DIR/usr/share/doc/wpeek/copyright" << 'COPYRIGHT'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: wpeek
License: MIT

Files: *
Copyright: 2026 cryan
License: MIT
 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction, including without limitation the rights
 to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 copies of the Software, and to permit persons to whom the Software is
 furnished to do so, subject to the following conditions:
 .
 The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
COPYRIGHT

# ── Build ─────────────────────────────────────────────────────────
dpkg-deb --root-owner-group --build "$BUILD_DIR"

DEB="$SCRIPT_DIR/build/${PKG}_${VERSION}_${ARCH}.deb"
echo ""
echo "Package built: $DEB"
echo "  Size: $(du -h "$DEB" | cut -f1)"
echo ""
echo "Install with:"
echo "  sudo apt install ./${PKG}_${VERSION}_${ARCH}.deb"
echo ""
echo "Uninstall with:"
echo "  sudo apt remove wpeek"

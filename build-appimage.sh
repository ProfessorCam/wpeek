#!/usr/bin/env bash
# Build an AppImage for wpeek
# Requires: wget (to fetch appimagetool if not present)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="${1:-1.2.0}"
LITE="${2:-}"  # pass "lite" as 2nd arg to skip bundling ffmpeg (smaller, needs system ffmpeg)
BUILD_DIR="$SCRIPT_DIR/build/appimage"
APPDIR="$BUILD_DIR/wpeek.AppDir"
TOOLS_DIR="$BUILD_DIR/tools"

echo "Building wpeek ${VERSION} AppImage..."

rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR/usr/lib/wpeek/wpeek"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$TOOLS_DIR"

# ── Fetch appimagetool if needed ──────────────────────────────────
APPIMAGETOOL="$TOOLS_DIR/appimagetool"
if [ ! -x "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    ARCH=$(uname -m)
    wget -q -O "$APPIMAGETOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x "$APPIMAGETOOL"
fi

# ── Python application ────────────────────────────────────────────
cp "$SCRIPT_DIR/wpeek/__init__.py"  "$APPDIR/usr/lib/wpeek/wpeek/"
cp "$SCRIPT_DIR/wpeek/__main__.py"  "$APPDIR/usr/lib/wpeek/wpeek/"
cp "$SCRIPT_DIR/wpeek/app.py"       "$APPDIR/usr/lib/wpeek/wpeek/"
cp "$SCRIPT_DIR/wpeek/recorder.py"  "$APPDIR/usr/lib/wpeek/wpeek/"

# ── Bundle ffmpeg binary (unless lite mode) ──────────────────────
if [ "$LITE" = "lite" ]; then
    echo "  Lite mode: skipping ffmpeg bundle (system ffmpeg required for GIF)"
else
    FFMPEG_PATH=$(which ffmpeg 2>/dev/null || true)
    if [ -n "$FFMPEG_PATH" ]; then
        cp "$FFMPEG_PATH" "$APPDIR/usr/bin/ffmpeg"
        # Copy ffmpeg's shared libraries, excluding core system libs that must
        # always come from the host (bundling glibc causes symbol mismatches on
        # distros with a different glibc version — e.g. the __tunable_is_initialized
        # GLIBC_PRIVATE error seen on Debian).
        EXCLUDE_PATTERN='/(libc|libc-[0-9]|libpthread|libm|libdl|librt|libnsl|libresolv|libutil|libnss_|libmvec|libmemusage|libpcprofile|ld-linux|ld-[0-9]|libGL|libGLX|libGLdispatch|libEGL|libvulkan)\.'
        for lib in $(ldd "$FFMPEG_PATH" 2>/dev/null | grep -oP '/\S+' || true); do
            if [ -f "$lib" ] && ! echo "$lib" | grep -qP "$EXCLUDE_PATTERN"; then
                [ -f "$APPDIR/usr/lib/$(basename "$lib")" ] || cp "$lib" "$APPDIR/usr/lib/" 2>/dev/null || true
            fi
        done
        echo "  Bundled ffmpeg from $FFMPEG_PATH"
    else
        echo "  WARNING: ffmpeg not found — GIF conversion will require system ffmpeg"
    fi
fi

# ── Desktop file ──────────────────────────────────────────────────
cat > "$APPDIR/wpeek.desktop" << 'DESKTOP'
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
cp "$APPDIR/wpeek.desktop" "$APPDIR/usr/share/applications/com.github.wpeek.desktop"

# ── Icons ─────────────────────────────────────────────────────────
cp "$SCRIPT_DIR/icons/wpeek-256.png" "$APPDIR/wpeek.png"
for size in 16 32 48 64 128 256 512; do
    mkdir -p "$APPDIR/usr/share/icons/hicolor/${size}x${size}/apps"
    cp "$SCRIPT_DIR/icons/wpeek-${size}.png" \
       "$APPDIR/usr/share/icons/hicolor/${size}x${size}/apps/wpeek.png"
done
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp "$SCRIPT_DIR/wpeek.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/wpeek.svg"

# ── AppRun ────────────────────────────────────────────────────────
cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
# AppRun for wpeek — uses host system GTK4/GStreamer/PipeWire
HERE="$(dirname "$(readlink -f "$0")")"

# Use bundled ffmpeg if available
if [ -x "${HERE}/usr/bin/ffmpeg" ]; then
    export PATH="${HERE}/usr/bin:${PATH}"
fi

# Use bundled libraries (ffmpeg deps) if present
if [ -d "${HERE}/usr/lib" ]; then
    export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH:-}"
fi

# Ensure system Python can find our app
export PYTHONPATH="${HERE}/usr/lib/wpeek:${PYTHONPATH:-}"

# Ensure the desktop file is available for GNOME introspection
# (copy to user's local applications if not already installed)
DESKTOP_SRC="${HERE}/usr/share/applications/com.github.wpeek.desktop"
DESKTOP_DST="${HOME}/.local/share/applications/com.github.wpeek.desktop"
if [ -f "$DESKTOP_SRC" ] && [ ! -f "$DESKTOP_DST" ]; then
    mkdir -p "$(dirname "$DESKTOP_DST")"
    cp "$DESKTOP_SRC" "$DESKTOP_DST" 2>/dev/null || true
    update-desktop-database "$(dirname "$DESKTOP_DST")" 2>/dev/null || true
fi

exec /usr/bin/python3 -m wpeek "$@"
APPRUN
chmod 755 "$APPDIR/AppRun"

# ── Build AppImage ────────────────────────────────────────────────
export ARCH=$(uname -m)
export VERSION="$VERSION"

# appimagetool may need --appimage-extract-and-run on systems without FUSE
SUFFIX=""
[ "$LITE" = "lite" ] && SUFFIX="-lite"
APPIMAGE_OUT="$SCRIPT_DIR/build/wpeek-${VERSION}-${ARCH}${SUFFIX}.AppImage"
"$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$APPIMAGE_OUT" 2>&1 || \
    "$APPIMAGETOOL" "$APPDIR" "$APPIMAGE_OUT" 2>&1

chmod +x "$APPIMAGE_OUT"

echo ""
echo "AppImage built: $APPIMAGE_OUT"
echo "  Size: $(du -h "$APPIMAGE_OUT" | cut -f1)"
echo ""
echo "Run with:"
echo "  ./$(basename "$APPIMAGE_OUT")"
echo ""
echo "System requirements:"
echo "  - GNOME on Wayland (Mutter ScreenCast)"
echo "  - python3-gi, GTK4, libadwaita"
echo "  - GStreamer with PipeWire plugin"
echo "  - ffmpeg (bundled, or system fallback)"

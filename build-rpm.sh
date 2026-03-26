#!/usr/bin/env bash
# Build an RPM package for wpeek (Fedora/RHEL/DNF)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="${1:-1.1.0}"
RELEASE="${2:-1}"
PKG="wpeek"

echo "Building ${PKG}-${VERSION}-${RELEASE} RPM..."

BUILD_ROOT="$SCRIPT_DIR/build/rpm"
rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# ── Create tarball ────────────────────────────────────────────────
TARDIR="$BUILD_ROOT/SOURCES/${PKG}-${VERSION}"
mkdir -p "$TARDIR/wpeek"
cp "$SCRIPT_DIR/wpeek/__init__.py"  "$TARDIR/wpeek/"
cp "$SCRIPT_DIR/wpeek/__main__.py"  "$TARDIR/wpeek/"
cp "$SCRIPT_DIR/wpeek/app.py"       "$TARDIR/wpeek/"
cp "$SCRIPT_DIR/wpeek/recorder.py"  "$TARDIR/wpeek/"
(cd "$BUILD_ROOT/SOURCES" && tar czf "${PKG}-${VERSION}.tar.gz" "${PKG}-${VERSION}")
rm -rf "$TARDIR"

# ── Spec file ─────────────────────────────────────────────────────
cat > "$BUILD_ROOT/SPECS/${PKG}.spec" << SPEC
Name:           ${PKG}
Version:        ${VERSION}
Release:        ${RELEASE}%{?dist}
Summary:        Screen area recorder for GNOME Wayland
License:        MIT
URL:            https://github.com/cryan/wpeek
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       gstreamer1-plugins-base
Requires:       gstreamer1-plugins-good
Requires:       gstreamer1-plugins-ugly-free
Requires:       gstreamer1-plugins-bad-free
Requires:       gstreamer1-pipewire
Requires:       ffmpeg-free
Recommends:     libnotify

%description
A Peek-like screen recorder that captures GIF, WebM, and MP4
files on GNOME Wayland. Uses Mutter ScreenCast and PipeWire
for screen capture, with a GTK4/libadwaita UI.

%prep
%setup -q

%install
mkdir -p %{buildroot}/usr/lib/%{name}/wpeek
install -m 644 wpeek/__init__.py  %{buildroot}/usr/lib/%{name}/wpeek/
install -m 644 wpeek/__main__.py  %{buildroot}/usr/lib/%{name}/wpeek/
install -m 644 wpeek/app.py       %{buildroot}/usr/lib/%{name}/wpeek/
install -m 644 wpeek/recorder.py  %{buildroot}/usr/lib/%{name}/wpeek/

mkdir -p %{buildroot}/usr/bin
cat > %{buildroot}/usr/bin/%{name} << 'LAUNCHER'
#!/usr/bin/python3
"""Launch wpeek."""
import sys
sys.path.insert(0, '/usr/lib/wpeek')
from wpeek.__main__ import main
sys.exit(main())
LAUNCHER
chmod 755 %{buildroot}/usr/bin/%{name}

mkdir -p %{buildroot}/usr/share/applications
cat > %{buildroot}/usr/share/applications/com.github.wpeek.desktop << 'DESKTOP'
[Desktop Entry]
Name=wpeek
Comment=Screen area recorder for GNOME Wayland
Exec=wpeek
Icon=video-x-generic
Terminal=false
Type=Application
Categories=AudioVideo;Video;Recorder;
Keywords=screencast;recording;gif;video;
StartupNotify=true
X-GNOME-Introspect=true
DESKTOP

%files
/usr/lib/%{name}/
/usr/bin/%{name}
/usr/share/applications/com.github.wpeek.desktop

%changelog
* $(date '+%a %b %d %Y') cryan <cryan@localhost> - ${VERSION}-${RELEASE}
- Initial RPM package
SPEC

# ── Build ─────────────────────────────────────────────────────────
rpmbuild --define "_topdir $BUILD_ROOT" -bb "$BUILD_ROOT/SPECS/${PKG}.spec"

RPM=$(find "$BUILD_ROOT/RPMS" -name '*.rpm' | head -1)
if [ -n "$RPM" ]; then
    cp "$RPM" "$SCRIPT_DIR/build/"
    BASENAME=$(basename "$RPM")
    echo ""
    echo "Package built: $SCRIPT_DIR/build/$BASENAME"
    echo ""
    echo "Install with:"
    echo "  sudo dnf install $SCRIPT_DIR/build/$BASENAME"
    echo ""
    echo "Uninstall with:"
    echo "  sudo dnf remove wpeek"
else
    echo "ERROR: rpmbuild failed — is rpm-build installed?" >&2
    echo "  sudo dnf install rpm-build" >&2
    exit 1
fi

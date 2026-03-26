<p align="center">
  <img src="icons/wpeek-128.png" alt="wpeek icon" width="128">
</p>

<h1 align="center">wpeek</h1>
<p align="center">Simple screen area recorder for GNOME Wayland.<br>A <a href="https://github.com/phw/peek">Peek</a> alternative that works on Wayland.</p>

---

Record your screen as **GIF**, **WebM** (VP9), or **MP4** (H.264). Select any region, hit record, and get your file.

## Features

- Screenshot-based region selector
- GIF with high-quality palette optimization
- WebM (VP9) and MP4 (H.264) output
- Multi-monitor support
- Configurable countdown delay (0/3/5/10s)
- GTK4 + libadwaita UI

## Install

### Ubuntu/Debian (.deb)

```bash
sudo apt install ./wpeek_1.2.0_all.deb
```

### Fedora/RHEL (.rpm)

```bash
# Build on a Fedora system:
./build-rpm.sh 1.2.0
sudo dnf install ./build/wpeek-1.2.0-1.*.noarch.rpm
```

### AppImage

```bash
chmod +x wpeek-1.2.0-x86_64.AppImage
./wpeek-1.2.0-x86_64.AppImage
```

### From source

```bash
./install-deps.sh
./run.sh
```

## Requirements

- GNOME on Wayland (uses Mutter ScreenCast + PipeWire)
- Python 3.10+, GTK4, libadwaita, GStreamer
- ffmpeg (for GIF conversion)

## Usage

1. Launch **wpeek**
2. Pick format and delay
3. Click **Record** (or <kbd>Ctrl</kbd>+<kbd>R</kbd>)
4. Drag to select a screen region
5. Click **Stop** (or <kbd>Ctrl</kbd>+<kbd>R</kbd> / <kbd>Esc</kbd>)
6. File is saved to `~/Videos/`

## Building packages

```bash
./build-deb.sh 1.2.0           # .deb
./build-rpm.sh 1.2.0           # .rpm (requires Fedora)
./build-appimage.sh 1.2.0      # AppImage (bundles ffmpeg)
./build-appimage.sh 1.2.0 lite # AppImage lite (uses system ffmpeg)
```

## License

MIT

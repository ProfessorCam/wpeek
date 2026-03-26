"""wpeek GTK4 application – screen area recorder for GNOME Wayland."""

import os
import subprocess
import tempfile
from datetime import datetime

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

import cairo
from gi.repository import Adw, Gdk, GLib, Gtk

from wpeek import recorder

# ── CSS ───────────────────────────────────────────────────────────────

CSS = """\
.wpeek-headerbar { min-height: 36px; }
.status-ready      { color: alpha(@window_fg_color, 0.55); font-size: 12px; }
.status-recording  { color: #e74c3c; font-weight: bold; font-size: 12px; }
.status-converting { color: #f39c12; font-weight: bold; font-size: 12px; }
.status-done       { color: #27ae60; font-size: 12px; }
.status-error      { color: #e74c3c; font-size: 12px; }
"""

# ── Screenshot helper ─────────────────────────────────────────────────


def _take_screenshot(path, connector):
    """Take a screenshot of a specific monitor."""
    # Try CLI tools first (they grab the whole desktop but it's better than nothing)
    for cmd in [['gnome-screenshot', '-f', path], ['grim', path]]:
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=5)
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return True
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired):
            continue
    # Fallback: Mutter ScreenCast single-frame capture of the specific monitor
    return recorder.capture_screenshot(path, connector=connector)


# ── Selection window (screenshot background) ─────────────────────────


class SelectionWindow(Gtk.Window):
    """Fullscreen window showing a screenshot. User drags to select a region."""

    def __init__(self, app, screenshot_path, monitor_offset, on_selected, on_cancelled):
        """
        Args:
            monitor_offset: (ox, oy) – the monitor's position in compositor
                space.  Added to drag coordinates so RecordArea gets absolute
                compositor coordinates.
        """
        super().__init__(application=app)
        self._on_selected = on_selected
        self._on_cancelled = on_cancelled
        self._screenshot_path = screenshot_path
        self._ox, self._oy = monitor_offset

        self.set_decorated(False)
        self.fullscreen()
        self.set_cursor(Gdk.Cursor.new_from_name('crosshair'))

        self._sx = self._sy = self._cx = self._cy = 0.0
        self._dragging = False

        overlay = Gtk.Overlay()

        if screenshot_path and os.path.exists(screenshot_path):
            pic = Gtk.Picture.new_for_filename(screenshot_path)
            pic.set_content_fit(Gtk.ContentFit.FILL)
            overlay.set_child(pic)
        else:
            overlay.set_child(Gtk.Box(vexpand=True))

        self._canvas = Gtk.DrawingArea()
        self._canvas.set_draw_func(self._draw)
        self._canvas.set_can_target(True)
        overlay.add_overlay(self._canvas)
        self.set_child(overlay)

        drag = Gtk.GestureDrag.new()
        drag.connect('drag-begin', self._begin)
        drag.connect('drag-update', self._update)
        drag.connect('drag-end', self._end)
        self._canvas.add_controller(drag)

        esc = Gtk.ShortcutController()
        esc.set_scope(Gtk.ShortcutScope.GLOBAL)
        esc.add_shortcut(Gtk.Shortcut.new(
            Gtk.KeyvalTrigger.new(Gdk.KEY_Escape, 0),
            Gtk.CallbackAction.new(lambda *_: self._cancel()),
        ))
        self.add_controller(esc)

    def _rect(self):
        x = min(self._sx, self._cx)
        y = min(self._sy, self._cy)
        return x, y, abs(self._cx - self._sx), abs(self._cy - self._sy)

    def _draw(self, _a, cr, width, height):
        if not self._dragging:
            cr.set_source_rgba(0, 0, 0, 0.25)
            cr.paint()
            cr.set_source_rgba(1, 1, 1, 0.8)
            cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL,
                                cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(22)
            txt = 'Drag to select the recording area  \u2022  Esc to cancel'
            ext = cr.text_extents(txt)
            cr.move_to((width - ext.width) / 2, (height + ext.height) / 2)
            cr.show_text(txt)
            return

        x, y, w, h = self._rect()

        # Dim everything AROUND the selection
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.rectangle(0, 0, width, y); cr.fill()
        cr.rectangle(0, y + h, width, height - y - h); cr.fill()
        cr.rectangle(0, y, x, h); cr.fill()
        cr.rectangle(x + w, y, width - x - w, h); cr.fill()

        # Red border
        cr.set_source_rgba(0.91, 0.30, 0.24, 0.95)
        cr.set_line_width(2)
        cr.rectangle(x, y, w, h)
        cr.stroke()

        # Dimension label
        cr.select_font_face('monospace', cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(14)
        label = f'{int(w)} \u00d7 {int(h)}'
        ext = cr.text_extents(label)
        lx = x + (w - ext.width) / 2
        ly = y + h + 22
        if ly + 4 > height:
            ly = y - 10
        pad = 5
        cr.set_source_rgba(0, 0, 0, 0.7)
        cr.rectangle(lx - pad, ly - ext.height - pad,
                     ext.width + 2 * pad, ext.height + 2 * pad)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.move_to(lx, ly)
        cr.show_text(label)

    def _begin(self, _g, x, y):
        self._sx, self._sy = x, y
        self._cx, self._cy = x, y
        self._dragging = True

    def _update(self, _g, dx, dy):
        self._cx = self._sx + dx
        self._cy = self._sy + dy
        self._canvas.queue_draw()

    def _end(self, _g, dx, dy):
        self._cx = self._sx + dx
        self._cy = self._sy + dy
        x, y, w, h = self._rect()
        self._dragging = False
        self._cleanup_file()
        self.close()
        if w > 20 and h > 20:
            # Convert window-local coordinates → absolute compositor coordinates
            self._on_selected(int(x + self._ox), int(y + self._oy),
                              int(w), int(h))
        else:
            self._on_cancelled()

    def _cancel(self):
        self._cleanup_file()
        self.close()
        self._on_cancelled()

    def _cleanup_file(self):
        if self._screenshot_path and os.path.exists(self._screenshot_path):
            try:
                os.unlink(self._screenshot_path)
            except OSError:
                pass


# ── Main window ───────────────────────────────────────────────────────


class WpeekWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='wpeek')
        self.set_default_size(420, -1)
        self.set_resizable(False)

        self._app = app
        self._rec = recorder.Recorder()
        self._recording = False
        self._timer_id = None
        self._timer_secs = 0
        self._format = 'gif'
        self._area = None
        self._countdown_id = None
        self._monitors = recorder.get_monitors()

        self._apply_css()
        self._build_ui()
        self._build_shortcuts()
        self.connect('close-request', self._on_close)

    @staticmethod
    def _apply_css():
        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(vbox)

        header = Adw.HeaderBar()
        header.add_css_class('wpeek-headerbar')

        # Left: format + delay
        left = Gtk.Box(spacing=6)
        self._fmt_drop = Gtk.DropDown.new_from_strings(['GIF', 'WebM', 'MP4'])
        self._fmt_drop.set_selected(0)
        self._fmt_drop.set_tooltip_text('Output format')
        self._fmt_drop.connect('notify::selected', self._on_fmt)
        left.append(self._fmt_drop)

        self._delay_drop = Gtk.DropDown.new_from_strings(
            ['No delay', '3 s', '5 s', '10 s'])
        self._delay_drop.set_selected(0)
        self._delay_drop.set_tooltip_text('Countdown before recording')
        left.append(self._delay_drop)
        header.pack_start(left)

        self._title = Adw.WindowTitle(title='wpeek', subtitle='')
        header.set_title_widget(self._title)

        # Right: record / stop
        self._rec_btn = Gtk.Button(icon_name='media-record-symbolic')
        self._rec_btn.add_css_class('destructive-action')
        self._rec_btn.set_tooltip_text('Record  (Ctrl+R)')
        self._rec_btn.connect('clicked', lambda _: self._on_record())
        header.pack_end(self._rec_btn)

        self._stop_btn = Gtk.Button(icon_name='media-playback-stop-symbolic')
        self._stop_btn.add_css_class('destructive-action')
        self._stop_btn.set_tooltip_text('Stop  (Ctrl+R / Escape)')
        self._stop_btn.connect('clicked', lambda _: self._on_stop())
        self._stop_btn.set_visible(False)
        header.pack_end(self._stop_btn)
        vbox.append(header)

        # Monitor selector (only shown when >1 monitor)
        if len(self._monitors) > 1:
            mon_box = Gtk.Box(spacing=8, margin_start=18, margin_end=18,
                              margin_top=8)
            mon_box.append(Gtk.Label(label='Monitor:'))
            labels = []
            for conn, mx, my, mw, mh in self._monitors:
                labels.append(f'{conn}  ({mw}\u00d7{mh} at {mx},{my})')
            self._mon_drop = Gtk.DropDown.new_from_strings(labels)
            # Default to the monitor at (0,0) if possible
            for idx, (_c, mx, my, _w, _h) in enumerate(self._monitors):
                if mx == 0 and my == 0:
                    self._mon_drop.set_selected(idx)
                    break
            self._mon_drop.set_hexpand(True)
            mon_box.append(self._mon_drop)
            vbox.append(mon_box)
        else:
            self._mon_drop = None

        # Status
        self._status = Gtk.Label(
            label='Press Record or Ctrl+R to select an area')
        self._status.add_css_class('status-ready')
        self._status.set_wrap(True)
        self._status.set_margin_top(14)
        self._status.set_margin_bottom(14)
        self._status.set_margin_start(18)
        self._status.set_margin_end(18)
        vbox.append(self._status)

    def _build_shortcuts(self):
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.GLOBAL)
        ctrl.add_shortcut(Gtk.Shortcut.new(
            Gtk.KeyvalTrigger.new(Gdk.KEY_r, Gdk.ModifierType.CONTROL_MASK),
            Gtk.CallbackAction.new(lambda *_: self._on_record_or_stop())))
        ctrl.add_shortcut(Gtk.Shortcut.new(
            Gtk.KeyvalTrigger.new(Gdk.KEY_Escape, 0),
            Gtk.CallbackAction.new(lambda *_: self._on_escape())))
        self.add_controller(ctrl)

    # ── Monitor helpers ───────────────────────────────────────────

    def _selected_monitor(self):
        """Return (connector, x, y, w, h) for the chosen monitor."""
        if not self._monitors:
            return None
        idx = self._mon_drop.get_selected() if self._mon_drop else 0
        return self._monitors[idx]

    # ── Status ────────────────────────────────────────────────────

    def _set_status(self, text, cls='status-ready'):
        for c in ('status-ready', 'status-recording',
                  'status-converting', 'status-done', 'status-error'):
            self._status.remove_css_class(c)
        self._status.add_css_class(cls)
        self._status.set_text(text)

    # ── Actions ───────────────────────────────────────────────────

    def _on_fmt(self, drop, _p):
        self._format = ['gif', 'webm', 'mp4'][drop.get_selected()]

    def _on_record_or_stop(self):
        if self._recording:
            self._on_stop()
        else:
            self._on_record()

    def _on_record(self):
        if self._recording:
            return
        self._rec_btn.set_sensitive(False)
        self._set_status('Taking screenshot\u2026')
        GLib.timeout_add(100, self._do_screenshot)

    def _on_stop(self):
        if self._recording:
            self._rec.stop()

    def _on_escape(self):
        if self._recording:
            self._on_stop()
        else:
            self.close()

    # ── Screenshot + selection ────────────────────────────────────

    def _do_screenshot(self):
        mon = self._selected_monitor()
        if mon is None:
            self.present()
            self._rec_btn.set_sensitive(True)
            self._set_status('No monitor found', 'status-error')
            return False

        connector, mx, my, mw, mh = mon
        tmp = os.path.join(tempfile.gettempdir(), 'wpeek_bg.png')
        _take_screenshot(tmp, connector)

        sel = SelectionWindow(
            self._app, tmp,
            monitor_offset=(mx, my),
            on_selected=self._on_area_selected,
            on_cancelled=self._on_area_cancelled,
        )
        sel.present()
        return False

    def _on_area_selected(self, x, y, w, h):
        self._area = (x, y, w, h)
        self.present()
        self._rec_btn.set_sensitive(True)

        delays = [0, 3, 5, 10]
        delay = delays[self._delay_drop.get_selected()]
        if delay > 0:
            self._start_countdown(delay)
        else:
            self._start_capture()

    def _on_area_cancelled(self):
        self.present()
        self._rec_btn.set_sensitive(True)
        self._set_status('Selection cancelled')

    # ── Countdown ─────────────────────────────────────────────────

    def _start_countdown(self, secs):
        self._remaining = secs
        self._set_status(f'Starting in {secs}\u2026', 'status-recording')
        self._countdown_id = GLib.timeout_add(1000, self._tick_cd)

    def _tick_cd(self):
        self._remaining -= 1
        if self._remaining > 0:
            self._set_status(f'Starting in {self._remaining}\u2026',
                             'status-recording')
            return True
        self._countdown_id = None
        self._start_capture()
        return False

    # ── Recording ─────────────────────────────────────────────────

    def _output_path(self):
        d = os.path.expanduser('~/Videos')
        os.makedirs(d, exist_ok=True)
        ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        return os.path.join(d, f'wpeek_{ts}.{self._format}')

    def _start_capture(self):
        x, y, w, h = self._area
        out = self._output_path()
        self._rec.start(x, y, w, h, out, self._format, callbacks={
            'started': self._cb_started,
            'stopped': self._cb_stopped,
            'converting': self._cb_converting,
            'error': self._cb_error,
        })

    def _cb_started(self):
        self._recording = True
        self._rec_btn.set_visible(False)
        self._stop_btn.set_visible(True)
        self._fmt_drop.set_sensitive(False)
        self._delay_drop.set_sensitive(False)
        if self._mon_drop:
            self._mon_drop.set_sensitive(False)
        x, y, w, h = self._area
        self._title.set_subtitle(f'{w}\u2009\u00d7\u2009{h}')
        self._timer_secs = 0
        self._timer_id = GLib.timeout_add(1000, self._tick_timer)
        self._set_status('Recording\u2026  0:00', 'status-recording')

    def _cb_converting(self):
        self._recording = False
        self._teardown()
        self._rec_btn.set_sensitive(False)
        self._set_status('Converting to GIF\u2026', 'status-converting')

    def _cb_stopped(self, path):
        self._recording = False
        self._teardown()
        self._rec_btn.set_sensitive(True)
        fname = os.path.basename(path)
        self._set_status(f'Saved {fname}', 'status-done')
        self._title.set_subtitle('')
        try:
            subprocess.Popen(
                ['notify-send', '-i', 'video-x-generic',
                 'wpeek', f'Saved to {path}'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            pass

    def _cb_error(self, msg):
        self._recording = False
        self._teardown()
        self._rec_btn.set_sensitive(True)
        self._set_status(f'Error: {msg}', 'status-error')

    def _teardown(self):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        self._stop_btn.set_visible(False)
        self._rec_btn.set_visible(True)
        self._fmt_drop.set_sensitive(True)
        self._delay_drop.set_sensitive(True)
        if self._mon_drop:
            self._mon_drop.set_sensitive(True)

    def _tick_timer(self):
        if not self._recording:
            return False
        self._timer_secs += 1
        m, s = divmod(self._timer_secs, 60)
        self._set_status(f'Recording\u2026  {m}:{s:02d}', 'status-recording')
        return True

    def _on_close(self, _w):
        if self._recording:
            self._rec.stop()
        return False


# ── Application ───────────────────────────────────────────────────────


class WpeekApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.github.wpeek')
        self.connect('activate', self._on_activate)

    def _on_activate(self, _app):
        win = WpeekWindow(self)
        win.present()

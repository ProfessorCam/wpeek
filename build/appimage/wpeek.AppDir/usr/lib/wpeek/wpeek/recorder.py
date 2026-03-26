"""Screen recording backend using GNOME Mutter ScreenCast D-Bus API + GStreamer."""

import os
import subprocess
import threading

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gio, GLib, Gst


def _have_element(name):
    """Check if a GStreamer element is available."""
    return Gst.ElementFactory.find(name) is not None


class Recorder:
    """Records a screen region via Mutter ScreenCast + GStreamer pipeline."""

    def __init__(self):
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._session_path = None
        self._session = None
        self._pipeline = None
        self._node_id = None
        self._recording = False
        self._output_path = None
        self._format = 'gif'
        self._tmp_path = None
        self._callbacks = {}
        self._signal_sub_id = None

    @property
    def is_recording(self):
        return self._recording

    def start(self, x, y, width, height, output_path, fmt='gif', callbacks=None):
        """Start recording a screen area (absolute compositor coordinates)."""
        self._output_path = output_path
        self._format = fmt
        self._callbacks = callbacks or {}

        width -= width % 2
        height -= height % 2

        if width < 10 or height < 10:
            self._emit('error', 'Recording area too small')
            return

        self._area_w = width
        self._area_h = height

        try:
            self._create_session(x, y, width, height)
        except Exception as e:
            self._emit('error', str(e))

    def stop(self):
        if not self._recording:
            return
        self._recording = False
        if self._pipeline:
            self._pipeline.send_event(Gst.Event.new_eos())

    # ── D-Bus ─────────────────────────────────────────────────────────

    def _create_session(self, x, y, w, h):
        sc = Gio.DBusProxy.new_sync(
            self._bus, Gio.DBusProxyFlags.NONE, None,
            'org.gnome.Mutter.ScreenCast',
            '/org/gnome/Mutter/ScreenCast',
            'org.gnome.Mutter.ScreenCast', None,
        )
        result = sc.call_sync(
            'CreateSession',
            GLib.Variant('(a{sv})', [{}]),
            Gio.DBusCallFlags.NONE, -1, None,
        )
        self._session_path = result.unpack()[0]

        self._session = Gio.DBusProxy.new_sync(
            self._bus, Gio.DBusProxyFlags.NONE, None,
            'org.gnome.Mutter.ScreenCast',
            self._session_path,
            'org.gnome.Mutter.ScreenCast.Session', None,
        )

        props = {'cursor-mode': GLib.Variant('u', 1)}
        result = self._session.call_sync(
            'RecordArea',
            GLib.Variant('(iiiia{sv})', [x, y, w, h, props]),
            Gio.DBusCallFlags.NONE, -1, None,
        )
        stream_path = result.unpack()[0]

        self._signal_sub_id = self._bus.signal_subscribe(
            'org.gnome.Mutter.ScreenCast',
            'org.gnome.Mutter.ScreenCast.Stream',
            'PipeWireStreamAdded',
            stream_path, None,
            Gio.DBusSignalFlags.NONE,
            self._on_pw_stream, None,
        )
        self._session.call_sync(
            'Start', None, Gio.DBusCallFlags.NONE, -1, None,
        )

    def _stop_session(self):
        if self._session:
            try:
                self._session.call_sync(
                    'Stop', None, Gio.DBusCallFlags.NONE, -1, None)
            except Exception:
                pass
            self._session = None
            self._session_path = None

    # ── PipeWire / GStreamer ──────────────────────────────────────────

    def _on_pw_stream(self, conn, sender, path, iface, signal, params, data):
        self._node_id = params.unpack()[0]
        if self._signal_sub_id is not None:
            self._bus.signal_unsubscribe(self._signal_sub_id)
            self._signal_sub_id = None
        # Delay 250 ms so PipeWire node is fully ready before GStreamer connects
        GLib.timeout_add(250, self._start_pipeline)

    def _start_pipeline(self):
        fmt = self._format

        if fmt == 'gif':
            # Near-lossless intermediate so GIF conversion starts from clean source
            self._tmp_path = self._output_path + '.tmp.mkv'
            target = self._tmp_path
            enc = 'x264enc qp-min=0 qp-max=10 speed-preset=ultrafast tune=zerolatency ! matroskamux' if _have_element('x264enc') else 'vp8enc min-quantizer=0 max-quantizer=4 cpu-used=4 end-usage=vbr target-bitrate=50000000 ! webmmux'
        elif fmt == 'mp4':
            target = self._output_path
            if _have_element('x264enc'):
                h264p = 'h264parse ! ' if _have_element('h264parse') else ''
                enc = f'x264enc tune=zerolatency speed-preset=superfast ! {h264p}mp4mux'
            else:
                enc = 'vp8enc deadline=1 cpu-used=16 ! webmmux'
                target = self._output_path.replace('.mp4', '.webm')
                self._output_path = target
        elif fmt == 'webm':
            target = self._output_path
            if _have_element('vp9enc'):
                enc = 'vp9enc min-quantizer=0 max-quantizer=20 cpu-used=4 end-usage=vbr target-bitrate=20000000 threads=4 ! webmmux'
            else:
                enc = 'vp8enc min-quantizer=0 max-quantizer=10 cpu-used=4 end-usage=vbr target-bitrate=20000000 ! webmmux'
        else:
            target = self._output_path
            enc = 'vp8enc min-quantizer=0 max-quantizer=10 cpu-used=4 end-usage=vbr target-bitrate=20000000 ! webmmux'

        if fmt == 'mp4':
            rawcaps = f'video/x-raw,framerate=30/1,format=I420,width={self._area_w},height={self._area_h}'
        else:
            rawcaps = 'video/x-raw,framerate=30/1'

        pipe_str = (
            f'pipewiresrc path={self._node_id} do-timestamp=true ! '
            f'videoconvert ! videoscale ! videorate ! '
            f'{rawcaps} ! '
            f'{enc} ! filesink location="{target}"'
        )

        self._pipeline = Gst.parse_launch(pipe_str)
        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message::error', self._on_gst_error)
        bus.connect('message::eos', self._on_gst_eos)

        self._pipeline.set_state(Gst.State.PLAYING)
        self._recording = True
        self._emit('started')
        return False

    def _on_gst_eos(self, bus, msg):
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
        self._stop_session()
        if self._format == 'gif' and self._tmp_path:
            self._emit('converting')
            threading.Thread(target=self._convert_gif, daemon=True).start()
        else:
            self._emit('stopped', self._output_path)

    def _on_gst_error(self, bus, msg):
        err, _dbg = msg.parse_error()
        self._emit('error', err.message)
        self._cleanup()

    # ── GIF conversion ────────────────────────────────────────────────

    def _convert_gif(self):
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-i', self._tmp_path,
                 '-vf', 'fps=24,'
                        'split[s0][s1];'
                        '[s0]palettegen=max_colors=256:stats_mode=diff:reserve_transparent=0[p];'
                        '[s1][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle',
                 '-loop', '0', self._output_path],
                check=True, capture_output=True,
            )
            os.unlink(self._tmp_path)
            self._tmp_path = None
            GLib.idle_add(self._emit, 'stopped', self._output_path)
        except Exception as e:
            GLib.idle_add(self._emit, 'error', f'GIF conversion failed: {e}')

    # ── Helpers ───────────────────────────────────────────────────────

    def _cleanup(self):
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
        self._stop_session()
        if self._signal_sub_id is not None:
            self._bus.signal_unsubscribe(self._signal_sub_id)
            self._signal_sub_id = None
        self._recording = False

    def _emit(self, event, *args):
        cb = self._callbacks.get(event)
        if cb:
            cb(*args)
        return False


# ── Screenshot via Mutter ScreenCast ──────────────────────────────────


def capture_screenshot(output_path, connector=None):
    """Capture a screenshot of a specific monitor via Mutter ScreenCast.

    Args:
        output_path: Where to write the PNG.
        connector: Monitor connector name (e.g. 'DP-2'). If None, uses
                   the monitor whose geometry starts at (0,0).
    Returns True on success.
    """
    from gi.repository import Gdk

    if connector is None:
        connector = _primary_connector()
    if connector is None:
        return False

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    try:
        sc = Gio.DBusProxy.new_sync(
            bus, Gio.DBusProxyFlags.NONE, None,
            'org.gnome.Mutter.ScreenCast',
            '/org/gnome/Mutter/ScreenCast',
            'org.gnome.Mutter.ScreenCast', None,
        )
        result = sc.call_sync(
            'CreateSession',
            GLib.Variant('(a{sv})', [{}]),
            Gio.DBusCallFlags.NONE, -1, None,
        )
        session_path = result.unpack()[0]

        session = Gio.DBusProxy.new_sync(
            bus, Gio.DBusProxyFlags.NONE, None,
            'org.gnome.Mutter.ScreenCast',
            session_path,
            'org.gnome.Mutter.ScreenCast.Session', None,
        )

        props = {'cursor-mode': GLib.Variant('u', 0)}
        result = session.call_sync(
            'RecordMonitor',
            GLib.Variant('(sa{sv})', [connector, props]),
            Gio.DBusCallFlags.NONE, -1, None,
        )
        stream_path = result.unpack()[0]

        node_id = [None]
        timed_out = [False]
        loop = GLib.MainLoop.new(None, False)

        def on_stream(_c, _s, _p, _i, _sig, params, _d):
            node_id[0] = params.unpack()[0]
            loop.quit()

        def on_timeout():
            timed_out[0] = True
            loop.quit()
            return False

        sub_id = bus.signal_subscribe(
            'org.gnome.Mutter.ScreenCast',
            'org.gnome.Mutter.ScreenCast.Stream',
            'PipeWireStreamAdded',
            stream_path, None,
            Gio.DBusSignalFlags.NONE,
            on_stream, None,
        )
        timeout_id = GLib.timeout_add(3000, on_timeout)

        session.call_sync('Start', None, Gio.DBusCallFlags.NONE, -1, None)
        loop.run()

        bus.signal_unsubscribe(sub_id)
        if not timed_out[0]:
            GLib.source_remove(timeout_id)

        if node_id[0] is None:
            try:
                session.call_sync('Stop', None, Gio.DBusCallFlags.NONE, -1, None)
            except Exception:
                pass
            return False

        # Small delay for node readiness
        import time
        time.sleep(0.15)

        pipe = Gst.parse_launch(
            f'pipewiresrc path={node_id[0]} num-buffers=1 ! '
            f'videoconvert ! pngenc ! '
            f'filesink location="{output_path}"'
        )
        pipe.set_state(Gst.State.PLAYING)
        gst_bus = pipe.get_bus()
        msg = gst_bus.timed_pop_filtered(
            5 * Gst.SECOND,
            Gst.MessageType.EOS | Gst.MessageType.ERROR,
        )
        ok = msg is not None and msg.type == Gst.MessageType.EOS
        pipe.set_state(Gst.State.NULL)

        try:
            session.call_sync('Stop', None, Gio.DBusCallFlags.NONE, -1, None)
        except Exception:
            pass

        return ok and os.path.exists(output_path) and os.path.getsize(output_path) > 0

    except Exception as e:
        print(f'Screenshot capture failed: {e}')
        return False


def _primary_connector():
    """Return the connector name of the monitor at (0,0), or the first one."""
    from gi.repository import Gdk
    display = Gdk.Display.get_default()
    monitors = display.get_monitors()
    fallback = None
    for i in range(monitors.get_n_items()):
        m = monitors.get_item(i)
        g = m.get_geometry()
        if fallback is None:
            fallback = m.get_connector()
        if g.x == 0 and g.y == 0:
            return m.get_connector()
    return fallback


def get_monitors():
    """Return list of (connector, x, y, width, height) for each monitor."""
    from gi.repository import Gdk
    display = Gdk.Display.get_default()
    mons = display.get_monitors()
    result = []
    for i in range(mons.get_n_items()):
        m = mons.get_item(i)
        g = m.get_geometry()
        result.append((m.get_connector(), g.x, g.y, g.width, g.height))
    return result

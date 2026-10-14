"""wsstrip — strip workspace ala Spaces macOS di tepi kiri layar (Hyprland).

Daemon GTK4 + gtk4-layer-shell. Tersembunyi; geser masuk saat kursor nempel tepi kiri
(sudut atas/bawah dikecualikan, kiri bawah = hot corner launcher noctalia) atau lewat
`wsstrip-send toggle` (Super+Tab). Klik kartu = pindah ke workspace itu.

Thumbnail: Hyprland gak bisa ditangkap per workspace yang tersembunyi, jadi tiap kali
sebuah workspace aktif (pindah workspace, window buka/tutup/pindah, sebelum strip
muncul) layarnya di-grim kecil ke $XDG_RUNTIME_DIR/wsstrip/ws-N.jpg. Kartu = isi
terakhir yang terlihat. Workspace yang belum pernah dilihat sejak login digambar
pakai ikon aplikasinya saja.
"""
import json
import os
import socket
import subprocess
import threading

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GioUnix", "2.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GioUnix, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LS  # noqa: E402

WORKSPACES = [1, 2, 3, 4, 5]        # semua tampil saat di-pin
FLOAT_COUNT = 3                     # mode melayang (hover) cuma 3 pertama
RUNTIME = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
SOCK = os.path.join(RUNTIME, "wsstrip.sock")
THUMBS = os.path.join(RUNTIME, "wsstrip")
CARD_W, CARD_H = 269, 151          # 16:9 (70% dari 384x216); grim diskalakan ke lebar ini
EDGE_SKIP = 140                    # px sudut atas/bawah yang gak memicu strip
DWELL_MS = 180                     # kursor harus diam di tepi segini dulu
HIDE_MS = 500                      # kursor harus di luar area strip segini baru sembunyi
AREA_PAD = 60                      # area strip = lebar kartu + segini ke kanan
POLL_MS = 100
SETTLE_MS = 650                    # tunggu animasi slide workspace selesai baru grim
PIN_CARD_W, PIN_CARD_H = 200, 113  # kartu saat di-pin (~75%), biar strip gak makan banyak ruang
PIN_FILE = os.path.expanduser("~/.local/state/wsstrip/pinned")

CSS = """
window.wsstrip { background: transparent; font-family: "Inter", sans-serif; }
.hit, window.stripwin { background: rgba(0, 0, 0, 0.01); }
.strip {
  background: rgba(22, 22, 26, 0.50);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
  padding: 8px 16px 12px 10px;
  opacity: 0;
  transform: translateX(-200px);
  transition: opacity 200ms ease-out, transform 380ms cubic-bezier(0.22, 1.15, 0.36, 1);
}
.strip.on { opacity: 1; transform: none; }
.title, .label { text-shadow: 0 1px 3px rgba(0, 0, 0, 0.85); }
.title { color: rgba(255, 255, 255, 0.70); font-size: 10px; font-weight: 700; margin: 0 0 0 4px; }
.label { color: rgba(255, 255, 255, 0.85); font-size: 11px; font-weight: 600; margin: 9px 0 4px 4px; }
.strip.pinned { padding: 6px 10px 8px 8px; border-radius: 14px; }
.strip.pinned .label { font-size: 10px; margin: 6px 0 3px 3px; }
.strip.pinned .title { font-size: 9px; }
.pin {
  min-height: 0; min-width: 0; padding: 1px 7px; margin: 0;
  border-radius: 8px; border: none; box-shadow: none;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.60); font-size: 10px; font-weight: 700;
}
.pin:hover { background: rgba(255, 255, 255, 0.18); color: #ffffff; }
.pin.pinned { background: rgba(255, 255, 255, 0.85); color: #16161a; }
.label.active { color: #ffffff; }
/* miring 3D: sisi kanan menjauh (rotateY dari tepi kiri), tetap landscape.
   Transform kartu per gaya animasi dibangkitkan dari ANIMS (lihat anim_css). */
.card {
  border-radius: 9px;
  border: 2px solid rgba(255, 255, 255, 0.10);
  background: linear-gradient(160deg, #2c3e66, #151a2b);
  box-shadow: 0 18px 30px rgba(0, 0, 0, 0.55), 0 2px 6px rgba(0, 0, 0, 0.40);
  transform-origin: left center;
  opacity: 0;
  transition: transform 460ms cubic-bezier(0.22, 1.2, 0.36, 1), border-color 160ms ease-out,
              box-shadow 200ms ease-out, opacity 220ms ease-out;
}
.card.n1 { transition-delay: 50ms, 0ms, 0ms, 50ms; }
.card.n2 { transition-delay: 100ms, 0ms, 0ms, 100ms; }
.card.n3 { transition-delay: 150ms, 0ms, 0ms, 150ms; }
.card.n4 { transition-delay: 200ms, 0ms, 0ms, 200ms; }
.strip.on .card { opacity: 1; }
.strip.on .card:hover {
  border-color: rgba(255, 255, 255, 0.45);
  box-shadow: 0 24px 40px rgba(0, 0, 0, 0.60), 0 2px 6px rgba(0, 0, 0, 0.40);
  transition-delay: 0ms;
}
.card.active { border-color: #ffffff; }
.card picture { margin: 2px; }
.icons { background: rgba(0, 0, 0, 0.45); border-radius: 7px; padding: 2px 4px; margin: 4px; }
.empty { color: rgba(235, 235, 245, 0.45); font-size: 11px; }
"""


# Gaya animasi masuk kartu: transform saat strip tersembunyi. Posisi diam & hover sama
# untuk semua gaya. Semua pakai daftar fungsi yang sama biar GTK bisa interpolasi.
ANIMS = {
    "pintu": dict(ry=68, s=0.92),            # kartu berayun kayak daun pintu
    "geser": dict(tx=-196),                  # meluncur dari kiri, bertingkat
    "flip": dict(rx=-75),                    # jatuh ke depan kayak Rolodex
    "zoom": dict(s=0.55, ry=40),             # muncul dari kedalaman
    "kipas": dict(rz=-28, ty=-42, s=0.85),   # menyebar kayak kartu remi
}
ANIM_DEFAULT = "kipas"
ANIM_FILE = os.path.expanduser("~/.local/state/wsstrip/anim")


def _tf(tx=0, ty=0, rx=0, ry=24, rz=0, s=1.0):
    return (f"perspective(900px) translate({tx}px, {ty}px) rotateX({rx}deg) "
            f"rotateY({ry}deg) rotate({rz}deg) scale({s})")


def anim_css():
    css = [f".strip.on .card {{ transform: {_tf()}; }}",
           # kartu workspace aktif (atau pilihan keyboard) ikut lurus kayak di-hover
           f".strip.on .card:hover, .strip.on .card.active {{ transform: {_tf(ry=6, s=1.04)}; }}"]
    for name, off in ANIMS.items():
        css.append(f".strip.anim-{name} .card {{ transform: {_tf(**{'ry': 24, **off})}; }}")
    # spesifisitas: aturan .on harus menang atas .anim-X
    css = css[2:] + [c.replace(".strip.on", ".strip.on.on") for c in css[:2]]
    return "\n".join(css)


def hypr(cmd):
    """Query JSON lewat socket perintah Hyprland (~0.1 ms; spawn hyprctl ~4 ms/panggil)."""
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(os.path.join(RUNTIME, "hypr", sig, ".socket.sock"))
            s.sendall(b"j/" + cmd.encode())
            buf = b""
            while chunk := s.recv(65536):
                buf += chunk
        return json.loads(buf)
    except (OSError, ValueError):
        return None


def gdk_monitor(display, name):
    mons = display.get_monitors()
    for i in range(mons.get_n_items()):
        m = mons.get_item(i)
        if m.get_connector() == name:
            return m
    return None


_icon_cache = {}
_info_cache = {}
ACTIVE_APP_FILE = os.path.join(RUNTIME, "rice-active-app")


def app_info(cls):
    """class window -> DesktopAppInfo (atau None)."""
    if cls in _info_cache:
        return _info_cache[cls]
    info = None
    for cand in (cls, cls.lower()):
        try:
            info = GioUnix.DesktopAppInfo.new(cand + ".desktop")
        except TypeError:
            info = None
        if info:
            break
    if not info:
        for group in GioUnix.DesktopAppInfo.search(cls):
            for did in group:
                info = GioUnix.DesktopAppInfo.new(did)
                if info:
                    break
            if info:
                break
    _info_cache[cls] = info
    return info


def app_icon(cls):
    """Ikon dari class window -> .desktop (Gio), fallback ikon generik."""
    if cls not in _icon_cache:
        info = app_info(cls)
        icon = info.get_icon() if info else None
        _icon_cache[cls] = icon or Gio.ThemedIcon.new("application-x-executable")
    return _icon_cache[cls]


def write_active_app(cls):
    """Nama aplikasi aktif (ala menu bar macOS) buat plugin bar noctalia dracarys/appname."""
    info = app_info(cls) if cls else None
    name = (info.get_display_name() if info else cls) or ""
    try:
        with open(ACTIVE_APP_FILE + ".tmp", "w") as f:
            f.write(name)
        os.replace(ACTIVE_APP_FILE + ".tmp", ACTIVE_APP_FILE)
    except OSError:
        pass
    return False


_tex_cache = {}


def icon_texture(cls, size):
    """Ikon sebagai tekstur bitmap, bukan SVG. GTK 4.24 menggambar ikon SVG sebagai
    path vektor (fill node); path itu di dalam kartu yang dianimasikan bikin renderer
    GSK gpu abort (gsk_gpu_render_pass_draw_clip_mask). Dirasterisasi 2x biar tetap
    tajam saat kartu diperbesar."""
    key = (cls, size)
    if key in _tex_cache:
        return _tex_cache[key]
    tex = None
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    paint = theme.lookup_by_gicon(app_icon(cls), size, 2, Gtk.TextDirection.NONE, 0)
    f = paint.get_file() if paint else None
    path = f.get_path() if f else None
    if path:
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size * 2, size * 2)
            ok, buf = pb.save_to_bufferv("png", [], [])
            if ok:
                tex = Gdk.Texture.new_from_bytes(GLib.Bytes.new(buf))
        except GLib.Error:
            tex = None
    _tex_cache[key] = tex
    return tex


class CardPicture(Gtk.Picture):
    """Picture berukuran tetap CARD_W x CARD_H: ukuran asli gambar (thumbnail lama 384px,
    atau area kanan strip ter-pin yang rasionya beda) gak boleh melebarkan kartu."""

    pinned = False   # diset Strip._layout; berlaku untuk semua kartu

    def do_measure(self, orientation, for_size):
        w, h = (PIN_CARD_W, PIN_CARD_H) if CardPicture.pinned else (CARD_W, CARD_H)
        n = w if orientation == Gtk.Orientation.HORIZONTAL else h
        return n, n, -1, -1


class Card:
    def __init__(self, strip, ws, n):
        self.ws = ws
        self.label = Gtk.Label(label=f"Desktop {ws}", xalign=0)
        self.label.add_css_class("label")
        self.overlay = Gtk.Overlay()
        self.overlay.add_css_class("card")
        self.overlay.add_css_class(f"n{n}")
        # jangan overflow HIDDEN: clip rounded GTK dihitung 2D, gambar kepotong saat kartu
        # diputar rotateY. Sudut gambar dibulatkan lewat padding kecil + radius kartu.
        self.overlay.set_cursor(Gdk.Cursor.new_from_name("pointer"))
        self.pic = CardPicture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self.overlay.set_child(self.pic)
        self.icons = Gtk.Box(spacing=4, halign=Gtk.Align.START, valign=Gtk.Align.END)
        self.icons.add_css_class("icons")
        self.overlay.add_overlay(self.icons)
        self.empty = Gtk.Label(label="Kosong", halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.empty.add_css_class("empty")
        self.overlay.add_overlay(self.empty)
        click = Gtk.GestureClick()
        click.connect("released", lambda *_: strip.go(ws))
        self.overlay.add_controller(click)

    def update(self, classes, active):
        path = os.path.join(THUMBS, f"ws-{self.ws}.jpg")
        has_thumb = os.path.exists(path)
        if has_thumb:
            # Gio.File baru tiap kali biar gambar dimuat ulang, bukan dari cache Picture
            self.pic.set_file(Gio.File.new_for_path(path))
        else:
            self.pic.set_paintable(None)
        while (c := self.icons.get_first_child()) is not None:
            self.icons.remove(c)
        for cls in classes[:6]:
            size = 26 if not has_thumb else 16
            tex = icon_texture(cls, size)
            if tex is None:   # tanpa file ikon: lewati daripada risiko path vektor
                continue
            img = Gtk.Image.new_from_paintable(tex)
            img.set_pixel_size(size)
            self.icons.append(img)
        # tanpa thumbnail: ikon di tengah kartu, besar, tanpa pil gelap
        self.icons.set_halign(Gtk.Align.START if has_thumb else Gtk.Align.CENTER)
        self.icons.set_valign(Gtk.Align.END if has_thumb else Gtk.Align.CENTER)
        if has_thumb:
            self.icons.add_css_class("icons")
        else:
            self.icons.remove_css_class("icons")
        self.icons.set_visible(bool(classes))
        self.empty.set_visible(not classes and not has_thumb)
        for w in (self.overlay, self.label):
            (w.add_css_class if active else w.remove_css_class)("active")


class Strip:
    def __init__(self, app):
        self.app = app
        self.win = Gtk.Window(application=app)
        self.win.add_css_class("wsstrip")
        LS.init_for_window(self.win)
        LS.set_namespace(self.win, "wsstrip")
        LS.set_layer(self.win, LS.Layer.OVERLAY)
        # cuma anchor kiri: surface = ukuran kartu, otomatis di tengah vertikal.
        # Latar alpha 1% (.stripwin): Hyprland gak kasih klik ke piksel 100% transparan.
        LS.set_anchor(self.win, LS.Edge.LEFT, True)
        LS.set_exclusive_zone(self.win, -1)
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.NONE)
        self.win.add_css_class("stripwin")

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER,
                           margin_start=8, margin_end=16, margin_top=16, margin_bottom=16)
        self.box.add_css_class("strip")
        self.anim = None
        self.set_anim(load_anim())
        head = Gtk.Box(spacing=6)
        title = Gtk.Label(label="WORKSPACE", xalign=0, hexpand=True)
        title.add_css_class("title")
        head.append(title)
        self.pin_btn = Gtk.Button(label="PIN", valign=Gtk.Align.CENTER)
        self.pin_btn.add_css_class("pin")
        self.pin_btn.set_cursor(Gdk.Cursor.new_from_name("pointer"))
        self.pin_btn.connect("clicked", lambda *_: self.set_pinned(not self.pinned))
        head.append(self.pin_btn)
        self.box.append(head)
        self.none = Gtk.Label(label="Belum ada aplikasi terbuka", xalign=0)
        self.none.add_css_class("label")
        self.box.append(self.none)
        self.cards = []
        for n, ws in enumerate(WORKSPACES):
            c = Card(self, ws, n)
            self.box.append(c.label)
            self.box.append(c.overlay)
            self.cards.append(c)
        self.win.set_child(self.box)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.win.add_controller(keys)
        self.hide_id = self.unmap_id = self.poll_id = None
        self.sel = 0
        self.pinned = False
        self._layout()

    # ---- mode pin ----------------------------------------------------------
    # Lepas: overlay melayang (layer OVERLAY, anchor kiri saja, tanpa exclusive zone).
    # Pin: layer TOP, anchor kiri+atas+bawah dan exclusive zone otomatis selebar strip,
    # jadi window tiling bergeser ke kanan dan strip makan ruang desktop (kayak bar).
    def _layout(self):
        CardPicture.pinned = self.pinned
        for c in self.cards:
            c.pic.queue_resize()
        self.refresh()
        (self.box.add_css_class if self.pinned else self.box.remove_css_class)("pinned")
        self.box.set_margin_start(4 if self.pinned else 8)
        self.box.set_margin_end(8 if self.pinned else 16)
        LS.set_layer(self.win, LS.Layer.TOP if self.pinned else LS.Layer.OVERLAY)
        for e in (LS.Edge.TOP, LS.Edge.BOTTOM):
            LS.set_anchor(self.win, e, self.pinned)
        if self.pinned:
            LS.auto_exclusive_zone_enable(self.win)
        else:
            LS.set_exclusive_zone(self.win, -1)
        self.pin_btn.set_label("PINNED" if self.pinned else "PIN")
        (self.pin_btn.add_css_class if self.pinned else self.pin_btn.remove_css_class)("pinned")

    def set_pinned(self, on):
        if on == self.pinned:
            return
        self.pinned = on
        try:
            os.makedirs(os.path.dirname(PIN_FILE), exist_ok=True)
            if on:
                open(PIN_FILE, "w").close()
            elif os.path.exists(PIN_FILE):
                os.unlink(PIN_FILE)
        except OSError:
            pass
        if self.poll_id:
            GLib.source_remove(self.poll_id)
            self.poll_id = None
        self._cancel_hide()
        self._layout()
        if on:
            self.show()
        else:
            # lepas pin: kursor biasanya masih di strip, jadi lanjut mode hover biasa
            self.show()
        self.app.edge.win.set_visible(not on)

    def set_anim(self, name):
        if name not in ANIMS:
            return False
        if self.anim:
            self.box.remove_css_class(f"anim-{self.anim}")
        self.anim = name
        self.box.add_css_class(f"anim-{name}")
        return True

    @property
    def visible_cards(self):
        return [c for c in self.cards if c.overlay.get_visible()]

    @property
    def shown(self):
        return self.win.get_visible() and self.unmap_id is None

    def show(self, keyboard=False):
        active = hypr("activeworkspace") or {}
        self._cancel_hide()
        if self.unmap_id:
            GLib.source_remove(self.unmap_id)
            self.unmap_id = None
        self.refresh(active)
        mon = gdk_monitor(self.win.get_display(), active.get("monitor"))
        if mon:
            LS.set_monitor(self.win, mon)
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.EXCLUSIVE if keyboard
                             else LS.KeyboardMode.NONE)
        ids = [c.ws for c in self.visible_cards]
        self.sel = ids.index(active["id"]) if active.get("id") in ids else 0
        if not self.win.get_visible():
            self.box.remove_css_class("on")
            self.win.present()
            GLib.timeout_add(16, lambda: (self.box.add_css_class("on"), False)[1])
        else:
            self.box.add_css_class("on")
        if self.pinned:
            if keyboard:   # Super+Tab saat pin = pilih pakai keyboard, lepas sendiri 6 dtk
                self.hide_id = GLib.timeout_add(6000, self._release_keys)
            return
        # Posisi kursor dipantau langsung (bukan enter/leave GTK: surface muncul di
        # bawah kursor yang diam = gak ada event enter). Selama kursor di kolom strip
        # (lebar strip + AREA_PAD, tinggi berapa pun) strip tetap tampil.
        self.mon_x = next((m["x"] for m in hypr("monitors") or []
                           if m.get("name") == active.get("monitor")), 0)
        self.armed = not keyboard   # via tombol: baru dipantau setelah kursor masuk area
        self.outside = 0
        if keyboard:
            self.hide_id = GLib.timeout_add(6000, self._kb_timeout)
        if not self.poll_id:
            self.poll_id = GLib.timeout_add(POLL_MS, self._poll)

    def _release_keys(self):
        self.hide_id = None
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.NONE)
        self.refresh()
        return False

    def _kb_timeout(self):
        self.hide_id = None
        if not self.armed:
            self.hide()
        return False

    def _poll(self):
        pos = cursor_pos()
        if pos is None:
            return True
        inside = 0 <= pos[0] - self.mon_x <= self.win.get_width() + AREA_PAD
        if inside:
            self.armed, self.outside = True, 0
        elif self.armed:
            self.outside += 1
            if self.outside * POLL_MS >= HIDE_MS:
                self.poll_id = None
                self.hide()
                return False
        return True

    def refresh(self, active=None):
        active = active or hypr("activeworkspace") or {}
        per_ws = {}
        for c in hypr("clients") or []:
            if c.get("mapped", True) and c.get("class"):
                apps = per_ws.setdefault(c["workspace"]["id"], [])
                if c["class"] not in apps:
                    apps.append(c["class"])
        # workspace kosong disembunyikan, kecuali yang sedang dipakai (biar tetap
        # kelihatan lagi di mana). Mode melayang cuma FLOAT_COUNT pertama.
        any_on = False
        for i, card in enumerate(self.cards):
            is_active = card.ws == active.get("id")
            on = (self.pinned or i < FLOAT_COUNT) and (bool(per_ws.get(card.ws)) or is_active)
            card.label.set_visible(on)
            card.overlay.set_visible(on)
            any_on = any_on or on
            if on:
                card.update(per_ws.get(card.ws, []), is_active)
        self.none.set_visible(not any_on)

    def toggle(self):
        if self.pinned:
            self.show(keyboard=True)
            return
        if self.shown:
            self.hide()
            return
        # foto dulu (sebelum strip kelihatan) tapi jangan nunggu lebih dari 200 ms
        state = {"done": False}

        def go():
            if not state["done"]:
                state["done"] = True
                self.show(keyboard=True)
            return False
        capture_async(go)
        GLib.timeout_add(200, go)

    def go(self, ws):
        hypr_eval(f"hl.dispatch(hl.dsp.focus({{ workspace = {ws} }}))")
        self.hide()

    def _on_key(self, ctl, keyval, code, state):
        name = Gdk.keyval_name(keyval) or ""
        if name == "Escape":
            self.hide()
        elif name[-1:].isdigit() and 1 <= int(name[-1]) <= len(self.visible_cards):
            self.go(self.visible_cards[int(name[-1]) - 1].ws)
        elif name in ("Up", "k", "Down", "j", "Tab"):
            step = -1 if name in ("Up", "k") else 1
            self.sel = (self.sel + step) % len(self.visible_cards)
            for i, c in enumerate(self.visible_cards):
                (c.overlay.add_css_class if i == self.sel else c.overlay.remove_css_class)("active")
        elif name in ("Return", "KP_Enter", "space"):
            self.go(self.visible_cards[self.sel].ws)
        else:
            return False
        self._cancel_hide()
        return True

    def _cancel_hide(self):
        if self.hide_id:
            GLib.source_remove(self.hide_id)
            self.hide_id = None

    def hide(self):
        self.hide_id = None
        if self.pinned:   # strip ter-pin gak pernah sembunyi; cukup lepas keyboard
            self._release_keys()
            return False
        if not self.win.get_visible() or self.unmap_id:
            return False
        if self.poll_id:
            GLib.source_remove(self.poll_id)
            self.poll_id = None
        self.box.remove_css_class("on")
        self.unmap_id = GLib.timeout_add(300, self._unmap)
        return False

    def _unmap(self):
        self.unmap_id = None
        self.win.set_visible(False)
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.NONE)
        return False


class EdgeTrigger:
    """Surface 1px transparan di tepi kiri; kursor diam di sana -> strip muncul."""

    def __init__(self, app, strip):
        self.strip = strip
        self.win = Gtk.Window(application=app)
        self.win.add_css_class("wsstrip")
        LS.init_for_window(self.win)
        LS.set_namespace(self.win, "wsstrip-edge")
        LS.set_layer(self.win, LS.Layer.OVERLAY)
        for e in (LS.Edge.LEFT, LS.Edge.TOP, LS.Edge.BOTTOM):
            LS.set_anchor(self.win, e, True)
        LS.set_margin(self.win, LS.Edge.TOP, EDGE_SKIP)
        LS.set_margin(self.win, LS.Edge.BOTTOM, EDGE_SKIP)
        LS.set_exclusive_zone(self.win, -1)
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.NONE)
        # GTK4 tetap kasih surface ini lebar 200px; yang penting cuma area input-nya,
        # jadi input dipotong ke 2px paling kiri (sisanya tembus klik). Piksel 2px itu
        # diberi alpha 1%: Hyprland gak kasih input mouse ke surface 100% transparan.
        hit = Gtk.Box(width_request=2, halign=Gtk.Align.START)
        hit.add_css_class("hit")
        self.win.set_child(hit)
        self.win.connect("realize", self._narrow_input)
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._enter)
        motion.connect("leave", self._leave)
        self.win.add_controller(motion)
        self.dwell = None
        self.win.present()

    def _narrow_input(self, win):
        rect = cairo.RectangleInt(0, 0, 2, 10000)
        win.get_surface().set_input_region(cairo.Region(rect))

    def _enter(self, *_):
        # mulai grim sekarang: selesai (~150 ms) pas jeda dwell habis, jadi strip
        # muncul tanpa nunggu dan gak ikut kefoto
        if not self.strip.win.get_visible():
            capture_async(self._captured)
        if not self.dwell:
            self.dwell = GLib.timeout_add(DWELL_MS, self._fire)

    def _leave(self, *_):
        if self.dwell:
            GLib.source_remove(self.dwell)
            self.dwell = None

    def _fire(self):
        self.dwell = None
        if not self.strip.pinned:
            self.strip.show()
        return False

    def _captured(self):
        # grim kelar setelah strip keburu muncul = muat ulang gambarnya
        if self.strip.shown:
            self.strip.refresh()


def load_anim():
    try:
        with open(ANIM_FILE) as f:
            name = f.read().strip()
        return name if name in ANIMS else ANIM_DEFAULT
    except OSError:
        return ANIM_DEFAULT


def hypr_eval(lua):
    subprocess.Popen(["hyprctl", "eval", lua],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cursor_pos():
    d = hypr("cursorpos")
    return (d["x"], d["y"]) if d and "x" in d else None


_capture = {"proc": None, "waiters": []}


def capture_async(done=None, skip_left=0):
    """Grim workspace aktif -> ws-N.jpg di latar (grim ~150 ms, jangan blok UI).
    `done` dipanggil setelah selesai (atau langsung kalau gak ada yang perlu difoto)."""
    if done:
        _capture["waiters"].append(done)
    if _capture["proc"]:
        return
    active = hypr("activeworkspace") or {}
    ws, mon = active.get("id"), active.get("monitor")
    if ws not in WORKSPACES or not mon:
        return _capture_done(None, None, None)
    m = next((m for m in hypr("monitors") or [] if m.get("name") == mon), None)
    if not m:
        return _capture_done(None, None, None)
    sc = m.get("scale", 1) or 1
    width, height = m["width"] / sc, m["height"] / sc
    # strip ter-pin: foto area desktop di sebelah kanannya saja (strip gak ikut kefoto)
    where = ["-o", mon]
    if skip_left:
        width -= skip_left
        where = ["-g", f"{int(m['x'] + skip_left)},{int(m['y'])} {int(width)}x{int(height)}"]
    os.makedirs(THUMBS, exist_ok=True)
    dst = os.path.join(THUMBS, f"ws-{ws}.jpg")
    try:
        proc = Gio.Subprocess.new(
            ["grim", *where, "-s", f"{CARD_W / width:.4f}", "-t", "jpeg", "-q", "80",
             dst + ".tmp"],
            Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_SILENCE)
    except GLib.Error:
        return _capture_done(None, None, None)
    _capture["proc"] = proc
    proc.wait_check_async(None, _capture_done, dst)


def _capture_done(proc, result, dst):
    _capture["proc"] = None
    try:
        if proc and proc.wait_check_finish(result):
            os.replace(dst + ".tmp", dst)
    except (GLib.Error, OSError):
        pass
    waiters, _capture["waiters"] = _capture["waiters"], []
    for cb in waiters:
        cb()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.dracarys.wsstrip")
        self.capture_id = None

    def do_activate(self):
        self.hold()
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS + anim_css())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 10)
        self.strip = Strip(self)
        self.edge = EdgeTrigger(self, self.strip)
        if os.path.exists(PIN_FILE):
            self.strip.set_pinned(True)
        try:
            os.unlink(SOCK)
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(SOCK)
        GLib.io_add_watch(self.sock.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, self._on_msg)
        threading.Thread(target=self._events, daemon=True).start()
        write_active_app((hypr("activewindow") or {}).get("class", ""))
        self._schedule_capture(SETTLE_MS)

    def _on_msg(self, fd, cond):
        cmd = self.sock.recv(64).decode(errors="ignore").strip()
        if cmd == "toggle":
            self.strip.toggle()
        elif cmd == "show":
            self.strip.show()
        elif cmd == "hide":
            self.strip.hide()
        elif cmd.startswith("pin"):
            arg = cmd[3:].strip()
            self.strip.set_pinned({"on": True, "off": False}.get(arg, not self.strip.pinned))
        elif cmd.startswith("anim"):
            # anim <nama> = ganti & simpan; anim = putar ke gaya berikutnya. Strip
            # langsung ditampilkan biar kelihatan hasilnya.
            names = list(ANIMS)
            arg = cmd[4:].strip() or names[(names.index(self.strip.anim) + 1) % len(names)]
            # ganti kelas cuma saat strip sudah ke-unmap: ganti target transform di
            # tengah transisi pernah bikin renderer GSK abort (clip_mask)
            if arg in ANIMS:
                os.makedirs(os.path.dirname(ANIM_FILE), exist_ok=True)
                with open(ANIM_FILE, "w") as f:
                    f.write(arg)
                self.strip.hide()

                def apply():
                    if self.strip.win.get_visible():
                        return True
                    self.strip.set_anim(arg)
                    GLib.timeout_add(50, lambda: (self.strip.show(keyboard=True), False)[1])
                    return False
                GLib.timeout_add(100, apply)
        return True

    def _events(self):
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        path = os.path.join(RUNTIME, "hypr", sig or "", ".socket2.sock")
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(path)
            for line in s.makefile("r", errors="ignore"):
                ev, _, data = line.rstrip("\n").partition(">>")
                if ev == "activewindow":   # data = "class,title"
                    GLib.idle_add(write_active_app, data.split(",", 1)[0])
                elif ev == "openlayer" and data.startswith("noctalia-bar"):
                    GLib.idle_add(self._on_bar_created)
                if ev in ("workspacev2", "openwindow", "closewindow", "movewindowv2",
                          "focusedmonv2"):
                    GLib.idle_add(self._on_event)
        except OSError:
            pass
        # socket putus = Hyprland selesai; jangan nyangkut jadi yatim
        GLib.idle_add(self.quit)

    def _on_bar_created(self):
        # Exclusive zone ditata sesuai urutan surface dibuat. Bar noctalia yang dibuat
        # ulang (reload config/restart) setelah strip ter-pin jadi ikut menghindari
        # kolom strip dan bergeser ke kanan. Petakan ulang strip supaya ia jadi yang
        # terakhir: bar kembali selebar layar, strip di bawahnya.
        if self.strip.pinned and not getattr(self, "_remap_id", None):
            self._remap_id = GLib.timeout_add(400, self._remap_strip)
        return False

    def _remap_strip(self):
        self._remap_id = None
        if self.strip.pinned:
            self.strip.win.set_visible(False)
            GLib.timeout_add(30, lambda: (self.strip.win.present(), False)[1])
        return False

    def _on_event(self):
        self._schedule_capture(SETTLE_MS)
        if self.strip.shown:
            self.strip.refresh()
        return False

    def _schedule_capture(self, ms):
        if self.capture_id:
            GLib.source_remove(self.capture_id)
        self.capture_id = GLib.timeout_add(ms, self._capture)

    def _capture(self):
        self.capture_id = None
        if self.strip.pinned:
            capture_async(self._after_capture, skip_left=self.strip.win.get_width())
        # strip melayang lagi kelihatan = jangan ikut kefoto ke thumbnail
        elif not self.strip.win.get_visible():
            capture_async()
        return False

    def _after_capture(self):
        if self.strip.shown:
            self.strip.refresh()


if __name__ == "__main__":
    App().run(None)

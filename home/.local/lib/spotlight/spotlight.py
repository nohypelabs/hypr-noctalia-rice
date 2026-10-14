"""spotlight — launcher ala Spotlight macOS untuk Hyprland.

Daemon GTK4 + gtk4-layer-shell (pola sama dengan keyhud/wsstrip). Awalnya cuma bar
pencarian di tengah atas; hasil (Top Hit, Aplikasi, Kalkulator, Cari di web) muncul
di bawahnya saat mengetik. Daemon yang sama juga memegang Launchpad: layar penuh berisi
grid ikon semua aplikasi per halaman, latar = desktop yang diblur.
Perintah lewat socket datagram $XDG_RUNTIME_DIR/spotlight.sock (pakai spotlight-send):
toggle | show | hide | query <teks> | launchpad | launchpad-hide | launchpad-page <n>.

Ikon aplikasi dirasterisasi jadi bitmap (lihat wsstrip): ikon SVG yang digambar sebagai
path vektor di dalam widget beranimasi bikin renderer GSK GTK 4.24 abort.
"""
import ast
import json
import threading
import math
import operator
import os
import socket
import subprocess
import urllib.parse

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GioUnix", "2.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GioUnix, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LS  # noqa: E402

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
SOCK = os.path.join(RUNTIME, "spotlight.sock")
USAGE_FILE = os.path.expanduser("~/.local/state/spotlight/usage.json")
WIDTH = 680
TOP_RATIO = 0.22            # jarak bar dari atas layar (proporsi tinggi monitor)
MAX_APPS = 7
WEB_SEARCH = "https://duckduckgo.com/?q={}"
LP_ICON = 76                # ukuran ikon Launchpad
LP_CELL_W, LP_CELL_H = 150, 128
LP_MAX_COLS, LP_MAX_ROWS = 7, 5   # sama dengan Launchpad macOS
LP_BG = os.path.join(RUNTIME, "spotlight-launchpad-bg.png")
# rice-launchpad.desktop sengaja TANPA NoDisplay (dock noctalia gak mau baca ikon entri
# NoDisplay), jadi disaring di sini
SELF_IDS = {"rice-launchpad.desktop"}

CSS = """
window.spotlight { background: rgba(0, 0, 0, 0.01); font-family: "Inter", sans-serif; }
.card {
  background: rgba(30, 30, 32, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 18px;
  box-shadow: 0 22px 60px rgba(0, 0, 0, 0.55), 0 2px 8px rgba(0, 0, 0, 0.35);
  opacity: 0;
  transform: scale(0.97);
  transition: opacity 140ms ease-out, transform 220ms cubic-bezier(0.22, 1.2, 0.36, 1);
}
.card.on { opacity: 1; transform: none; }
.searchrow { padding: 12px 18px; }
.glass { color: rgba(235, 235, 245, 0.55); font-family: "JetBrainsMono Nerd Font"; font-size: 22px; margin-right: 12px; }
entry.query, entry.query text {
  background: none; border: none; box-shadow: none; outline: none; padding: 0; min-height: 0;
  color: #ffffff; font-size: 24px; font-weight: 300; caret-color: #0a84ff;
}
entry.query text placeholder { color: rgba(235, 235, 245, 0.35); }
.sep { background: rgba(255, 255, 255, 0.10); min-height: 1px; }
.results { padding: 6px 8px 8px 8px; }
.section { color: rgba(235, 235, 245, 0.50); font-size: 11px; font-weight: 700; margin: 8px 12px 4px 12px; }
.row { border-radius: 10px; padding: 6px 10px; }
.row.top { padding: 10px 10px; }
.row.sel { background: #0a64d8; }
.row .name { color: #ffffff; font-size: 15px; }
.row.top .name { font-size: 18px; font-weight: 600; }
.row .sub { color: rgba(235, 235, 245, 0.50); font-size: 12px; }
.row.sel .sub { color: rgba(255, 255, 255, 0.75); }
.row .hint { color: rgba(255, 255, 255, 0.0); font-size: 12px; }
.row.sel .hint { color: rgba(255, 255, 255, 0.80); }
.row .glyph { color: rgba(235, 235, 245, 0.75); font-family: "JetBrainsMono Nerd Font"; font-size: 20px;
  min-width: 28px; }
.row.top .glyph { font-size: 28px; min-width: 40px; }

/* ---- Launchpad ---- */
window.launchpad { background: rgba(0, 0, 0, 0.01); font-family: "Inter", sans-serif; }
.lp-tint { background: rgba(16, 16, 22, 0.45); }
.lp-bg { opacity: 0; transition: opacity 220ms ease-out; }
.lp-bg.on { opacity: 1; }
.lp-content {
  opacity: 0; transform: scale(1.08);
  transition: opacity 180ms ease-out, transform 280ms cubic-bezier(0.22, 1, 0.36, 1);
}
.lp-content.on { opacity: 1; transform: none; }
entry.lp-search {
  background: rgba(255, 255, 255, 0.14); border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 9px; box-shadow: none; min-height: 30px; padding: 0 10px;
  color: #ffffff; font-size: 14px; caret-color: #ffffff;
}
entry.lp-search text placeholder { color: rgba(255, 255, 255, 0.55); }
.lp-cell { border-radius: 16px; padding: 8px 4px; }
.lp-cell image { transition: transform 140ms ease-out; }
.lp-cell:hover image { transform: scale(1.08); }
.lp-cell.sel { background: rgba(255, 255, 255, 0.16); }
.lp-name { color: #ffffff; font-size: 12px; text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8); margin-top: 6px; }
.lp-dot { min-width: 8px; min-height: 8px; border-radius: 4px; margin: 0 5px;
  background: rgba(255, 255, 255, 0.35); }
.lp-dot.on { background: rgba(255, 255, 255, 0.95); }
.lp-empty { color: rgba(255, 255, 255, 0.6); font-size: 15px; }
"""

# ---------------------------------------------------------------------------
# Ikon (dirasterisasi, lihat docstring)
# ---------------------------------------------------------------------------
_tex = {}


def icon_texture(gicon, size):
    key = (gicon.to_string() if gicon else "", size)
    if key in _tex:
        return _tex[key]
    tex = None
    if gicon:
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        paint = theme.lookup_by_gicon(gicon, size, 2, Gtk.TextDirection.NONE, 0)
        f = paint.get_file() if paint else None
        path = f.get_path() if f else None
        if path:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size * 2, size * 2)
                if not pb.get_has_alpha():
                    pb = pb.add_alpha(False, 0, 0, 0)
                # langsung dari piksel (tanpa encode PNG): ~2x lebih cepat
                tex = Gdk.MemoryTexture.new(pb.get_width(), pb.get_height(),
                                            Gdk.MemoryFormat.R8G8B8A8, pb.read_pixel_bytes(),
                                            pb.get_rowstride())
            except GLib.Error:
                tex = None
    _tex[key] = tex
    return tex


# ---------------------------------------------------------------------------
# Kalkulator aman (ast, cuma angka & operator)
# ---------------------------------------------------------------------------
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
        ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
          "log": math.log10, "ln": math.log, "abs": abs, "round": round}
_CONSTS = {"pi": math.pi, "e": math.e}


def _ev(n):
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        a, b = _ev(n.left), _ev(n.right)
        if isinstance(n.op, ast.Pow) and abs(b) > 100:
            raise ValueError
        return _OPS[type(n.op)](a, b)
    if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
        return _OPS[type(n.op)](_ev(n.operand))
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS \
            and len(n.args) == 1:
        return _FUNCS[n.func.id](_ev(n.args[0]))
    if isinstance(n, ast.Name) and n.id in _CONSTS:
        return _CONSTS[n.id]
    raise ValueError


def calc(q):
    expr = q.strip().replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", ".")
    if not expr or not any(c.isdigit() for c in expr):
        return None
    if not any(op in expr for op in "+-*/%(") and not any(f + "(" in expr for f in _FUNCS):
        return None
    try:
        v = _ev(ast.parse(expr, mode="eval").body)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        v = round(v, 10)
        if v == int(v) and abs(v) < 1e15:
            v = int(v)
    return f"{v:,}".replace(",", " ") if isinstance(v, int) else str(v)


# ---------------------------------------------------------------------------
# Indeks aplikasi + skor pencarian
# ---------------------------------------------------------------------------
class Apps:
    def __init__(self):
        self.items = []
        self.usage = self._load_usage()
        self.dirty = True
        Gio.AppInfoMonitor.get().connect("changed", lambda *_: setattr(self, "dirty", True))

    @staticmethod
    def _load_usage():
        try:
            with open(USAGE_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def bump(self, app_id):
        self.usage[app_id] = self.usage.get(app_id, 0) + 1
        try:
            os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
            with open(USAGE_FILE, "w") as f:
                json.dump(self.usage, f)
        except OSError:
            pass

    def refresh(self):
        if not self.dirty:
            return
        self.dirty = False
        items = []
        for a in Gio.AppInfo.get_all():
            if not a.should_show() or not isinstance(a, GioUnix.DesktopAppInfo):
                continue
            if a.get_id() in SELF_IDS:   # entri dock Launchpad sendiri jangan ikut di grid
                continue
            kw = " ".join(a.get_keywords() or [])
            items.append({
                "id": a.get_id(), "info": a, "name": a.get_display_name() or a.get_name(),
                "generic": a.get_generic_name() or "", "kw": kw.lower(),
                "exec": os.path.basename((a.get_executable() or "").lower()),
            })
        self.items = items

    def search(self, q):
        q = q.strip().lower()
        if not q:
            return []
        out = []
        for it in self.items:
            s = self._score(q, it)
            if s > 0:
                s += min(self.usage.get(it["id"], 0), 30) * 2
                out.append((s, it))
        out.sort(key=lambda t: (-t[0], t[1]["name"].lower()))
        return [it for _, it in out]

    @staticmethod
    def _score(q, it):
        name = it["name"].lower()
        if name == q:
            return 1000
        if name.startswith(q):
            return 800 - len(name)
        words = name.replace("-", " ").split()
        if any(w.startswith(q) for w in words):
            return 600 - len(name)
        if q in name:
            return 400 - name.index(q)
        if it["exec"].startswith(q):
            return 350
        if q in it["generic"].lower() or q in it["kw"]:
            return 250
        # subsequence (mis. "vsc" -> "Visual Studio Code")
        i = 0
        for ch in name:
            if i < len(q) and ch == q[i]:
                i += 1
        return 100 if i == len(q) and len(q) >= 2 else 0


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def launch_app(apps, it):
    apps.bump(it["id"])
    # sesi uwsm: jalankan sebagai unit systemd terpisah (gak ikut mati bareng daemon ini)
    if any(k.startswith("UWSM_") for k in os.environ) and GLib.find_program_in_path("uwsm"):
        subprocess.Popen(["uwsm", "app", "--", it["id"]], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    else:
        it["info"].launch([], None)


def focused_monitor(display):
    try:
        out = subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True, text=True,
                             timeout=0.5).stdout
        name = next((m["name"] for m in json.loads(out) if m.get("focused")), None)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    mons = display.get_monitors()
    for i in range(mons.get_n_items()):
        m = mons.get_item(i)
        if m.get_connector() == name:
            return m
    return None


class Row(Gtk.Box):
    def __init__(self, kind, title, sub="", gicon=None, glyph="", top=False, hint="⏎", data=None):
        super().__init__(spacing=12)
        self.kind, self.data = kind, data
        self.add_css_class("row")
        if top:
            self.add_css_class("top")
        size = 40 if top else 28
        tex = icon_texture(gicon, size) if gicon else None
        if tex:
            img = Gtk.Image.new_from_paintable(tex)
            img.set_pixel_size(size)
            self.append(img)
        else:
            g = Gtk.Label(label=glyph or "󰘔")
            g.add_css_class("glyph")
            self.append(g)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        name = Gtk.Label(label=title, xalign=0, ellipsize=3)
        name.add_css_class("name")
        col.append(name)
        if sub:
            s = Gtk.Label(label=sub, xalign=0, ellipsize=3)
            s.add_css_class("sub")
            col.append(s)
        self.append(col)
        h = Gtk.Label(label=hint)
        h.add_css_class("hint")
        self.append(h)


class Spotlight:
    def __init__(self, app):
        self.app = app
        self.apps = Apps()
        self.rows, self.sel = [], 0
        self.unmap_id = None

        self.win = Gtk.Window(application=app)
        self.win.add_css_class("spotlight")
        LS.init_for_window(self.win)
        LS.set_namespace(self.win, "spotlight")
        LS.set_layer(self.win, LS.Layer.OVERLAY)
        for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
            LS.set_anchor(self.win, e, True)   # layar penuh (alpha 1%): klik di luar = tutup
        LS.set_exclusive_zone(self.win, -1)
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.NONE)

        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=WIDTH,
                            halign=Gtk.Align.CENTER, valign=Gtk.Align.START)
        self.card.add_css_class("card")
        row = Gtk.Box(spacing=4)
        row.add_css_class("searchrow")
        glass = Gtk.Label(label="\uf002")   # nf-fa-search
        glass.add_css_class("glass")
        row.append(glass)
        self.entry = Gtk.Entry(hexpand=True, placeholder_text="Spotlight Search")
        self.entry.add_css_class("query")
        self.entry.connect("changed", lambda *_: self.update())
        self.entry.connect("activate", lambda *_: self.activate())
        row.append(self.entry)
        self.card.append(row)
        self.sep = Gtk.Box()
        self.sep.add_css_class("sep")
        self.card.append(self.sep)
        self.results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.results.add_css_class("results")
        self.card.append(self.results)
        self.win.set_child(self.card)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.win.add_controller(keys)
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.win.add_controller(click)

    # ---- tampil/sembunyi ---------------------------------------------------
    @property
    def shown(self):
        return self.win.get_visible() and self.unmap_id is None

    def toggle(self):
        self.hide() if self.shown else self.show()

    def show(self):
        if self.unmap_id:
            GLib.source_remove(self.unmap_id)
            self.unmap_id = None
        self.apps.refresh()
        mon = focused_monitor(self.win.get_display())
        if mon:
            LS.set_monitor(self.win, mon)
            self.card.set_margin_top(int(mon.get_geometry().height * TOP_RATIO))
        self.entry.set_text("")
        self.update()
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.EXCLUSIVE)
        if not self.win.get_visible():
            self.card.remove_css_class("on")
            self.win.present()
            GLib.timeout_add(16, lambda: (self.card.add_css_class("on"), False)[1])
        self.entry.grab_focus()

    def hide(self):
        if not self.win.get_visible() or self.unmap_id:
            return
        self.card.remove_css_class("on")
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.NONE)
        self.unmap_id = GLib.timeout_add(150, self._unmap)

    def _unmap(self):
        self.unmap_id = None
        self.win.set_visible(False)
        return False

    # ---- hasil -------------------------------------------------------------
    def update(self):
        q = self.entry.get_text()
        while (c := self.results.get_first_child()) is not None:
            self.results.remove(c)
        self.rows = []
        if q.strip():
            res = calc(q)
            apps = self.apps.search(q)
            if res is not None:
                self._section("KALKULATOR")
                self._add(Row("calc", f"= {res}", f"{q.strip()}  ·  ⏎ salin", glyph="󰃬",
                              top=True, hint="Salin", data=res.replace(" ", "")))
            if apps:
                top, rest = apps[0], apps[1:MAX_APPS + 1]
                self._section("TOP HIT" if res is None else "APLIKASI")
                self._add(self._app_row(top, top=res is None))
                if rest:
                    if res is None:
                        self._section("APLIKASI")
                    for it in rest:
                        self._add(self._app_row(it))
            self._section("WEB")
            self._add(Row("web", f"Cari “{q.strip()}” di web", "DuckDuckGo", glyph="󰖟",
                          hint="Buka", data=q.strip()))
        has = bool(self.rows)
        self.sep.set_visible(has)
        self.results.set_visible(has)
        self.sel = 0
        self._paint()

    def _app_row(self, it, top=False):
        sub = it["generic"] or "Aplikasi"
        return Row("app", it["name"], sub, gicon=it["info"].get_icon(), top=top,
                   hint="Buka", data=it)

    def _section(self, text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.add_css_class("section")
        self.results.append(lbl)

    def _add(self, row):
        self.results.append(row)
        self.rows.append(row)

    def _paint(self):
        for i, r in enumerate(self.rows):
            (r.add_css_class if i == self.sel else r.remove_css_class)("sel")

    # ---- input -------------------------------------------------------------
    def _on_key(self, ctl, keyval, code, state):
        name = Gdk.keyval_name(keyval) or ""
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if name == "Escape":
            if self.entry.get_text():
                self.entry.set_text("")
            else:
                self.hide()
            return True
        if name in ("Down", "Tab") or (ctrl and name in ("n", "j")):
            self._move(1)
            return True
        if name in ("Up", "ISO_Left_Tab") or (ctrl and name in ("p", "k")):
            self._move(-1)
            return True
        return False

    def _move(self, step):
        if self.rows:
            self.sel = (self.sel + step) % len(self.rows)
            self._paint()

    def _on_click(self, gesture, n, x, y):
        picked = self.win.pick(x, y, Gtk.PickFlags.DEFAULT)
        w = picked
        while w is not None and w is not self.card:
            if isinstance(w, Row):
                self.sel = self.rows.index(w)
                self.activate()
                return
            w = w.get_parent()
        if w is None:   # klik di luar kartu
            self.hide()

    def activate(self):
        if not self.rows:
            return
        r = self.rows[self.sel]
        if r.kind == "app":
            self.launch(r.data)
        elif r.kind == "calc":
            subprocess.Popen(["wl-copy", r.data], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif r.kind == "web":
            subprocess.Popen(["xdg-open", WEB_SEARCH.format(urllib.parse.quote(r.data))],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.hide()

    def launch(self, it):
        launch_app(self.apps, it)


class Launchpad:
    """Grid ikon semua aplikasi, layar penuh, per halaman (ala Launchpad macOS)."""

    def __init__(self, app, apps):
        self.app, self.apps = app, apps
        self.pages, self.page, self.cells, self.sel = [], 0, [], -1
        self.cols, self.rows = LP_MAX_COLS, LP_MAX_ROWS
        self.unmap_id = None
        self.scroll_acc, self.scroll_lock = 0.0, False
        self.built_for = None

        self.win = Gtk.Window(application=app)
        self.win.add_css_class("launchpad")
        LS.init_for_window(self.win)
        LS.set_namespace(self.win, "launchpad")
        LS.set_layer(self.win, LS.Layer.OVERLAY)
        for e in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
            LS.set_anchor(self.win, e, True)
        LS.set_exclusive_zone(self.win, -1)
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.NONE)

        over = Gtk.Overlay()
        self.bg = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
        self.bg.add_css_class("lp-bg")
        over.set_child(self.bg)
        tint = Gtk.Box(hexpand=True, vexpand=True)
        tint.add_css_class("lp-tint")
        over.add_overlay(tint)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content.add_css_class("lp-content")
        self.entry = Gtk.Entry(placeholder_text="Cari", width_request=260,
                               halign=Gtk.Align.CENTER, margin_top=56)
        self.entry.add_css_class("lp-search")
        self.entry.connect("changed", lambda *_: self.rebuild())
        self.entry.connect("activate", lambda *_: self._activate_sel())
        self.content.append(self.entry)
        self.stack = Gtk.Stack(vexpand=True, transition_duration=320,
                               transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.content.append(self.stack)
        self.dots = Gtk.Box(halign=Gtk.Align.CENTER, margin_bottom=56)
        self.content.append(self.dots)
        over.add_overlay(self.content)
        self.win.set_child(over)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.win.add_controller(keys)
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", self._on_scroll)
        scroll.connect("scroll-end", lambda *_: setattr(self, "scroll_acc", 0.0))
        self.win.add_controller(scroll)
        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.win.add_controller(click)

    # ---- tampil/sembunyi ---------------------------------------------------
    @property
    def shown(self):
        return self.win.get_visible() and self.unmap_id is None

    def toggle(self):
        self.hide() if self.shown else self.show()

    def show(self):
        if self.unmap_id:
            GLib.source_remove(self.unmap_id)
            self.unmap_id = None
        mon = focused_monitor(self.win.get_display())
        if mon:
            LS.set_monitor(self.win, mon)
            g = mon.get_geometry()
            self.cols = max(4, min(LP_MAX_COLS, (g.width - 200) // LP_CELL_W))
            self.rows = max(3, min(LP_MAX_ROWS, (g.height - 260) // (LP_CELL_H + 12)))
        self.apps.refresh()
        self.entry.set_text("")
        self.rebuild(force=True)
        if self.win.get_visible():
            self._present()
            return
        self._presented = False
        self.mon = mon
        if os.path.exists(LP_BG):
            # latar = foto desktop dari penutupan sebelumnya (sudah diblur berat, beda
            # sedikit gak kelihatan) -> Launchpad bisa langsung muncul
            self._bg_ready = True
            self._present()
        else:
            # pertama kali: foto dulu sebelum Launchpad kelihatan, tunggu maks 300 ms
            self.bg.remove_css_class("on")
            self.bg.set_paintable(None)
            self._grab_background(mon)
            GLib.timeout_add(300, lambda: (self._present(), False)[1])

    def _present(self):
        if getattr(self, "_presented", True) and self.win.get_visible():
            return
        self._presented = True
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.EXCLUSIVE)
        self.content.remove_css_class("on")
        self.win.present()
        GLib.timeout_add(16, lambda: (self.content.add_css_class("on"), False)[1])
        self.entry.grab_focus()
        if os.path.exists(LP_BG) and self._bg_ready:
            self._set_background()

    def hide(self):
        if not self.win.get_visible() or self.unmap_id:
            return
        self.content.remove_css_class("on")
        self.bg.remove_css_class("on")
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.NONE)
        self.unmap_id = GLib.timeout_add(200, self._unmap)

    def _unmap(self):
        self.unmap_id = None
        self.win.set_visible(False)
        # perbarui foto latar buat pembukaan berikutnya, setelah aplikasi sempat muncul
        GLib.timeout_add(1500, self._refresh_bg_later)
        return False

    def _refresh_bg_later(self):
        if not self.win.get_visible():
            self._grab_background(getattr(self, "mon", None), present=False)
        return False

    # Latar = layar sekarang, diperkecil + blur (grim + Pillow di thread terpisah). Strip
    # dipanggil sebelum window tampil, jadi Launchpad sendiri gak ikut kefoto.
    def _grab_background(self, mon, present=True):
        name = mon.get_connector() if mon else None
        if present:
            self._bg_ready = False

        def work():
            try:
                cmd = ["grim", "-s", "0.25", "-t", "ppm", "-"]
                if name:
                    cmd[1:1] = ["-o", name]
                raw = subprocess.run(cmd, capture_output=True, timeout=2).stdout
                from io import BytesIO
                from PIL import Image, ImageEnhance, ImageFilter
                im = Image.open(BytesIO(raw)).convert("RGB")
                im = im.filter(ImageFilter.GaussianBlur(10))
                im = ImageEnhance.Brightness(im).enhance(0.8)
                im.save(LP_BG + ".tmp.png")
                os.replace(LP_BG + ".tmp.png", LP_BG)
            except Exception:   # Pillow/grim gak ada: cukup latar gelap polos
                if present:
                    GLib.idle_add(lambda: (self._present(), False)[1])
                return
            if present:
                self._bg_ready = True
                GLib.idle_add(lambda: (self._present(), self._set_background(), False)[2])
        threading.Thread(target=work, daemon=True).start()

    def _set_background(self):
        if self.win.get_visible():
            # muat lewat texture baru (Gio.File sama bisa kena cache Picture)
            try:
                self.bg.set_paintable(Gdk.Texture.new_from_filename(LP_BG))
            except GLib.Error:
                return False
            self.bg.add_css_class("on")
        return False

    # ---- grid --------------------------------------------------------------
    def rebuild(self, force=False):
        q = self.entry.get_text().strip()
        items = self.apps.search(q) if q else sorted(self.apps.items,
                                                      key=lambda it: it["name"].lower())
        key = (q, self.cols, self.rows, len(self.apps.items))
        if not force and key == self.built_for:
            return
        self.built_for = key
        while (c := self.stack.get_first_child()) is not None:
            self.stack.remove(c)
        per = self.cols * self.rows
        self.pages, self.cells = [], []
        for start in range(0, max(len(items), 1), per):
            grid = Gtk.Grid(column_homogeneous=True, row_homogeneous=True, row_spacing=12,
                            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            for i, it in enumerate(items[start:start + per]):
                cell = self._cell(it)
                grid.attach(cell, i % self.cols, i // self.cols, 1, 1)
                self.cells.append(cell)
            if not items:
                lbl = Gtk.Label(label="Gak ada aplikasi yang cocok")
                lbl.add_css_class("lp-empty")
                grid.attach(lbl, 0, 0, 1, 1)
            name = f"p{len(self.pages)}"
            self.stack.add_named(grid, name)
            self.pages.append(name)
        self.sel = 0 if (q and self.cells) else -1
        self._paint_sel()
        self.goto(0, animate=False)

    def _cell(self, it):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=LP_CELL_W,
                      height_request=LP_CELL_H, halign=Gtk.Align.CENTER, valign=Gtk.Align.START)
        box.add_css_class("lp-cell")
        box.it = it
        tex = icon_texture(it["info"].get_icon(), LP_ICON)
        img = Gtk.Image.new_from_paintable(tex) if tex else Gtk.Image.new_from_icon_name(
            "application-x-executable")
        img.set_pixel_size(LP_ICON)
        box.append(img)
        lbl = Gtk.Label(label=it["name"], ellipsize=3, max_width_chars=16, justify=2)
        lbl.add_css_class("lp-name")
        box.append(lbl)
        box.set_cursor(Gdk.Cursor.new_from_name("pointer"))
        return box

    def goto(self, n, animate=True):
        if not self.pages:
            return
        n = max(0, min(n, len(self.pages) - 1))
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT if animate
                                       else Gtk.StackTransitionType.NONE)
        self.page = n
        self.stack.set_visible_child_name(self.pages[n])
        while (c := self.dots.get_first_child()) is not None:
            self.dots.remove(c)
        self.dots.set_visible(len(self.pages) > 1)
        for i in range(len(self.pages)):
            d = Gtk.Box()
            d.add_css_class("lp-dot")
            if i == n:
                d.add_css_class("on")
            self.dots.append(d)

    def _paint_sel(self):
        for i, c in enumerate(self.cells):
            (c.add_css_class if i == self.sel else c.remove_css_class)("sel")

    def _activate_sel(self):
        if 0 <= self.sel < len(self.cells):
            self._launch(self.cells[self.sel].it)

    def _launch(self, it):
        launch_app(self.apps, it)
        self.hide()

    # ---- input -------------------------------------------------------------
    def _on_key(self, ctl, keyval, code, state):
        name = Gdk.keyval_name(keyval) or ""
        typing = bool(self.entry.get_text())
        if name == "Escape":
            if typing:
                self.entry.set_text("")
            else:
                self.hide()
            return True
        if name in ("Page_Down",) or (name == "Right" and not typing):
            self.goto(self.page + 1)
            return True
        if name in ("Page_Up",) or (name == "Left" and not typing):
            self.goto(self.page - 1)
            return True
        if typing and name in ("Right", "Left", "Down", "Up", "Tab") and self.cells:
            step = {"Right": 1, "Tab": 1, "Left": -1, "Down": self.cols, "Up": -self.cols}[name]
            self.sel = max(0, min(len(self.cells) - 1, self.sel + step))
            self._paint_sel()
            return True
        return False

    def _on_scroll(self, ctl, dx, dy):
        # touchpad: geser horizontal (atau vertikal) = ganti halaman, sekali per gerakan
        if self.scroll_lock:
            return True
        self.scroll_acc += dx if abs(dx) > abs(dy) else dy
        if abs(self.scroll_acc) >= 1.5:
            self.goto(self.page + (1 if self.scroll_acc > 0 else -1))
            self.scroll_acc, self.scroll_lock = 0.0, True
            GLib.timeout_add(350, lambda: (setattr(self, "scroll_lock", False), False)[1])
        return True

    def _on_click(self, gesture, n, x, y):
        w = self.win.pick(x, y, Gtk.PickFlags.DEFAULT)
        while w is not None:
            if hasattr(w, "it"):
                self._launch(w.it)
                return
            if w is self.entry or w is self.dots:
                return
            w = w.get_parent()
        self.hide()   # klik area kosong = tutup (kayak macOS)


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.dracarys.spotlight")

    def do_activate(self):
        self.hold()
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 10)
        self.ui = Spotlight(self)
        self.ui.apps.refresh()
        self.lp = Launchpad(self, self.ui.apps)
        # siapkan ikon semua aplikasi di latar biar Launchpad/Spotlight pertama gak nunggu
        todo = [it["info"].get_icon() for it in self.ui.apps.items if it["info"].get_icon()]

        def warm():
            for gicon in todo[:6]:
                for size in (LP_ICON, 28, 40):
                    icon_texture(gicon, size)
            del todo[:6]
            return bool(todo)
        GLib.idle_add(warm, priority=GLib.PRIORITY_LOW)
        try:
            os.unlink(SOCK)
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(SOCK)
        GLib.io_add_watch(self.sock.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, self._on_msg)

    def _on_msg(self, fd, cond):
        cmd = self.sock.recv(512).decode(errors="ignore").strip()
        if cmd == "toggle":
            self.lp.hide()
            self.ui.toggle()
        elif cmd == "show":
            self.ui.show()
        elif cmd == "hide":
            self.ui.hide()
        elif cmd == "launchpad":
            self.ui.hide()
            self.lp.toggle()
        elif cmd == "launchpad-hide":
            self.lp.hide()
        elif cmd.startswith("launchpad-page "):   # dipakai buat tes/screenshot
            self.lp.goto(int(cmd.split()[1]) - 1)
        elif cmd.startswith("query "):   # buka dengan teks terisi (dipakai buat tes)
            self.ui.show()
            self.ui.entry.set_text(cmd[6:])
            self.ui.entry.set_position(-1)
        return True


if __name__ == "__main__":
    App().run(None)

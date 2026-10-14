"""spotlight — launcher ala Spotlight macOS untuk Hyprland.

Daemon GTK4 + gtk4-layer-shell (pola sama dengan keyhud/wsstrip). Awalnya cuma bar
pencarian di tengah atas; hasil (Top Hit, Aplikasi, Kalkulator, Cari di web) muncul
di bawahnya saat mengetik. Perintah lewat socket datagram $XDG_RUNTIME_DIR/spotlight.sock
(pakai spotlight-send): toggle | show | hide | query <teks>.

Ikon aplikasi dirasterisasi jadi bitmap (lihat wsstrip): ikon SVG yang digambar sebagai
path vektor di dalam widget beranimasi bikin renderer GSK GTK 4.24 abort.
"""
import ast
import json
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
                ok, buf = pb.save_to_bufferv("png", [], [])
                if ok:
                    tex = Gdk.Texture.new_from_bytes(GLib.Bytes.new(buf))
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
        self.apps.bump(it["id"])
        # sesi uwsm: jalankan sebagai unit systemd terpisah (gak ikut mati bareng daemon ini)
        if any(k.startswith("UWSM_") for k in os.environ) and GLib.find_program_in_path("uwsm"):
            subprocess.Popen(["uwsm", "app", "--", it["id"]], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        else:
            it["info"].launch([], None)


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
            self.ui.toggle()
        elif cmd == "show":
            self.ui.show()
        elif cmd == "hide":
            self.ui.hide()
        elif cmd.startswith("query "):   # buka dengan teks terisi (dipakai buat tes)
            self.ui.show()
            self.ui.entry.set_text(cmd[6:])
            self.ui.entry.set_position(-1)
        return True


if __name__ == "__main__":
    App().run(None)

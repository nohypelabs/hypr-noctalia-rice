"""keyhud — HUD keybind ala Omarchy + cheatsheet gaya macOS untuk Hyprland.

Daemon GTK4 + gtk4-layer-shell (surface layer, jadi gak ikut tiling).
Tanpa blur: layer_rule blur Hyprland 0.56 gak ngefek ke surface ini (noctalia pakai
ext-background-effect, gak bisa dari GTK4 Python), jadi kartunya dibuat hampir solid.
Perintah lewat socket datagram $XDG_RUNTIME_DIR/keyhud.sock (pakai keyhud-send):
  show <idx>    tampilkan HUD untuk bind ke-idx (registry ditulis config/binds.lua)
  cheatsheet    buka/tutup daftar pintasan
  toggle-osd    nyalakan/matikan HUD (diingat di ~/.local/state/keyhud/osd-off)
"""
import json
import os
import re
import socket
import subprocess

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LS  # noqa: E402

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
SOCK = os.path.join(RUNTIME, "keyhud.sock")
REGISTRY = os.path.join(RUNTIME, "keyhud-binds.tsv")
BINDS_LUA = os.path.expanduser("~/.config/hypr/config/binds.lua")
STATE_DIR = os.path.expanduser("~/.local/state/keyhud")
OSD_OFF = os.path.join(STATE_DIR, "osd-off")
OSD_SECONDS = 1.3

MODS = {"SUPER": "⌘", "SHIFT": "⇧", "ALT": "⌥", "CTRL": "⌃", "CONTROL": "⌃"}
KEYS = {
    "RETURN": "↩", "Return": "↩", "Escape": "esc", "SPACE": "space", "Left": "←",
    "Right": "→", "Up": "↑", "Down": "↓", "BackSpace": "⌫", "Tab": "⇥", "grave": "`",
    "slash": "/", "minus": "−", "Print": "PrtSc", "mouse_down": "scroll ↓",
    "mouse_up": "scroll ↑",
}
DIRS = {"left": "kiri", "right": "kanan", "up": "atas", "down": "bawah",
        "l": "kiri", "r": "kanan", "u": "atas", "d": "bawah"}
MODES = {"duplicate": "Layar: duplikat", "extend": "Layar: perpanjang",
         "external": "Layar: eksternal saja", "internal": "Layar: laptop saja"}

# Urutan penting: aturan yang lebih spesifik ditaruh di atas.
RULES = [
    (r"window\.close", "Tutup window"),
    (r"window\.float", "Floating ↔ tiling"),
    (r"window\.fullscreen", "Layar penuh"),
    (r"bar-toggle", "Tampilkan / sembunyikan bar"),
    (r"togglesplit", "Ganti arah split"),
    (r"preselect r", "Window berikutnya di kanan"),
    (r"preselect d", "Window berikutnya di bawah"),
    (r"session lock", "Kunci layar"),
    (r"panel-(toggle|open) session", "Menu power"),
    (r'focus\(\{ direction = "(\w+)"', lambda m, n: "Fokus ke " + DIRS[m.group(1)]),
    (r"cycle_next", "Ganti window"),
    (r'move\(\{ direction = "(\w)"', lambda m, n: "Geser window ke " + DIRS[m.group(1)]),
    (r'window\.move\(\{ workspace = "e\+1"', "Kirim window ke workspace berikutnya"),
    (r'window\.move\(\{ workspace = "e-1"', "Kirim window ke workspace sebelumnya"),
    (r'window\.move\(\{ workspace = "special', "Kirim window ke scratchpad"),
    (r"window\.move\(\{ workspace = i", lambda m, n: f"Kirim window ke workspace {n}"),
    (r'focus\(\{ workspace = "e\+1"', "Workspace berikutnya"),
    (r'focus\(\{ workspace = "e-1"', "Workspace sebelumnya"),
    (r'focus\(\{ workspace = "empty"', "Workspace kosong"),
    (r"focus\(\{ workspace = i", lambda m, n: f"Ke workspace {n}"),
    (r"toggle_special", "Scratchpad"),
    (r"quick-access-terminal", "Terminal dropdown"),
    (r"-e btop", "Monitor sistem (btop)"),
    (r"exec_cmd\(terminal\)", "Terminal"),
    (r"FILE_MANAGER", "File manager"),
    (r'"kate"', "Kate"),
    (r'"kcalc"', "Kalkulator"),
    (r'"brave"', "Brave"),
    (r"control-center network", "Wi-Fi"),
    (r"control-center bluetooth", "Bluetooth"),
    (r"exec_cmd\(menu\)", "Launcher aplikasi"),
    (r"panel-toggle clipboard", "Riwayat clipboard"),
    (r"screenshot-region", "Screenshot area"),
    (r"screenshot-fullscreen", "Screenshot layar penuh"),
    (r"screenshot-annotate", "Screenshot + coretan"),
    (r'"obs"', "OBS (rekam layar)"),
    (r"display-mode\.sh (\w+)", lambda m, n: MODES.get(m.group(1), m.group(1))),
    (r"nwg-displays", "Pengaturan layar"),
    (r"hyprctl reload", "Muat ulang Hyprland"),
    (r"wallpaper-random", "Wallpaper acak"),
    (r"theme-mode-toggle", "Mode gelap / terang"),
    (r"clear-history", "Hapus semua notifikasi"),
    (r"notification-clear-active", "Tutup notifikasi"),
    (r"dnd-toggle", "Jangan Ganggu"),
    (r'panel-toggle control-center"', "Control Center"),
    (r"toggle-osd", "HUD keybind on / off"),
    (r"keyhud|cheatsheet", "Daftar pintasan"),
]
SECTIONS = {
    "Basics": "Dasar", "Focus": "Fokus", "Move window": "Pindah window", "Apps": "Aplikasi",
    "Screenshots": "Screenshot", "Rekam layar": "Aplikasi", "Display modes": "Layar",
    "Reload / exit": "Sistem", "Wallpaper": "Tampilan", "Tema dark/light": "Tampilan",
    "Notifications": "Notifikasi", "Scratchpad": "Workspace", "Workspaces": "Workspace",
    "Workspace navigation": "Workspace", "Ekstra khusus Hyprland": "Lainnya",
    "keyhud": "Lainnya",
}

CSS = """
window.keyhud { background: transparent; font-family: "Inter", sans-serif; }
.hud {
  background: rgba(36, 36, 38, 0.90);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 20px;
  padding: 12px 20px;
  box-shadow: 0 8px 26px rgba(0, 0, 0, 0.40);
  opacity: 0;
  transform: scale(0.92) translateY(10px);
  transition: opacity 160ms ease-out, transform 280ms cubic-bezier(0.34, 1.45, 0.64, 1);
}
.hud.on { opacity: 1; transform: none; }
.hud .desc { color: rgba(255, 255, 255, 0.92); font-size: 15px; font-weight: 500; margin-left: 6px; }
.keycap {
  background: rgba(255, 255, 255, 0.13);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-bottom-color: rgba(0, 0, 0, 0.35);
  border-radius: 8px;
  color: #ffffff;
  min-width: 26px;
  padding: 3px 8px;
  font-size: 15px;
  font-weight: 600;
}
.hud .keycap { min-height: 26px; }

.backdrop { background: rgba(0, 0, 0, 0.40); }
.sheet {
  background: rgba(30, 30, 32, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 24px;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
  padding: 22px 24px 18px 24px;
  opacity: 0;
  transform: scale(0.96);
  transition: opacity 160ms ease-out, transform 300ms cubic-bezier(0.34, 1.3, 0.64, 1);
}
.sheet.on { opacity: 1; transform: none; }
.sheet .title { color: #ffffff; font-size: 22px; font-weight: 700; }
.sheet .subtitle { color: rgba(235, 235, 245, 0.55); font-size: 13px; }
.sheet entry {
  background: rgba(118, 118, 128, 0.24);
  border: none; border-radius: 10px; box-shadow: none;
  color: #ffffff; min-height: 34px; padding: 0 10px; font-size: 14px;
  caret-color: #0a84ff;
}
.sheet entry:focus-within { outline: 3px solid rgba(10, 132, 255, 0.55); outline-offset: 0; }
.sheet scrolledwindow, .sheet viewport, .sheet flowbox, .sheet flowboxchild { background: transparent; }
.sheet flowboxchild { padding: 0; }
.section {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 14px;
  padding: 10px 14px 8px 14px;
}
.section-title {
  color: rgba(235, 235, 245, 0.55); font-size: 11px; font-weight: 700;
  letter-spacing: 1px; margin-bottom: 4px;
}
.row { padding: 5px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
.row:last-child { border-bottom: none; }
.row .desc { color: rgba(255, 255, 255, 0.90); font-size: 14px; padding-left: 2px; }
.row .keycap { font-size: 12px; min-width: 20px; padding: 1px 6px; border-radius: 6px; }
.empty { color: rgba(235, 235, 245, 0.45); font-size: 14px; margin: 40px; }
.hint { color: rgba(235, 235, 245, 0.40); font-size: 12px; margin-top: 10px; }
"""


def key_tokens(keys):
    out = []
    for tok in [t.strip() for t in keys.split("+")]:
        if not tok:
            continue
        if tok in MODS:
            out.append(MODS[tok])
        elif tok in KEYS:
            out.append(KEYS[tok])
        else:
            out.append(tok.upper() if len(tok) == 1 else tok)
    return out


def load_source():
    try:
        with open(BINDS_LUA, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return [], []
    sections, cur = [], "Lainnya"
    for ln in lines:
        m = re.match(r"^--\s*###\s*(.+?)\s*#+\s*$", ln)
        if m:
            raw = m.group(1)
            cur = next((v for k, v in SECTIONS.items() if raw.startswith(k)), raw)
        sections.append(cur)
    return lines, sections


def describe(text, keys):
    n = None
    last = keys.split("+")[-1].strip()
    if last.isdigit():
        n = int(last) or 10
    for pat, label in RULES:
        m = re.search(pat, text)
        if m:
            return label(m, n) if callable(label) else label
    c = re.search(r"--\s*(?:sway:\s*)?(.+)$", text)
    return c.group(1).strip() if c else keys


class Registry:
    def __init__(self):
        self.mtime = None
        self.entries = {}

    def refresh(self):
        try:
            mtime = (os.stat(REGISTRY).st_mtime, os.stat(BINDS_LUA).st_mtime)
        except OSError:
            return
        if mtime == self.mtime:
            return
        self.mtime = mtime
        lines, sections = load_source()
        entries = {}
        with open(REGISTRY, encoding="utf-8") as f:
            for row in f:
                parts = row.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                idx, keys, line = int(parts[0]), parts[1], int(parts[2] or 0)
                text = ""
                if 0 < line <= len(lines):
                    text = lines[line - 1]
                    if text.rstrip().endswith(",") and line < len(lines):
                        text += " " + lines[line]
                section = sections[line - 1] if 0 < line <= len(sections) else "Lainnya"
                entries[idx] = dict(keys=keys, line=line, text=text, section=section,
                                    desc=describe(text, keys))
        self.entries = entries

    def get(self, idx):
        self.refresh()
        return self.entries.get(idx)

    def sheet_rows(self):
        """Baris cheatsheet per seksi; bind hasil loop (beda tombol terakhir) digabung."""
        self.refresh()
        groups, order = {}, []
        for idx in sorted(self.entries):
            e = self.entries[idx]
            if "mouse" in e["keys"] or e["keys"].startswith("XF86"):
                continue
            head, _, last = e["keys"].rpartition("+")
            gid = (e["line"], head.strip()) if e["line"] else ("k", e["keys"])
            if gid not in groups:
                groups[gid] = dict(e, lasts=[])
                order.append(gid)
            groups[gid]["lasts"].append(last.strip())
        sections = {}
        for gid in order:
            g = groups[gid]
            lasts = g["lasts"]
            if len(lasts) > 1:
                head = g["keys"].rpartition("+")[0]
                caps = key_tokens(head) if head else []
                if all(x.isdigit() for x in lasts):
                    caps.append("1…0")
                    desc = re.sub(r"\b\d+\b", "1–10", g["desc"])
                else:
                    caps.append(" / ".join(key_tokens(x)[0] for x in lasts))
                    desc = g["desc"]
            else:
                caps, desc = key_tokens(g["keys"]), g["desc"]
            sections.setdefault(g["section"], []).append((desc, caps))
        return sections


def focused_monitor(display):
    try:
        out = subprocess.run(["hyprctl", "-j", "activeworkspace"], capture_output=True,
                             text=True, timeout=0.5).stdout
        name = json.loads(out).get("monitor")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    mons = display.get_monitors()
    for i in range(mons.get_n_items()):
        m = mons.get_item(i)
        if m.get_connector() == name:
            return m
    return None


def keycaps_box(caps, spacing=5):
    box = Gtk.Box(spacing=spacing)
    for c in caps:
        lbl = Gtk.Label(label=c)
        lbl.add_css_class("keycap")
        box.append(lbl)
    return box


class Hud:
    def __init__(self, app):
        self.app = app
        self.win = Gtk.Window(application=app)
        self.win.add_css_class("keyhud")
        LS.init_for_window(self.win)
        LS.set_namespace(self.win, "keyhud-osd")
        LS.set_layer(self.win, LS.Layer.OVERLAY)
        LS.set_anchor(self.win, LS.Edge.BOTTOM, True)
        LS.set_margin(self.win, LS.Edge.BOTTOM, 100)
        LS.set_keyboard_mode(self.win, LS.KeyboardMode.NONE)
        LS.set_exclusive_zone(self.win, -1)
        self.card = Gtk.Box(spacing=6)
        self.card.add_css_class("hud")
        self.card.set_margin_top(24)
        self.card.set_margin_bottom(44)
        self.card.set_margin_start(40)
        self.card.set_margin_end(40)
        self.win.set_child(self.card)
        self.win.connect("realize", self._click_through)
        self.hide_id = None
        self.unmap_id = None

    def _click_through(self, win):
        win.get_surface().set_input_region(cairo.Region())

    def show(self, caps, desc):
        while (c := self.card.get_first_child()) is not None:
            self.card.remove(c)
        self.card.append(keycaps_box(caps))
        lbl = Gtk.Label(label=desc)
        lbl.add_css_class("desc")
        self.card.append(lbl)
        for src in (self.hide_id, self.unmap_id):
            if src:
                GLib.source_remove(src)
        self.unmap_id = None
        if not self.win.get_visible():
            mon = focused_monitor(self.win.get_display())
            if mon:
                LS.set_monitor(self.win, mon)
            self.card.remove_css_class("on")
            self.win.present()
            GLib.timeout_add(16, lambda: (self.card.add_css_class("on"), False)[1])
        else:
            self.card.add_css_class("on")
        self.hide_id = GLib.timeout_add(int(OSD_SECONDS * 1000), self._fade)

    def _fade(self):
        self.hide_id = None
        self.card.remove_css_class("on")
        self.unmap_id = GLib.timeout_add(260, self._unmap)
        return False

    def _unmap(self):
        self.unmap_id = None
        self.win.set_visible(False)
        return False


class Sheet:
    def __init__(self, app, registry):
        self.app, self.registry, self.win = app, registry, None

    def toggle(self):
        if self.win:
            self.close()
        else:
            self.open()

    def open(self):
        win = Gtk.Window(application=self.app)
        win.add_css_class("keyhud")
        LS.init_for_window(win)
        LS.set_namespace(win, "keyhud-sheet")
        LS.set_layer(win, LS.Layer.OVERLAY)
        for edge in (LS.Edge.TOP, LS.Edge.BOTTOM, LS.Edge.LEFT, LS.Edge.RIGHT):
            LS.set_anchor(win, edge, True)
        LS.set_keyboard_mode(win, LS.KeyboardMode.EXCLUSIVE)
        LS.set_exclusive_zone(win, -1)
        mon = focused_monitor(win.get_display())
        if mon:
            LS.set_monitor(win, mon)
        geo = mon.get_geometry() if mon else None

        backdrop = Gtk.Box()
        backdrop.add_css_class("backdrop")
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.add_css_class("sheet")
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)
        card.set_hexpand(True)
        width = min(980, (geo.width - 80) if geo else 980)
        height = min(660, (geo.height - 120) if geo else 660)
        card.set_size_request(width, -1)
        backdrop.append(card)

        head = Gtk.Box(spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        t = Gtk.Label(label="Pintasan Keyboard", xalign=0)
        t.add_css_class("title")
        self.subtitle = Gtk.Label(xalign=0)
        self.subtitle.add_css_class("subtitle")
        titles.append(t)
        titles.append(self.subtitle)
        titles.set_hexpand(True)
        head.append(titles)
        self.search = Gtk.SearchEntry(placeholder_text="Cari pintasan…")
        self.search.set_size_request(280, -1)
        self.search.set_valign(Gtk.Align.CENTER)
        self.search.connect("search-changed", lambda *_: self.fill())
        self.search.connect("stop-search", lambda *_: self.close())
        head.append(self.search)
        card.append(head)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(height - 130)
        scroll.set_max_content_height(height - 130)
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                                column_spacing=12, row_spacing=12, max_children_per_line=2,
                                min_children_per_line=2, valign=Gtk.Align.START)
        scroll.set_child(self.flow)
        card.append(scroll)
        hint = Gtk.Label(label="esc tutup  ·  ketik untuk mencari  ·  ⌘⇧/ HUD keybind on/off")
        hint.add_css_class("hint")
        card.append(hint)

        win.set_child(backdrop)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        win.add_controller(keys)
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click, card)
        backdrop.add_controller(click)

        self.win, self.card = win, card
        self.fill()
        win.present()
        self.search.grab_focus()
        GLib.timeout_add(16, lambda: (card.add_css_class("on"), False)[1])

    def fill(self):
        while (c := self.flow.get_first_child()) is not None:
            self.flow.remove(c)
        q = self.search.get_text().strip().lower()
        total = 0
        for section, rows in self.registry.sheet_rows().items():
            if q:
                rows = [r for r in rows if q in r[0].lower() or q in section.lower()
                        or q in " ".join(r[1]).lower()]
            if not rows:
                continue
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.add_css_class("section")
            st = Gtk.Label(label=section.upper(), xalign=0)
            st.add_css_class("section-title")
            box.append(st)
            for desc, caps in rows:
                row = Gtk.Box(spacing=10)
                row.add_css_class("row")
                d = Gtk.Label(label=desc, xalign=0, hexpand=True)
                d.add_css_class("desc")
                row.append(d)
                row.append(keycaps_box(caps, spacing=3))
                box.append(row)
                total += 1
            self.flow.append(box)
        if total == 0:
            e = Gtk.Label(label="Gak ada pintasan yang cocok")
            e.add_css_class("empty")
            self.flow.append(e)
        self.subtitle.set_label(f"{total} pintasan" + (f" cocok dengan “{q}”" if q else ""))

    def _on_key(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def _on_click(self, gesture, n, x, y, card):
        picked = self.win.pick(x, y, Gtk.PickFlags.DEFAULT)
        if picked is None or not (picked == card or picked.is_ancestor(card)):
            self.close()

    def close(self):
        if not self.win:
            return
        win, self.win = self.win, None
        self.card.remove_css_class("on")
        GLib.timeout_add(140, lambda: (win.destroy(), False)[1])


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="dev.dracarys.keyhud")
        self.registry = Registry()
        self.osd_on = not os.path.exists(OSD_OFF)

    def do_activate(self):
        self.hold()
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 10)
        self.hud = Hud(self)
        self.sheet = Sheet(self, self.registry)
        try:
            os.unlink(SOCK)
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(SOCK)
        GLib.io_add_watch(self.sock.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN, self._on_msg)

    def _on_msg(self, fd, cond):
        msg = self.sock.recv(256).decode(errors="ignore").split()
        if not msg:
            return True
        cmd = msg[0]
        if cmd == "show" and len(msg) > 1 and msg[1].isdigit():
            if self.osd_on and not self.sheet.win:
                e = self.registry.get(int(msg[1]))
                if e:
                    self.hud.show(key_tokens(e["keys"]), e["desc"])
        elif cmd == "cheatsheet":
            self.sheet.toggle()
        elif cmd == "toggle-osd":
            self.osd_on = not self.osd_on
            os.makedirs(STATE_DIR, exist_ok=True)
            if self.osd_on:
                if os.path.exists(OSD_OFF):
                    os.unlink(OSD_OFF)
                self.hud.show(["⌘", "⇧", "/"], "HUD keybind nyala")
            else:
                open(OSD_OFF, "w").close()
        return True


if __name__ == "__main__":
    App().run(None)

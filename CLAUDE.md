# CLAUDE.md — konteks buat sesi Claude Code di repo ini

Rice Hyprland (config Lua, ≥ 0.56) + noctalia 5.x bernuansa macOS/iOS. Repo ini **public**:
jangan pernah commit rahasia, IP, nama/email asli, isi chat, atau screenshot yang memuat itu.
Commit memakai identitas noreply GitHub (sudah diset di `git config` lokal repo ini).

## Alur kerja

- Config yang **hidup** ada di `$HOME` mesin utama. Repo cuma cermin di `home/` (path home = `@HOME@`).
- Habis mengubah sesuatu di `$HOME`: `./sync.sh` → `git diff` → commit → push.
  `sync.sh` hanya memperbarui file yang sudah dilacak; file baru disalin manual dulu ke `home/<path sama>`.
- `install.sh [--no-packages|--no-backup|--dry-run]` memasang ke mesin lain. Tes aman tanpa menyentuh
  home asli: `HOME=$(mktemp -d) ./install.sh --no-packages`.
- Tool baru di `~/.local/bin` → tambahkan ke daftar `chmod +x` di `install.sh`; paket baru → `packages.txt`;
  fitur baru → tabel "Isi rice" + shortcut + troubleshooting di `README.md`.

## Komponen buatan sendiri

| Komponen | Lokasi | Inti |
|---|---|---|
| **wsstrip** | `.local/lib/wsstrip/wsstrip.py`, `bin/wsstrip`, `bin/wsstrip-send` | Strip workspace kiri (kartu 3D). Hover tepi kiri / Super+Tab; pin = Super+Ctrl+Tab (exclusive zone, 5 ws, ws kosong disembunyikan). 5 gaya animasi (default `kipas`). Juga menulis nama app aktif ke `$XDG_RUNTIME_DIR/rice-active-app` dan memetakan ulang strip saat bar noctalia dibuat ulang. |
| **spotlight** | `.local/lib/spotlight/spotlight.py`, `bin/spotlight`, `bin/spotlight-send` | Launcher Spotlight (Super+Space) + **Launchpad** (Super+G, cubit 4 jari, ikon dock `rice-launchpad`). Perintah: `toggle show hide query <t> launchpad launchpad-hide launchpad-page <n>`. |
| **keyhud** | `.local/lib/keyhud/keyhud.py` | HUD keybind + cheatsheet Super+/. Label diturunkan dari isi baris `binds.lua`. |
| Plugin noctalia | `.local/share/noctalia-plugins/{spotlight,appname,uptime}` | Luau. API yang terbukti ada: `noctalia.getenv/readFile/writeFile/fileExists/expandPath/runAsync/setUpdateInterval`, `barWidget.setText/setGlyph/setTooltip/setVisible`, `function update()`, `function onClick()`. Cek: `noctalia plugins lint <dir>`. |
| noctalia-keepalive | `.local/bin/noctalia-keepalive` | Nyalakan ulang noctalia (bukan `noctalia.service`, biar gak ikut di sesi Plasma). |

Semua daemon Python: GTK4 + gtk4-layer-shell, wrapper `LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so`,
loop nyala-ulang di wrapper (exit ≠ 0 → restart). Restart daemon: `pkill -f '^python3 .*/<nama>.py'`
(pola tanpa `^` ikut membunuh shell yang menjalankan perintahnya). Stop total: bunuh wrapper `bin/<nama>` dulu.

## Jebakan yang sudah ketemu (jangan diulang)

- **Ikon SVG di widget beranimasi bikin GTK 4.24 abort** (`gsk_gpu_render_pass_draw_clip_mask`, vulkan & gl;
  `GSK_RENDERER=ngl` cuma alias `gl`). Selalu rasterisasi ikon → `Gdk.MemoryTexture` dari pixbuf.
- **Hyprland gak kirim input mouse ke surface layer 100% transparan** → latar alpha 1%.
  GTK4 memaksa surface kosong lebar 200px → potong input region pakai cairo.
- **Surface muncul di bawah kursor diam = gak ada event enter** → wsstrip memantau posisi kursor lewat
  socket `.socket.sock` (`j/cursorpos`), bukan enter/leave GTK.
- `set_overflow(HIDDEN)` + transform 3D memotong gambar (clip GTK dihitung 2D).
- **Exclusive zone ditata menurut urutan surface dibuat**: panel noctalia "attached", OSD `top_center`, dan
  bar yang dibuat ulang ikut bergeser oleh kolom strip ter-pin → panel dibuat `floating`, OSD `top_right`,
  strip di-remap saat event `openlayer>>noctalia-bar*`.
- `hyprctl dispatch workspace N` gagal di config Lua → `hyprctl eval 'hl.dispatch(hl.dsp.focus({ workspace = N }))'`.
- Action `hl.gesture` di Lua boleh **function**; `"dispatcher"`/`"exec"` ditolak. Menguji `hl.gesture` lewat
  `hyprctl eval` menambah gesture live — selalu `hyprctl reload` sesudahnya.
- Setelan noctalia yang aktif: `~/.local/state/noctalia/settings.toml` (bukan `~/.config/noctalia`).
  `noctalia config validate` gak mengecek nilai enum. noctalia membaca/menulis setelan home **asli** walau
  `HOME` diganti (Hyprland nested dengan HOME palsu tetap menulis setelan asli) — jangan pakai cara itu.
- Entri dock harus TANPA `NoDisplay` (dock gak baca ikonnya); dock baru membaca ikon setelah config dock reload.
- Mengubah `lockscreen_widgets` saat layar terkunci → noctalia crash.

## Screenshot README (`screenshots/`)

Ambil di desktop asli **setelah** jendela pribadi ditutup, pakai workspace kosong (mis. 9) + aplikasi demo,
`noctalia msg notification-dnd-set on`, dan cek tiap gambar sebelum commit. fastfetch: jalankan
`kitty sh -c "fastfetch --config <json tanpa IP/baterai>; sleep infinity"` (`--hold` membuka shell yang
menjalankan fastfetch lengkap). btop/daftar proses dan halaman Launchpad yang memuat aplikasi kerja
jangan dipublikasikan. MPRIS palsu (Gio DBus) bisa dipakai untuk memunculkan pil Now Playing tanpa suara.

## Ide lanjutan yang belum dikerjakan

- Baterai gaya iOS (widget battery noctalia belum punya opsi bentuk).
- OSD yang menyatu dengan island tengah (posisi OSD noctalia cuma preset).
- Tes install penuh di mesin kosong / Arch polos (`noctalia-git` dari AUR).

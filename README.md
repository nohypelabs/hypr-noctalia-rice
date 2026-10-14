# hypr-noctalia-rice

Rice Hyprland + [noctalia](https://github.com/noctalia-dev/noctalia) bernuansa macOS/iOS, dari laptop CachyOS.
Bisa dipasang ke laptop atau PC lain berbasis Arch dengan satu skrip.

## Isi

| Bagian | Keterangan |
|---|---|
| **Hyprland** (`~/.config/hypr`, config Lua, butuh ≥ 0.56) | Dekorasi squircle + blur, animasi pegas ala iOS, perpindahan workspace vertikal, swipe 4 jari atas/bawah (sensitif), mode proyektor Super+P |
| **noctalia** (`~/.local/state/noctalia/settings.toml`) | Bar "Dynamic Island", dock ngambang + magnifikasi, launcher ala Spotlight, lock screen ala iOS, hot corner, Night Light, plugin `uptime` |
| **wsstrip** | Strip workspace di kiri (kartu 3D gaya Stage Manager). Muncul saat kursor di tepi kiri, bisa di-pin jadi kolom tetap (5 workspace, workspace kosong disembunyikan) |
| **keyhud** | HUD tiap kali keybind ditekan + cheatsheet (Super+/) |
| **noctalia-keepalive** | Nyalakan ulang noctalia kalau mati (mis. setelah suspend) |
| **kitty** | Tema Tokyo Night, terminal dropdown, kitten scroll/search |
| **Wallpaper** | 6 wallpaper orisinal gaya iOS/macOS (digenerate, bukan aset Apple) |
| **Tema** | Font Inter, ikon & kursor MacTahoe (dipasang dari GitHub vinceliuice), qt6ct, adw-gtk3-dark |

## Pasang

```bash
gh repo clone nohypelabs/hypr-noctalia-rice   # atau git clone via ssh
cd hypr-noctalia-rice
./install.sh --dry-run    # lihat dulu apa yang bakal diubah
./install.sh
```

Opsi: `--no-packages` (config saja), `--no-backup` (timpa tanpa backup), `--dry-run`.

Yang dilakukan `install.sh`:
1. Pasang paket dari `packages.txt` (pacman; yang gak ada di repo dicoba lewat `paru`/`yay`).
2. Pasang ikon + kursor MacTahoe ke `~/.local/share/icons` (dilewati kalau sudah ada).
3. Salin isi `home/` ke `$HOME`. Placeholder `@HOME@` diganti path home mesin itu.
   File lama yang beda isinya dibackup ke `~/.local/share/hypr-noctalia-rice/backup-<waktu>/`.
4. Cek versi Hyprland, noctalia, binding Python gtk4-layer-shell, dan validasi setelan noctalia.

Setelah itu logout dan pilih sesi **Hyprland (uwsm-managed)**.

### Sesuaikan per mesin
- `~/.config/hypr/config/variables.lua`: nama monitor (`MONITOR1`), browser, aplikasi default.
- `~/.config/hypr/config/binds.lua`: beberapa bind menunjuk aplikasi KDE (`kate`, `kcalc`) dan `brave`.
- Wallpaper per monitor di setelan noctalia memakai nama output `eDP-1` / `HDMI-A-1`. Output lain
  memakai `[wallpaper.default]`.
- noctalia di CachyOS ada di repo `cachyos-extra`. Di Arch polos dicari lewat AUR.

## Shortcut utama

| Tombol | Aksi |
|---|---|
| Super+/ | Cheatsheet semua keybind |
| tepi kiri layar / Super+Tab | Strip workspace (keyboard: 1–5, ↑↓, Enter, Esc) |
| Super+Ctrl+Tab | Pin / lepas strip (makan ruang desktop) |
| Super+Shift+Tab | Ganti gaya animasi strip (pintu, geser, flip, zoom, kipas) |
| Super+Shift+W | Wallpaper acak |
| Super+P | Mode layar (duplikat / perpanjang / eksternal / laptop) |
| swipe 4 jari ↑↓ | Pindah workspace |

## Merawat repo

Habis ngoprek rice di mesin utama:

```bash
./sync.sh        # tarik config yang sedang dipakai ke home/ (path → @HOME@)
git diff         # cek perubahan
git commit -am "..." && git push
```

`sync.sh` cuma memperbarui file yang sudah ada di `home/`. File baru disalin manual dulu ke
`home/<path yang sama>`.

## Catatan teknis

- **wsstrip:** ikon aplikasi di kartu sengaja dirasterisasi jadi bitmap. Ikon SVG yang ikut
  dianimasikan bikin renderer GSK di GTK 4.24 abort (`gsk_gpu_render_pass_draw_clip_mask`).
- **wsstrip:** pemicu tepi kiri berupa strip 2px dengan alpha 1%, karena Hyprland gak kirim input
  mouse ke surface yang 100% transparan.
- **noctalia:** setelan yang aktif ada di `~/.local/state/noctalia/settings.toml` (ditulis GUI Settings)
  dan menimpa `~/.config/noctalia/config.toml`.

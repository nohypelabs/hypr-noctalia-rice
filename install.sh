#!/usr/bin/env bash
# Pasang rice Hyprland + noctalia ala macOS/iOS ke $HOME pengguna ini.
#
#   ./install.sh                 pasang paket + config (file lama dibackup dulu)
#   ./install.sh --no-packages   config saja, paket gak disentuh
#   ./install.sh --no-backup     timpa langsung tanpa backup
#   ./install.sh --dry-run       tampilkan rencana tanpa mengubah apa pun
#
# Khusus distro berbasis Arch (Arch, CachyOS, EndeavourOS, ...). Jangan jalankan sebagai root.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO/home"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$HOME/.local/share/hypr-noctalia-rice/backup-$STAMP"
DO_PKGS=1 DO_BACKUP=1 DRY=0

for a in "$@"; do
  case "$a" in
    --no-packages) DO_PKGS=0 ;;
    --no-backup) DO_BACKUP=0 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opsi gak dikenal: $a (lihat --help)" >&2; exit 2 ;;
  esac
done

c_info=$'\e[1;34m' c_ok=$'\e[1;32m' c_warn=$'\e[1;33m' c_off=$'\e[0m'
info() { printf '%s==>%s %s\n' "$c_info" "$c_off" "$*"; }
ok()   { printf '%s ✓%s %s\n' "$c_ok" "$c_off" "$*"; }
warn() { printf '%s !%s %s\n' "$c_warn" "$c_off" "$*" >&2; }
run()  { if ((DRY)); then printf '   [dry-run] %s\n' "$*"; else "$@"; fi; }

[[ $EUID -eq 0 ]] && { echo "Jalankan sebagai user biasa, bukan root (sudo dipanggil seperlunya)." >&2; exit 1; }
command -v pacman >/dev/null || { echo "Butuh distro berbasis Arch (pacman gak ketemu)." >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Paket
# ---------------------------------------------------------------------------
install_packages() {
  info "Memasang paket"
  mapfile -t want < <(sed -e 's/#.*//' -e 's/[[:space:]]//g' "$REPO/packages.txt" | grep -v '^$')
  local repo_pkgs=() aur_pkgs=()
  for p in "${want[@]}"; do
    if pacman -Si "$p" >/dev/null 2>&1; then repo_pkgs+=("$p"); else aur_pkgs+=("$p"); fi
  done
  run sudo pacman -S --needed --noconfirm "${repo_pkgs[@]}"
  if ((${#aur_pkgs[@]})); then
    local helper=""
    for h in paru yay; do command -v "$h" >/dev/null && { helper=$h; break; }; done
    if [[ -n $helper ]]; then
      run "$helper" -S --needed --noconfirm "${aur_pkgs[@]}" || warn "Sebagian paket AUR gagal: ${aur_pkgs[*]}"
    else
      warn "Gak ada di repo & gak ada AUR helper (paru/yay): ${aur_pkgs[*]} — pasang manual."
    fi
  fi
  ok "Paket selesai"
}

# Tema ikon + kursor MacTahoe (gak ada di repo resmi) dari GitHub vinceliuice, dipasang
# ke ~/.local/share/icons. Dilewati kalau sudah ada.
install_mactahoe() {
  local icons="$HOME/.local/share/icons"
  if [[ -d $icons/MacTahoe-dark && -d $icons/MacTahoe-cursors ]]; then
    ok "Ikon & kursor MacTahoe sudah ada"; return
  fi
  info "Memasang ikon & kursor MacTahoe (github.com/vinceliuice/MacTahoe-icon-theme)"
  ((DRY)) && { echo "   [dry-run] git clone + ./install.sh + cursors/install.sh"; return; }
  local tmp; tmp="$(mktemp -d)"
  if git clone --depth 1 https://github.com/vinceliuice/MacTahoe-icon-theme "$tmp/mt" >/dev/null 2>&1; then
    (cd "$tmp/mt" && ./install.sh >/dev/null) || warn "Install ikon MacTahoe gagal"
    if [[ -x $tmp/mt/cursors/install.sh ]]; then
      (cd "$tmp/mt/cursors" && ./install.sh >/dev/null) || warn "Install kursor MacTahoe gagal"
    fi
    # kursor kadang terpasang di ~/.icons; samakan ke ~/.local/share/icons
    for d in "$HOME"/.icons/MacTahoe*cursors; do
      [[ -d $d && ! -e $icons/$(basename "$d") ]] && mkdir -p "$icons" && cp -r "$d" "$icons/"
    done
    ok "MacTahoe terpasang"
  else
    warn "Gagal clone MacTahoe-icon-theme — ikon/kursor pakai bawaan dulu."
  fi
  rm -rf "$tmp"
}

# ---------------------------------------------------------------------------
# 2. Config: salin home/ ke $HOME, @HOME@ diganti path home mesin ini
# ---------------------------------------------------------------------------
install_files() {
  info "Menyalin config ke $HOME"
  local n=0 backed=0
  while IFS= read -r -d '' f; do
    local rel="${f#"$SRC"/}" dst="$HOME/${f#"$SRC"/}" want="$f"
    # file ber-@HOME@ dibandingkan dalam bentuk yang sudah diisi path home ini
    if grep -Iq '@HOME@' "$f" 2>/dev/null; then
      want="$(mktemp)"; sed "s|@HOME@|$HOME|g" "$f" > "$want"
    fi
    if [[ -e $dst ]] && ((DO_BACKUP)) && ! cmp -s "$want" "$dst"; then
      run mkdir -p "$(dirname "$BACKUP/$rel")"
      run cp -a "$dst" "$BACKUP/$rel"
      backed=$((backed + 1))
    fi
    run mkdir -p "$(dirname "$dst")"
    if grep -Iq '@HOME@' "$f" 2>/dev/null; then
      if ((DRY)); then echo "   [dry-run] tulis $dst (@HOME@ → $HOME)"
      else sed "s|@HOME@|$HOME|g" "$f" > "$dst"; chmod --reference="$f" "$dst"; fi
    else
      run cp -a "$f" "$dst"
    fi
    [[ $want != "$f" ]] && rm -f "$want"
    n=$((n + 1))
  done < <(find "$SRC" -type f -print0)
  run chmod +x "$HOME"/.local/bin/{keyhud,keyhud-send,wsstrip,wsstrip-send,noctalia-keepalive} \
               "$HOME"/.config/hypr/scripts/*.sh
  run mkdir -p "$HOME/Pictures/Screenshots"
  ok "$n file disalin"
  ((backed)) && ok "$backed file lama dibackup ke $BACKUP"
  return 0
}

post_checks() {
  info "Pengecekan"
  local v
  v="$(hyprctl version -j 2>/dev/null | jq -r .version 2>/dev/null || pacman -Q hyprland 2>/dev/null | awk '{print $2}')"
  [[ -n $v ]] && ok "Hyprland $v (butuh >= 0.56 untuk config Lua)" || warn "Hyprland belum terpasang"
  command -v noctalia >/dev/null && ok "noctalia ada" || warn "noctalia belum terpasang"
  python3 -c 'import gi; gi.require_version("Gtk4LayerShell","1.0"); from gi.repository import Gtk4LayerShell' 2>/dev/null \
    && ok "gtk4-layer-shell untuk Python OK" || warn "gtk4-layer-shell/python-gobject belum lengkap (wsstrip & keyhud gak jalan)"
  if command -v noctalia >/dev/null && ! ((DRY)); then
    noctalia config validate "$HOME/.local/state/noctalia/settings.toml" >/dev/null 2>&1 \
      && ok "settings noctalia valid" || warn "noctalia config validate kasih peringatan (cek manual)"
  fi
}

((DO_PKGS)) && install_packages
((DO_PKGS)) && install_mactahoe
install_files
post_checks

cat <<EOF

${c_ok}Selesai.${c_off} Langkah berikutnya:
  1. Logout, pilih sesi "Hyprland (uwsm-managed)" di layar login.
  2. Sesuaikan ${c_info}~/.config/hypr/config/variables.lua${c_off} (nama monitor, browser, aplikasi default).
  3. Shortcut: Super+/ cheatsheet · tepi kiri / Super+Tab strip workspace ·
     Super+Ctrl+Tab pin strip · Super+Shift+Tab ganti animasi strip · Super+Shift+W ganti wallpaper.
EOF

#!/usr/bin/env bash
# Daftar keybind dari config/binds.lua (komentar "-- sway: ..." ikut tampil).
BINDS="$HOME/.config/hypr/config/binds.lua"
list=$(grep -E '^\s*hl\.bind\(' "$BINDS" \
  | sed -E 's/^\s*hl\.bind\(mainMod \.\. " \+ /SUPER + /; s/^\s*hl\.bind\("//; s/",\s*/  →  /; s/\)\s*,\s*\{[^}]*\}\)?//; s/\s*--\s*/   # /' \
  | column -t -s '→' 2>/dev/null)
kitty --class cheatsheet --title "Keybinds" sh -c "printf '%s\n' \"\$1\" | less -R" _ "$list"

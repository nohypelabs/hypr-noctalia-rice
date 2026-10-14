#!/usr/bin/env bash
# Kebalikan install.sh: tarik config yang sedang dipakai di mesin ini ke dalam repo
# (cuma file yang sudah dilacak di home/), path home diganti @HOME@ lagi.
# Pakai setelah ngoprek rice, lalu `git diff` buat lihat perubahannya.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO/home"
n=0 miss=0
while IFS= read -r -d '' f; do
  live="$HOME/${f#"$SRC"/}"
  if [[ ! -e $live ]]; then
    echo " ! gak ada di mesin ini: ${f#"$SRC"/}" >&2; miss=$((miss + 1)); continue
  fi
  if grep -Iq . "$live" 2>/dev/null; then
    sed "s|$HOME|@HOME@|g" "$live" > "$f.tmp"
    chmod --reference="$live" "$f.tmp" && mv "$f.tmp" "$f"
  else
    cp -a "$live" "$f"
  fi
  n=$((n + 1))
done < <(find "$SRC" -type f -print0)
# wallpaper pribadi (bukan ios-/macos- bawaan repo) di setelan noctalia → wallpaper bawaan
sed -i -E '/Wallpapers\/(ios|macos)-/! s#(@HOME@/Pictures/Wallpapers/)[^"]+\.(png|jpe?g|webp)"#\1macos-mesh-aurora.png"#' \
  "$SRC/.local/state/noctalia/settings.toml"
echo "$n file disinkronkan ke repo$( ((miss)) && echo ", $miss gak ketemu")."
echo "File baru gak otomatis ikut: salin manual ke home/<path yang sama> dulu."
git -C "$REPO" status --short

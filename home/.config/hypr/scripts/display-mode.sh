#!/usr/bin/env bash
# Mode layar ala Win+P untuk Hyprland: duplicate | extend | external | internal.
# Ditulis ulang dari versi sway (swaymsg → hyprctl). Perubahan bersifat runtime
# (hyprctl keyword monitor); konfigurasi permanen tetap di config/monitors.lua.
set -u

notify() {
    command -v notify-send >/dev/null 2>&1 && notify-send -t 3000 -u low "Display Mode" "$1" 2>/dev/null || true
}

monitors_json() { hyprctl monitors all -j 2>/dev/null; }

get_internal() {
    local name
    name=$(monitors_json | jq -r '.[] | select(.name | test("eDP|LVDS")) | .name' | head -n1)
    [ -n "$name" ] && echo "$name" || echo "eDP-1"
}

get_external() {
    # Konektor terhubung selain internal (sysfs, sama seperti versi sway).
    local internal="$1" f name
    for f in /sys/class/drm/card*-HDMI-* /sys/class/drm/card*-DP-*; do
        [ -f "$f/status" ] || continue
        [ "$(cat "$f/status" 2>/dev/null)" = "connected" ] || continue
        name=$(basename "$f" | sed 's/^card[0-9]*-//')
        [ "$name" != "$internal" ] && { echo "$name"; return; }
    done
}

INTERNAL=$(get_internal)
EXTERNAL=$(get_external "$INTERNAL")

require_external() {
    if [ -z "$EXTERNAL" ]; then
        notify "$1: tidak ada layar eksternal terdeteksi — colok HDMI/DP dulu"
        exit 0
    fi
}

STATE_FILE="$HOME/.local/state/hyprland/display-mode"
mkdir -p "$(dirname "$STATE_FILE")"

# State dibaca config/monitors.lua; reload supaya rule monitor dihitung ulang.
apply() {
    echo "$1" > "$STATE_FILE"
    hyprctl reload >/dev/null
}

case "${1:-}" in
    duplicate)
        require_external "Duplicate"
        apply duplicate
        notify "Duplicate: $EXTERNAL mencerminkan $INTERNAL"
        ;;
    extend)
        require_external "Extend"
        apply extend
        notify "Extend: $EXTERNAL di kanan $INTERNAL"
        ;;
    external)
        require_external "External only"
        apply external-only
        notify "Hanya $EXTERNAL"
        ;;
    internal)
        apply internal-only
        notify "Hanya $INTERNAL"
        ;;
    *)
        echo "Pemakaian: $(basename "$0") duplicate|extend|external|internal" >&2
        exit 1
        ;;
esac

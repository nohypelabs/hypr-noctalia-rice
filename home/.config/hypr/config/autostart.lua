-- Auto-start config
-- if you dont use UWSM add your auto start programs here, otherwise use XDG autostart https://wiki.archlinux.org/title/XDG_Autostart

hl.on("hyprland.start", function ()
    hl.exec_cmd("dbus-update-activation-environment --systemd --all")
    hl.exec_cmd(os.getenv("HOME") .. "/.local/bin/noctalia-keepalive")
    hl.exec_cmd("hypridle")
    hl.exec_cmd(os.getenv("HOME") .. "/.local/bin/docked-no-sleep")  -- monitor eksternal = gak suspend
    hl.exec_cmd(os.getenv("HOME") .. "/.local/bin/keyhud")  -- HUD keybind + cheatsheet Super+/
    hl.exec_cmd(os.getenv("HOME") .. "/.local/bin/spotlight")  -- launcher Spotlight, Super+Space
    hl.exec_cmd(os.getenv("HOME") .. "/.local/bin/wsstrip")  -- strip workspace kiri, hover tepi kiri / Super+Tab
    hl.exec_cmd("xhost +SI:localuser:root")
end)

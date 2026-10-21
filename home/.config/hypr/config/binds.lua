-- Keybinds: port 1:1 dari ~/.config/sway/config (bagian "Noctalia-style keybinds")
-- Urutan & komentar ngikutin file sway-nya biar gampang dibandingin side-by-side.
--
-- Aturan port:
--   * kombo tombol PERSIS sama kayak sway — gak ada yang di-remap lagi
--   * kalau tool-nya sway-only, dipakai padanan native Hyprland:
--       swaylock/fuzzel/cliphist/wlogout/waybar/swaync/modal wifi-bt -> noctalia
--       swaymsg       -> hyprctl (script display-mode versi hypr)
--   * sisanya (grim/slurp, nwg-displays) jalan apa adanya
--
-- Cek sebelum login: Hyprland --verify-config

local mainMod = _G.mainMod or "SUPER"
local terminal = TERMINAL or "kitty"  -- variables.lua CachyOS
local menu = os.getenv("HOME") .. "/.local/bin/spotlight-send toggle || noctalia msg panel-toggle launcher"  -- launcher Spotlight (~/.local/lib/spotlight), cadangan launcher noctalia
local hyprScripts = os.getenv("HOME") .. "/.config/hypr/scripts"

-- exec_cmd dijalanin lewat /bin/sh, jadi pipe / $(...) / || aman ditulis langsung.
local function shell(cmd)
  return hl.dsp.exec_cmd(cmd)
end

-- Helper: noctalia dulu (biar OSD-nya muncul), fallback ke tool langsung kalau
-- daemon-nya lagi mati. Padanan dari sway yang pakai pactl + show-slider waybar.
local function noctalia(msg, fallback)
  if fallback then
    return hl.dsp.exec_cmd("noctalia msg " .. msg .. " || " .. fallback)
  end
  return hl.dsp.exec_cmd("noctalia msg " .. msg)
end

-- ### keyhud ###############################################################
-- HUD keybind ala Omarchy (~/.local/lib/keyhud): tiap hl.bind di file ini dicatat ke
-- registry $XDG_RUNTIME_DIR/keyhud-binds.tsv (idx, tombol, nomor baris) dan, kalau
-- bukan mouse/media/screenshot, ikut kirim "show <idx>" ke daemon. Label aksi
-- diturunkan keyhud dari isi baris ini, jadi bind baru otomatis ikut muncul.
local keyhudSend = os.getenv("HOME") .. "/.local/bin/keyhud-send"
local keyhudList = {}
local rawBind = hl.bind
local keyhudQuiet = { "mouse", "XF86", "Print", "F10", "slash" }
hl.bind = function(keys, dsp, opts)
  local line = 0
  local info = debug and debug.getinfo and debug.getinfo(2, "Sl")
  if info and tostring(info.short_src):find("binds%.lua") then line = info.currentline end
  keyhudList[#keyhudList + 1] = keys .. "\t" .. line
  local quiet = opts and opts.mouse
  for _, s in ipairs(keyhudQuiet) do
    if keys:find(s, 1, true) then quiet = true end
  end
  if quiet or type(dsp) == "function" then return rawBind(keys, dsp, opts) end
  local osd = hl.dsp.exec_cmd(keyhudSend .. " show " .. #keyhudList)
  return rawBind(keys, function() hl.dispatch(dsp); hl.dispatch(osd) end, opts)
end


-- ### Basics ###############################################################
hl.bind(mainMod .. " + Escape", hl.dsp.window.close())                          -- sway: $mod+Escape kill
hl.bind(mainMod .. " + Q", hl.dsp.window.close())                               -- sway: $mod+q kill
hl.bind(mainMod .. " + ALT + SPACE", hl.dsp.window.float({ action = "toggle" })) -- sway: $mod+Mod1+space floating toggle
hl.bind(mainMod .. " + F", hl.dsp.window.fullscreen({ mode = "fullscreen", action = "toggle" })) -- sway: $mod+f fullscreen
hl.bind(mainMod .. " + J", noctalia("bar-toggle"))                              -- sway: $mod+j bar-toggle.sh (waybar) -> bar noctalia
hl.bind(mainMod .. " + Y", hl.dsp.layout("togglesplit"))                        -- sway: $mod+y layout toggle split
hl.bind(mainMod .. " + H", hl.dsp.layout("preselect r"))                        -- sway: $mod+h splith (dwindle: window berikutnya ke kanan)
hl.bind(mainMod .. " + SHIFT + V", hl.dsp.layout("preselect d"))                -- sway: $mod+Shift+v splitv (window berikutnya ke bawah)
hl.bind(mainMod .. " + L", hl.dsp.exec_cmd("@HOME@/.local/bin/lock"), { locked = true })                            -- sway: $mod+l swaylock
hl.bind(mainMod .. " + ALT + C", noctalia("panel-toggle session"))              -- sway: $mod+Mod1+c wlogout

-- ### Drag / resize floating windows pakai mouse ############################
-- sway: floating_modifier $mod normal (kiri = pindah, kanan = resize)
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- ### Focus ################################################################
hl.bind(mainMod .. " + Left", hl.dsp.focus({ direction = "left" }))             -- sway: $mod+Left focus left
hl.bind(mainMod .. " + Right", hl.dsp.focus({ direction = "right" }))           -- sway: $mod+Right focus right
hl.bind(mainMod .. " + Up", hl.dsp.focus({ direction = "up" }))                 -- sway: $mod+Up focus up
hl.bind(mainMod .. " + Down", hl.dsp.focus({ direction = "down" }))             -- sway: $mod+Down focus down
-- sway: Mod1+Tab focus mode_toggle (tiling <-> floating). Hyprland gak punya
-- padanan persis; cycle_next = keliling window di workspace, paling mirip rasanya.
hl.bind("ALT + Tab", hl.dsp.window.cycle_next())

-- ### Move window ##########################################################
hl.bind(mainMod .. " + SHIFT + Right", hl.dsp.window.move({ direction = "r" })) -- sway: $mod+Shift+Right move right
hl.bind(mainMod .. " + SHIFT + Left", hl.dsp.window.move({ direction = "l" }))  -- sway: $mod+Shift+Left move left
hl.bind(mainMod .. " + SHIFT + Up", hl.dsp.window.move({ direction = "u" }))    -- sway: $mod+Shift+Up move up
hl.bind(mainMod .. " + SHIFT + Down", hl.dsp.window.move({ direction = "d" }))  -- sway: $mod+Shift+Down move down
hl.bind(mainMod .. " + CTRL + SHIFT + Right", hl.dsp.window.move({ workspace = "e+1" })) -- sway: move container to workspace next
hl.bind(mainMod .. " + CTRL + SHIFT + Left", hl.dsp.window.move({ workspace = "e-1" }))  -- sway: move container to workspace prev

-- ### Apps #################################################################
hl.bind(mainMod .. " + RETURN", hl.dsp.exec_cmd(terminal))                      -- sway: $mod+Return $term
hl.bind(mainMod .. " + grave", hl.dsp.exec_cmd("rio-dropdown"))  -- terminal dropdown (~/.local/bin/rio-dropdown)
hl.bind(mainMod .. " + E", hl.dsp.exec_cmd(FILE_MANAGER))
hl.bind(mainMod .. " + T", hl.dsp.exec_cmd("kate"))                             -- sway: $mod+t kate
hl.bind(mainMod .. " + C", hl.dsp.exec_cmd("kcalc"))                            -- sway: $mod+c kcalc
hl.bind(mainMod .. " + B", hl.dsp.exec_cmd("brave"))                            -- sway: $mod+b brave
hl.bind(mainMod .. " + W", noctalia("panel-toggle control-center network"))     -- sway: $mod+w wifi-modal.sh
hl.bind(mainMod .. " + SHIFT + B", noctalia("panel-toggle control-center bluetooth"))     -- sway: $mod+Shift+b
hl.bind(mainMod .. " + O", noctalia("panel-toggle control-center bluetooth"))             -- sway: $mod+o
hl.bind("CTRL + SHIFT + Escape", hl.dsp.exec_cmd(terminal .. " -e btop"))       -- sway: Control+Shift+Escape $term btop
hl.bind(mainMod .. " + SPACE", hl.dsp.exec_cmd(menu))                           -- sway: $mod+Space fuzzel -> launcher noctalia
-- clipboard history bawaan noctalia (gantiin cliphist)
hl.bind(mainMod .. " + V", noctalia("panel-toggle clipboard"))

-- ### Screenshots (noctalia) ##############################################
-- PrtSc Latitude = Fn+F10 (keysym Print). F10 polos juga screenshot (diambil dari aplikasi).
-- Hasil: masuk clipboard + ~/Pictures/Screenshots. Di overlay region: Enter/Space buka editor anotasi.
for _, key in ipairs({ "Print", "F10" }) do
    hl.bind(key, noctalia("screenshot-region"), { locked = true })                    -- pilih area
    hl.bind("SHIFT + " .. key, noctalia("screenshot-fullscreen"), { locked = true })  -- satu layar penuh
    hl.bind(mainMod .. " + " .. key, noctalia("screenshot-annotate"))                 -- coret-coret di layar
end

-- ### Rekam layar (OBS) ######################################################
-- Sumber "Screen Capture (PipeWire)" lewat xdg-desktop-portal-hyprland (di KDE
-- lewat portal KDE — scene OBS yang sama jalan di dua sesi). Encoder: VA-API
-- (Intel iHD) agar tidak membebani CPU.
hl.bind(mainMod .. " + R", hl.dsp.exec_cmd("obs"))                               -- buka OBS

-- ### Display modes ala Windows Win+P ######################################
-- display-mode.sh versi hypr (hyprctl), bukan yang di ~/.config/sway/scripts (swaymsg)
hl.bind(mainMod .. " + P", hl.dsp.exec_cmd("nwg-displays"))                                     -- sway: $mod+p
hl.bind(mainMod .. " + SHIFT + P", hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/hypr/scripts/display-mode.sh duplicate"))
hl.bind(mainMod .. " + CTRL + P", hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/hypr/scripts/display-mode.sh extend"))
hl.bind(mainMod .. " + ALT + SHIFT + P", hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/hypr/scripts/display-mode.sh external"))
hl.bind(mainMod .. " + SHIFT + O", hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/hypr/scripts/display-mode.sh internal"))
hl.bind("XF86Display", hl.dsp.exec_cmd("nwg-displays"))                                          -- sway: XF86Display

-- ### Reload / exit ########################################################
hl.bind(mainMod .. " + SHIFT + C", hl.dsp.exec_cmd("hyprctl reload"))           -- sway: $mod+Shift+c reload
-- sway: $mod+Shift+e -> swaynag konfirmasi exit. Di hypr pakai panel session
-- noctalia (ada logout/reboot/shutdown) biar gak langsung keluar tanpa konfirmasi.
hl.bind(mainMod .. " + SHIFT + E", noctalia("panel-open session"))

-- ### Wallpaper ############################################################
-- wallpaper dipegang noctalia: acak dari ~/Pictures/Wallpapers (termasuk ios-*/macos-*), rotasi otomatis mati
hl.bind(mainMod .. " + SHIFT + W", noctalia("wallpaper-random")) -- sway: $mod+Shift+w

-- ### Tema dark/light ######################################################
-- Cuma tema noctalia. Script theme-toggle.sh (waybar) sengaja gak dipakai: dia nulis
-- ~/.config/gtk-{3,4}.0 + gsettings yang dipakai bareng sesi Plasma -> bocor lintas sesi.
hl.bind(mainMod .. " + SHIFT + T", noctalia("theme-mode-toggle")) -- sway: $mod+Shift+t

-- ### Notifications ########################################################
-- Di sway ini swaync. Di Hyprland notif dipegang noctalia:
--   close-latest  -> gak ada padanan per-notif, dipakai clear-active (semua popup aktif)
--   close-all     -> clear-active + clear-history
--   toggle-panel  -> control-center (tempat notif numpuk di noctalia)
--   toggle-dnd    -> notification-dnd-toggle
hl.bind(mainMod .. " + A", noctalia("notification-clear-active"))               -- sway: $mod+a
hl.bind(mainMod .. " + SHIFT + A",
  shell("noctalia msg notification-clear-active; noctalia msg notification-clear-history")) -- sway: $mod+Shift+a
hl.bind(mainMod .. " + N", noctalia("panel-toggle control-center"))             -- sway: $mod+n
hl.bind(mainMod .. " + SHIFT + N", noctalia("notification-dnd-toggle"))         -- sway: $mod+Shift+n

-- ### Scratchpad ###########################################################
-- sway scratchpad -> special workspace "magic" di Hyprland
hl.bind(mainMod .. " + SHIFT + minus", hl.dsp.window.move({ workspace = "special:magic" })) -- sway: move scratchpad
hl.bind(mainMod .. " + minus", hl.dsp.workspace.toggle_special("magic"))                    -- sway: scratchpad show

-- ### Workspaces ###########################################################
-- Pindah workspace lewat wsstrip (animasi zoom kartu); kalau daemon mati, jatuh ke dispatch biasa.
local function ws_go(target)
  local home = os.getenv("HOME")
  local arg = type(target) == "number" and tostring(target) or target
  local native = type(target) == "number" and tostring(target) or '"' .. target .. '"'
  return hl.dsp.exec_cmd(home .. '/.local/bin/wsstrip-send "go ' .. arg .. '" || hyprctl eval \'hl.dispatch(hl.dsp.focus({ workspace = ' .. native .. ' }))\'')
end
-- sway: $mod+1..0 workspace, $mod+Shift+1..0 & $mod+Mod1+1..0 move container
for i = 1, 10 do
  local key = tostring(i % 10)
  hl.bind(mainMod .. " + " .. key, ws_go(i))
  hl.bind(mainMod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = i }))
  hl.bind(mainMod .. " + ALT + " .. key, hl.dsp.window.move({ workspace = i }))
end

-- ### Workspace navigation #################################################
-- "e+1"/"e-1" = workspace yang beneran ada (padanan `workspace next/prev` sway)
hl.bind(mainMod .. " + CTRL + Right", ws_go("e+1"))      -- sway: $mod+Control+Right
hl.bind(mainMod .. " + CTRL + Left", ws_go("e-1"))       -- sway: $mod+Control+Left
hl.bind(mainMod .. " + CTRL + Down", hl.dsp.focus({ workspace = "empty" }))     -- sway: empty-workspace.sh
hl.bind(mainMod .. " + CTRL + ALT + Right", hl.dsp.window.move({ workspace = "e+1" })) -- sway: $mod+Control+Mod1+Right
hl.bind(mainMod .. " + CTRL + ALT + Left", hl.dsp.window.move({ workspace = "e-1" }))  -- sway: $mod+Control+Mod1+Left
hl.bind(mainMod .. " + mouse_down", ws_go("e+1"))        -- sway: $mod+button4 workspace next
hl.bind(mainMod .. " + mouse_up", ws_go("e-1"))          -- sway: $mod+button5 workspace prev

-- ### Media keys ###########################################################
-- sway: pactl/brightnessctl + slider waybar. Di hypr: noctalia (udah ada OSD-nya),
-- fallback ke pactl/brightnessctl kalau daemon noctalia mati.
hl.bind("XF86AudioMute", noctalia("volume-mute", "pactl set-sink-mute @DEFAULT_SINK@ toggle"), { locked = true })
hl.bind("XF86AudioLowerVolume", noctalia("volume-down", "pactl set-sink-volume @DEFAULT_SINK@ -5%"), { repeating = true, locked = true })
hl.bind("XF86AudioRaiseVolume", noctalia("volume-up", "pactl set-sink-volume @DEFAULT_SINK@ +5%"), { repeating = true, locked = true })
hl.bind("XF86AudioMicMute", noctalia("mic-mute", "pactl set-source-mute @DEFAULT_SOURCE@ toggle"), { locked = true })
hl.bind("XF86AudioPlay", noctalia("media toggle", "playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPause", noctalia("media toggle", "playerctl play-pause"), { locked = true })
hl.bind("XF86AudioNext", noctalia("media next", "playerctl next"), { locked = true })
hl.bind("XF86AudioPrev", noctalia("media previous", "playerctl previous"), { locked = true })
hl.bind("XF86AudioStop", noctalia("media stop", "playerctl stop"), { locked = true })
hl.bind("XF86MonBrightnessDown", noctalia("brightness-down", "brightnessctl set 5%-"), { repeating = true, locked = true })
hl.bind("XF86MonBrightnessUp", noctalia("brightness-up", "brightnessctl set 5%+"), { repeating = true, locked = true })

-- ### Ekstra khusus Hyprland (kombo ini gak dipakai di sway) ################
hl.bind("XF86PowerOff", hl.dsp.exec_cmd("@HOME@/.local/bin/lock"), { locked = true })
hl.bind(mainMod .. " + BackSpace", hl.dsp.workspace.toggle_special("magic"))    -- scratchpad alt
hl.bind(mainMod .. " + slash", shell(keyhudSend .. " cheatsheet || " .. hyprScripts .. "/cheatsheet.sh")) -- daftar keybind (keyhud, fallback kitty)
hl.bind(mainMod .. " + SHIFT + slash", shell(keyhudSend .. " toggle-osd"))       -- HUD keybind on/off
hl.bind(mainMod .. " + G", shell(os.getenv("HOME") .. "/.local/bin/spotlight-send launchpad")) -- Launchpad: grid semua aplikasi
hl.bind(mainMod .. " + Tab", shell(os.getenv("HOME") .. "/.local/bin/wsstrip-send toggle")) -- strip workspace kiri ala Spaces (wsstrip)
hl.bind(mainMod .. " + SHIFT + Tab", shell(os.getenv("HOME") .. "/.local/bin/wsstrip-send anim")) -- ganti gaya animasi strip workspace
hl.bind(mainMod .. " + CTRL + Tab", shell(os.getenv("HOME") .. "/.local/bin/wsstrip-send pin")) -- pin/lepas strip workspace (makan ruang desktop)

-- keyhud: tulis registry lalu kembalikan hl.bind asli
hl.bind = rawBind
local keyhudFile = io.open((os.getenv("XDG_RUNTIME_DIR") or "/tmp") .. "/keyhud-binds.tsv", "w")
if keyhudFile then
  for i, v in ipairs(keyhudList) do keyhudFile:write(i .. "\t" .. v .. "\n") end
  keyhudFile:close()
end

-- Lid: backlight eDP-1 mati saat ditutup dengan eksternal terpasang (output tetap ada, lihat monitors.lua)
local lidScript = os.getenv("HOME") .. "/.config/hypr/scripts/lid.sh"
rawBind("switch:on:Lid Switch", hl.dsp.exec_cmd(lidScript .. " close"), { locked = true })
rawBind("switch:off:Lid Switch", hl.dsp.exec_cmd(lidScript .. " open"), { locked = true })

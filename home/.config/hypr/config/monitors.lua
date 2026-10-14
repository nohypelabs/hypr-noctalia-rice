-- Monitor wiki https://wiki.hypr.land/Configuring/Basics/Monitors/
-- Mode layar (Win+P) dibaca dari state file yang ditulis scripts/display-mode.sh:
--   duplicate | extend | external-only | internal-only
-- Semua port eksternal (HDMI/DP/USB-C) dapat rule yang sama, jadi proyektor di
-- port mana pun ikut mode yang dipilih.

local INTERNAL = "eDP-1"
local STATE_FILE = os.getenv("HOME") .. "/.local/state/hyprland/display-mode"

local function read_mode()
    local file = io.open(STATE_FILE, "r")
    if not file then return "external-only" end
    local line = file:read("*l")
    file:close()
    local mode = line and line:match("^%s*(.-)%s*$") or ""
    if mode == "dual" then mode = "extend" end -- state lama
    if mode == "" then mode = "external-only" end
    return mode
end

-- Konektor eksternal dari sysfs: { name = "HDMI-A-1", connected = true }
local function external_ports()
    local ports = {}
    local ls = io.popen("ls /sys/class/drm 2>/dev/null")
    if not ls then return ports end
    for entry in ls:lines() do
        local name = entry:match("^card%d+%-(.+)$")
        if name and (name:match("^HDMI") or name:match("^DP")) then
            local f = io.open("/sys/class/drm/" .. entry .. "/status", "r")
            local status = f and f:read("*l") or ""
            if f then f:close() end
            ports[#ports + 1] = { name = name, connected = (status == "connected") }
        end
    end
    ls:close()
    return ports
end

local function connected_signature(ports)
    local names = {}
    for _, p in ipairs(ports) do
        if p.connected then names[#names + 1] = p.name end
    end
    return table.concat(names, ",")
end

local mode = read_mode()
local ports = external_ports()
local any_external = connected_signature(ports) ~= ""

hl.monitor({
    output   = INTERNAL,
    mode     = "preferred",
    position = "0x0",
    scale    = 1.0,
    -- Tanpa layar eksternal, laptop jangan pernah dimatikan (layar hitam).
    -- Rule port eksternal tetap ikut mode, supaya saat dicolok lagi langsung nyala.
    disabled = (mode == "external-only" and any_external),
})

-- Monitor yang mode "preferred"-nya bukan refresh tertinggi. Rule desc: menang
-- atas rule nama port, jadi dipasang per port dengan mode/posisi yang sama.
-- Legion 34W-2c via HDMI: mode bawaan maks 120Hz, padahal range EDID 48-240Hz.
-- Pakai modeline reduced blanking biar muat batas HDMI 2.0 laptop (~600 MHz):
--   2560x1080@180 = 556 MHz (dipakai), 1920x1080@240 = 576 MHz
--   ("modeline 576.48 1920 1928 1960 2000 1080 1083 1091 1201 +hsync -vsync").
--   3440x1440@144 (~740 MHz) ditolak driver, jatuh ke 100Hz.
local MODE_OVERRIDES = {
    ["desc:Lenovo Group Limited Legion 34W-2c"] = "modeline 555.98 2560 2568 2600 2640 1080 1083 1091 1170 +hsync -vsync",
}

for _, p in ipairs(ports) do
    local spec = { output = p.name, mode = "preferred", scale = "auto" }
    if mode == "duplicate" then
        spec.position = "auto"
        spec.mirror = INTERNAL
    elseif mode == "extend" then
        spec.position = "auto-right"
    elseif mode == "internal-only" then
        spec.disabled = true
    else -- external-only
        spec.position = "0x0"
    end
    hl.monitor(spec)
    if p.connected then
        for desc, m in pairs(MODE_OVERRIDES) do
            local o = {}
            for k, v in pairs(spec) do o[k] = v end
            o.output, o.mode = desc, m
            hl.monitor(o)
        end
    end
end

-- Hotplug: kalau set port yang terhubung berubah (colok/cabut proyektor),
-- reload supaya rule di atas dihitung ulang (mis. laptop nyala lagi saat HDMI
-- dicabut di mode external-only). Disable/enable dari reload sendiri tidak
-- mengubah sysfs, jadi tidak loop.
local signature_at_load = connected_signature(ports)
local function on_hotplug()
    if connected_signature(external_ports()) ~= signature_at_load then
        hl.exec_cmd("hyprctl reload")
    end
end
hl.on("monitor.added", on_hotplug)
hl.on("monitor.removed", on_hotplug)

-- Input configuration

hl.config({
    input = {
        -- sensitivity = -0.25,
        accel_profile = "flat",
    },
    -- swipe workspace 4 jari lebih sensitif (default 300 / 0.5 / 30):
    -- jarak tarik penuh 140px, cukup lewat 24% buat pindah, kibasan cepat langsung pindah
    gestures = {
        workspace_swipe_distance = 140,
        workspace_swipe_cancel_ratio = 0.24,
        workspace_swipe_min_speed_to_force = 14,
    },
    -- Uncomment the section below to enable software cursors; this can help with cursor display or behavior issues
    -- cursor = {
    --     no_hardware_cursors = 1,
    -- },
})

hl.gesture({ fingers = 4, direction = "vertical",   action = "workspace" }) -- vertikal, searah animasi slidevert
hl.gesture({ fingers = 3, direction = "down",       action = "close" })
hl.gesture({ fingers = 3, direction = "up",         action = "fullscreen" })
hl.gesture({ fingers = 3, direction = "left",       action = "float" })

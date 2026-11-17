-- Look and feel configuration

hl.config({
    general = {
        gaps_in = 5,
        gaps_out = 10,
        border_size = 1,
        extend_border_grab_area = 10,
        resize_on_border = true,
        col = {
            -- Garis putih tipis, sama dengan bingkai strip workspace (wsstrip: 1px rgba(255,255,255,0.12))
            active_border = "rgba(ffffff1f)",
            inactive_border = "rgba(ffffff1f)",
        },
    },
    group = {
        col = {
            border_active = CACHYLBLUE,
            border_inactive = CACHYGRAY,
            border_locked_active = CACHYDBLUE,
            border_locked_inactive = CACHYGRAY,
        },
        groupbar = {
            col = {
                active = CACHYLGREEN,
                inactive = CACHYGRAY,
                locked_active = CACHYDBLUE,
                locked_inactive = CACHYGRAY,
            },
        },
    },
    decoration = {
        dim_special = 0.3,
        -- Sudut 14px lingkaran biasa (power 2), sama dengan bingkai strip workspace ter-pin (wsstrip .strip.pinned)
        rounding = 14,
        rounding_power = 2.0,
        active_opacity = 0.96,
        inactive_opacity = 0.90,
        fullscreen_opacity = 1,
        shadow = {
            enabled = true,
            range = 32,
            render_power = 3,
            offset = "0 8",
            color = "rgba(00000070)",
            color_inactive = "rgba(00000038)",
        },
        blur = {
            enabled = true,
            size = 8,
            passes = 3,
            noise = 0.02,
            contrast = 1.0,
            brightness = 0.9,
            vibrancy = 0.25,
            vibrancy_darkness = 0.2,
            popups = true,
            special = true,
        },
    },
})

-- Look and feel configuration

hl.config({
    general = {
        gaps_in = 5,
        gaps_out = 10,
        border_size = 1,
        extend_border_grab_area = 10,
        resize_on_border = true,
        col = {
            -- Garis tipis ala macOS: putih transparan, bukan gradasi hijau
            active_border = "rgba(ffffff40)",
            inactive_border = "rgba(ffffff14)",
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
        -- Sudut "squircle" (continuous corner) ala Apple
        rounding = 14,
        rounding_power = 3.0,
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

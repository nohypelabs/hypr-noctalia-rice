hl.config({
    dwindle = {
        preserve_split = true,
        -- Area dibelah kiri-kanan hanya kalau lebarnya > 1.5x tingginya; selain itu atas-bawah.
        -- Di monitor ultrawide, 2 window di separuh kanan jadi bertumpuk, bukan kolom sempit.
        split_width_multiplier = 1.5,
    },
    ecosystem = {
        no_update_news = true,
        no_donation_nag = true,
    },
    misc = {
        col = {
            splash = CACHYLGREEN,
        },
        middle_click_paste = false,
        enable_swallow = true,
        swallow_regex = "(kitty|rio|Rio|ghostty|[Kk]onsole|Alacritty|gnome-terminal|xfce[0-9]?-terminal)",
        vrr = 3,
        -- Kalau noctalia mati saat layar terkunci (mis. habis resume), noctalia baru boleh ambil alih kunci.
        allow_session_lock_restore = true,
    },
    render = {
        direct_scanout = 2,
        -- Use the option below if you find games constantly black screening for a couple seconds whenever direct scanout enables/disables
        -- non_shader_cm = 0,
    },
    xwayland = {
        force_zero_scaling = true
    },
})

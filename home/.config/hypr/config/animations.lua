-- Animasi ala iOS/macOS: pegas (spring) seperti UIKit/SwiftUI, see https://wiki.hypr.land/Configuring/Advanced-and-Cool/Animations/
-- Konversi parameter Apple: stiffness = (2π/response)², dampening = 4π·ratio/response (mass 1)

-- Beziers
hl.curve("easeOutQuint",   { type = "bezier", points = { {0.23, 1},    {0.32, 1}    } })
hl.curve("easeInOutCubic", { type = "bezier", points = { {0.65, 0.05}, {0.36, 1}    } })
hl.curve("linear",         { type = "bezier", points = { {0, 0},       {1, 1}       } })
hl.curve("almostLinear",   { type = "bezier", points = { {0.5, 0.5},   {0.75, 1}    } })
hl.curve("quick",          { type = "bezier", points = { {0.15, 0},    {0.1, 1}     } })
hl.curve("overshoot",      { type = "bezier", points = { {0.5, 0.9}, {0.1, 1.1}     } })
hl.curve("appleOut",       { type = "bezier", points = { {0.32, 0.72}, {0, 1}       } })

-- Springs
hl.curve("easy",           { type = "spring", mass = 1, stiffness = 500, dampening = 35 })
hl.curve("rubber",         { type = "spring", mass = 1, stiffness = 200, dampening = 15 })
hl.curve("appleBouncy",    { type = "spring", mass = 1, stiffness = 200, dampening = 20 }) -- response 0.45, ratio ~0.7: buka app, sedikit mantul
hl.curve("appleSmooth",    { type = "spring", mass = 1, stiffness = 160, dampening = 21 }) -- response 0.5, ratio ~0.83: default UIKit
hl.curve("appleSnappy",    { type = "spring", mass = 1, stiffness = 320, dampening = 31 }) -- response 0.35, ratio ~0.86: geser/resize

-- Animations
hl.animation({ leaf = "global",              enabled = true, speed = 3,   bezier = "quick"                          })
hl.animation({ leaf = "windowsIn",           enabled = true, speed = 3,   spring = "appleBouncy", style = "popin 80%" })
hl.animation({ leaf = "windowsOut",          enabled = true, speed = 2.5, bezier = "appleOut",    style = "popin 88%" })
hl.animation({ leaf = "windowsMove",         enabled = true, speed = 3,   spring = "appleSnappy"                    })
hl.animation({ leaf = "fadeIn",              enabled = true, speed = 2.5, bezier = "appleOut"                       })
hl.animation({ leaf = "fadeOut",             enabled = true, speed = 2,   bezier = "appleOut"                       })
hl.animation({ leaf = "fadeSwitch",          enabled = true, speed = 3,   bezier = "appleOut"                       })
hl.animation({ leaf = "border",              enabled = true, speed = 4,   bezier = "appleOut"                       })
hl.animation({ leaf = "workspaces",          enabled = true, speed = 4,   spring = "appleSmooth", style = "slidevert" }) -- vertikal, searah strip workspace (wsstrip)
-- Dipanggil wsstrip (hyprctl eval) saat klik kartu: pindah workspace instan di balik animasi zoom kartu.
function rice_ws_anim(on)
  hl.animation({ leaf = "workspaces", enabled = on, speed = 4, spring = "appleSmooth", style = "slidevert" })
end
hl.animation({ leaf = "specialWorkspaceIn",  enabled = true, speed = 3,   spring = "appleBouncy", style = "slidevert" })
hl.animation({ leaf = "specialWorkspaceOut", enabled = true, speed = 2.5, bezier = "appleOut",    style = "slidevert" })

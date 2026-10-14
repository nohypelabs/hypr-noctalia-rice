--!nonstrict
-- Tombol kaca pembesar di bar: buka launcher Spotlight (daemon ~/.local/lib/spotlight).
-- Kalau daemon gak jalan, jatuh ke launcher bawaan noctalia.

local CMD = "sh -c '$HOME/.local/bin/spotlight-send toggle || noctalia msg panel-toggle launcher'"

barWidget.setGlyph("search")
barWidget.setText("")
barWidget.setTooltip("Spotlight (Super+Space)")

function onClick()
  noctalia.runAsync(CMD)
end

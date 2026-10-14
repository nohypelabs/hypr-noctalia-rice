--!nonstrict
-- Nama aplikasi aktif ala menu bar macOS. wsstrip menulis nama .desktop aplikasi yang
-- difokus ke $XDG_RUNTIME_DIR/rice-active-app tiap event activewindow Hyprland;
-- di sini cukup dibaca berkala (file kecil di tmpfs, murah).

local runtime = noctalia.getenv("XDG_RUNTIME_DIR") or ""
local PATH = runtime .. "/rice-active-app"
local last = nil

noctalia.setUpdateInterval(250)

local function render()
  local name = noctalia.readFile(PATH) or ""
  name = string.gsub(name, "%s+$", "")
  if name == last then return end
  last = name
  barWidget.setVisible(name ~= "")
  barWidget.setText(name)
  barWidget.setTooltip(name)
end

function update()
  render()
end

render()

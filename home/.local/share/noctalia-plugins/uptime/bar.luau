--!nonstrict
-- Uptime laptop di bar: teks ringkas (2j 17m / 1h 3j), detail lengkap di tooltip.

noctalia.setUpdateInterval(30000)

local function uptimeSeconds(): number
  local raw = noctalia.readFile("/proc/uptime") or ""
  return tonumber(string.match(raw, "^(%d+)")) or 0
end

local function render()
  local s = uptimeSeconds()
  local d = s // 86400
  local h = (s % 86400) // 3600
  local m = (s % 3600) // 60

  local short
  if d > 0 then
    short = string.format("%dh %dj", d, h)
  elseif h > 0 then
    short = string.format("%dj %dm", h, m)
  else
    short = string.format("%dm", m)
  end

  local parts = {}
  if d > 0 then table.insert(parts, d .. " hari") end
  if h > 0 then table.insert(parts, h .. " jam") end
  table.insert(parts, m .. " menit")

  barWidget.setGlyph("clock-up")
  barWidget.setText(barWidget.isVertical() and "" or short)
  barWidget.setTooltip("Nyala selama " .. table.concat(parts, " "))
end

function update()
  render()
end

render()

-- Simple Hammerspoon HTTP alert server for SafeFamily
local server = hs.httpserver.new()
server:setPort(9181)

local function centerAlert(message)
  local screen = hs.screen.mainScreen()
  local frame = screen:frame()
  hs.alert.closeAll(0)
  hs.alert.show(
    message,
    {
      atScreenEdge = 2, -- center
      strokeWidth = 8,
      strokeColor = { white = 1, alpha = 0.9 },
      fillColor = { red = 0.1, green = 0.12, blue = 0.15, alpha = 0.92 },
      textColor = { white = 1, alpha = 1 },
      textSize = 26,
      radius = 12,
      fadeInDuration = 0.12,
      fadeOutDuration = 0.2
    },
    screen,
    4
  )
end

server:setCallback(function(method, path, headers, body)
  if method ~= "POST" then
    return "Only POST allowed", 405, { ["Content-Type"] = "text/plain" }
  end

  if path == "/alert" then
    local msg = "Task feedback needed"
    if body and #body > 0 then
      local ok, decoded = pcall(hs.json.decode, body)
      if ok and decoded and decoded.message then
        msg = decoded.message
      end
    end
    centerAlert(msg)
    return "OK", 200, { ["Content-Type"] = "text/plain" }
  end

  return "Not found", 404, { ["Content-Type"] = "text/plain" }
end)

server:start()

-- testing
-- curl -X POST http://localhost:9181/alert \
--   -H "Content-Type: application/json" \
--   -d '{"message":"Task feedback needed: 19:00-19:30 - Math"}'

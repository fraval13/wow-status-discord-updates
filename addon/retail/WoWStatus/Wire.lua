-- Common transport behavior for addon-message queues.
WoWStatusWire = {}
local W, S = WoWStatusWire, WoWStatusSafe

-- Classifies a pcall of a send: "sent"; "throttled" (the game asks to wait, so
-- retry later); "uncertain" (an older client's false, which can also mean
-- throttled); "offline" (the target logged off); or "failed". SendAddonMessage
-- returns an Enum.SendAddonMessageResult on newer clients and a boolean on older
-- ones; the deprecated global wrapper returns the code second, so the last value
-- that is not nil counts.
local RESULT = {Success = 0, AddonMessageThrottle = 3, ChannelThrottle = 8, AddOnMessageLockdown = 11, TargetOffline = 12}
function W.sendResult(ok, ...)
    if not ok then return "failed" end
    local result
    for i = select("#", ...), 1, -1 do
        local value = select(i, ...)
        if value ~= nil then result = S.value(value); break end
    end
    if type(result) ~= "number" then return result == false and "uncertain" or "sent" end
    local codes = type(Enum) == "table" and type(Enum.SendAddonMessageResult) == "table" and Enum.SendAddonMessageResult or {}
    local function is(name) return result == (codes[name] or RESULT[name]) end
    if is("Success") then return "sent" end
    if is("AddonMessageThrottle") or is("ChannelThrottle") or is("AddOnMessageLockdown") then return "throttled" end
    return is("TargetOffline") and "offline" or "failed"
end
-- Seconds to wait before sending item again after result, or nil to move on.
-- A throttle is always retried, after 2, 4, 8, then every 16 s while throttles
-- on the queue's prefix (counted in state) continue. An older client's false is
-- retried once, after 2 s, without counting as a throttle. If that retry says
-- false too, false is final on this queue for the next minute, so a client that
-- always says false is barely slowed down, and one whose false is a long
-- throttle still gets retries again after that.
function W.retryWait(result, item, state, now)
    if result == "throttled" then
        state.throttles = (state.throttles or 0) + 1
        return math.min(2 ^ state.throttles, 16)
    end
    if result == "uncertain" then
        if not item.unsure and now >= (state.falseFinalUntil or 0) then item.unsure = true; return 2 end
        if item.unsure then state.falseFinalUntil = now + 60 end
    end
    item.unsure, state.throttles = nil, 0
    return nil
end

-- Send one item with the caller's pacing state. A wait keeps its destination
-- at the head of the caller's queue, so a retry never advances the cursor.
function W.attempt(send, item, state, now, ...)
    local result = W.sendResult(pcall(send, ...))
    return result, W.retryWait(result, item, state, now)
end

-- Loaded before modules so they can register in TOC order. Register one
-- definition per module, with optional init(db, character) and slash handlers.
-- A slash handler receives (arguments, command, character, say). The enabled
-- table can hide individual commands behind a feature flag.
WoWStatus = {}
local modules, names, commands = {}, {}, {}

function WoWStatus.register(module)
    assert(type(module.name) == "string" and not names[module.name], "Duplicate or missing module name")
    for command, handler in pairs(module.slash or {}) do
        assert(type(command) == "string" and command:match("^[%w_%-]+$")
            and command ~= "help" and type(handler) == "function" and not commands[command],
            "Invalid or duplicate slash command: " .. tostring(command))
    end
    for command, handler in pairs(module.slash or {}) do
        commands[command] = {handler = handler, enabled = module.enabled and module.enabled[command]}
    end
    names[module.name] = true
    modules[#modules + 1] = module
end

function WoWStatus.initializeModules(db, character)
    for _, module in ipairs(modules) do
        if module.init then module.init(db, character) end
    end
end

local function available(entry)
    return entry and (not entry.enabled or entry.enabled())
end

function WoWStatus.runCommand(command, rest, character, say)
    local entry = commands[command]
    if not available(entry) then return false end
    entry.handler(rest, command, character, say)
    return true
end

function WoWStatus.commands()
    local result = {"help"}
    for command, entry in pairs(commands) do
        if available(entry) then result[#result + 1] = command end
    end
    table.sort(result)
    return result
end

"""'No player named ...' replies to the addon's own whispers are hidden (live Forever report)."""
from test_addon import make_lua


def test_not_found_lines_are_hidden_only_for_names_the_addon_just_whispered():
    lua = make_lua()
    lua.execute('''
        ERR_CHAT_PLAYER_NOT_FOUND_S = "No player named '%s' is currently playing."
        local group = "x"
        WoWStatusPopups.whispered("Edith Aateigen-CAMWOWEU5Realm1PvE")
        assert(WoWStatusPopups.filterNotFound("No player named 'Edith Aateigen' is currently playing."))
        assert(WoWStatusPopups.filterNotFound("No player named 'edith aateigen' is currently playing."))
        -- Someone the addon did not whisper: the line stays.
        assert(not WoWStatusPopups.filterNotFound("No player named 'Bob' is currently playing."))
        assert(not WoWStatusPopups.filterNotFound("Some other system message"))
        -- Only for a few seconds after the whisper.
        local now = time()
        function time() return now + 11 end
        assert(not WoWStatusPopups.filterNotFound("No player named 'Edith Aateigen' is currently playing."))
    ''')


def test_every_addon_whisper_is_recorded():
    lua = make_lua()
    lua.execute('''
        ERR_CHAT_PLAYER_NOT_FOUND_S = "No player named '%s' is currently playing."
        WoWStatusGroups.update("dawnwatch","")
        local group = next(character().group_ids)
        __channelNames = {WoWStatusGroups.channel(group)}
        fire("PLAYER_LEVEL_UP", 3)
        for _ = 1, 5 do WoWStatusPopups.tick() end
        local target
        for _, p in ipairs(__sent) do if p.kind == "WHISPER" then target = p.target end end
        assert(target, "an update was whispered")
        assert(WoWStatusPopups.filterNotFound("No player named '" .. target:match("^[^-]+") .. "' is currently playing."))
    ''')

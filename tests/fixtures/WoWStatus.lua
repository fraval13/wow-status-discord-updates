-- Synthetic input for home testing, not exported from a real account.
WoWStatusDB = {
    ["version"] = 1,
    ["characters"] = {
        ["classic-era:Test Realm:Player-123-0001"] = {
            ["enrolled"] = true,
            ["identity"] = {guid="Player-123-0001", name="Thora", realm="Test Realm", client="classic-era"},
            ["settings"] = {
                enabled=true, introduction_confirmed=true,
                fields={level=true, class=true, race=true, zone=false},
                announcements={introduction=true, level=true},
                loot_quality=4, level_interval=10,
            },
            ["snapshot"] = {level=10, class="Warrior", race="Dwarf", zone="PRIVATE"},
            ["exported_at"] = 1793000000,
            ["events"] = {
                {id="intro", kind="introduction", at=1793000000, data={}},
                {id="level-10", kind="level", at=1793000000, data={level=10}},
            },
        },
    },
}

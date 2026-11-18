# Contributing a display language

WoW Status currently ships English and Nynorsk. The registry accepts additional
banks, including partial ones. This guide describes the infrastructure; it does
not promise a new translation or change the repository's licensing terms. The
licence and contribution-guide work is tracked separately in #196 and #197.

Copy the structure below into `addon/shared/LocaleDE.lua` (the short example is
illustrative, not a translation shipped by the addon):

```lua
local W = WoWStatusLocale
W.register("de", "Deutsch", {"deDE"}, {
    ["Activity"] = "Aktivität",
    ["Close"] = "Schließen",
}, {
    {"^Reached level (%d+)!$", "Stufe %1 erreicht!"},
})
```

The arguments are the command code, native display name, matching WoW client
locales, exact English-to-translated strings, and ordered Lua pattern/replacement
pairs. The final optional argument is a native action label for a two-language
switch. Language codes use lowercase ASCII letters/digits and start with a
letter. Codes and client aliases must be unique. Register each bank once; use
`W.extend("de", moreExact, morePatterns)` to split a long bank into sections.

English source strings are keys. Preserve format placeholders, such as `%d` and
`%.1f`, and Lua captures such as `%1`. A pattern can use a replacement function
for sentences that need it; it must only format the display value. Do not send
messages, change saved data, use locale-dependent Lua character classes, or alter
names supplied by players. Missing and empty exact translations fall back to the
English source; captions remain in their separate English/Nynorsk banks.

Put the new file in each edition's TOC immediately after `LocaleNN.lua`, before
any page consumes translations. Stage the shared file and TOCs, then run
`python scripts/sync_addons.py` and stage the mirrored copies. A new bank needs no
edit to `Locale.lua`, the settings chooser or the slash-command router. The
existing test clients still have explicit load lists until #232 merges: add the
file there too while that is the case.

Only brand-new accounts choose an available bank from `GetLocale()`. Existing
accounts keep their choice, including the old implicit English choice. English
is the fallback when a client bank is unavailable. The existing account-wide
`language` value is reused; choosing English still clears it, so no saved shape
or migration is needed. `/wstatus language <code>` and Notifications → Language
override the choice. Reload to update labels in windows already built.

Run the key report with the development environment:

```sh
python scripts/check_locales.py
python scripts/check_locales.py --edition forever
python -m pytest -q tests/test_locale.py tests/test_locale_registry.py
python -m pytest -q --lua=5.1
```

The report lists uncovered literal English keys for every registered bank,
including those found through common page helpers, and accepts partial banks.
`--strict` makes any uncovered key fail the command. An explicit identity entry
counts as covered when a proper name or symbol is intentionally the same. The
report does not prove coverage of sentences assembled dynamically; review them
and pattern grammar in the game. The existing Nynorsk completeness test remains
in place. Full default and Lua 5.1 suites, all four editions and a live controller
check are part of the handoff; mocks cannot establish font coverage or rendering.

Only displayed text changes. Event types, packet content, IDs and shared facts
remain English. Translate interface text here; keep caption personalities,
reaction voices and homepage translation in their own workflows.

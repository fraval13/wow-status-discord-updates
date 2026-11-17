# Adding a display language

WoW Status shows its windows in English by default, with Nynorsk as the one
extra language that ships. The locale layer is a registry, so a new language is
**one new file and one line in each TOC** — `addon/shared/Locale.lua` never needs
changing (issue #154).

Only the display side is translated. What players send each other stays English
and is translated when it is shown, so friends on different languages keep
working together. Captions (`docs/notification-flavour-text.md` and the
personalities) are a separate, much larger job and are not part of this.

## The file

Copy `addon/shared/LocaleNN.lua` as a shape to follow and name the new file after
the language, for example `addon/shared/LocaleDE.lua`:

```lua
-- German texts for WoWStatusLocale (English text -> German). Display only.
local W = WoWStatusLocale
local add = W.language("deDE", "Deutsch", "Auf Deutsch umstellen")

add({
    ["Close"] = "Schließen",
    ["Reactions"] = "Reaktionen",
})
```

`W.language(code, name, switchLabel)` registers the bank and returns the `add`
for it. Call `add` as often as you like; each call takes an exact table and an
optional list of `{pattern, replacement}` rules, tried in order when no exact
text matches.

- **`code`** should be the WoW client locale the bank belongs to: `deDE`,
  `frFR`, `esES`, `esMX`, `itIT`, `ptBR`, `ruRU`, `koKR`, `zhCN`, `zhTW`. A
  player on that client then gets the language without choosing it. (`nn` is the
  exception: WoW has no Norwegian client, so Nynorsk is only ever chosen by hand.)
- **`name`** is the language's own name for itself, shown in Options.
- **`switchLabel`** is the Options button's text, written in the language it
  switches *to*, so each reader can find it.

## Wiring it in

1. `git add` the new file, then run `python scripts/sync_addons.py` to mirror it
   into all four editions.
2. Add its file name to each `addon/*/WoWStatus/WoWStatus.toc`, right after
   `LocaleNN.lua`.
3. Add it to the two test load lists: `run_addon_file(...)` in
   `tests/test_addon.py` and the file list in `tests/test_forever.py`.
4. Add the code to the list in
   `tests/test_locale.py::test_every_language_bank_covers_the_texts_the_windows_show`.
   That test collects every English text the windows show and fails with the
   ones the bank still lacks, so it doubles as the to-do list.

## What a partial translation does

Nothing breaks. `WoWStatusLocale.T` falls back **per string**: a text the bank
has is shown translated, and one it lacks is shown in English. A bank with ten
lines in it is already useful, and the coverage test above says what is left.

## Things to keep in mind

- Text that goes over the wire is never translated. Only what a window, a chat
  line or the log *shows* passes through `T()`.
- Keep Lua pattern classes out of translated texts. `%s` and `%c` follow the C
  library's locale and misread Norwegian and German letters (issue #23); build
  such a line by concatenation instead, as `WhenWePlay.lua` does.
- Labels built once need a `/reload` to change; lists and notifications follow
  immediately.
- The homepage has its own copy deck and is not translated from these files.

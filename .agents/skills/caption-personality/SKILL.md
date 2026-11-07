---
name: caption-personality
description: Add or extend a WoW Status caption personality (the selectable voice of the flavour line under notifications and of the reaction whispers). Use when asked to add a new personality, write more captions, class death roasts or reaction whispers for one, or fix a personality's English or Nynorsk lines.
---

# Caption personality

A **personality** is one voice for the flavour captions (13 category files of
English/Nynorsk **pairs** in `docs/caption-personalities/<id>/`) and for reaction
whispers (18 files in `<id>/reactions/`), generated into
`addon/shared/Flavour<Name>.lua`. Format, counts and selection rules live in
`docs/caption-personalities/README.md`; read it first. Classic
(`Flavour.lua`, `docs/notification-flavour-text.md`) is a separate bank and stays
untouched here.

## Adding a personality

1. **Name it.** Pick a short lowercase `id`, an English name and a Nynorsk name.
   Add `Personality(id, name, nn_name, 'Flavour<Name>.lua')` to `PERSONALITIES`
   in `scripts/build_personalities.py` (its position there is its menu position).
2. **Write the captions and reactions.** Follow [`writing-brief.md`](writing-brief.md)
   for every category file, and its "Reactions" section for the 18 reaction files. Done when `python scripts/build_personalities.py --check --only <id>`
   reports only that the Lua file is stale (it is generated in the next step).
3. **Generate.** `python scripts/build_personalities.py`, then `git add` the new
   JSON and Lua and run `python scripts/sync_addons.py` (it copies only tracked
   files into the four editions).
4. **Load it.** Add `Flavour<Name>.lua` to each edition's `WoWStatus.toc` after
   the other `Flavour*.lua` personality files, in `PERSONALITIES` order, and to
   `PERSONALITY_FILES` in `tests/test_addon.py` in the same order. Raise the
   personality count in `tests/test_personalities.py` (`#P.order`, `#P.voices()`, the
   number of clicks that cycles back to Random, and the voice count in the Random test)
   and in `tests/test_reaction_voices.py` (`#voices` and the clicks back to Random).
5. **Document it.** Add a row to the table in `docs/caption-personalities/README.md`,
   name it in the README "Caption personalities" section, and add a player-facing
   note under `## Unreleased` in `CHANGELOG.md` (one line, at most 120 characters).
6. **Verify.** Run the checks in `AGENTS.md` ("Editing and validation"), including
   `pytest -q --lua=5.1`. Done when `tests/test_personalities.py`, `test_reaction_voices.py`,
   `test_reactions.py`, `test_flavour.py`,
   `test_locale.py` and `test_sync_addons.py` pass.

## Extending or fixing an existing personality

Edit its JSON (keep each `nn` line paired with its `en` line, and the counts in
the README), then run steps 3 and 6. Captions already saved in players' logs keep
their wording by position, so rewrite a line in place rather than reordering or
deleting lines.

# Contributing to WoW Status

Thank you for looking. WoW Status is a World of Warcraft addon that shares a
group of friends' progress between their game clients, plus the static homepage
and a preserved Python companion. This file is for anyone who wants to report
something or send a change. [`AGENTS.md`](AGENTS.md) is the deeper reference —
it is written for coding agents and carries the full rules for releases and
deployment — and it stays the authority wherever the two disagree.

## Reporting something

- **A bug in the addon**: open an issue with the *Bug report* form. If WoW Status
  itself raised a Lua error, `/wstatus errors` (or **Options → Diagnostics**)
  collects a report you can paste in: version, edition, client build, the page
  that was open and the error with its stack. Group and character names are
  replaced by `<group>` and `<name>` before you see it, so it is safe to post.
- **An idea**: the *Feature request* form. Say what you want to happen in the
  game rather than how to build it.
- **A question about using the addon**: the CurseForge page's comments are a
  better place than an issue.
- **A security problem**: do not open an issue. See
  [`SECURITY.md`](SECURITY.md).

A group ID is a shared secret. Never paste a real one into an issue, a pull
request, a log or a screenshot.

## Getting set up

```sh
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

The addon itself needs no build step: the Lua is loaded by the game, and the
tests run it in an embedded Lua runtime.

## Running the checks

```sh
.venv/bin/python -m pytest -q          # the whole suite
.venv/bin/python -m pytest -q --lua=5.1  # again, on the Lua the game runs
.venv/bin/ruff check src tests scripts
node --check website/app.js
node --check website/flavour.js
git diff --check
```

The second run matters: the test runtime's default Lua is newer than the game's,
and every WoW client runs Lua 5.1. CI runs both, on Linux and Windows.

Pass text encodings explicitly in Python (`read_text(encoding='utf-8')` and
friends). Windows otherwise decodes as cp1252, and CI turns that into an error.

## Working on the addon

- **Shared Lua lives in `addon/shared/`.** The four editions —
  `addon/{vanilla,forever,tbc,retail}/WoWStatus/` — are self-contained copies
  with their own adapters and TOCs. Edit the shared file, `git add` it, then run
  `python scripts/sync_addons.py` to mirror it into all four. `--check` reports
  drift without writing, and CI runs it.
- **A new Lua file** needs a line in each of the four TOCs, before the files that
  use it, and an entry in the test load lists (`tests/test_addon.py`,
  `tests/test_forever.py`).
- **Lua 5.1 syntax only** in shared code, and keep the guards around APIs that
  are missing or restricted in some clients (`Safe.lua` is the boundary).
- **All four editions, every time.** A feature that only works on one is not
  finished.
- **Controller support is not optional.** Make every interactive element a
  `Button`, `CheckButton` or `EditBox` with an `OnClick` (or a mouse-enabled
  `Frame` with `OnMouseUp`), disable buttons that do nothing, put lists in a
  `ScrollFrame`, name a new window `WoWStatus<Name>` and add it to
  `UISpecialFrames` so B closes it. `Gamepad.lua` finds controls by walking
  visible frames, so a plain texture with a click handler is unreachable. Add a
  test that `WoWStatusGamepad.controls` reaches the new controls, and say in the
  pull request that live-pad checks are still the owner's.
- **New player-visible strings need Nynorsk** in `LocaleNN.lua`. The addon ships
  a complete translation; an untranslated string shows up as English in a
  Nynorsk client.
- **Captions** are generated. Edit the JSON under `docs/caption-personalities/`,
  run `python scripts/build_personalities.py`, then sync — never hand-edit a
  `Flavour<Name>.lua`.
- Do not modify player SavedVariables to test a release, and back up a local game
  installation's addon folder before replacing it.

## Pull requests

- **Do not change the version.** `project.version` in `pyproject.toml` and the
  four TOCs are bumped by the release pipeline on `main`, not in a feature
  branch. `python scripts/sync_version.py --check` must stay clean.
- **A player-facing change adds one note file** in `changelog.d/`, named after
  the issue (`222-labs-page.md`), holding one or more `- ` lines of plain text at
  most 120 characters. Do not edit `CHANGELOG.md` and do not run
  `scripts/whats_new.py` for a note: the release moves the files for you. See
  [`changelog.d/README.md`](changelog.d/README.md).
- **Say what you did not verify.** Rendering, game API availability, controller
  behaviour and cross-realm delivery need a live client, and the test suite cannot
  show them. An honest "not verified here" is worth more than a confident claim.
- Keep the diff to the change at hand. Several people and agents work in this
  repository at once, so a branch that also reformats a file is painful to merge.
- Commit messages are written in Nynorsk with a gentle, warm tone; see
  `.agents/skills/git-commit/`. English is fine in pull request descriptions.

## What not to commit

Secrets, tokens, exported player data, SavedVariables, SQLite files, private
deployment archives, and any real group name. Respect `.gitignore`.

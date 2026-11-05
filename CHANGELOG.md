# What's New

Player-facing release notes. The newest section is shown once in game after an
update (`/wstatus news` opens it again) and fills the homepage release panel.
`python scripts/whats_new.py` regenerates `addon/shared/WhatsNewData.lua` from this
file; run `python scripts/sync_addons.py` afterwards.

Rules: one `## <version>` heading per release, newest first, matching
`pyproject.toml` (the release pull request adds it). Each note is one `- ` line of
plain text, at most 120 characters, without `|` or markup. An optional
`## Unreleased` section collects notes for the next release and is not shipped.

## 0.14.12

- Retail and Forever minimap buttons sit in the right place
- Dungeon clears use the game's completion data correctly
- Clearer wording when you join a group
- Group warnings for invalid log data
- Removed group channels are left after /reload
- A death counts once when you release your spirit

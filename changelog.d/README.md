# Pending release notes

A pull request with a player-facing change adds **one new file** here instead of
editing `CHANGELOG.md`. Because every pull request writes its own file, parallel
pull requests never conflict over release notes.

- Name it after the issue or branch: `247-changelog-note-files.md` (lowercase
  letters, digits, `.`, `_` and `-`, ending in `.md`).
- Write one or more `- ` lines. Each is plain text, at most 120 characters,
  without `|` or markup such as backticks or `**`, and written for players.
  Blank lines are allowed; nothing else is.
- Do not touch `CHANGELOG.md` or any `WhatsNewData.lua`, and do not run
  `scripts/whats_new.py` for a note. Only a release with no note files at all
  falls back to the public commit title, so every player-facing change needs a
  note file of its own.

On each main push, `scripts/prepare_release.py` moves every note file here into a
new `## <version>` section of `CHANGELOG.md` (in issue-number order), regenerates
the What's New data and deletes the note files in the release commit.
`python scripts/whats_new.py --check` and `tests/test_whats_new.py` reject an
invalid note file in the pull request that adds it.

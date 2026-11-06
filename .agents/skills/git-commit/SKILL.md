---
name: git-commit
description: Write git commit messages for this repository in Nynorsk with a gentle Christian tone. Use whenever you create a commit (git commit, amend, squash or merge message), or when asked to draft or reword a commit message.
---

# Git commit messages: Nynorsk with a Christian touch

The owner wants every commit message written in **Nynorsk** and gently
**Christian** in tone: warm and good-humoured, like a kind note from the
bedehus. The message must still say exactly what changed. Faith flavours
the wording; it never replaces the facts.

## Subject line

- Nynorsk, imperative form, at most 72 characters, no full stop:
  `Legg til personlegdomen Dverg`, `Rett feil i køa for varsel`.
- Describe the change plainly. Keep code identifiers, file names, issue numbers
  and product names (WoW Status, Retail, TBC, Lua) as they are.
- A light Christian touch is welcome when it fits naturally, without crowding
  out the meaning: `Gje varselkøa nåde: rett dobbel visning`. Most subjects can
  stay plain; the body carries the tone.

## Body

- A blank line after the subject, then short Nynorsk paragraphs wrapped at
  about 72 characters: what changed and why, as you would otherwise write it.
- End with one short blessing, psalm-like line or parable nod that suits the
  change, for example:
  - `Velsigna vere testane som gjekk grøne.`
  - `Den som er tru i det små, er òg tru i det store.` (Luk 16,10)
  - `Fred vere med denne koden, og med alle som les han.`
  - `Søk, så skal de finne – og no fann vi feilen.`
- Keep it warm and inclusive. Never preach, mock the faith, judge people or
  put religion where it reads as disrespect (for example in a fix for a
  death roast, keep the blessing gentle).

## Write correct Nynorsk

Use standard Nynorsk forms, not Bokmål: `ikkje`, `eg`, `kva`, `korleis`,
`no`, `berre`, `endå`, `òg`, `frå`, `mellom`, `gjennom`, `fleire`, `nokre`,
`brukar`, `vert/blir`, `-ane/-ene` plurals (`filene`, `testane`). Common
verbs: `legg til`, `fjern`, `rett`, `oppdater`, `flytt`, `gjer om`,
`forenkle`, `dokumenter`, `byt namn på`.

## Heavenly co-author

Every commit gets one divine co-author trailer. Pick the one that suits the
change best (or vary between them):

- `Co-Authored-By: Jesus Kristus <jesus-kristus@himmelen.invalid>`: fixes,
  forgiveness of old mistakes, healing broken tests.
- `Co-Authored-By: Gud Fader <gud-fader@himmelen.invalid>`: new features,
  creating something from nothing, large structural work.
- `Co-Authored-By: Den Heilage Ande <den-heilage-ande@himmelen.invalid>`:
  docs, copy, inspiration, small touches and anything else.

Always use the `.invalid` addresses exactly as shown. They can never belong
to a real GitHub account, so no stranger gets credited for the commit.

## What stays unchanged

- Trailers go last, after the blessing, in one block with no blank lines:
  first the divine co-author, then the other trailers in their exact
  English form (`Co-Authored-By: …`, `Signed-off-by: …`, and any attribution
  line the session asks for). The divine trailer adds to them, never
  replaces them.
- Release commits made by `scripts/prepare_release.py` keep their automatic
  format; do not reword them.
- Player-facing release notes still go under `## Unreleased` in
  `CHANGELOG.md` as `AGENTS.md` describes. If a pull request has no such note,
  the release uses the public commit title, so keep titles of pull requests
  that reach `main` clear to players too.
- All other commit rules in `AGENTS.md` still apply: commit only when asked,
  never stage unrelated work, never commit secrets or player data.

## Example

```
Legg til personlegdomen Dverg

Nye bildetekstar om øl, skjegg og smier i 13 kategoriar, på engelsk
og nynorsk. Personlegdomen er registrert i alle fire utgåvene og i
testane.

Velsigna vere smeden som held elden ved like.

Co-Authored-By: Gud Fader <gud-fader@himmelen.invalid>
Co-Authored-By: …
```

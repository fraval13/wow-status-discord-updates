# Wago Addons listing and automatic publishing

Wago project ID: `mNww12No`. The proposed public slug is `wow-status`; use the
project-ID link <https://addons.wago.io/addons/mNww12No> until the slug is saved.
A project ID and a URL slug are different fields.

The `wago` job in `.github/workflows/checks.yml` publishes one ZIP for each of
Retail, Classic Era, TBC Anniversary and Forever. It runs beside CurseForge after
`deploy` has verified the homepage release. Both jobs check out the exact verified
release revision. A Wago failure does not undo a successful homepage deployment
or CurseForge upload.

## One-time setup

1. Finish the Wago listing with the fields below and any approval Wago requires.
2. Create an API key in the [Wago developer account](https://addons.wago.io/account/apikeys).
3. Store it as the GitHub repository Actions secret `WAGO_API_TOKEN`. Do not put it
   in Git, the listing, an issue, a chat message or a command-line argument.
4. Set the repository variable `WAGO_PROJECT_ID` to `mNww12No`. All four TOCs
   declare this public ID as `X-Wago-ID`.
5. Merge the next release, or run **Actions → Checks and addon packages → Run
   workflow** on `main`. For the first Wago upload, turn **Skip CurseForge
   uploads** on and leave **Wago editions to upload** at `all`. This still runs
   validation, deployment and public verification; it reuses an already prepared
   release rather than bumping it again.

Without the project variable, the Wago job is skipped. Without the token, it
writes an explicit skipped notice and job summary and does not build or upload
packages. A green workflow with that notice does not establish a Wago upload.

## What is uploaded

The job rebuilds the four homepage ZIPs from the verified release commit. The
Forever file also receives every spoken-reaction clip from the published
`voice-pack` release, just like CurseForge; homepage downloads stay small. There
is one top-level `WoWStatus/` folder per ZIP. Missing clips fail the job before
uploading files.

`scripts/upload_wago.py` checks every selected ZIP before its first upload:

- All selected versions match, and each has notes in `CHANGELOG.md`.
- Every main TOC declares the configured Wago project ID.
- Its exact WoW client patch, derived from `Interface`, is listed for the correct
  edition by Wago's public game catalogue. There is no fallback to a different
  patch or game edition.

Each release is stable, labelled `<version> (<edition>)`, with that version's
release notes. Uploads use Wago's documented bearer-token multipart API. Only
Wago receives the token, redirects are refused, server error bodies are not
logged, and POSTs are not automatically retried. A successful HTTP response means
Wago accepted the upload; check its dashboard for publication or moderation.

Wago's guide documents the upload endpoint and project IDs. Its current packager
uses `supported_<flavour>_patches` arrays, including Forever, rather than the older
singular fields in the guide:

- [Wago API guide](https://docs.wago.io/)
- [Live game catalogue](https://addons.wago.io/api/data/game)
- [Wago upload implementation in BigWigs packager](https://github.com/BigWigsMods/packager/blob/master/release.sh)

### Retry only missing files

A run can upload some editions before another upload fails. First check Wago's
version list: a timeout may have happened after Wago accepted a file. Do not
repeat successful uploads; Wago may create duplicate files.

For a partial retry, manually dispatch the workflow on `main`, turn **Skip
CurseForge uploads** on, and select the missing edition under **Wago editions to
upload**. Repeat for any other missing edition. The deploy gate still prevents
an older revision from publishing over the current main release.

For a local check with no uploads and no token:

```sh
WAGO_PROJECT_ID=mNww12No python scripts/upload_wago.py --dry-run
```

Build the committed release first. This checks Wago's live patch catalogue and
prints the metadata for the selected ZIPs. `--edition forever` selects just that
edition. A real upload needs the token in the environment; keep it out of shell
history. Mocked HTTP tests do not establish a real Wago upload.

## Listing inputs

The screenshot shows Wago's **Import readme** button copying the repository README.
That file contains developer instructions as well as player information. Replace
the description with [the player-facing Markdown](wago-description.md); avoid
importing the README over it afterwards. The release upload sends files and
release notes, not the listing description.

| Input | Value |
| --- | --- |
| Display Name | WoW Status |
| URL Slug | wow-status, if available |
| Summary | Share milestones with friends in WoW: level-ups, first clears, battleground results and a shared activity log. No companion app required. |
| Description | Paste the complete contents of `docs/wago-description.md` |
| Addon Website | https://wow.frankvalde.com/ |
| Addon License | https://github.com/fraval13/wow-status-discord-updates/blob/main/LICENSE |
| Addon Wiki | https://wow.frankvalde.com/#getting-started |
| Addon Source | https://github.com/fraval13/wow-status-discord-updates |
| Support link | https://github.com/fraval13/wow-status-discord-updates/issues |
| Discord link | Leave empty; there is no public support-server invite in this repository |
| Categories | Chat & Communication |
| Hide from 3rd party addon updaters | Leave unchecked |
| Unlisted | Leave unchecked for a public release |
| Thumbnail | `assets/branding/WoWStatus-curseforge.png` (existing 400 × 400 PNG) |

The code is MIT. Original branding, captions and reaction text have separate
redistribution terms in the README; the description links to those terms.
No real group name belongs in the listing or screenshots.

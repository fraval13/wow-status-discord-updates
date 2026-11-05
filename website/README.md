# WoW Status homepage

Buildless HTML/CSS/JS, published at **https://wow.frankvalde.com/** through the
existing Caddy server. All fonts, images and scripts are served locally. No
analytics, sign-in, external runtime dependencies, or player data.

Build from the repository root:

```sh
python scripts/build_homepage.py --addon-ref HEAD
python -m http.server 4173 --directory dist/homepage --bind 127.0.0.1
```

The output is `dist/homepage/`. All four ZIPs contain the top-level `WoWStatus`
folder expected by WoW and hold only the TOC, the files it lists and
`Textures/*.tga`; any other committed file (for example `.DS_Store` or `WTF/`) is
left out, and a TOC-listed file that is not committed fails the build. The build
also fails unless all four TOC versions equal the `pyproject.toml` version. Addon
files always come from the specified committed Git revision. Uncommitted addon
edits are excluded.
Each build replaces the output folder as a whole, so a deleted asset or an old ZIP
never survives a rebuild, and a failed build leaves the earlier one in place. The
builder refuses an existing `--output` folder that is not an earlier build.
Version and file sizes on the page come from the packaged release. Checksums and
the exact addon revision are published at `/downloads/release.json`.

## Deployment

The homepage is independent from the dormant companion services. Caddy serves
`/srv/wow-status-homepage/current`, an atomic symlink into `releases/`. The existing
two known `/groups/` routes still proxy to their original ports; unknown groups
still return 404. No application restart or player database changes are needed.

Use `python deploy/publish_homepage.py --host root@193.243.189.202` after building.
This requires ordinary authorized SSH access (for the current session, use
`SSH_AUTH_SOCK=/tmp/wow-forever-deploy-agent.sock`). Before contacting the server it
checks the build folder and refuses to publish when:

- `downloads/release.json` names another revision than the checkout's `HEAD`;
- `website/` (apart from its `README.md`, `ARTWORK.md` and file-manager files such
  as `.DS_Store`, which the build never copies), the builder
  (`scripts/build_homepage.py`, `scripts/whats_new.py`), `deploy/render_caddyfile.py`
  or `deploy/install_homepage.py` has uncommitted, untracked or ignored files, or
  files marked assume-unchanged or skip-worktree: publishing reads them from the
  working tree;
- a ZIP does not match its size and SHA-256 in `release.json`;
- any file is stale, missing or different compared with a fresh build it makes
  itself. It uploads that fresh build, so file-manager files such as `.DS_Store`
  in the folder are ignored.

The Caddyfile is rendered from the committed `deploy/Caddyfile.production.template`.
On the server, `deploy/install_homepage.py` checks the upload's SHA-256 and the live
Caddyfile, extracts the new static release with public read permissions, validates
the candidate Caddyfile outside the web root, switches the symlink and gracefully
reloads Caddy. A failure removes the partial release and the upload; one after the
switch first restores the previous site and Caddyfile and restarts Caddy if it
stopped. The previous configuration and release stay available for rollback; after
a successful publish only the newest five static releases (the new one among them)
and Caddyfile backups are kept, plus the release that was live before. The install
holds the pipeline receiver's deployment lock, so it waits (up to ten minutes) while
a pipeline deploy runs, and refuses if that deploy switched the site meanwhile. It
reads the server's
private `groups.json` to render the
group routes (never the Discord settings) and refuses to change the live routes.
`--dry-run` prints the Caddy change without uploading anything; that output holds
the group route keys, so keep it private.

After publication check `/`, all four ZIP downloads and their contents, the release
manifest, both existing group `/health` endpoints, and an unknown group URL.
When publishing a future release, update the displayed release notes in
`index.html`, rebuild with its addon revision, then republish.

## Automatic releases

The **Checks and addon packages** workflow builds this site on both test platforms.
CI addon artifacts use the very same ZIPs as the site. The deployment job rebuilds
for its exact commit and includes the public output in its private deployment tar.
`deploy/make_release.py` refuses a stale homepage revision.

The root-owned receiver verifies the public manifest, checksums, ZIPs and displayed
version against the incoming addon TOCs before activation. Once both application
health checks pass, it switches the public symlink to the sealed release's
`public-homepage/` directory. A failed build/health check leaves the old site and
downloads in place; the receiver also retains the old symlink for rollback.
If the public verification below fails, the deploy job asks the receiver to roll
back to the preceding release and homepage, unless a manual publish replaced the
homepage since (see `deploy/SERVER.md`).
The constant Caddy document-root path needs no reload for these later releases.

Version text and sizes are filled automatically from the addon release metadata.
Feature changes keep the current version; a separate release pull request edits
`pyproject.toml` and runs `python scripts/sync_version.py` to update the TOCs. Do not edit version labels by hand on the website. The pipeline runs on pushed `main` commits or manual
workflow dispatches. Local commits alone cannot trigger GitHub Actions.

After deployment, the workflow fetches the live homepage, release manifest and
all four ZIP downloads using `scripts/verify_homepage.py`, and compares them with
the `release.json` the deploy job built itself (`--manifest`), not only with the
manifest the site serves. It checks the exact commit revision, that the served
manifest equals the local one, the visible download links, that every ZIP's size
and SHA-256 match the local build, and the version labels. Each ZIP must hold
exactly its TOC, the files the TOC lists and `Textures/*.tga` under `WoWStatus/`;
path traversal, duplicate, directory, symlink or other unexpected entries fail. A stale,
tampered or missing public download fails the release verification step.

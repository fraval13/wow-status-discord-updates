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
Version and file sizes on the page come from the packaged release. Checksums and
the exact addon revision are published at `/downloads/release.json`.

## Deployment

The homepage is independent from the dormant companion services. Caddy serves
`/srv/wow-status-homepage/current`, an atomic symlink into `releases/`. The existing
two known `/groups/` routes still proxy to their original ports; unknown groups
still return 404. No application restart or player database changes are needed.

Use `python deploy/publish_homepage.py --host root@193.243.189.202` after building.
This requires ordinary authorized SSH access (for the current session, use
`SSH_AUTH_SOCK=/tmp/wow-forever-deploy-agent.sock`). It uploads a new static release,
validates Caddy, switches the symlink and gracefully reloads Caddy. The previous
configuration and release stay available for rollback. See the script for the
exact maintenance steps; it never reads application secrets.

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
The constant Caddy document-root path needs no reload for these later releases.

Version text and sizes are filled automatically from the addon release metadata.
When changing the addon, bump the TOC/project version as usual; do not edit version
labels by hand on the website. The pipeline runs on pushed `main` commits or manual
workflow dispatches. Local commits alone cannot trigger GitHub Actions.

After deployment, the workflow fetches the live homepage, release manifest and
all four ZIP downloads using `scripts/verify_homepage.py`. It checks the exact
commit revision, visible download links, public hashes, ZIP contents and version
labels. A stale or missing public download fails the release verification step.

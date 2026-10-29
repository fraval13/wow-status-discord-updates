# WoW Status homepage

Buildless HTML/CSS/JS, published at **https://wow.frankvalde.com/** through the
existing Caddy server. All fonts, images and scripts are served locally. No
analytics, sign-in, external runtime dependencies, or player data.

Build from the repository root:

```sh
python scripts/build_homepage.py --addon-ref HEAD
python -m http.server 4173 --directory dist/homepage --bind 127.0.0.1
```

The output is `dist/homepage/`. Both ZIPs contain the top-level `WoWStatus`
folder expected by WoW; every TOC-listed file is checked. Addon files always come
from the specified committed Git revision. Uncommitted addon edits are excluded.
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

After publication check `/`, both ZIP downloads and their contents, the release
manifest, both existing group `/health` endpoints, and an unknown group URL.
When publishing a future release, update the displayed release notes in
`index.html`, rebuild with its addon revision, then republish.

# Weaving Computer update feed

This public repository coordinates stable WC-Split releases. It contains no
custom updater, archive extractor, signature implementation, or installation
helper. Those security-sensitive mechanics are provided by the maintained,
MIT-licensed [Velopack](https://github.com/velopack/velopack) project.

The release workflow dispatches matching host and frontend builds, waits for
all four platform artifacts, validates the Velopack feeds, and deploys a static
GitHub Pages tree:

```text
host/windows-x86_64/
frontend/windows-x86_64/
```

Each directory is a standard Velopack HTTP source containing
`releases.stable.json`, update packages, and the current fresh installer. The
host reads its own platform feed from Pages and mirrors the two frontend feeds
to clients on the LAN.

## Publishing

Configure `PRODUCT_BUILD_TOKEN` in this repository's `stable-publishing`
environment with Actions read/write access to
`Dahlqvistad/weaving_computer.host` and
`Dahlqvistad/weaving_computer.frontend`. Enable GitHub Pages with **GitHub
Actions** as the source.

On a development computer where the updates, host, and frontend repositories
are sibling directories, authenticate GitHub CLI once:

```bash
gh auth login -h github.com
gh auth setup-git
```

Commit product changes, then publish the next stable version with one command:

```bash
python3 scripts/publish_release.py 1.2.3
```

The script requires clean, already-pushed `main` branches in all three
repositories. It updates and
commits both `pyproject.toml` versions when necessary, pushes those small
release-preparation commits, chooses the next sequence, pushes matching
annotated release tags to the exact host and frontend repositories, and starts
this repository's publication workflow.
The tag-triggered product workflows build on Windows and create the two GitHub
Releases; the updates workflow then publishes and verifies both public feeds.
Use `--dry-run` to validate without creating tags or starting workflows. The
workspace-, frontend-, and host-level `release_windows.py` files are
compatibility entry points for the same command and never build locally.

The macOS build is ad-hoc signed for internal use. The first installation
therefore requires explicit Gatekeeper approval. Before public or untrusted
distribution, replace this with Developer ID signing and notarization; a hash
from an unauthenticated feed proves integrity, not publisher identity.

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

1. Set both product `pyproject.toml` versions to the same strict SemVer.
2. Configure a `PRODUCT_BUILD_TOKEN` Actions secret with Actions read/write
   access to `Dahlqvistad/weaving_computer.host` and
   `Dahlqvistad/weaving_computer.app`.
3. Enable GitHub Pages with **GitHub Actions** as the source.
4. Run **Publish coordinated stable release** with a version and a sequence
   greater than the value in `sequence.txt`.

The macOS build is ad-hoc signed for internal use. The first installation
therefore requires explicit Gatekeeper approval. Before public or untrusted
distribution, replace this with Developer ID signing and notarization; a hash
from an unauthenticated feed proves integrity, not publisher identity.

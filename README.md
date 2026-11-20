# Weaving Computer update feed

This repository coordinates stable WC-Split releases. Installer creation,
package verification, staging, activation, and rollback are delegated to the
maintained, MIT-licensed [Velopack](https://github.com/velopack/velopack)
project. WC-Split additionally defines a `.wcupdate` transport archive for
moving the standard host and frontend Velopack feeds to an offline host.

The release tooling either dispatches matching host and frontend builds or
builds both products on a local Windows computer. It validates the Velopack
feeds and deploys a static GitHub Pages tree:

```text
host/windows-x86_64/
frontend/windows-x86_64/
```

Each directory is a standard Velopack HTTP source containing
`releases.stable.json`, update packages, and the latest verified product
installer. The Pages root also publishes `installer.stable.json` for the private
general installer. That installer always reads the current manifest before
downloading anything, so a previously downloaded copy installs the latest
coordinated host and frontend release instead of a version embedded in the
installer. Its source and executable are kept in the private
`weaving_computer.installer` repository. The host reads its own platform feed
from Pages and mirrors the frontend feed to clients on the LAN.

`extensions.toml` is the release composition source of truth. Both publication
paths resolve it to exact extension commits and install every locked host or
frontend extension before PyInstaller runs. The resulting extensions are built
into the normal application packages without placing extension source in either
product repository.

## Building and publishing

### Local Windows build (no GitHub Actions)

Use a 64-bit Windows 10 or Windows 11 computer with Git installed. For the
first build, open PowerShell and run this complete command:

```powershell
git clone https://github.com/Dahlqvistad/weaving_computer.updates.git; cd weaving_computer.updates; .\release-windows.cmd
```

For every later build, open PowerShell in the cloned
`weaving_computer.updates` folder and run:

```powershell
.\release-windows.cmd
```

The build command fast-forwards the updates repository, installs missing
GitHub CLI, Python 3.12, and .NET 8 prerequisites with `winget`, and opens
GitHub's browser login when necessary. It then:

1. selects the next coordinated version and monotonic sequence;
2. clones clean host, frontend, and locked extension sources;
3. runs product and extension checks and tests;
4. builds both Windows applications with PyInstaller and Velopack;
5. creates fresh host and frontend installers; and
6. combines both update feeds into one verified `.wcupdate` file.

Nothing is tagged, published, or uploaded. Output remains in
`.local-release\vVERSION\output` and contains:

```text
Vavdator-Server-vVERSION-Setup.exe
Vavdatorn-vVERSION-Setup.exe
WC-Split-vVERSION-SEQUENCE.wcupdate
```

Use the two installers for a fresh computer. On an installed host, open
**Updates**, choose the `.wcupdate` file, wait for it to be staged, and select
**Activate**. The host update and matching frontend update are applied as one
coordinated release. Extensions selected by `extensions.toml` are already
compiled into both packages and are listed in the bundle manifest.

GitHub Actions is not invoked, and no Actions artifact storage is used.

Useful validation and override forms are:

```powershell
# Select an explicit version.
.\release-windows.cmd -Version 26.11.3

# Override the deterministic sequence when coordinating with another channel.
.\release-windows.cmd -Version 26.11.3 -Sequence 26011003
```

`-SkipTests` exists only for an explicitly accepted emergency. Normal builds
stop if a product or extension test fails. All application
and extension changes referenced by `extensions.toml` must be committed and
pushed before starting from the Windows computer.

### GitHub Actions release

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
python3 scripts/publish_release.py
```

The script chooses the version automatically as `YY.MONTH.SEQUENCE`, for
example `v26.11.2` for the second publication in November 2026. The monthly
sequence is derived from existing host and frontend GitHub Releases. The
updater's separate monotonic release sequence is also incremented
automatically and never resets.

The script requires clean, already-pushed `main` branches in all three
repositories. It updates and
commits both `pyproject.toml` versions when necessary, pushes those small
release-preparation commits, chooses both version counters, pushes matching
annotated release tags to the exact host and frontend repositories, and starts
this repository's publication workflow.
The product workflows build on Windows and create the two GitHub Releases; the
updates workflow then publishes and verifies both public feeds, the stable
installer manifest, and the two product `Setup.exe` files used by the private
general installer. The general installer supports install/update, repair, and
uninstall. Repair reruns the latest verified Velopack installers; uninstall
removes both application installations but preserves production data and
settings stored outside the application directories.
Use `--dry-run` to validate without creating tags or starting workflows. The
workspace-, frontend-, and host-level `release_windows.py` files are
compatibility entry points for the same command and never build locally.

Extensions selected by `extensions.toml` are compiled into both products and
listed by the installer. Hardware integrations are not silently activated; for
example, DYMO must be enabled and configured in Host settings after installation.

The macOS build is ad-hoc signed for internal use. The first installation
therefore requires explicit Gatekeeper approval. Before public or untrusted
distribution, replace this with Developer ID signing and notarization; a hash
from an unauthenticated feed proves integrity, not publisher identity.

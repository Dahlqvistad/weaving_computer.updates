"""Publish one coordinated WC-Split release from a developer workstation.

Run from the WC-split workspace or the updates repository:

    python3 scripts/publish_release.py 1.2.3

The command pushes matching annotated product tags, then dispatches the updates
repository. GitHub Actions builds both products from those tags, creates their
GitHub Releases, validates the Velopack packages, and deploys the public feed.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

import tomllib

UPDATES_REPOSITORY = "Dahlqvistad/weaving_computer.updates"
UPDATES_WORKFLOW = "publish-stable.yaml"
PAGES_ROOT = "https://dahlqvistad.github.io/weaving_computer.updates"
STRICT_SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")

UPDATES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = UPDATES_ROOT.parent


@dataclass(frozen=True, slots=True)
class Product:
    name: str
    repository: str
    directory: Path
    release_title: str


PRODUCTS = (
    Product(
        name="host",
        repository="Dahlqvistad/weaving_computer.host",
        directory=WORKSPACE_ROOT / "host",
        release_title="Vävdator Server",
    ),
    Product(
        name="frontend",
        repository="Dahlqvistad/weaving_computer.frontend",
        directory=WORKSPACE_ROOT / "frontend",
        release_title="Vävdatorn",
    ),
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help="Strict stable SemVer, e.g. 1.2.3")
    parser.add_argument(
        "--version",
        dest="version_option",
        help="Compatibility alias for the positional version",
    )
    parser.add_argument(
        "--sequence",
        type=int,
        help="Release sequence; defaults to the current public sequence plus one",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run local validation and print the intended publication",
    )
    arguments = parser.parse_args()
    if bool(arguments.version) == bool(arguments.version_option):
        parser.error("provide the version once, either positionally or with --version")
    arguments.version = normalize_version(arguments.version or arguments.version_option)
    return arguments


def normalize_version(value: str) -> str:
    version = value.strip().removeprefix("v")
    if STRICT_SEMVER.fullmatch(version) is None:
        raise ValueError("Stable releases require a strict MAJOR.MINOR.PATCH version.")
    return version


def run(
    *arguments: str,
    cwd: Path = UPDATES_ROOT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if check and result.returncode != 0:
        command_output = result.stdout.strip() or "No command output."
        raise RuntimeError(
            f"Command failed: {' '.join(arguments)}\n{command_output}"
        )
    return result


def output(*arguments: str, cwd: Path = UPDATES_ROOT) -> str:
    return run(*arguments, cwd=cwd).stdout.strip()


def require_prerequisites() -> None:
    if shutil.which("git") is None:
        raise RuntimeError("Git is required.")
    if shutil.which("gh") is None:
        raise RuntimeError("GitHub CLI is required. Install it and run 'gh auth login'.")
    authentication = run("gh", "auth", "status")
    if authentication.returncode != 0 or "Failed to log in" in authentication.stdout:
        raise RuntimeError(
            "GitHub CLI is not authenticated. Run 'gh auth login -h github.com' "
            "and then 'gh auth setup-git'."
        )


def ensure_clean_product(product: Product) -> None:
    if not (product.directory / ".git").exists():
        raise RuntimeError(f"Missing local {product.name} repository: {product.directory}")
    if output("git", "status", "--porcelain", cwd=product.directory):
        raise RuntimeError(
            f"{product.name} has uncommitted changes. Commit them before releasing."
        )
    branch = output("git", "branch", "--show-current", cwd=product.directory)
    if branch != "main":
        raise RuntimeError(
            f"{product.name} is on branch {branch!r}; coordinated releases use 'main'."
        )


def ensure_updates_repository_is_pushed() -> None:
    if output("git", "status", "--porcelain", cwd=UPDATES_ROOT):
        raise RuntimeError(
            "updates has uncommitted changes. Commit and push the release workflow "
            "before publishing."
        )
    branch = output("git", "branch", "--show-current", cwd=UPDATES_ROOT)
    if branch != "main":
        raise RuntimeError(
            f"updates is on branch {branch!r}; coordinated releases use 'main'."
        )
    local_sha = output("git", "rev-parse", "HEAD", cwd=UPDATES_ROOT)
    remote_sha = output(
        "gh",
        "api",
        f"repos/{UPDATES_REPOSITORY}/commits/main",
        "--jq",
        ".sha",
    )
    if local_sha != remote_sha:
        raise RuntimeError("updates HEAD is not the published main commit. Push it first.")


def project_version(project_file: Path) -> str:
    with project_file.open("rb") as source:
        payload = tomllib.load(source)
    version = payload.get("project", {}).get("version")
    if not isinstance(version, str):
        raise TypeError(f"Missing [project].version in {project_file}")
    return version


def update_project_version(project_file: Path, version: str) -> bool:
    current = project_version(project_file)
    if current == version:
        return False
    source = project_file.read_text(encoding="utf-8")
    old_line = f'version = "{current}"'
    new_line = f'version = "{version}"'
    if source.count(old_line) != 1:
        raise RuntimeError(f"Could not safely update version in {project_file}")
    project_file.write_text(source.replace(old_line, new_line), encoding="utf-8")
    return True


def prepare_product_version(product: Product, version: str) -> None:
    project_file = product.directory / "pyproject.toml"
    if update_project_version(project_file, version):
        run("git", "add", "pyproject.toml", cwd=product.directory)
        run(
            "git",
            "commit",
            "-m",
            f"Prepare release v{version}",
            cwd=product.directory,
        )


def ensure_product_is_pushed(product: Product) -> None:
    local_sha = output("git", "rev-parse", "HEAD", cwd=product.directory)
    remote_sha = output(
        "gh",
        "api",
        f"repos/{product.repository}/commits/main",
        "--jq",
        ".sha",
    )
    if local_sha != remote_sha:
        raise RuntimeError(
            f"{product.name} HEAD is not the published main commit. Push it first."
        )


def push_product_main(product: Product) -> None:
    target = f"https://github.com/{product.repository}.git"
    run("git", "push", target, "HEAD:main", cwd=product.directory)


def ensure_tag_does_not_exist(product: Product, version: str) -> None:
    tag = f"v{version}"
    target = f"https://github.com/{product.repository}.git"
    remote_tag = output(
        "git",
        "ls-remote",
        "--tags",
        target,
        f"refs/tags/{tag}",
        cwd=product.directory,
    )
    if remote_tag:
        raise RuntimeError(
            f"{product.repository} already has tag {tag}; publish a higher version."
        )
    if output("git", "tag", "--list", tag, cwd=product.directory):
        raise RuntimeError(
            f"{product.name} already has a local {tag} tag. Remove it or use a "
            "higher version."
        )


def push_release_tag(product: Product, version: str, sequence: int) -> None:
    tag = f"v{version}"
    message = f"Coordinated release {tag}\n\nsequence: {sequence}"
    target = f"https://github.com/{product.repository}.git"
    run("git", "tag", "--annotate", tag, "--message", message, cwd=product.directory)
    try:
        run(
            "git",
            "push",
            target,
            f"refs/tags/{tag}:refs/tags/{tag}",
            cwd=product.directory,
        )
    except RuntimeError:
        run("git", "tag", "--delete", tag, cwd=product.directory)
        raise


def current_public_sequence() -> int:
    encoded = output(
        "gh",
        "api",
        f"repos/{UPDATES_REPOSITORY}/contents/sequence.txt",
        "--jq",
        ".content",
    )
    try:
        return int(base64.b64decode(encoded).decode("utf-8").strip())
    except (ValueError, UnicodeDecodeError) as error:
        raise RuntimeError("The updates repository has an invalid sequence.txt.") from error


def ensure_release_does_not_exist(product: Product, version: str) -> None:
    result = run(
        "gh",
        "release",
        "view",
        f"v{version}",
        "--repo",
        product.repository,
        check=False,
    )
    if result.returncode == 0:
        raise RuntimeError(
            f"{product.repository} already has release v{version}; "
            "publish a higher version."
        )


def dispatch_updates(version: str, sequence: int) -> None:
    run(
        "gh",
        "workflow",
        "run",
        UPDATES_WORKFLOW,
        "--repo",
        UPDATES_REPOSITORY,
        "--ref",
        "main",
        "-f",
        f"version={version}",
        "-f",
        f"sequence={sequence}",
        "-f",
        "dispatch_products=false",
    )


def find_updates_run(version: str, sequence: int) -> int:
    expected_title = f"Publish stable {version} (sequence {sequence})"
    for _ in range(60):
        runs = json.loads(
            output(
                "gh",
                "run",
                "list",
                "--repo",
                UPDATES_REPOSITORY,
                "--workflow",
                UPDATES_WORKFLOW,
                "--event",
                "workflow_dispatch",
                "--limit",
                "30",
                "--json",
                "databaseId,displayTitle",
            )
        )
        for workflow_run in runs:
            if workflow_run.get("displayTitle") == expected_title:
                return int(workflow_run["databaseId"])
        time.sleep(2)
    raise RuntimeError("Timed out while locating the updates workflow run.")


def verify_release(product: Product, version: str) -> None:
    payload = json.loads(
        output(
            "gh",
            "release",
            "view",
            f"v{version}",
            "--repo",
            product.repository,
            "--json",
            "tagName,name,assets",
        )
    )
    expected_title = f"{product.release_title} v{version}"
    if payload.get("tagName") != f"v{version}" or payload.get("name") != expected_title:
        raise RuntimeError(f"Unexpected release identity for {product.repository}.")
    names = [
        asset.get("name", "")
        for asset in payload.get("assets", [])
        if isinstance(asset, dict)
    ]
    required_suffixes = ("Setup.exe", "Portable.zip", "-full.nupkg")
    missing = [
        suffix
        for suffix in required_suffixes
        if not any(name.endswith(suffix) for name in names)
    ]
    if missing:
        raise RuntimeError(
            f"{product.repository} release is missing assets ending in: "
            f"{', '.join(missing)}"
        )


def fetch_feed(component: str) -> dict[str, object]:
    url = f"{PAGES_ROOT}/{component}/windows-x86_64/releases.stable.json"
    request = Request(url, headers={"User-Agent": "wc-split-release-verifier"})
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise TypeError(f"Invalid update feed at {url}")
    return payload


def verify_feed(component: str, version: str) -> None:
    last_error: Exception | None = None
    for _ in range(24):
        try:
            payload = fetch_feed(component)
            assets = payload.get("Assets")
            if isinstance(assets, list) and any(
                isinstance(asset, dict) and asset.get("Version") == version
                for asset in assets
            ):
                return
        except Exception as error:  # noqa: BLE001
            last_error = error
        time.sleep(5)
    detail = f": {last_error}" if last_error is not None else ""
    raise RuntimeError(f"Public {component} feed did not publish {version}{detail}")


def verify_publication(version: str, sequence: int) -> None:
    for product in PRODUCTS:
        verify_release(product, version)
        verify_feed(product.name, version)
    if current_public_sequence() != sequence:
        raise RuntimeError("The updates repository did not record the release sequence.")


def main() -> None:
    arguments = parse_arguments()
    version: str = arguments.version
    require_prerequisites()
    ensure_updates_repository_is_pushed()
    for product in PRODUCTS:
        ensure_clean_product(product)
        ensure_product_is_pushed(product)
        ensure_tag_does_not_exist(product, version)
        ensure_release_does_not_exist(product, version)
    current_sequence = current_public_sequence()
    sequence = (
        arguments.sequence
        if arguments.sequence is not None
        else current_sequence + 1
    )
    if sequence <= current_sequence:
        raise RuntimeError(
            f"Sequence must be greater than the published value {current_sequence}."
        )

    print(f"Coordinated release: v{version}, sequence {sequence}")
    if arguments.dry_run:
        for product in PRODUCTS:
            current = project_version(product.directory / "pyproject.toml")
            print(f"  {product.name}: {current} -> {version}, then tag v{version}")
        print("Dry run complete; no tags or workflows were changed.")
        return

    run("gh", "auth", "setup-git")
    for product in PRODUCTS:
        prepare_product_version(product, version)
    for product in PRODUCTS:
        push_product_main(product)
    for product in PRODUCTS:
        push_release_tag(product, version, sequence)

    dispatch_updates(version, sequence)
    run_id = find_updates_run(version, sequence)
    print(f"Waiting for coordinated updates workflow ({run_id})...", flush=True)
    run(
        "gh",
        "run",
        "watch",
        str(run_id),
        "--repo",
        UPDATES_REPOSITORY,
        "--exit-status",
    )
    verify_publication(version, sequence)
    print(f"Published and verified WC-Split v{version} (sequence {sequence}).")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, TypeError, ValueError) as error:
        raise SystemExit(f"Release failed: {error}") from error

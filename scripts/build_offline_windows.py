"""Build local Windows installers and one portable WC-Split update bundle."""

from __future__ import annotations

import argparse
import platform
import shutil
import struct
import sys
from pathlib import Path

from scripts import install_extensions
from scripts import offline_bundle
from scripts import publish_release as release_support
from scripts import windows_build_support as build_support


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Strict SemVer; defaults to the next release")
    parser.add_argument(
        "--sequence",
        type=int,
        help="Monotonic sequence; defaults to a deterministic value from the version",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Build without tests; use only for an explicitly accepted emergency",
    )
    return parser.parse_args()


def require_windows_environment(updates_root: Path) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Windows installers must be built on Windows.")
    if struct.calcsize("P") != 8 or platform.machine().casefold() not in {
        "amd64",
        "x86_64",
    }:
        raise RuntimeError("Use 64-bit x86 Python to build the win-x64 release.")
    for command in ("git", "dotnet"):
        if shutil.which(command) is None:
            raise RuntimeError(f"Required command is not installed: {command}")
    install_extensions.load_profile(updates_root / "extensions.toml")


def select_version(
    requested_version: str | None,
    product_repositories: dict[str, Path],
) -> str:
    if requested_version:
        return release_support.normalize_version(requested_version)
    current_versions = [
        release_support.project_version(repository / "pyproject.toml")
        for repository in product_repositories.values()
    ]
    return release_support.next_calendar_version(current_versions)


def deterministic_sequence(version: str) -> int:
    major, minor, patch = (int(part) for part in version.split("."))
    return major * 1_000_000 + minor * 1_000 + patch


def extension_metadata(
    checkouts: tuple[build_support.ExtensionCheckout, ...],
) -> list[dict[str, str]]:
    return [
        {
            "id": checkout.source.extension_id,
            "ref": checkout.source.ref,
            "commit": checkout.commit,
            "host_version": release_support.project_version(
                checkout.directory / checkout.source.host_path / "pyproject.toml"
            ),
            "frontend_version": release_support.project_version(
                checkout.directory / checkout.source.frontend_path / "pyproject.toml"
            ),
        }
        for checkout in checkouts
    ]


def copy_installer(
    release_directory: Path,
    output_directory: Path,
    output_name: str,
) -> Path:
    installers = list(release_directory.glob("*Setup.exe"))
    if len(installers) != 1:
        raise RuntimeError(
            f"Expected exactly one installer in {release_directory}, "
            f"found {len(installers)}."
        )
    destination = output_directory / output_name
    shutil.copy2(installers[0], destination)
    return destination


def main() -> None:
    arguments = parse_arguments()
    updates_root = release_support.UPDATES_ROOT
    require_windows_environment(updates_root)
    workspace_root = updates_root / ".local-release"
    preparation = workspace_root / "preparing"
    if preparation.exists():
        raise RuntimeError(
            f"A previous build workspace remains at {preparation}. Remove it and retry."
        )
    preparation.mkdir(parents=True)
    try:
        product_repositories = {
            product.name: build_support.clone_product(
                product,
                preparation,
                updates_root,
            )
            for product in build_support.PRODUCTS
        }
        version = select_version(arguments.version, product_repositories)
        sequence = (
            arguments.sequence
            if arguments.sequence is not None
            else deterministic_sequence(version)
        )
        if sequence < 1:
            raise ValueError("The release sequence must be positive.")
        workspace = workspace_root / f"v{version}"
        if workspace.exists():
            raise RuntimeError(
                f"Build output already exists at {workspace}. Remove it and retry."
            )
        preparation.replace(workspace)
        product_repositories = {
            name: workspace / repository.name
            for name, repository in product_repositories.items()
        }

        profile, checkouts = build_support.prepare_extension_profile(
            updates_root / "extensions.toml",
            workspace,
            updates_root,
        )
        tools_directory = workspace / "tools"
        tools_directory.mkdir()
        build_support.run(
            "dotnet",
            "tool",
            "install",
            "--tool-path",
            str(tools_directory),
            "vpk",
            "--version",
            "1.2.161",
            cwd=updates_root,
        )
        vpk = tools_directory / "vpk.exe"
        release_directories = {
            product.name: build_support.build_product(
                product,
                product_repositories[product.name],
                profile,
                checkouts,
                version,
                sequence,
                vpk,
                skip_tests=arguments.skip_tests,
            )
            for product in build_support.PRODUCTS
        }
        output_directory = workspace / "output"
        output_directory.mkdir()
        bundle = offline_bundle.create_offline_bundle(
            release_directories,
            output_directory / f"WC-Split-v{version}-{sequence}.wcupdate",
            version=version,
            sequence=sequence,
            extensions=extension_metadata(checkouts),
        )
        host_installer = copy_installer(
            release_directories["host"],
            output_directory,
            f"Vavdator-Server-v{version}-Setup.exe",
        )
        frontend_installer = copy_installer(
            release_directories["frontend"],
            output_directory,
            f"Vavdatorn-v{version}-Setup.exe",
        )
        print(f"\nBuilt WC-Split v{version} (sequence {sequence}).")
        print(f"Host installer: {host_installer}")
        print(f"Frontend installer: {frontend_installer}")
        print(f"Offline update: {bundle}")
    except Exception:
        if preparation.exists():
            shutil.rmtree(preparation)
        raise


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise SystemExit(f"Local Windows build failed: {error}") from error

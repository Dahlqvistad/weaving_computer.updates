"""Assemble and validate public WC-Split update and installer files."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tomllib
from pathlib import Path
from typing import Any

INSTALLER_MANIFEST_FORMAT = "wc-split-installer"
INSTALLER_MANIFEST_FORMAT_VERSION = 1
INSTALLER_MANIFEST_NAME = "installer.stable.json"
TARGETS = (
    ("host", "WeavingComputer.Host", "Vavdator Server", "windows", "x86_64"),
    (
        "frontend",
        "WeavingComputer.Frontend",
        "Vavdatorn",
        "windows",
        "x86_64",
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("incoming", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sequence", required=True, type=int)
    parser.add_argument("--extensions", required=True, type=Path)
    arguments = parser.parse_args()
    assemble_public_release(
        arguments.incoming,
        arguments.output,
        sequence=arguments.sequence,
        extensions_path=arguments.extensions,
    )


def assemble_public_release(
    incoming: Path,
    output: Path,
    *,
    sequence: int,
    extensions_path: Path,
) -> None:
    if sequence < 1:
        raise ValueError("Release sequence must be positive.")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / ".nojekyll").touch()

    versions: set[str] = set()
    installers: dict[str, dict[str, Any]] = {}
    for component, package_id, display_name, platform_name, architecture in TARGETS:
        artifact_name = f"{component}-{platform_name}-{architecture}"
        source = next(incoming.rglob(artifact_name), None)
        if source is None or not source.is_dir():
            raise ValueError(f"Missing downloaded artifact: {artifact_name}")
        destination = output / component / f"{platform_name}-{architecture}"
        destination.mkdir(parents=True)
        feed = source / "releases.stable.json"
        if not feed.is_file():
            raise ValueError(f"Missing Velopack feed: {feed}")
        shutil.copy2(feed, destination)
        payload = _read_json_object(feed)
        assets = payload.get("Assets")
        if not isinstance(assets, list):
            raise ValueError(f"Invalid asset list in {feed}")
        for asset in assets:
            filename = asset.get("FileName") if isinstance(asset, dict) else None
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise ValueError(f"Unsafe asset filename in {feed}")
            source_asset = source / filename
            if not source_asset.is_file():
                raise ValueError(f"Feed references missing asset: {source_asset}")
            shutil.copy2(source_asset, destination / filename)

        version = validate_feed(destination, expected_package_id=package_id)
        versions.add(version)
        installer = _find_installer(source)
        public_installer = destination / installer.name
        shutil.copy2(installer, public_installer)
        installers[component] = {
            "display_name": display_name,
            "package_id": package_id,
            "installer": {
                "url": public_installer.relative_to(output).as_posix(),
                "size": public_installer.stat().st_size,
                "sha256": _sha256(public_installer),
            },
        }

    if len(versions) != 1:
        raise ValueError(f"Product feeds are not coordinated: {sorted(versions)}")
    version = versions.pop()
    manifest = {
        "format": INSTALLER_MANIFEST_FORMAT,
        "format_version": INSTALLER_MANIFEST_FORMAT_VERSION,
        "release": {
            "version": version,
            "sequence": sequence,
            "platform": "windows",
            "architecture": "x86_64",
        },
        "products": installers,
        "extensions": _load_extensions(extensions_path),
    }
    (output / INSTALLER_MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_feed(directory: Path, *, expected_package_id: str) -> str:
    feed_path = directory / "releases.stable.json"
    payload = _read_json_object(feed_path)
    assets = payload.get("Assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError(f"Invalid or empty Velopack feed: {feed_path}")
    full_versions: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError(f"Invalid asset in {feed_path}")
        if asset.get("PackageId") != expected_package_id:
            raise ValueError(f"Unexpected package ID in {feed_path}")
        filename = asset.get("FileName")
        expected_hash = asset.get("SHA256")
        expected_size = asset.get("Size")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError(f"Unsafe asset filename in {feed_path}")
        asset_path = directory / filename
        if not asset_path.is_file():
            raise ValueError(f"Feed references missing asset: {asset_path}")
        if expected_size != asset_path.stat().st_size:
            raise ValueError(f"Asset size mismatch: {asset_path}")
        actual_hash = _sha256(asset_path)
        if not isinstance(expected_hash, str) or actual_hash.casefold() != expected_hash.casefold():
            raise ValueError(f"Asset checksum mismatch: {asset_path}")
        if asset.get("Type") == "Full" and isinstance(asset.get("Version"), str):
            full_versions.append(asset["Version"])
    if not full_versions:
        raise ValueError(f"Feed has no full release: {feed_path}")
    return full_versions[-1]


def _find_installer(directory: Path) -> Path:
    installers = sorted(directory.glob("*Setup.exe"))
    if len(installers) != 1 or installers[0].stat().st_size == 0:
        raise ValueError(
            f"Expected exactly one non-empty Setup.exe in {directory}, "
            f"found {len(installers)}."
        )
    return installers[0]


def _load_extensions(profile_path: Path) -> list[dict[str, Any]]:
    with profile_path.open("rb") as profile_file:
        payload = tomllib.load(profile_file)
    raw_extensions = payload.get("extensions")
    if not isinstance(raw_extensions, list):
        raise ValueError(f"Invalid extension profile: {profile_path}")
    extensions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_extension in raw_extensions:
        if not isinstance(raw_extension, dict):
            raise ValueError(f"Invalid extension entry: {profile_path}")
        extension_id = raw_extension.get("id")
        display_name = raw_extension.get("display_name")
        ref = raw_extension.get("ref")
        host_config_path = raw_extension.get("host_config_path")
        if not isinstance(extension_id, str) or not extension_id.strip():
            raise ValueError(f"Extension is missing an ID: {profile_path}")
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError(f"Extension {extension_id} is missing a ref.")
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError(f"Extension {extension_id} is missing a display name.")
        if (
            not isinstance(host_config_path, list)
            or not host_config_path
            or any(
                not isinstance(part, str) or not part.strip()
                for part in host_config_path
            )
        ):
            raise ValueError(
                f"Extension {extension_id} has an invalid host config path."
            )
        if extension_id in seen:
            raise ValueError(f"Duplicate extension ID: {extension_id}")
        seen.add(extension_id)
        extensions.append(
            {
                "id": extension_id,
                "display_name": display_name,
                "ref": ref,
                "host_config_path": host_config_path,
            }
        )
    return sorted(extensions, key=lambda extension: extension["id"])


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON file: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()

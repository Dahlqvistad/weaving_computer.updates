"""Create one portable WC-Split update archive from two Velopack outputs."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections.abc import Iterable
from pathlib import Path

BUNDLE_FORMAT = "wc-split-update"
BUNDLE_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
PLATFORM_KEY = "windows-x86_64"
PRODUCTS = {
    "host": "WeavingComputer.Host",
    "frontend": "WeavingComputer.Frontend",
}


def create_offline_bundle(
    release_directories: dict[str, Path],
    destination: Path,
    *,
    version: str,
    sequence: int,
    extensions: Iterable[dict[str, str]],
) -> Path:
    """Validate Velopack outputs and write an atomic, self-describing bundle."""
    files: list[tuple[str, Path]] = []
    for product_name, package_id in PRODUCTS.items():
        release_directory = release_directories[product_name]
        feed_path = release_directory / "releases.stable.json"
        asset_paths = _validated_feed_assets(
            feed_path,
            release_directory,
            package_id,
            version,
        )
        archive_root = f"{product_name}/{PLATFORM_KEY}"
        files.append((f"{archive_root}/releases.stable.json", feed_path))
        files.extend((f"{archive_root}/{path.name}", path) for path in asset_paths)

    manifest = {
        "format": BUNDLE_FORMAT,
        "format_version": BUNDLE_FORMAT_VERSION,
        "release": {
            "version": version,
            "sequence": sequence,
            "platform": "windows",
            "architecture": "x86_64",
            "bootstrap_protocol": 1,
        },
        "extensions": sorted(extensions, key=lambda extension: extension["id"]),
        "files": [
            {
                "path": archive_path,
                "size": source.stat().st_size,
                "sha256": _sha256(source),
            }
            for archive_path, source in sorted(files)
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_STORED,
            allowZip64=True,
        ) as archive:
            archive.writestr(
                MANIFEST_NAME,
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            )
            for archive_path, source in sorted(files):
                archive.write(source, archive_path)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def _validated_feed_assets(
    feed_path: Path,
    release_directory: Path,
    package_id: str,
    version: str,
) -> tuple[Path, ...]:
    try:
        payload = json.loads(feed_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid Velopack feed: {feed_path}") from error
    assets = payload.get("Assets") if isinstance(payload, dict) else None
    if not isinstance(assets, list) or not assets:
        raise RuntimeError(f"Velopack feed has no assets: {feed_path}")
    asset_paths: list[Path] = []
    full_versions: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("PackageId") != package_id:
            raise RuntimeError(f"Velopack feed has the wrong package ID: {feed_path}")
        filename = asset.get("FileName")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise RuntimeError(f"Velopack feed has an unsafe filename: {feed_path}")
        asset_path = release_directory / filename
        if not asset_path.is_file() or asset_path.stat().st_size != asset.get("Size"):
            raise RuntimeError(
                f"Velopack feed references a missing asset: {asset_path}"
            )
        expected_hash = asset.get("SHA256")
        if not isinstance(expected_hash, str) or (
            _sha256(asset_path).casefold() != expected_hash.casefold()
        ):
            raise RuntimeError(f"Velopack asset checksum failed: {asset_path}")
        asset_paths.append(asset_path)
        if asset.get("Type") == "Full" and isinstance(asset.get("Version"), str):
            full_versions.append(asset["Version"])
    if not full_versions or full_versions[-1] != version:
        raise RuntimeError(f"Velopack feed does not contain version {version}.")
    return tuple(asset_paths)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

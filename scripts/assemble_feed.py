"""Assemble and validate the four Velopack feeds downloaded from CI."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

TARGETS = (
    ("host", "windows", "x86_64"),
    ("host", "macos", "arm64"),
    ("frontend", "windows", "x86_64"),
    ("frontend", "macos", "arm64"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("incoming", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    if arguments.output.exists():
        shutil.rmtree(arguments.output)
    arguments.output.mkdir(parents=True)
    (arguments.output / ".nojekyll").touch()

    versions: set[str] = set()
    for component, platform_name, architecture in TARGETS:
        artifact_name = f"{component}-{platform_name}-{architecture}"
        source = next(arguments.incoming.rglob(artifact_name), None)
        if source is None or not source.is_dir():
            raise SystemExit(f"Missing downloaded artifact: {artifact_name}")
        destination = arguments.output / component / f"{platform_name}-{architecture}"
        shutil.copytree(source, destination)
        versions.add(validate_feed(destination))
    if len(versions) != 1:
        raise SystemExit(f"Product feeds are not coordinated: {sorted(versions)}")


def validate_feed(directory: Path) -> str:
    feed_path = directory / "releases.stable.json"
    payload = json.loads(feed_path.read_text(encoding="utf-8"))
    assets = payload.get("Assets") if isinstance(payload, dict) else None
    if not isinstance(assets, list) or not assets:
        raise SystemExit(f"Invalid or empty Velopack feed: {feed_path}")
    full_versions: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise SystemExit(f"Invalid asset in {feed_path}")
        filename = asset.get("FileName")
        expected_hash = asset.get("SHA256")
        expected_size = asset.get("Size")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise SystemExit(f"Unsafe asset filename in {feed_path}")
        asset_path = directory / filename
        if not asset_path.is_file():
            raise SystemExit(f"Feed references missing asset: {asset_path}")
        if expected_size != asset_path.stat().st_size:
            raise SystemExit(f"Asset size mismatch: {asset_path}")
        actual_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        if not isinstance(expected_hash, str) or actual_hash.lower() != expected_hash.lower():
            raise SystemExit(f"Asset checksum mismatch: {asset_path}")
        if asset.get("Type") == "Full" and isinstance(asset.get("Version"), str):
            full_versions.append(asset["Version"])
    if not full_versions:
        raise SystemExit(f"Feed has no full release: {feed_path}")
    return full_versions[-1]


if __name__ == "__main__":
    main()

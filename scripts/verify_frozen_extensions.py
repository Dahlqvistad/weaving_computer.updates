"""Verify that PyInstaller copied every selected extension entry point."""

from __future__ import annotations

import argparse
import configparser
import tomllib
from pathlib import Path
from typing import Literal

type Product = Literal["host", "frontend"]


def expected_extension_ids(profile_path: Path) -> set[str]:
    with profile_path.open("rb") as profile_file:
        payload = tomllib.load(profile_file)
    raw_extensions = payload.get("extensions")
    if not isinstance(raw_extensions, list):
        raise ValueError("Extension profile must contain an extensions array")
    identifiers: set[str] = set()
    for extension in raw_extensions:
        extension_id = extension.get("id") if isinstance(extension, dict) else None
        if not isinstance(extension_id, str) or not extension_id.strip():
            raise ValueError("Extension profile contains an invalid ID")
        identifiers.add(extension_id)
    return identifiers


def frozen_extension_ids(frozen_directory: Path, product: Product) -> set[str]:
    group = f"wc_split.{product}_extensions"
    identifiers: set[str] = set()
    for entry_points_file in frozen_directory.rglob("entry_points.txt"):
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(entry_points_file, encoding="utf-8")
        if parser.has_section(group):
            identifiers.update(parser.options(group))
    return identifiers


def verify_frozen_extensions(
    profile_path: Path,
    product: Product,
    frozen_directory: Path,
) -> None:
    expected = expected_extension_ids(profile_path)
    installed = frozen_extension_ids(frozen_directory, product)
    missing = expected - installed
    if missing:
        raise RuntimeError(
            "Frozen application is missing extension metadata: "
            + ", ".join(sorted(missing))
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--product", required=True, choices=("host", "frontend"))
    parser.add_argument("--frozen-dir", required=True, type=Path)
    arguments = parser.parse_args()
    verify_frozen_extensions(
        arguments.profile,
        arguments.product,
        arguments.frozen_dir,
    )


if __name__ == "__main__":
    main()

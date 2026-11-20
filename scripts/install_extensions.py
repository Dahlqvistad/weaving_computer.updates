"""Install the exact extension packages selected by a release profile."""

from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tomllib

type Product = Literal["host", "frontend"]


@dataclass(frozen=True, slots=True)
class ExtensionSource:
    extension_id: str
    repository: str
    ref: str
    host_path: Path
    frontend_path: Path

    def package_path(self, product: Product) -> Path:
        return self.host_path if product == "host" else self.frontend_path


def load_profile(profile_path: Path) -> tuple[ExtensionSource, ...]:
    payload = tomllib.loads(profile_path.read_text(encoding="utf-8"))
    if payload.get("profile_version") != 1:
        raise ValueError("Extension profile_version must be 1")
    raw_extensions = payload.get("extensions")
    if not isinstance(raw_extensions, list):
        raise ValueError("Extension profile must contain an extensions array")
    extensions: list[ExtensionSource] = []
    identifiers: set[str] = set()
    for raw_extension in raw_extensions:
        if not isinstance(raw_extension, dict):
            raise ValueError("Each extension profile entry must be an object")
        required = (
            "id",
            "repository",
            "ref",
            "host_path",
            "frontend_path",
        )
        if any(
            not isinstance(raw_extension.get(key), str)
            or not raw_extension[key].strip()
            for key in required
        ):
            raise ValueError("Extension profile entries require non-empty strings")
        extension_id = raw_extension["id"].strip()
        if extension_id in identifiers:
            raise ValueError(f"Duplicate extension ID: {extension_id}")
        identifiers.add(extension_id)
        extensions.append(
            ExtensionSource(
                extension_id=extension_id,
                repository=raw_extension["repository"].strip(),
                ref=raw_extension["ref"].strip(),
                host_path=_safe_relative_path(raw_extension["host_path"]),
                frontend_path=_safe_relative_path(raw_extension["frontend_path"]),
            )
        )
    return tuple(extensions)


def install_extensions(profile_path: Path, product: Product) -> None:
    entry_point_group = f"wc_split.{product}_extensions"
    with tempfile.TemporaryDirectory(prefix="wc-split-extensions-") as temp_dir:
        checkout_root = Path(temp_dir)
        for extension in load_profile(profile_path):
            checkout = checkout_root / extension.extension_id
            _run(
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "--no-tags",
                extension.repository,
                str(checkout),
            )
            _run(
                "git",
                "-C",
                str(checkout),
                "fetch",
                "--depth=1",
                "origin",
                extension.ref,
            )
            _run("git", "-C", str(checkout), "switch", "--detach", "FETCH_HEAD")
            package = checkout / extension.package_path(product)
            if not (package / "pyproject.toml").is_file():
                raise RuntimeError(f"Extension package does not exist: {package}")
            _run(sys.executable, "-m", "pip", "install", str(package))

    installed_ids = {
        entry_point.name
        for entry_point in importlib.metadata.entry_points(group=entry_point_group)
    }
    expected_ids = {
        extension.extension_id for extension in load_profile(profile_path)
    }
    missing = expected_ids - installed_ids
    if missing:
        raise RuntimeError(
            f"Installed packages did not register {entry_point_group}: "
            f"{', '.join(sorted(missing))}"
        )


def _safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Extension package path must be relative and safe: {value}")
    return path


def _run(*arguments: str) -> None:
    subprocess.run(arguments, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--product", required=True, choices=("host", "frontend"))
    arguments = parser.parse_args()
    install_extensions(arguments.profile, arguments.product)


if __name__ == "__main__":
    main()

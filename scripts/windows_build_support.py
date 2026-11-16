"""Shared, side-effect-limited helpers for local Windows release builds."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts import install_extensions
from scripts import publish_release as release_support


@dataclass(frozen=True, slots=True)
class WindowsProduct:
    name: str
    repository: str
    spec: str
    pack_id: str
    pack_title: str
    pack_directory: Path
    main_executable: str


@dataclass(frozen=True, slots=True)
class ExtensionCheckout:
    source: install_extensions.ExtensionSource
    directory: Path
    commit: str


PRODUCTS = (
    WindowsProduct(
        name="host",
        repository="Dahlqvistad/weaving_computer.host",
        spec="wc_split_host_windows.spec",
        pack_id="WeavingComputer.Host",
        pack_title="Vävdator Server",
        pack_directory=Path("dist") / "Vävdator Server",
        main_executable="Vävdator Server.exe",
    ),
    WindowsProduct(
        name="frontend",
        repository="Dahlqvistad/weaving_computer.frontend",
        spec="wc_split_app_windows.spec",
        pack_id="WeavingComputer.Frontend",
        pack_title="Vävdatorn",
        pack_directory=Path("dist") / "Vävdatorn",
        main_executable="Vävdatorn.exe",
    ),
)


def run(
    *arguments: str,
    cwd: Path,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    print(f"[{cwd}]> {' '.join(arguments)}", flush=True)
    result = subprocess.run(
        arguments,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if check and result.returncode != 0:
        detail = result.stdout.strip() if result.stdout else "No command output."
        raise RuntimeError(f"Command failed: {' '.join(arguments)}\n{detail}")
    return result


def output(*arguments: str, cwd: Path) -> str:
    return run(*arguments, cwd=cwd, capture=True).stdout.strip()


def clone_product(
    product: WindowsProduct,
    workspace: Path,
    updates_root: Path,
) -> Path:
    destination = workspace / product.name
    run(
        "git",
        "clone",
        "--branch",
        "main",
        "--single-branch",
        f"https://github.com/{product.repository}.git",
        str(destination),
        cwd=updates_root,
    )
    return destination


def _checkout_ref(
    source: install_extensions.ExtensionSource,
    directory: Path,
    updates_root: Path,
) -> str:
    run(
        "git",
        "clone",
        "--filter=blob:none",
        "--no-checkout",
        source.repository,
        str(directory),
        cwd=updates_root,
    )
    checkout = run(
        "git",
        "checkout",
        "--detach",
        source.ref,
        cwd=directory,
        check=False,
        capture=True,
    )
    if checkout.returncode != 0:
        run("git", "checkout", "--detach", "origin/main", cwd=directory)
    commit = output("git", "rev-parse", "HEAD", cwd=directory)
    validate_extension_checkout(source, directory)
    return commit


def validate_extension_checkout(
    source: install_extensions.ExtensionSource,
    directory: Path,
) -> None:
    host_version = release_support.project_version(
        directory / source.host_path / "pyproject.toml"
    )
    frontend_version = release_support.project_version(
        directory / source.frontend_path / "pyproject.toml"
    )
    expected_ref = f"{source.extension_id}-v{host_version}"
    if host_version != frontend_version or source.ref != expected_ref:
        raise RuntimeError(
            f"Extension ref {source.ref!r} is inconsistent. Host/frontend versions "
            f"must match and produce the expected ref {expected_ref!r}."
        )


def prepare_extension_profile(
    profile_path: Path,
    workspace: Path,
    updates_root: Path,
) -> tuple[Path, tuple[ExtensionCheckout, ...]]:
    checkouts: list[ExtensionCheckout] = []
    for source in install_extensions.load_profile(profile_path):
        directory = workspace / "extensions" / source.extension_id
        directory.parent.mkdir(parents=True, exist_ok=True)
        commit = _checkout_ref(source, directory, updates_root)
        checkouts.append(ExtensionCheckout(source, directory, commit))
    checkout_tuple = tuple(checkouts)
    resolved_profile = workspace / "extensions.resolved.toml"
    resolved_profile.write_text(
        render_resolved_profile(checkout_tuple),
        encoding="utf-8",
    )
    return resolved_profile, checkout_tuple


def render_resolved_profile(checkouts: tuple[ExtensionCheckout, ...]) -> str:
    lines = ["profile_version = 1", ""]
    for checkout in checkouts:
        source = checkout.source
        lines.extend(
            (
                "[[extensions]]",
                f"id = {json.dumps(source.extension_id)}",
                f"repository = {json.dumps(source.repository)}",
                f"ref = {json.dumps(checkout.commit)}",
                f"host_path = {json.dumps(source.host_path.as_posix())}",
                f"frontend_path = {json.dumps(source.frontend_path.as_posix())}",
                "",
            )
        )
    return "\n".join(lines)


def venv_python(repository: Path) -> Path:
    return repository.parent / "venvs" / repository.name / "Scripts" / "python.exe"


def build_product(
    product: WindowsProduct,
    repository: Path,
    resolved_profile: Path,
    extension_checkouts: tuple[ExtensionCheckout, ...],
    version: str,
    sequence: int,
    vpk: Path,
    *,
    skip_tests: bool,
) -> Path:
    release_support.update_project_version(repository / "pyproject.toml", version)
    python = venv_python(repository)
    python.parent.parent.mkdir(parents=True, exist_ok=True)
    run(
        sys.executable,
        "-m",
        "venv",
        str(python.parent.parent),
        cwd=repository,
    )
    run(str(python), "-m", "pip", "install", "--upgrade", "pip", cwd=repository)
    run(str(python), "-m", "pip", "install", ".[dev]", cwd=repository)
    run(
        str(python),
        str(release_support.UPDATES_ROOT / "scripts/install_extensions.py"),
        "--profile",
        str(resolved_profile),
        "--product",
        product.name,
        cwd=repository,
    )
    if not skip_tests:
        run(str(python), "-m", "ruff", "check", "src", "tests", cwd=repository)
        if product.name == "frontend":
            run(str(python), "-m", "ruff", "check", "scripts", cwd=repository)
            run(str(python), "scripts/check_translations.py", cwd=repository)
        run(str(python), "-m", "pytest", "-q", cwd=repository)
        for extension in extension_checkouts:
            package = extension.source.package_path(product.name)
            extension_directory = extension.directory / package
            run(
                str(python),
                "-m",
                "ruff",
                "check",
                "src",
                "tests",
                cwd=extension_directory,
            )
            run(str(python), "-m", "pytest", "-q", cwd=extension_directory)

    run(
        str(python),
        "scripts/generate_release_identity.py",
        "--version",
        version,
        "--sequence",
        str(sequence),
        "--platform",
        "windows",
        "--architecture",
        "x86_64",
        cwd=repository,
    )
    run(
        str(python),
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        product.spec,
        cwd=repository,
    )
    release_directory = repository.parent / "artifacts" / product.name
    release_directory.mkdir(parents=True)
    run(
        str(vpk),
        "pack",
        "--packId",
        product.pack_id,
        "--packTitle",
        product.pack_title,
        "--packVersion",
        version,
        "--packDir",
        str(product.pack_directory),
        "--mainExe",
        product.main_executable,
        "--channel",
        "stable",
        "--runtime",
        "win-x64",
        "--outputDir",
        str(release_directory),
        "--icon",
        "app-icon.ico",
        cwd=repository,
    )
    verify_release_assets(release_directory)
    return release_directory


def verify_release_assets(release_directory: Path) -> None:
    names = [path.name for path in release_directory.iterdir() if path.is_file()]
    required = ("Setup.exe", "Portable.zip", "-full.nupkg")
    missing = [
        suffix
        for suffix in required
        if not any(name.endswith(suffix) for name in names)
    ]
    if missing or "releases.stable.json" not in names:
        detail = [*missing]
        if "releases.stable.json" not in names:
            detail.append("releases.stable.json")
        raise RuntimeError(f"Release output is missing: {', '.join(detail)}")

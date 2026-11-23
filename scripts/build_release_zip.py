#!/usr/bin/env python3
"""Package and inspect only tracked, releasable project files."""

from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {
    ".agents",
    ".aws",
    ".codex",
    ".git",
    ".github-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    "__pycache__",
    ".test-build",
    ".vite",
    "test-artifacts",
    "dist",
    "build",
}
REQUIRED_PATHS = {
    "README.md",
    "Dockerfile",
    "render.yaml",
    "netlify.toml",
    "api/pyproject.toml",
    "web/package.json",
    "docs/deployment.md",
    "docs/portfolio-case-study.md",
    "docs/screenshots/01-dashboard-desktop.png",
    "docs/screenshots/02-incident-detail-desktop.png",
    "docs/screenshots/03-stored-replay-desktop.png",
    "docs/screenshots/04-simulated-approval-desktop.png",
    "docs/screenshots/05-dashboard-mobile.png",
}


def forbidden(path: PurePosixPath) -> bool:
    parts = path.parts
    if any(part in FORBIDDEN_PARTS or part.startswith(".git") for part in parts):
        return True
    name = path.name.lower()
    allowed_env_examples = {".env.example", "web/.env.development.fixture.example"}
    if name == ".env" or (
        name.startswith(".env.") and path.as_posix() not in allowed_env_examples
    ):
        return True
    if name.endswith((".pem", ".key", ".p12", ".pfx", ".sqlite", ".db")):
        return True
    if name.endswith(".zip") or name.endswith(".pyc") or name.endswith(".tsbuildinfo"):
        return True
    if name in {"id_rsa", "id_ed25519", "credentials", "secrets.json"}:
        return True
    return False


def tracked_paths() -> list[PurePosixPath]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    paths = [PurePosixPath(item.decode()) for item in result.stdout.split(b"\0") if item]
    return [path for path in paths if not forbidden(path)]


def inspect_archive(archive: Path) -> tuple[int, int]:
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
        if bad:
            raise ValueError(f"Archive CRC verification failed for {bad}")
        names = set(zf.namelist())
        required_missing = REQUIRED_PATHS - names
        if required_missing:
            raise ValueError(f"Archive is missing required project files: {sorted(required_missing)}")
        prohibited = [name for name in names if forbidden(PurePosixPath(name))]
        if prohibited:
            raise ValueError(f"Archive contains prohibited paths: {sorted(prohibited)}")
        return len(names), sum(info.file_size for info in zf.infolist())


def build(output: Path) -> tuple[int, int]:
    paths = tracked_paths()
    if not paths:
        raise ValueError("No tracked project files were found. Run this command in a Git checkout.")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for relative in paths:
            source = ROOT.joinpath(*relative.parts)
            if not source.is_file():
                continue
            resolved = source.resolve()
            if ROOT not in resolved.parents:
                raise ValueError(f"Tracked path resolves outside the project root: {relative}")
            zf.write(source, relative.as_posix())
            count += 1
    if not count:
        raise ValueError("No releasable tracked files were written to the archive.")
    return inspect_archive(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "incident-atlas-release.zip",
        help="Destination archive (default: repository root).",
    )
    args = parser.parse_args()
    try:
        count, size = build(args.output)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"Release archive failed: {exc}", file=sys.stderr)
        return 1
    print(f"Inspected {count} tracked project files ({size:,} uncompressed bytes).")
    print(f"Release archive: {args.output.resolve()}")
    print("Excluded generated output, local environments, secrets, caches, and Git metadata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

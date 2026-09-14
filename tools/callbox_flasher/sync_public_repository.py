from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
from pathlib import Path

EXPECTED_REMOTE = "github.com/Tunglam0605/Setup-Callbox"
PRESERVE = {".git", "LICENSE"}
FORBIDDEN_SUFFIXES = {".py", ".pyc", ".ps1", ".spec", ".c", ".h", ".cpp", ".hpp"}



def _remove_readonly(func, path, _exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def remove_tree(path: Path) -> None:
    shutil.rmtree(path, onerror=_remove_readonly)

def git_output(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def verify_public_bundle(bundle: Path) -> None:
    required = {
        "Setup-CallBox.exe",
        "Setup-CallBox.exe.sha256",
        "release-manifest.json",
        "README.md",
        ".gitignore",
    }
    missing = [name for name in required if not (bundle / name).is_file()]
    if missing:
        raise RuntimeError(f"Public bundle thiếu: {', '.join(missing)}")
    for path in bundle.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise RuntimeError(f"Public bundle chứa source/build file: {path}")
        lower_parts = {part.lower() for part in path.parts}
        if "src" in lower_parts or "tests" in lower_parts or "test" in lower_parts:
            raise RuntimeError(f"Public bundle chứa source/test tree: {path}")
        if path.name == "Setup-CallBox.factory.json":
            raise RuntimeError("Không được publish factory profile thật.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize verified binary-only bundle into Setup-Callbox clone")
    parser.add_argument("repository", type=Path)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    repo = args.repository.resolve()
    bundle = args.bundle.resolve()

    if not (repo / ".git").is_dir():
        raise SystemExit(f"Not a git repository: {repo}")
    origin = git_output(repo, "remote", "get-url", "origin")
    normalized = origin.replace("https://", "").replace("http://", "").replace(".git", "").rstrip("/")
    if normalized.lower() != EXPECTED_REMOTE.lower():
        raise SystemExit(f"Refusing to modify unexpected repository origin: {origin}")
    verify_public_bundle(bundle)

    for child in repo.iterdir():
        if child.name in PRESERVE:
            continue
        if child.is_dir():
            remove_tree(child)
        else:
            child.unlink()

    for source in bundle.iterdir():
        target = repo / source.name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)

    verify_public_bundle(repo)
    print(f"Synchronized public repository: {repo}")
    print(f"Origin: {origin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

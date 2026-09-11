"""Portable Windows self-update support for Setup CallBox.

The updater stays independent from ESP32 flashing logic. It checks the latest
GitHub Release, validates immutable asset URLs, downloads the EXE plus SHA-256
sidecar, verifies the digest, then launches the downloaded EXE as a helper that
replaces and relaunches the current executable after exit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

REPOSITORY = "Tunglam0605/Setup-Callbox"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
UPDATE_ASSET_NAME = "Setup-CallBox.exe"
UPDATE_HASH_NAME = UPDATE_ASSET_NAME + ".sha256"
USER_AGENT = "AUBOT-Setup-CallBox-Updater/1.0"
MAX_EXE_SIZE = 128 * 1024 * 1024
MAX_METADATA_SIZE = 512 * 1024
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class UpdateError(RuntimeError):
    """Update discovery, verification or installation failed."""


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        match = SEMVER_RE.fullmatch(str(value).strip())
        if not match:
            raise ValueError(f"Invalid semantic version: {value!r}")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ReleaseInfo:
    version: SemVer
    tag: str
    notes: str
    release_page: str
    exe_url: str
    hash_url: str
    exe_size: int


@dataclass(frozen=True)
class UpdateCheckResult:
    available: bool
    release: ReleaseInfo


def _validate_release_url(url: str, tag: str, filename: str) -> None:
    parsed = urlparse(url)
    expected_path = f"/{REPOSITORY}/releases/download/{tag}/{filename}"
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.path != expected_path
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise UpdateError(f"Unsafe or unexpected release asset URL for {filename}.")


def _read_limited(response, limit: int, label: str) -> bytes:
    length = response.headers.get("Content-Length")
    if length is not None and int(length) > limit:
        raise UpdateError(f"{label} is larger than the supported limit.")
    data = response.read(limit + 1)
    if len(data) > limit:
        raise UpdateError(f"{label} is larger than the supported limit.")
    return data


class GitHubReleaseUpdater:
    def __init__(
        self,
        api_url: str = LATEST_RELEASE_API,
        opener: Callable = urllib.request.urlopen,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_url = api_url
        self.opener = opener
        self.timeout_seconds = timeout_seconds

    def _open(self, url: str):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        return self.opener(req, timeout=self.timeout_seconds)

    def check(self, current_version: str) -> UpdateCheckResult:
        try:
            current = SemVer.parse(current_version)
        except ValueError as exc:
            raise UpdateError("Current Setup CallBox version is invalid.") from exc
        try:
            with self._open(self.api_url) as response:
                raw = _read_limited(response, MAX_METADATA_SIZE, "GitHub release metadata")
        except UpdateError:
            raise
        except Exception as exc:
            raise UpdateError(f"Cannot check GitHub Releases: {exc}") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateError("GitHub release metadata is not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise UpdateError("GitHub release metadata has an invalid shape.")

        tag = str(payload.get("tag_name", "")).strip()
        if not tag.startswith("v"):
            raise UpdateError("Latest release tag must use the vX.Y.Z format.")
        try:
            version = SemVer.parse(tag[1:])
        except ValueError as exc:
            raise UpdateError("Latest release tag is not semantic versioning.") from exc
        if payload.get("draft") or payload.get("prerelease"):
            raise UpdateError("Latest API result is not a stable release.")

        release_page = str(payload.get("html_url", ""))
        expected_page = f"https://github.com/{REPOSITORY}/releases/tag/{tag}"
        if release_page != expected_page:
            raise UpdateError("Latest release page does not belong to Setup-Callbox.")

        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise UpdateError("Latest release does not contain an asset list.")
        by_name = {str(a.get("name")): a for a in assets if isinstance(a, dict)}
        exe_asset = by_name.get(UPDATE_ASSET_NAME)
        hash_asset = by_name.get(UPDATE_HASH_NAME)
        if exe_asset is None or hash_asset is None:
            raise UpdateError("Latest release is missing Setup-CallBox.exe or its SHA-256 file.")

        exe_url = str(exe_asset.get("browser_download_url", ""))
        hash_url = str(hash_asset.get("browser_download_url", ""))
        _validate_release_url(exe_url, tag, UPDATE_ASSET_NAME)
        _validate_release_url(hash_url, tag, UPDATE_HASH_NAME)
        try:
            exe_size = int(exe_asset.get("size", 0))
        except (TypeError, ValueError) as exc:
            raise UpdateError("Release EXE size is invalid.") from exc
        if exe_size <= 0 or exe_size > MAX_EXE_SIZE:
            raise UpdateError("Release EXE size is outside the supported range.")

        release = ReleaseInfo(
            version=version,
            tag=tag,
            notes=str(payload.get("body", ""))[:20000],
            release_page=release_page,
            exe_url=exe_url,
            hash_url=hash_url,
            exe_size=exe_size,
        )
        return UpdateCheckResult(version > current, release)

    def download(
        self,
        release: ReleaseInfo,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> tuple[Path, str]:
        progress_cb = progress or (lambda _done, _total: None)
        try:
            with self._open(release.hash_url) as response:
                hash_text = _read_limited(response, 4096, "SHA-256 metadata").decode("utf-8")
        except UpdateError:
            raise
        except Exception as exc:
            raise UpdateError(f"Cannot download SHA-256 metadata: {exc}") from exc

        fields = hash_text.strip().split()
        if not fields or not SHA256_RE.fullmatch(fields[0]):
            raise UpdateError("Release SHA-256 metadata is invalid.")
        expected_sha = fields[0].lower()
        if len(fields) >= 2 and Path(fields[-1].lstrip("*")).name != UPDATE_ASSET_NAME:
            raise UpdateError("Release SHA-256 metadata references the wrong file.")

        base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        dest_dir = base / "AUBOT" / "Setup-CallBox" / "updates" / release.tag
        dest_dir.mkdir(parents=True, exist_ok=True)
        final_path = dest_dir / UPDATE_ASSET_NAME
        temp_path = dest_dir / (UPDATE_ASSET_NAME + ".part")
        digest = hashlib.sha256()
        received = 0
        try:
            with self._open(release.exe_url) as response, temp_path.open("wb") as out:
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) != release.exe_size:
                    raise UpdateError("Release EXE Content-Length does not match GitHub metadata.")
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > release.exe_size:
                        raise UpdateError("Downloaded EXE is larger than GitHub metadata.")
                    digest.update(chunk)
                    out.write(chunk)
                    progress_cb(received, release.exe_size)
                out.flush()
                os.fsync(out.fileno())
            if received != release.exe_size:
                raise UpdateError("Downloaded EXE size does not match GitHub metadata.")
            actual_sha = digest.hexdigest()
            if actual_sha != expected_sha:
                raise UpdateError("Downloaded EXE SHA-256 verification failed.")
            os.replace(temp_path, final_path)
            return final_path, actual_sha
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise


def launch_update_helper(
    downloaded_exe: Path,
    target_exe: Path,
    parent_pid: int,
    expected_sha256: str,
) -> None:
    source = Path(downloaded_exe).resolve()
    target = Path(target_exe).resolve()
    if not source.is_file():
        raise UpdateError("Verified update EXE is missing.")
    if target.suffix.lower() != ".exe":
        raise UpdateError("Current application target must be an EXE.")
    subprocess.Popen(
        [
            str(source),
            "--apply-update",
            "--target",
            str(target),
            "--parent-pid",
            str(int(parent_pid)),
            "--expected-sha256",
            expected_sha256.lower(),
        ],
        close_fds=True,
        shell=False,
        cwd=str(source.parent),
    )


def _wait_for_windows_process(pid: int, timeout_seconds: float = 60.0) -> None:
    if pid <= 0:
        return
    if sys.platform != "win32":
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.1)
        raise UpdateError("Timed out waiting for the old application process to exit.")

    import ctypes
    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(synchronize, False, int(pid))
    if not handle:
        return
    try:
        result = kernel32.WaitForSingleObject(handle, int(timeout_seconds * 1000))
        if result == wait_timeout:
            raise UpdateError("Timed out waiting for the old application process to exit.")
        if result != wait_object_0:
            raise UpdateError("Failed while waiting for the old application process.")
    finally:
        kernel32.CloseHandle(handle)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def apply_verified_update(
    source_executable: Path,
    target_executable: Path,
    parent_pid: int,
    expected_sha256: str,
    relaunch: bool = True,
) -> None:
    source = Path(source_executable).resolve()
    target = Path(target_executable).resolve()
    if not source.is_file():
        raise UpdateError("Update helper executable does not exist.")
    if not SHA256_RE.fullmatch(expected_sha256 or ""):
        raise UpdateError("Expected update SHA-256 is invalid.")
    if file_sha256(source).lower() != expected_sha256.lower():
        raise UpdateError("Update helper EXE no longer matches the verified SHA-256.")
    if target.suffix.lower() != ".exe" or not target.parent.is_dir():
        raise UpdateError("Update target is invalid.")
    if source == target:
        raise UpdateError("Update helper cannot replace itself in place.")

    _wait_for_windows_process(parent_pid)
    new_path = target.with_name(target.name + ".update-new")
    backup_path = target.with_name(target.name + ".update-backup")
    try:
        if target.exists():
            shutil.copy2(target, backup_path)
        shutil.copy2(source, new_path)
        if file_sha256(new_path).lower() != expected_sha256.lower():
            raise UpdateError("Copied update EXE failed SHA-256 verification.")
        os.replace(new_path, target)
        if relaunch:
            subprocess.Popen([str(target)], close_fds=True, shell=False, cwd=str(target.parent))
        backup_path.unlink(missing_ok=True)
    except Exception as exc:
        try:
            new_path.unlink(missing_ok=True)
        except Exception:
            pass
        if backup_path.exists():
            try:
                os.replace(backup_path, target)
            except Exception:
                pass
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError(f"Cannot replace the current Setup CallBox EXE: {exc}") from exc

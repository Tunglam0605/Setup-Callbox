"""Verified public release catalog, firmware cache and portable self-update.

Private source code builds the executable and firmware images.  The public
Setup-Callbox repository is only a release channel containing binaries and
manifests.  Every downloaded artifact is size- and SHA-256-verified before use.
"""
from __future__ import annotations

import hashlib
import hmac
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

from tools.callbox_flasher.src.flash_manifest import BaselineManifest, load_baseline_manifest
from tools.callbox_flasher.src.image_validator import validate_application

PUBLIC_REPOSITORY = "Tunglam0605/Setup-Callbox"
RAW_BASE = f"https://raw.githubusercontent.com/{PUBLIC_REPOSITORY}/main"
RELEASE_MANIFEST_URL = f"{RAW_BASE}/release-manifest.json"
PUBLIC_GITHUB_BASE = f"https://github.com/{PUBLIC_REPOSITORY}"
USER_AGENT = "AUBOT-Setup-CallBox/1.2"
SCHEMA_VERSION = 1
MAX_JSON_SIZE = 256 * 1024
MAX_TOOL_SIZE = 128 * 1024 * 1024
MAX_FIRMWARE_FILE_SIZE = 8 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        match = SEMVER_RE.fullmatch(str(value).strip())
        if not match:
            raise ValueError(f"Semantic version không hợp lệ: {value!r}")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ToolRelease:
    version: SemVer
    filename: str
    size: int
    sha256: str
    url: str


@dataclass(frozen=True)
class FirmwareRelease:
    package_version: SemVer
    firmware_version: SemVer
    min_tool_version: SemVer
    manifest_url: str


@dataclass(frozen=True)
class ReleaseCatalog:
    channel: str
    tool: ToolRelease
    firmware: FirmwareRelease


@dataclass(frozen=True)
class RemoteImage:
    role: str
    offset: int
    filename: str
    size: int
    sha256: str
    url: str


@dataclass(frozen=True)
class RemoteFirmwarePackage:
    package_version: SemVer
    chip: str
    flash_size: str
    flash_mode: str
    flash_frequency: str
    baud: int
    images: tuple[RemoteImage, ...]
    application: RemoteImage


def cache_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
    return base / "AUBOT" / "Setup-CallBox"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_release_url(url: str, *, firmware_prefix: str | None = None) -> str:
    parsed = urlparse(str(url))
    if parsed.scheme != "https" or parsed.params or parsed.query or parsed.fragment:
        raise ReleaseError(f"URL phát hành không an toàn: {url}")
    host = parsed.netloc.lower()
    if host == "raw.githubusercontent.com":
        base_path = f"/{PUBLIC_REPOSITORY}/main/"
        if not parsed.path.startswith(base_path):
            raise ReleaseError("Raw URL không thuộc Setup-Callbox.")
        if firmware_prefix and not parsed.path.startswith(base_path + firmware_prefix.strip("/") + "/"):
            raise ReleaseError("Firmware URL nằm ngoài thư mục package được phép.")
    elif host == "github.com":
        if not parsed.path.startswith(f"/{PUBLIC_REPOSITORY}/"):
            raise ReleaseError("GitHub URL không thuộc Setup-Callbox.")
    else:
        raise ReleaseError(f"Host phát hành không được phép: {host}")
    return url


def _int_offset(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.lower().startswith("0x") else int(value)
    raise ValueError("offset must be int or string")


def _validate_hash(value: str) -> str:
    value = str(value).strip().lower()
    if not SHA256_RE.fullmatch(value):
        raise ReleaseError("SHA-256 trong manifest không hợp lệ.")
    return value


class ReleaseManager:
    def __init__(
        self,
        current_tool_version: str,
        *,
        manifest_url: str = RELEASE_MANIFEST_URL,
        opener: Callable = urllib.request.urlopen,
        timeout_seconds: float = 8.0,
        root: Path | None = None,
    ) -> None:
        self.current_tool_version = SemVer.parse(current_tool_version)
        self.manifest_url = _safe_release_url(manifest_url)
        self.opener = opener
        self.timeout_seconds = timeout_seconds
        self.root = Path(root) if root is not None else cache_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def _open(self, url: str):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json,application/octet-stream"},
        )
        return self.opener(request, timeout=self.timeout_seconds)

    def _read_limited(self, response, limit: int, label: str) -> bytes:
        raw_len = response.headers.get("Content-Length")
        if raw_len is not None:
            try:
                if int(raw_len) > limit:
                    raise ReleaseError(f"{label} vượt quá kích thước cho phép.")
            except ValueError:
                pass
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ReleaseError(f"{label} vượt quá kích thước cho phép.")
        return data

    def _fetch_json(self, url: str) -> dict:
        _safe_release_url(url)
        try:
            with self._open(url) as response:
                raw = self._read_limited(response, MAX_JSON_SIZE, "Release manifest")
            data = json.loads(raw.decode("utf-8"))
        except ReleaseError:
            raise
        except Exception as exc:
            raise ReleaseError(f"Không thể tải release manifest: {exc}") from exc
        if not isinstance(data, dict):
            raise ReleaseError("Release manifest phải là JSON object.")
        return data

    def fetch_catalog(self) -> ReleaseCatalog:
        data = self._fetch_json(self.manifest_url)
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ReleaseError("schema_version của release manifest không được hỗ trợ.")
        if data.get("channel") != "stable":
            raise ReleaseError("Tool chỉ nhận channel stable.")
        tool = data.get("tool")
        firmware = data.get("firmware")
        if not isinstance(tool, dict) or not isinstance(firmware, dict):
            raise ReleaseError("Release manifest thiếu tool hoặc firmware.")

        tool_version = SemVer.parse(str(tool.get("version", "")))
        tool_filename = str(tool.get("filename", ""))
        if tool_filename != "Setup-CallBox.exe":
            raise ReleaseError("Tên tool release không hợp lệ.")
        tool_size = int(tool.get("size", 0))
        if tool_size <= 0 or tool_size > MAX_TOOL_SIZE:
            raise ReleaseError("Kích thước tool release không hợp lệ.")
        tool_release = ToolRelease(
            version=tool_version,
            filename=tool_filename,
            size=tool_size,
            sha256=_validate_hash(tool.get("sha256", "")),
            url=_safe_release_url(str(tool.get("url", ""))),
        )

        fw_package = SemVer.parse(str(firmware.get("package_version", "")))
        fw_version = SemVer.parse(str(firmware.get("firmware_version", "")))
        min_tool = SemVer.parse(str(firmware.get("min_tool_version", "")))
        manifest_url = _safe_release_url(
            str(firmware.get("manifest_url", "")),
            firmware_prefix=f"firmware/v{fw_package}",
        )
        return ReleaseCatalog(
            channel="stable",
            tool=tool_release,
            firmware=FirmwareRelease(
                package_version=fw_package,
                firmware_version=fw_version,
                min_tool_version=min_tool,
                manifest_url=manifest_url,
            ),
        )

    def tool_update_available(self, catalog: ReleaseCatalog) -> bool:
        return catalog.tool.version > self.current_tool_version

    def embedded_firmware_manifest(self) -> BaselineManifest:
        manifest = load_baseline_manifest()
        manifest.verify_assets()
        return manifest

    def _active_pointer_path(self) -> Path:
        return self.root / "active-firmware.json"

    def active_firmware_version(self) -> SemVer:
        try:
            manifest = self.load_active_firmware_manifest()
            return SemVer.parse(manifest.firmware_version)
        except Exception:
            return SemVer(0, 0, 0)

    def load_active_firmware_manifest(self) -> BaselineManifest:
        candidates: list[BaselineManifest] = []
        embedded_error: Exception | None = None
        try:
            candidates.append(self.embedded_firmware_manifest())
        except Exception as error:
            embedded_error = error

        pointer = self._active_pointer_path()
        if pointer.is_file():
            try:
                data = json.loads(pointer.read_text(encoding="utf-8"))
                version = SemVer.parse(str(data.get("package_version", "")))
                package_root = self.root / "firmware" / f"v{version}"
                manifest = load_baseline_manifest(package_root)
                manifest.verify_assets()
                candidates.append(manifest)
            except Exception:
                # Corrupted/partial cache must never block factory flashing.
                pass
        if candidates:
            return max(
                enumerate(candidates),
                key=lambda entry: (SemVer.parse(entry[1].firmware_version), entry[0]),
            )[1]
        if embedded_error is not None:
            raise embedded_error
        return self.embedded_firmware_manifest()

    def firmware_update_available(self, catalog: ReleaseCatalog) -> bool:
        if catalog.firmware.min_tool_version > self.current_tool_version:
            return False
        return catalog.firmware.firmware_version > self.active_firmware_version()

    def _parse_remote_firmware(self, data: dict, catalog: ReleaseCatalog) -> RemoteFirmwarePackage:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ReleaseError("Firmware manifest schema không được hỗ trợ.")
        package_version = SemVer.parse(str(data.get("package_version", "")))
        if package_version != catalog.firmware.package_version:
            raise ReleaseError("Firmware package version không khớp release catalog.")
        if str(data.get("firmware_version", "")) != str(catalog.firmware.firmware_version):
            raise ReleaseError("Firmware version không khớp release catalog.")
        chip = str(data.get("chip", ""))
        flash_size = str(data.get("flash_size", ""))
        flash_mode = str(data.get("flash_mode", ""))
        flash_frequency = str(data.get("flash_frequency", ""))
        baud = int(data.get("baud", 0))
        if (chip, flash_size, flash_mode, flash_frequency, baud) != ("esp32s3", "16MB", "dio", "80m", 460800):
            raise ReleaseError("Firmware package không đúng target ESP32-S3 16MB production.")

        package_prefix = f"firmware/v{package_version}"
        expected = {
            "bootloader": (0x0, "bootloader.bin"),
            "partition_table": (0x8000, "partition-table.bin"),
            "ota_data": (0x210000, "ota_data_initial.bin"),
        }
        raw_images = data.get("images")
        raw_app = data.get("application")
        if not isinstance(raw_images, list) or not isinstance(raw_app, dict):
            raise ReleaseError("Firmware manifest thiếu images/application.")

        def parse_image(item: dict, expected_role: str | None = None) -> RemoteImage:
            if not isinstance(item, dict):
                raise ReleaseError("Image entry không hợp lệ.")
            role = str(item.get("role", ""))
            if expected_role is not None and role != expected_role:
                raise ReleaseError(f"Sai role firmware: {role}")
            filename = str(item.get("filename", ""))
            if not filename or Path(filename).name != filename:
                raise ReleaseError("Tên file firmware không hợp lệ.")
            offset = _int_offset(item.get("offset"))
            size = int(item.get("size", 0))
            if size <= 0 or size > MAX_FIRMWARE_FILE_SIZE:
                raise ReleaseError(f"Kích thước {filename} không hợp lệ.")
            return RemoteImage(
                role=role,
                offset=offset,
                filename=filename,
                size=size,
                sha256=_validate_hash(item.get("sha256", "")),
                url=_safe_release_url(str(item.get("url", "")), firmware_prefix=package_prefix),
            )

        parsed: list[RemoteImage] = []
        by_role = {str(item.get("role", "")): item for item in raw_images if isinstance(item, dict)}
        if set(by_role) != set(expected):
            raise ReleaseError("Firmware package phải có đúng bootloader, partition_table và ota_data.")
        for role, (offset, filename) in expected.items():
            image = parse_image(by_role[role], role)
            if image.offset != offset or image.filename != filename:
                raise ReleaseError(f"Offset/tên file {role} không đúng production contract.")
            parsed.append(image)

        application = parse_image(raw_app, "application")
        if application.offset != 0x10000 or application.filename != "callbox_sews.bin":
            raise ReleaseError("Application phải là callbox_sews.bin tại 0x10000.")
        return RemoteFirmwarePackage(
            package_version=package_version,
            chip=chip,
            flash_size=flash_size,
            flash_mode=flash_mode,
            flash_frequency=flash_frequency,
            baud=baud,
            images=tuple(sorted(parsed, key=lambda item: item.offset)),
            application=application,
        )

    def _download_verified(
        self,
        url: str,
        destination: Path,
        expected_size: int,
        expected_sha256: str,
        progress: Optional[Callable[[str, int, int], None]] = None,
        label: str = "artifact",
    ) -> Path:
        _safe_release_url(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_suffix(destination.suffix + ".part")
        digest = hashlib.sha256()
        received = 0
        callback = progress or (lambda _label, _done, _total: None)
        try:
            with self._open(url) as response, temp_path.open("wb") as out:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > expected_size:
                        raise ReleaseError(f"{label} lớn hơn kích thước trong manifest.")
                    digest.update(chunk)
                    out.write(chunk)
                    callback(label, received, expected_size)
                out.flush()
                os.fsync(out.fileno())
            if received != expected_size:
                raise ReleaseError(f"{label} sai kích thước sau khi tải.")
            actual = digest.hexdigest().lower()
            if not hmac.compare_digest(actual, expected_sha256.lower()):
                raise ReleaseError(f"{label} sai SHA-256.")
            os.replace(temp_path, destination)
            return destination
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def sync_firmware(
        self,
        catalog: ReleaseCatalog,
        progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> BaselineManifest:
        if catalog.firmware.min_tool_version > self.current_tool_version:
            raise ReleaseError(
                f"Firmware v{catalog.firmware.firmware_version} yêu cầu tool >= v{catalog.firmware.min_tool_version}."
            )
        remote_data = self._fetch_json(catalog.firmware.manifest_url)
        package = self._parse_remote_firmware(remote_data, catalog)
        final_root = self.root / "firmware" / f"v{package.package_version}"
        assets = final_root / "assets"
        assets.mkdir(parents=True, exist_ok=True)

        for image in (*package.images, package.application):
            target = assets / image.filename
            if target.is_file() and target.stat().st_size == image.size:
                try:
                    if hmac.compare_digest(file_sha256(target), image.sha256):
                        continue
                except OSError:
                    pass
            self._download_verified(image.url, target, image.size, image.sha256, progress, image.role)

        local_manifest = {
            "baseline_version": f"release-{package.package_version}",
            "firmware_version": str(package.package_version),
            "chip": package.chip,
            "flash_size": package.flash_size,
            "flash_mode": package.flash_mode,
            "flash_frequency": package.flash_frequency,
            "baud": package.baud,
            "images": [
                {
                    "offset": hex(image.offset),
                    "filename": image.filename,
                    "size": image.size,
                    "sha256": image.sha256,
                }
                for image in package.images
            ],
            "application": {
                "offset": hex(package.application.offset),
                "filename": package.application.filename,
                "size": package.application.size,
                "sha256": package.application.sha256,
            },
        }
        manifest_path = assets / "baseline-manifest.json"
        temp_manifest = assets / "baseline-manifest.json.part"
        temp_manifest.write_text(json.dumps(local_manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_manifest, manifest_path)

        manifest = load_baseline_manifest(final_root)
        manifest.verify_assets()
        validate_application(manifest.application.path)
        if SemVer.parse(manifest.firmware_version) != catalog.firmware.firmware_version:
            raise ReleaseError("firmware_version trong cache không khớp release catalog.")

        pointer_data = {"package_version": str(package.package_version)}
        pointer_tmp = self._active_pointer_path().with_suffix(".json.part")
        pointer_tmp.write_text(json.dumps(pointer_data, indent=2) + "\n", encoding="utf-8")
        os.replace(pointer_tmp, self._active_pointer_path())
        return manifest

    def download_tool_update(
        self,
        catalog: ReleaseCatalog,
        progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> tuple[Path, str]:
        if not self.tool_update_available(catalog):
            raise ReleaseError("Không có phiên bản tool mới hơn.")
        dest = self.root / "updates" / f"v{catalog.tool.version}" / catalog.tool.filename
        self._download_verified(
            catalog.tool.url,
            dest,
            catalog.tool.size,
            catalog.tool.sha256,
            progress,
            "tool",
        )
        return dest, catalog.tool.sha256


def launch_update_helper(downloaded_exe: Path, target_exe: Path, parent_pid: int, expected_sha256: str) -> None:
    source = Path(downloaded_exe).resolve()
    target = Path(target_exe).resolve()
    if not source.is_file() or target.suffix.lower() != ".exe":
        raise ReleaseError("Đường dẫn self-update không hợp lệ.")
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


def _wait_for_process(pid: int, timeout_seconds: float = 60.0) -> None:
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
        raise ReleaseError("Timeout khi chờ tool cũ thoát.")
    import ctypes
    synchronize = 0x00100000
    wait_object_0 = 0
    wait_timeout = 0x00000102
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(synchronize, False, int(pid))
    if not handle:
        return
    try:
        result = kernel32.WaitForSingleObject(handle, int(timeout_seconds * 1000))
        if result == wait_timeout:
            raise ReleaseError("Timeout khi chờ tool cũ thoát.")
        if result != wait_object_0:
            raise ReleaseError("Không thể chờ process tool cũ.")
    finally:
        kernel32.CloseHandle(handle)


def apply_verified_update(
    source_executable: Path,
    target_executable: Path,
    parent_pid: int,
    expected_sha256: str,
    *,
    relaunch: bool = True,
) -> None:
    source = Path(source_executable).resolve()
    target = Path(target_executable).resolve()
    if not source.is_file() or target.suffix.lower() != ".exe" or not target.parent.is_dir():
        raise ReleaseError("Self-update target không hợp lệ.")
    expected = _validate_hash(expected_sha256)
    if not hmac.compare_digest(file_sha256(source), expected):
        raise ReleaseError("Update helper không còn khớp SHA-256 đã verify.")
    if source == target:
        raise ReleaseError("Update helper không thể tự thay chính nó tại cùng đường dẫn.")

    _wait_for_process(parent_pid)
    new_path = target.with_name(target.name + ".update-new")
    backup_path = target.with_name(target.name + ".update-backup")
    try:
        if target.exists():
            shutil.copy2(target, backup_path)
        shutil.copy2(source, new_path)
        if not hmac.compare_digest(file_sha256(new_path), expected):
            raise ReleaseError("Bản copy update sai SHA-256.")
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
        if isinstance(exc, ReleaseError):
            raise
        raise ReleaseError(f"Không thể thay tool hiện tại: {exc}") from exc

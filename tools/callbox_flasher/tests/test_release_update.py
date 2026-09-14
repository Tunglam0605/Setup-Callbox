import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.callbox_flasher.src.flash_manifest import load_baseline_manifest
from tools.callbox_flasher.src.image_validator import validate_application
from tools.callbox_flasher.src.release_update import (
    RAW_BASE,
    ReleaseError,
    ReleaseManager,
    SemVer,
)
from tools.callbox_flasher.src.ui_updates import UpdateUiMixin


class FakeResponse:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self.data) - self.pos
        chunk = self.data[self.pos:self.pos + size]
        self.pos += len(chunk)
        return chunk


class FakeOpener:
    def __init__(self, mapping):
        self.mapping = mapping

    def __call__(self, request, timeout=None):
        url = getattr(request, "full_url", request)
        if url not in self.mapping:
            raise OSError(f"unexpected URL: {url}")
        return FakeResponse(self.mapping[url])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReleaseUpdateTests(unittest.TestCase):
    def setUp(self):
        self.embedded = load_baseline_manifest()
        self.embedded.verify_assets()
        self.app_info = validate_application(self.embedded.application.path)
        self.fw_version = self.embedded.firmware_version
        self.fw_dir = f"firmware/v{self.fw_version}"
        self.fw_manifest_url = f"{RAW_BASE}/{self.fw_dir}/firmware-manifest.json"
        self.tool_url = f"{RAW_BASE}/Setup-CallBox.exe"
        self.tool_bytes = b"MZ" + b"tool-release" * 100

        role_by_name = {
            "bootloader.bin": "bootloader",
            "partition-table.bin": "partition_table",
            "ota_data_initial.bin": "ota_data",
        }
        images = []
        self.mapping = {}
        for image in self.embedded.images:
            data = image.path.read_bytes()
            url = f"{RAW_BASE}/{self.fw_dir}/{image.filename}"
            self.mapping[url] = data
            images.append({
                "role": role_by_name[image.filename],
                "offset": hex(image.offset),
                "filename": image.filename,
                "size": len(data),
                "sha256": sha(data),
                "url": url,
            })
        app_data = self.embedded.application.path.read_bytes()
        app_url = f"{RAW_BASE}/{self.fw_dir}/{self.embedded.application.filename}"
        self.mapping[app_url] = app_data
        application = {
            "role": "application",
            "offset": hex(self.embedded.application.offset),
            "filename": self.embedded.application.filename,
            "size": len(app_data),
            "sha256": sha(app_data),
            "url": app_url,
        }
        fw_manifest = {
            "schema_version": 1,
            "package_version": self.fw_version,
            "firmware_version": self.fw_version,
            "chip": "esp32s3",
            "flash_size": "16MB",
            "flash_mode": "dio",
            "flash_frequency": "80m",
            "baud": 460800,
            "images": images,
            "application": application,
        }
        self.mapping[self.fw_manifest_url] = json.dumps(fw_manifest).encode()

        catalog = {
            "schema_version": 1,
            "channel": "stable",
            "tool": {
                "version": "1.3.0",
                "filename": "Setup-CallBox.exe",
                "size": len(self.tool_bytes),
                "sha256": sha(self.tool_bytes),
                "url": self.tool_url,
            },
            "firmware": {
                "package_version": self.fw_version,
                "firmware_version": self.fw_version,
                "min_tool_version": "1.2.0",
                "manifest_url": self.fw_manifest_url,
            },
        }
        self.catalog_url = f"{RAW_BASE}/release-manifest.json"
        self.mapping[self.catalog_url] = json.dumps(catalog).encode()
        self.mapping[self.tool_url] = self.tool_bytes

    def test_semver_ordering(self):
        self.assertGreater(SemVer.parse("1.2.1"), SemVer.parse("1.2.0"))
        self.assertEqual(str(SemVer.parse("1.2.0")), "1.2.0")

    def test_catalog_and_tool_update_download_are_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ReleaseManager(
                "1.2.0",
                opener=FakeOpener(self.mapping),
                root=Path(tmp),
            )
            catalog = mgr.fetch_catalog()
            self.assertTrue(mgr.tool_update_available(catalog))
            path, digest = mgr.download_tool_update(catalog)
            self.assertEqual(path.read_bytes(), self.tool_bytes)
            self.assertEqual(digest, sha(self.tool_bytes))

    def test_firmware_sync_creates_verified_active_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ReleaseManager(
                "1.2.0",
                opener=FakeOpener(self.mapping),
                root=Path(tmp),
            )
            catalog = mgr.fetch_catalog()
            manifest = mgr.sync_firmware(catalog)
            manifest.verify_assets()
            active = mgr.load_active_firmware_manifest()
            self.assertTrue(active.baseline_version.startswith("release-"))
            validate_application(active.application.path)
            self.assertEqual(active.firmware_version, self.fw_version)

    def test_corrupt_cached_pointer_falls_back_to_embedded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "active-firmware.json").write_text('{"package_version":"9.9.9"}', encoding="utf-8")
            mgr = ReleaseManager("1.2.0", opener=FakeOpener(self.mapping), root=root)
            manifest = mgr.load_active_firmware_manifest()
            self.assertEqual(manifest.application.sha256, self.embedded.application.sha256)

    def test_older_verified_cache_cannot_override_newer_embedded_firmware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_root = root / "firmware" / "v1.5.3"
            assets = package_root / "assets"
            assets.mkdir(parents=True)
            for image in (*self.embedded.images, self.embedded.application):
                shutil.copy2(image.path, assets / image.filename)
            manifest_data = json.loads(
                (self.embedded.application.path.parent / "baseline-manifest.json").read_text(encoding="utf-8")
            )
            manifest_data["baseline_version"] = "release-1.5.3"
            manifest_data["firmware_version"] = "1.5.3"
            (assets / "baseline-manifest.json").write_text(
                json.dumps(manifest_data), encoding="utf-8"
            )
            (root / "active-firmware.json").write_text(
                '{"package_version":"1.5.3"}', encoding="utf-8"
            )

            mgr = ReleaseManager("1.3.6", opener=FakeOpener(self.mapping), root=root)
            active = mgr.load_active_firmware_manifest()

            self.assertEqual(active.firmware_version, "1.5.6")
            self.assertEqual(active.application.sha256, self.embedded.application.sha256)

    def test_wrong_sha_rejects_tool_download(self):
        broken = dict(self.mapping)
        catalog = json.loads(broken[self.catalog_url].decode())
        catalog["tool"]["sha256"] = "0" * 64
        broken[self.catalog_url] = json.dumps(catalog).encode()
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ReleaseManager("1.2.0", opener=FakeOpener(broken), root=Path(tmp))
            with self.assertRaises(ReleaseError):
                mgr.download_tool_update(mgr.fetch_catalog())

    def test_foreign_manifest_url_is_rejected(self):
        with self.assertRaises(ReleaseError):
            ReleaseManager("1.2.0", manifest_url="https://example.com/release-manifest.json")


class _Var:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class _UpdateUiHarness(UpdateUiMixin):
    def __init__(self, release_manager):
        self.release_manager = release_manager
        self.system_firmware_var = _Var()
        self.system_release_var = _Var()
        self._release_check_running = True

    def _worker_refresh_release_summary(self):
        pass

    def _worker_update_button_state(self):
        pass

    def _set_tool_update_buttons(self, *args, **kwargs):
        pass


class UpdateUiVersionTests(unittest.TestCase):
    def test_release_check_displays_active_firmware_not_older_catalog_version(self):
        embedded = load_baseline_manifest()
        manager = SimpleNamespace(
            load_active_firmware_manifest=lambda: embedded,
            tool_update_available=lambda _catalog: False,
        )
        ui = _UpdateUiHarness(manager)
        catalog = SimpleNamespace(
            firmware=SimpleNamespace(firmware_version=SemVer.parse("1.5.3")),
            tool=SimpleNamespace(version=SemVer.parse("1.3.6")),
        )

        ui._on_release_check_success(catalog, firmware_updated=False)

        self.assertEqual(ui.system_firmware_var.value, "v1.5.6")


if __name__ == "__main__":
    unittest.main()

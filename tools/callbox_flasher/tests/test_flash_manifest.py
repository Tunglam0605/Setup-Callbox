import hashlib
import pathlib
import shutil
import tempfile
import unittest

from tools.callbox_flasher.src.flash_manifest import (
    BaselineManifest,
    ManifestError,
    load_baseline_manifest,
)
from tools.callbox_flasher.src.resources import resource_path


class FlashManifestTests(unittest.TestCase):
    def test_approved_manifest_loads_four_fixed_contract_fields(self):
        manifest = load_baseline_manifest()
        self.assertEqual(manifest.baseline_version, "development-a95135d")
        self.assertEqual(
            [(item.offset, item.filename) for item in manifest.images],
            [(0x0, "bootloader.bin"), (0x8000, "partition-table.bin"),
             (0x210000, "ota_data_initial.bin")],
        )
        manifest.verify_assets()

    def test_modified_embedded_asset_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(resource_path("assets"), root / "assets")
            target = root / "assets" / "bootloader.bin"
            data = bytearray(target.read_bytes())
            data[0] ^= 0x01
            target.write_bytes(data)
            with self.assertRaisesRegex(ManifestError, "bootloader.bin.*SHA-256"):
                load_baseline_manifest(root).verify_assets()

    def test_asset_with_invalid_size_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            shutil.copytree(resource_path("assets"), root / "assets")
            target = root / "assets" / "bootloader.bin"
            target.write_bytes(target.read_bytes() + b"corrupt")
            with self.assertRaisesRegex(ManifestError, "bootloader.bin.*kích thước"):
                load_baseline_manifest(root).verify_assets()

    def test_invalid_chip_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            assets_dir = root / "assets"
            assets_dir.mkdir()
            (assets_dir / "baseline-manifest.json").write_text(
                '{"baseline_version": "development-a95135d", "chip": "esp32", "flash_size": "16MB", '
                '"flash_mode": "dio", "flash_frequency": "80m", "baud": 460800, "images": []}',
                encoding="utf-8"
            )
            with self.assertRaisesRegex(ManifestError, "esp32s3"):
                load_baseline_manifest(root)


if __name__ == "__main__":
    unittest.main()

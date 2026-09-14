import pathlib
import unittest
import serial

from tools.callbox_flasher.src.esptool_adapter import (
    EspToolAdapter,
    FlashToolError,
    ProbeResult,
    sanitize_log,
)
from tools.callbox_flasher.src.flash_manifest import load_baseline_manifest


class EspToolAdapterTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.adapter = EspToolAdapter(
            runner=lambda argv: self.calls.append(argv) or "MAC: aa:bb:cc:dd:ee:ff"
        )
        self.manifest = load_baseline_manifest()

    def test_probe_pins_esp32s3_before_destructive_work(self):
        result = self.adapter.probe("COM7", lambda _: None)
        self.assertEqual(result.mac, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(self.calls[0][-1], "read-mac")
        self.assertIn("esp32s3", self.calls[0])

    def test_write_uses_fixed_settings_and_offsets(self):
        self.adapter.write("COM7", self.manifest, pathlib.Path("application.bin"), lambda _: None)
        argv = self.calls[0]
        self.assertIn("write-flash", argv)
        self.assertEqual(argv[argv.index("--flash-size") + 1], "16MB")
        self.assertEqual(
            argv[-8:],
            [
                "0x0",
                str(self.manifest.images[0].path),
                "0x8000",
                str(self.manifest.images[1].path),
                "0x10000",
                "application.bin",
                "0x210000",
                str(self.manifest.images[2].path),
            ],
        )

    def test_verify_uses_same_four_images(self):
        self.adapter.verify("COM7", self.manifest, pathlib.Path("application.bin"), lambda _: None)
        argv = self.calls[0]
        self.assertIn("verify-flash", argv)
        self.assertNotIn("erase-flash", argv)
        self.assertEqual(
            argv[-8:],
            [
                "0x0",
                str(self.manifest.images[0].path),
                "0x8000",
                str(self.manifest.images[1].path),
                "0x10000",
                "application.bin",
                "0x210000",
                str(self.manifest.images[2].path),
            ],
        )

    def test_erase_calls_erase_flash(self):
        self.adapter.erase("COM7", self.manifest, lambda _: None)
        argv = self.calls[0]
        self.assertIn("erase-flash", argv)

    def test_erase_otadata_calls_erase_region(self):
        self.adapter.erase_otadata("COM7", self.manifest, lambda _: None)
        argv = self.calls[0]
        self.assertIn("erase-region", argv)
        self.assertIn("0x210000", argv)
        self.assertIn("0x2000", argv)

    def test_write_app_only_writes_single_offset(self):
        self.adapter.write_app("COM7", self.manifest, pathlib.Path("application.bin"), lambda _: None)
        argv = self.calls[0]
        self.assertIn("write-flash", argv)
        self.assertEqual(argv[-2:], ["0x10000", "application.bin"])

    def test_verify_app_only_verifies_single_offset(self):
        self.adapter.verify_app("COM7", self.manifest, pathlib.Path("application.bin"), lambda _: None)
        argv = self.calls[0]
        self.assertIn("verify-flash", argv)
        self.assertEqual(argv[-2:], ["0x10000", "application.bin"])

    def test_write_baseline_writes_three_embedded_images(self):
        self.adapter.write_baseline("COM7", self.manifest, lambda _: None)
        argv = self.calls[0]
        self.assertIn("write-flash", argv)
        self.assertNotIn("0x10000", argv)
        self.assertIn("0x0", argv)
        self.assertIn("0x8000", argv)
        self.assertIn("0x210000", argv)

    def test_verify_baseline_verifies_three_embedded_images(self):
        self.adapter.verify_baseline("COM7", self.manifest, lambda _: None)
        argv = self.calls[0]
        self.assertIn("verify-flash", argv)
        self.assertNotIn("0x10000", argv)
        self.assertIn("0x0", argv)
        self.assertIn("0x8000", argv)
        self.assertIn("0x210000", argv)

    def test_reset_calls_run_with_hard_reset(self):
        self.adapter.reset("COM7", self.manifest, lambda _: None)
        argv = self.calls[0]
        self.assertIn("run", argv)
        self.assertEqual(argv[argv.index("--after") + 1], "hard-reset")

    def test_port_busy_failure_translation(self):
        def failing_runner(argv):
            raise serial.SerialException("could not open port 'COM7': PermissionError(13, 'Access is denied.')")

        adapter = EspToolAdapter(runner=failing_runner)
        with self.assertRaisesRegex(FlashToolError, "Cổng COM7 đang được chương trình khác sử dụng"):
            adapter.probe("COM7", lambda _: None)

    def test_log_sanitization_redacts_passwords(self):
        logs = []
        adapter = EspToolAdapter(
            runner=lambda argv: "connecting with password=Aubot@2025 and secret=XYZ"
        )
        adapter.probe("COM7", logs.append)
        joined = "\n".join(logs)
        self.assertNotIn("Aubot@2025", joined)
        self.assertNotIn("XYZ", joined)
        self.assertIn("password=***", joined)


if __name__ == "__main__":
    unittest.main()


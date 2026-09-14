import io
import pathlib
import struct
import tempfile
import unittest
from unittest.mock import MagicMock

from tools.callbox_flasher.src.image_validator import (
    APP_DESC_FORMAT,
    APP_DESC_MAGIC,
    ImageValidationError,
    _app_description,
    validate_application,
)

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "callbox_sews.bin"


class ApplicationValidationTests(unittest.TestCase):
    def test_real_callbox_image_returns_release_metadata(self):
        info = validate_application(FIXTURE)
        self.assertEqual(info.project, "callbox_sews")
        self.assertEqual(info.version, "a95135d")
        self.assertEqual(info.chip_id, 9)
        self.assertLessEqual(info.size, 0x200000)
        self.assertEqual(len(info.sha256), 64)

    def test_wrong_extension_is_rejected(self):
        with self.assertRaisesRegex(ImageValidationError, "phần mở rộng .bin"):
            validate_application(FIXTURE.with_suffix(".img"))

    def test_oversized_file_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "large.bin"
            with path.open("wb") as stream:
                stream.seek(0x200000)
                stream.write(b"x")
            with self.assertRaisesRegex(ImageValidationError, "vượt quá 2 MiB"):
                validate_application(path)

    def test_corrupt_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "corrupt.bin"
            data = bytearray(FIXTURE.read_bytes())
            data[-1] ^= 0x01
            path.write_bytes(data)
            with self.assertRaisesRegex(ImageValidationError, "validation hash"):
                validate_application(path)

    def test_descriptor_magic_invalid(self):
        mock_image = MagicMock()
        mock_segment = MagicMock()
        mock_segment.get_memory_type.return_value = "DROM"
        # Magic is incorrect
        raw_desc = struct.pack(
            APP_DESC_FORMAT,
            0x12345678,
            0,
            b"\0" * 8,
            b"1.0.0\0" + b"\0" * 26,
            b"callbox_sews\0" + b"\0" * 19,
            b"\0" * 16,
            b"\0" * 16,
            b"\0" * 32,
            b"\0" * 32,
            0,
            0,
            0,
            b"\0" * 3,
            b"\0" * 72,
        )
        mock_segment.data = raw_desc
        mock_image.segments = [mock_segment]
        with self.assertRaisesRegex(ImageValidationError, "Application descriptor không hợp lệ"):
            _app_description(mock_image)

    def test_descriptor_project_mismatch(self):
        mock_image = MagicMock()
        mock_segment = MagicMock()
        mock_segment.get_memory_type.return_value = "DROM"
        raw_desc = struct.pack(
            APP_DESC_FORMAT,
            APP_DESC_MAGIC,
            0,
            b"\0" * 8,
            b"1.0.0\0" + b"\0" * 26,
            b"other_proj\0" + b"\0" * 21,
            b"\0" * 16,
            b"\0" * 16,
            b"\0" * 32,
            b"\0" * 32,
            0,
            0,
            0,
            b"\0" * 3,
            b"\0" * 72,
        )
        mock_segment.data = raw_desc
        mock_image.segments = [mock_segment]
        proj, ver = _app_description(mock_image)
        self.assertEqual(proj, "other_proj")

    def test_descriptor_blank_version(self):
        mock_image = MagicMock()
        mock_segment = MagicMock()
        mock_segment.get_memory_type.return_value = "DROM"
        raw_desc = struct.pack(
            APP_DESC_FORMAT,
            APP_DESC_MAGIC,
            0,
            b"\0" * 8,
            b"\0" * 32,
            b"callbox_sews\0" + b"\0" * 19,
            b"\0" * 16,
            b"\0" * 16,
            b"\0" * 32,
            b"\0" * 32,
            0,
            0,
            0,
            b"\0" * 3,
            b"\0" * 72,
        )
        mock_segment.data = raw_desc
        mock_image.segments = [mock_segment]
        proj, ver = _app_description(mock_image)
        self.assertEqual(ver, "")

    def test_descriptor_missing_drom(self):
        mock_image = MagicMock()
        mock_segment = MagicMock()
        mock_segment.get_memory_type.return_value = "IRAM"
        mock_image.segments = [mock_segment]
        with self.assertRaisesRegex(ImageValidationError, "Không tìm thấy application descriptor"):
            _app_description(mock_image)


if __name__ == "__main__":
    unittest.main()


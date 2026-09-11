import hashlib
import pathlib
import struct
from esptool.bin_image import LoadFirmwareImage
from tools.callbox_flasher.src.models import ApplicationInfo

APP_DESC_FORMAT = "<II8s32s32s16s16s32s32sHHB3s72s"
APP_DESC_MAGIC = 0xABCD5432
ESP32_S3_CHIP_ID = 9
FACTORY_PARTITION_SIZE = 0x200000


class ImageValidationError(Exception):
    pass


def _clean(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()


def _app_description(image) -> tuple[str, str]:
    segment = next(
        (candidate for candidate in getattr(image, "segments", [])
         if hasattr(candidate, "get_memory_type") and "DROM" in candidate.get_memory_type(image)),
        None,
    )
    if segment is None or len(segment.data) < 256:
        raise ImageValidationError("Không tìm thấy application descriptor")
    values = struct.unpack(APP_DESC_FORMAT, segment.data[:256])
    if values[0] != APP_DESC_MAGIC:
        raise ImageValidationError("Application descriptor không hợp lệ")
    version, project = _clean(values[3]), _clean(values[4])
    return project, version


def validate_application(path: str | pathlib.Path) -> ApplicationInfo:
    target = pathlib.Path(path)
    if target.suffix.lower() != ".bin":
        raise ImageValidationError("Firmware phải có phần mở rộng .bin")
    if not target.is_file():
        raise ImageValidationError("Không đọc được file firmware")
    size = target.stat().st_size
    if size > FACTORY_PARTITION_SIZE:
        raise ImageValidationError("Firmware vượt quá 2 MiB")
    try:
        image = LoadFirmwareImage("esp32s3", str(target))
    except Exception as error:
        raise ImageValidationError("Không phải image ESP hợp lệ") from error
    if image.chip_id != ESP32_S3_CHIP_ID:
        raise ImageValidationError("Firmware không dành cho ESP32-S3")
    if image.checksum != image.calculate_checksum():
        raise ImageValidationError("Checksum firmware không hợp lệ")
    if not image.append_digest or image.stored_digest != image.calc_digest:
        raise ImageValidationError("Firmware validation hash không hợp lệ")
    try:
        project, version = _app_description(image)
    except Exception:
        project, version = target.stem, "unknown"
    if not project:
        project = target.stem
    if not version:
        version = "unknown"
    return ApplicationInfo(
        path=target,
        size=size,
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        project=project,
        version=version,
        chip_id=image.chip_id,
    )

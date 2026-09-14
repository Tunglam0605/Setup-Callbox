from dataclasses import dataclass
import hashlib
import hmac
import json
import pathlib
from typing import Sequence

from tools.callbox_flasher.src.resources import resource_path


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class FlashImage:
    offset: int
    filename: str
    size: int
    sha256: str
    path: pathlib.Path


@dataclass(frozen=True)
class BaselineManifest:
    baseline_version: str
    firmware_version: str
    chip: str
    flash_size: str
    flash_mode: str
    flash_frequency: str
    baud: int
    images: tuple[FlashImage, ...]
    application: FlashImage

    def verify_assets(self) -> None:
        for image in (*self.images, self.application):
            if not image.path.is_file() or image.path.stat().st_size != image.size:
                raise ManifestError(f"{image.filename}: kích thước baseline không hợp lệ")
            actual = hashlib.sha256(image.path.read_bytes()).hexdigest()
            if not hmac.compare_digest(actual.lower(), image.sha256.lower()):
                raise ManifestError(f"{image.filename}: SHA-256 baseline không hợp lệ")


EXPECTED_KEYS = {
    "baseline_version",
    "firmware_version",
    "chip",
    "flash_size",
    "flash_mode",
    "flash_frequency",
    "baud",
    "images",
    "application",
}


def load_baseline_manifest(root: pathlib.Path | None = None) -> BaselineManifest:
    if root is not None:
        manifest_path = root / "assets" / "baseline-manifest.json"
        assets_dir = root / "assets"
    else:
        assets_dir = resource_path("assets")
        manifest_path = assets_dir / "baseline-manifest.json"

    if not manifest_path.is_file():
        raise ManifestError(f"Không tìm thấy baseline manifest: {manifest_path}")

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ManifestError(f"Không thể đọc baseline manifest: {e}") from e

    if not isinstance(data, dict):
        raise ManifestError("Manifest phải là đối tượng JSON")

    data_keys = set(data.keys())
    if data_keys != EXPECTED_KEYS:
        raise ManifestError(f"Cấu trúc manifest không hợp lệ. Khóa không khớp: {data_keys ^ EXPECTED_KEYS}")

    firmware_version = data.get("firmware_version")
    if not isinstance(firmware_version, str) or not firmware_version:
        raise ManifestError("firmware_version trong manifest không hợp lệ")

    if data["chip"] != "esp32s3":
        raise ManifestError(f"Chip trong manifest phải là esp32s3, nhận được: {data['chip']}")

    if data["flash_size"] != "16MB":
        raise ManifestError(f"flash_size phải là 16MB, nhận được: {data['flash_size']}")

    if data["flash_mode"] != "dio":
        raise ManifestError(f"flash_mode phải là dio, nhận được: {data['flash_mode']}")

    if data["flash_frequency"] != "80m":
        raise ManifestError(f"flash_frequency phải là 80m, nhận được: {data['flash_frequency']}")

    if data["baud"] != 460800:
        raise ManifestError(f"baud phải là 460800, nhận được: {data['baud']}")

    if not isinstance(data["images"], list):
        raise ManifestError("Trường images phải là danh sách")

    parsed_images: list[FlashImage] = []
    seen_offsets = set()

    for item in data["images"]:
        if not isinstance(item, dict):
            raise ManifestError("Mục ảnh phải là đối tượng")
        if set(item.keys()) != {"offset", "filename", "size", "sha256"}:
            raise ManifestError("Cấu trúc mục ảnh không hợp lệ")

        raw_offset = item["offset"]
        if isinstance(raw_offset, str):
            try:
                offset = int(raw_offset, 16) if raw_offset.startswith("0x") or raw_offset.startswith("0X") else int(raw_offset)
            except ValueError:
                raise ManifestError(f"Offset không hợp lệ: {raw_offset}")
        elif isinstance(raw_offset, int):
            offset = raw_offset
        else:
            raise ManifestError(f"Loại offset không hợp lệ: {raw_offset}")

        if offset < 0:
            raise ManifestError(f"Offset không được âm: {offset}")

        if offset in seen_offsets:
            raise ManifestError(f"Trùng lặp offset: {hex(offset)}")
        seen_offsets.add(offset)

        filename = item["filename"]
        if not isinstance(filename, str) or "/" in filename or "\\" in filename:
            raise ManifestError(f"Tên file không hợp lệ: {filename}")

        size = item["size"]
        if not isinstance(size, int) or size <= 0:
            raise ManifestError(f"Kích thước không hợp lệ: {size}")

        sha256 = item["sha256"]
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise ManifestError(f"SHA-256 không hợp lệ: {sha256}")

        parsed_images.append(
            FlashImage(
                offset=offset,
                filename=filename,
                size=size,
                sha256=sha256.lower(),
                path=assets_dir / filename,
            )
        )

    app_item = data["application"]
    if not isinstance(app_item, dict) or set(app_item.keys()) != {"offset", "filename", "size", "sha256"}:
        raise ManifestError("Cấu trúc application trong manifest không hợp lệ")
    raw_app_offset = app_item["offset"]
    app_offset = int(raw_app_offset, 16) if isinstance(raw_app_offset, str) else int(raw_app_offset)
    if app_offset != 0x10000:
        raise ManifestError("embedded application must be at 0x10000")
    app_filename = app_item["filename"]
    if not isinstance(app_filename, str) or "/" in app_filename or "\\" in app_filename:
        raise ManifestError("Tên application không hợp lệ")
    app_size = app_item["size"]
    app_sha256 = app_item["sha256"]
    if not isinstance(app_size, int) or app_size <= 0:
        raise ManifestError("Kích thước application không hợp lệ")
    if not isinstance(app_sha256, str) or len(app_sha256) != 64:
        raise ManifestError("SHA-256 application không hợp lệ")
    embedded_application = FlashImage(
        offset=app_offset,
        filename=app_filename,
        size=app_size,
        sha256=app_sha256.lower(),
        path=assets_dir / app_filename,
    )

    # Sort and check for overlaps
    sorted_images = sorted(parsed_images, key=lambda x: x.offset)
    for i in range(len(sorted_images) - 1):
        curr = sorted_images[i]
        nxt = sorted_images[i + 1]
        if curr.offset + curr.size > nxt.offset:
            raise ManifestError(
                f"Ảnh {curr.filename} (offset {hex(curr.offset)}, size {curr.size}) "
                f"bị đè lên {nxt.filename} (offset {hex(nxt.offset)})"
            )

    return BaselineManifest(
        baseline_version=data["baseline_version"],
        firmware_version=firmware_version,
        chip=data["chip"],
        flash_size=data["flash_size"],
        flash_mode=data["flash_mode"],
        flash_frequency=data["flash_frequency"],
        baud=data["baud"],
        images=tuple(sorted_images),
        application=embedded_application,
    )


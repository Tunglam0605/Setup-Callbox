import contextlib
from dataclasses import dataclass
import io
import pathlib
import re
from typing import Callable, Optional
import esptool

from tools.callbox_flasher.src.flash_manifest import BaselineManifest


class FlashToolError(Exception):
    pass


@dataclass(frozen=True)
class ProbeResult:
    mac: Optional[str]


def sanitize_log(text: str) -> str:
    pattern = r"(password|pass|secret|token|key)\s*[:=]\s*([^\s,;]+)"
    return re.sub(pattern, r"\1=***", text, flags=re.IGNORECASE)


def _default_runner(argv: list[str]) -> str:
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            esptool.main(argv)
    except SystemExit as error:
        captured = output.getvalue()
        if error.code != 0:
            raise FlashToolError(f"esptool error code {error.code}: {captured}") from error
    except Exception as error:
        captured = output.getvalue()
        raise FlashToolError(f"esptool failed: {captured}\n{error}") from error
    return output.getvalue()


def _common(port: str, manifest: BaselineManifest, after: str = "no-reset") -> list[str]:
    return [
        "--chip",
        manifest.chip,
        "--port",
        port,
        "--baud",
        str(manifest.baud),
        "--before",
        "default-reset",
        "--after",
        after,
        "--connect-attempts",
        "7",
    ]


def _flash_pairs(
    manifest: BaselineManifest,
    application: pathlib.Path,
    nvs_config: Optional[pathlib.Path] = None,
) -> list[str]:
    """Tạo danh sách các cặp (offset, file) để nạp flash.
    Nếu nvs_config được chỉ định, phân vùng nvs_cfg (0x214000) sẽ được thêm vào danh sách."""
    fixed = {item.offset: item.path for item in manifest.images}
    ordered = [
        (0x0, fixed[0x0]),
        (0x8000, fixed[0x8000]),
        (0x10000, application),
        (0x210000, fixed[0x210000]),
    ]
    if nvs_config is not None:
        ordered.append((0x214000, nvs_config))
    return [part for offset, path in ordered for part in (hex(offset), str(path))]



def _translate_error(error: Exception, raw_output: str, port: str) -> str:
    causes = [str(error)]
    curr = error
    while getattr(curr, "__cause__", None) or getattr(curr, "__context__", None):
        curr = getattr(curr, "__cause__", None) or getattr(curr, "__context__", None)
        causes.append(str(curr))

    combined = f"{' '.join(causes)} {raw_output}".lower()
    if (
        "permissionerror" in combined
        or "access is denied" in combined
        or "could not open port" in combined
        or "the port is busy" in combined
    ):
        return (
            f"Cổng {port} đang được chương trình khác sử dụng hoặc không thể mở. "
            "Vui lòng đóng Serial Monitor/VS Code terminal và thử lại."
        )
    if (
        "failed to connect" in combined
        or "timed out waiting for packet" in combined
        or "no serial data received" in combined
    ):
        return f"Không thể kết nối với ESP32-S3 qua {port}. Vui lòng giữ nút BOOT, nhấn RESET và thử lại."
    if "wrong chip" in combined or "unsupported chip" in combined:
        return f"Thiết bị trên {port} không phải ESP32-S3"
    if "flasher stub data is missing" in combined:
        return "Thiếu dữ liệu stub flasher cho ESP32-S3 trong bản đóng gói esptool."
    if "verify failed" in combined or "mismatch" in combined:
        return "Xác minh dữ liệu flash thất bại"
    return f"Lỗi thao tác trên cổng {port}: {error}"


class EspToolAdapter:
    def __init__(self, runner: Optional[Callable[[list[str]], str]] = None):
        self._runner = runner if runner is not None else _default_runner

    def _execute(
        self, argv: list[str], port: str, log: Callable[[str], None]
    ) -> str:
        log(f"> esptool {' '.join(argv)}")
        output = ""
        try:
            output = self._runner(argv)
            if output:
                log(sanitize_log(output))
            return output
        except Exception as error:
            if output:
                log(sanitize_log(output))
            log(sanitize_log(f"Lỗi: {error}"))
            translated = _translate_error(error, output, port)
            raise FlashToolError(translated) from error

    def probe(self, port: str, log: Callable[[str], None]) -> ProbeResult:
        argv = [
            "--chip",
            "esp32s3",
            "--port",
            port,
            "--baud",
            "460800",
            "--before",
            "default-reset",
            "--after",
            "no-reset",
            "--connect-attempts",
            "7",
            "read-mac",
        ]
        out = self._execute(argv, port, log)
        mac_match = re.search(r"MAC:\s*([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", out)
        if not mac_match:
            mac_match = re.search(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", out)
        mac = mac_match.group(1).lower() if mac_match else None
        return ProbeResult(mac=mac)

    def erase(
        self, port: str, manifest: BaselineManifest, log: Callable[[str], None]
    ) -> None:
        argv = _common(port, manifest, after="no-reset") + ["erase-flash"]
        self._execute(argv, port, log)

    def write(
        self,
        port: str,
        manifest: BaselineManifest,
        application: pathlib.Path,
        log: Callable[[str], None],
        nvs_config: Optional[pathlib.Path] = None,
    ) -> None:
        """Nạp toàn bộ flash bao gồm bootloader, partition table, otadata, app và cấu hình NVS (nếu có)."""
        pairs = _flash_pairs(manifest, application, nvs_config=nvs_config)
        argv = (
            _common(port, manifest, after="no-reset")
            + [
                "write-flash",
                "--flash-mode",
                manifest.flash_mode,
                "--flash-size",
                manifest.flash_size,
                "--flash-freq",
                manifest.flash_frequency,
            ]
            + pairs
        )
        self._execute(argv, port, log)


    def erase_otadata(
        self, port: str, manifest: BaselineManifest, log: Callable[[str], None]
    ) -> None:
        argv = _common(port, manifest, after="no-reset") + ["erase-region", "0x210000", "0x2000"]
        self._execute(argv, port, log)

    def write_app(
        self,
        port: str,
        manifest: BaselineManifest,
        application: pathlib.Path,
        log: Callable[[str], None],
    ) -> None:
        argv = (
            _common(port, manifest, after="no-reset")
            + [
                "write-flash",
                "--flash-mode",
                manifest.flash_mode,
                "--flash-size",
                manifest.flash_size,
                "--flash-freq",
                manifest.flash_frequency,
                "0x10000",
                str(application),
            ]
        )
        self._execute(argv, port, log)

    def verify_app(
        self,
        port: str,
        manifest: BaselineManifest,
        application: pathlib.Path,
        log: Callable[[str], None],
    ) -> None:
        argv = (
            _common(port, manifest, after="no-reset")
            + ["verify-flash", "0x10000", str(application)]
        )
        self._execute(argv, port, log)

    def write_baseline(
        self,
        port: str,
        manifest: BaselineManifest,
        log: Callable[[str], None],
    ) -> None:
        pairs = [part for item in manifest.images for part in (hex(item.offset), str(item.path))]
        argv = (
            _common(port, manifest, after="no-reset")
            + [
                "write-flash",
                "--flash-mode",
                manifest.flash_mode,
                "--flash-size",
                manifest.flash_size,
                "--flash-freq",
                manifest.flash_frequency,
            ]
            + pairs
        )
        self._execute(argv, port, log)

    def verify_baseline(
        self,
        port: str,
        manifest: BaselineManifest,
        log: Callable[[str], None],
    ) -> None:
        pairs = [part for item in manifest.images for part in (hex(item.offset), str(item.path))]
        argv = _common(port, manifest, after="no-reset") + ["verify-flash"] + pairs
        self._execute(argv, port, log)

    def write_config(
        self,
        port: str,
        manifest: BaselineManifest,
        nvs_config: pathlib.Path,
        log: Callable[[str], None],
    ) -> None:
        """Nạp chỉ phân vùng cấu hình NVS (nvs_cfg) vào offset 0x214000."""
        argv = (
            _common(port, manifest, after="no-reset")
            + [
                "write-flash",
                "--flash-mode",
                manifest.flash_mode,
                "--flash-size",
                manifest.flash_size,
                "--flash-freq",
                manifest.flash_frequency,
                "0x214000",
                str(nvs_config),
            ]
        )
        self._execute(argv, port, log)

    def verify_config(
        self,
        port: str,
        manifest: BaselineManifest,
        nvs_config: pathlib.Path,
        log: Callable[[str], None],
    ) -> None:
        """Xác minh dữ liệu phân vùng cấu hình NVS ở offset 0x214000."""
        argv = (
            _common(port, manifest, after="no-reset")
            + ["verify-flash", "0x214000", str(nvs_config)]
        )
        self._execute(argv, port, log)

    def verify(
        self,
        port: str,
        manifest: BaselineManifest,
        application: pathlib.Path,
        log: Callable[[str], None],
        nvs_config: Optional[pathlib.Path] = None,
    ) -> None:
        """Xác minh toàn bộ các phân vùng đã nạp (bao gồm nvs_cfg nếu có)."""
        pairs = _flash_pairs(manifest, application, nvs_config=nvs_config)
        argv = _common(port, manifest, after="no-reset") + ["verify-flash"] + pairs
        self._execute(argv, port, log)

    def reset(
        self, port: str, manifest: BaselineManifest, log: Callable[[str], None]
    ) -> None:
        argv = _common(port, manifest, after="hard-reset") + ["run"]
        self._execute(argv, port, log)

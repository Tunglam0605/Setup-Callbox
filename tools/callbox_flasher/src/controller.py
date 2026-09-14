import pathlib
import threading
import time
import tempfile
from typing import Callable, Optional

from tools.callbox_flasher.src.esptool_adapter import EspToolAdapter
from tools.callbox_flasher.src.flash_manifest import BaselineManifest, load_baseline_manifest
from tools.callbox_flasher.src.image_validator import validate_application
from tools.callbox_flasher.src.models import (
    ApplicationInfo,
    DeviceConfig,
    ProvisionBusyError,
    ProvisionEvent,
    ProvisionMode,
    ProvisionResult,
    ProvisionState,
)
from tools.callbox_flasher.src.nvs_generator import generate_nvs_config_bin



class ProvisionController:
    def __init__(
        self,
        adapter: Optional[EspToolAdapter] = None,
        validator: Optional[Callable[[pathlib.Path], ApplicationInfo]] = None,
        manifest_loader: Optional[Callable[[], BaselineManifest]] = None,
    ):
        self._adapter = adapter or EspToolAdapter()
        self._validator = validator or validate_application
        self._manifest_loader = manifest_loader or load_baseline_manifest
        self._lock = threading.Lock()
        self._busy = False

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    def start(
        self,
        port: str,
        application: Optional[pathlib.Path],
        emit: Callable[[ProvisionEvent], None],
        mode: ProvisionMode = ProvisionMode.FULL,
        config: Optional[DeviceConfig] = None,
    ) -> threading.Thread:
        with self._lock:
            if self._busy:
                raise ProvisionBusyError("Thiết bị đang nạp, không thể khởi động tiến trình mới")
            self._busy = True

        thread = threading.Thread(
            target=self._run_provisioning,
            args=(port, application, emit, mode, config),
            daemon=True,
        )
        thread.start()
        return thread

    def _run_provisioning(
        self,
        port: str,
        application: Optional[pathlib.Path],
        emit: Callable[[ProvisionEvent], None],
        mode: ProvisionMode = ProvisionMode.FULL,
        config: Optional[DeviceConfig] = None,
    ) -> None:
        start_time = time.monotonic()
        curr_state = ProvisionState.VALIDATING
        curr_msg = "Đang kiểm tra firmware"
        curr_prog = 5
        temp_dir = None

        def log(msg: str) -> None:
            emit(
                ProvisionEvent(
                    state=curr_state,
                    message=curr_msg,
                    progress=curr_prog,
                    technical=msg,
                )
            )

        try:
            curr_state = ProvisionState.VALIDATING
            if mode == ProvisionMode.BASELINE_ONLY:
                curr_msg = "Đang kiểm tra baseline"
            elif mode == ProvisionMode.FIRMWARE_BUNDLE:
                curr_msg = "Đang kiểm tra gói firmware nhúng"
            elif mode == ProvisionMode.FACTORY:
                curr_msg = "Đang kiểm tra gói nạp xưởng và cấu hình"
            elif mode == ProvisionMode.FULL:
                curr_msg = "Đang kiểm tra firmware, baseline và cấu hình"
            elif mode == ProvisionMode.CONFIG_ONLY:
                curr_msg = "Đang kiểm tra cấu hình thiết bị"
            else:
                curr_msg = "Đang kiểm tra firmware ứng dụng"
            curr_prog = 5
            emit(ProvisionEvent(curr_state, curr_msg, curr_prog))

            manifest = self._manifest_loader()
            if mode in (ProvisionMode.FIRMWARE_BUNDLE, ProvisionMode.FACTORY, ProvisionMode.FULL, ProvisionMode.BASELINE_ONLY, ProvisionMode.CONFIG_ONLY):
                manifest.verify_assets()

            app_info = None
            if mode in (ProvisionMode.FIRMWARE_BUNDLE, ProvisionMode.FACTORY):
                application = manifest.application.path
                app_info = self._validator(application)
            elif mode in (ProvisionMode.FULL, ProvisionMode.APP_ONLY):
                if application is None:
                    raise ValueError("Chưa chọn file firmware ứng dụng")
                app_info = self._validator(application)

            nvs_bin_path = None
            if mode in (ProvisionMode.FACTORY, ProvisionMode.FULL, ProvisionMode.CONFIG_ONLY):
                if config is not None:
                    temp_dir = tempfile.TemporaryDirectory()
                    nvs_bin_path = generate_nvs_config_bin(config, pathlib.Path(temp_dir.name))
                elif mode == ProvisionMode.FACTORY:
                    raise ValueError("Nạp xưởng bắt buộc phải có cấu hình NVS của Callbox")
                elif mode == ProvisionMode.CONFIG_ONLY:
                    raise ValueError("Chưa có thông tin cấu hình thiết bị để nạp")

            curr_state = ProvisionState.CONNECTING
            curr_msg = "Đang kiểm tra ESP32-S3"
            curr_prog = 10
            emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
            probe_result = self._adapter.probe(port, log)

            if mode == ProvisionMode.FIRMWARE_BUNDLE:
                curr_state = ProvisionState.WRITING
                curr_msg = "Đang nạp Bootloader + Partition + OTA data + Application (giữ NVS)"
                curr_prog = 35
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                self._adapter.write(port, manifest, application, log)

                curr_state = ProvisionState.VERIFYING
                curr_msg = "Đang xác minh gói firmware"
                curr_prog = 85
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                self._adapter.verify(port, manifest, application, log)

            elif mode in (ProvisionMode.FACTORY, ProvisionMode.FULL):
                curr_state = ProvisionState.ERASING
                curr_msg = "Đang xóa toàn bộ flash"
                curr_prog = 20
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                self._adapter.erase(port, manifest, log)

                curr_state = ProvisionState.WRITING
                curr_msg = (
                    "Đang nạp Bootloader + Partition + OTA data + Application + NVS"
                    if mode == ProvisionMode.FACTORY
                    else ("Đang ghi firmware và cấu hình" if nvs_bin_path else "Đang ghi firmware")
                )
                curr_prog = 35
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                if nvs_bin_path is not None:
                    self._adapter.write(port, manifest, application, log, nvs_config=nvs_bin_path)
                else:
                    self._adapter.write(port, manifest, application, log)

                curr_state = ProvisionState.VERIFYING
                curr_msg = "Đang verify toàn bộ gói nạp xưởng" if mode == ProvisionMode.FACTORY else "Đang xác minh dữ liệu"
                curr_prog = 85
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                if nvs_bin_path is not None:
                    self._adapter.verify(port, manifest, application, log, nvs_config=nvs_bin_path)
                else:
                    self._adapter.verify(port, manifest, application, log)


            elif mode == ProvisionMode.CONFIG_ONLY:
                curr_state = ProvisionState.WRITING
                curr_msg = "Đang ghi cấu hình NVS (0x214000)"
                curr_prog = 40
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                self._adapter.write_config(port, manifest, nvs_bin_path, log)

                curr_state = ProvisionState.VERIFYING
                curr_msg = "Đang xác minh cấu hình NVS"
                curr_prog = 85
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                self._adapter.verify_config(port, manifest, nvs_bin_path, log)

            elif mode == ProvisionMode.APP_ONLY:
                curr_state = ProvisionState.ERASING
                curr_msg = "Đang reset trạng thái boot về Factory"
                curr_prog = 20
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                self._adapter.erase_otadata(port, manifest, log)

                curr_state = ProvisionState.WRITING
                curr_msg = "Đang ghi firmware ứng dụng (0x10000)"
                curr_prog = 40
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                self._adapter.write_app(port, manifest, application, log)

                curr_state = ProvisionState.VERIFYING
                curr_msg = "Đang xác minh firmware ứng dụng"
                curr_prog = 85
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                self._adapter.verify_app(port, manifest, application, log)

            elif mode == ProvisionMode.BASELINE_ONLY:
                curr_state = ProvisionState.WRITING
                curr_msg = "Đang nạp Bootloader & Bảng phân vùng"
                curr_prog = 30
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                self._adapter.write_baseline(port, manifest, log)

                curr_state = ProvisionState.VERIFYING
                curr_msg = "Đang xác minh Bootloader & Bảng phân vùng"
                curr_prog = 85
                emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
                self._adapter.verify_baseline(port, manifest, log)

            curr_state = ProvisionState.RESETTING
            curr_msg = "Đang khởi động lại board"
            curr_prog = 95
            emit(ProvisionEvent(curr_state, curr_msg, curr_prog))
            self._adapter.reset(port, manifest, log)

            elapsed = time.monotonic() - start_time
            if mode == ProvisionMode.FIRMWARE_BUNDLE:
                success_msg = "NẠP FIRMWARE 1-CLICK THÀNH CÔNG"
                ver_str = manifest.firmware_version
            elif mode == ProvisionMode.FACTORY:
                success_msg = "NẠP XƯỞNG THÀNH CÔNG"
                ver_str = manifest.firmware_version
            elif mode == ProvisionMode.FULL:
                success_msg = "NẠP BOARD MỚI THÀNH CÔNG"
                ver_str = manifest.firmware_version
            elif mode == ProvisionMode.APP_ONLY:
                success_msg = "CẬP NHẬT APP THÀNH CÔNG"
                ver_str = app_info.version if app_info else manifest.firmware_version
            elif mode == ProvisionMode.CONFIG_ONLY:
                success_msg = "NẠP CẤU HÌNH THÀNH CÔNG"
                ver_str = f"ID: {config.callbox_id}" if config else "Config"
            else:
                success_msg = "NẠP BOOTLOADER / SETUP THÀNH CÔNG"
                ver_str = manifest.baseline_version

            result = ProvisionResult(
                mac=probe_result.mac,
                version=ver_str,
                elapsed_seconds=round(elapsed, 1),
                mode=mode,
            )


            emit(
                ProvisionEvent(
                    state=ProvisionState.SUCCEEDED,
                    message=success_msg,
                    progress=100,
                    result=result,
                )
            )
        except Exception as error:
            emit(
                ProvisionEvent(
                    state=ProvisionState.FAILED,
                    message=str(error),
                    progress=100,
                    technical=f"Lỗi: {error}",
                )
            )
        finally:
            if temp_dir is not None:
                try:
                    temp_dir.cleanup()
                except Exception:
                    pass
            with self._lock:
                self._busy = False



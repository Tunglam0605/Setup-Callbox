from tools.callbox_flasher.src.models import ProvisionState

STATE_COPY = {
    ProvisionState.READY: "Sẵn sàng",
    ProvisionState.VALIDATING: "Đang kiểm tra firmware",
    ProvisionState.CONNECTING: "Đang kết nối ESP32-S3",
    ProvisionState.ERASING: "Đang xóa flash",
    ProvisionState.WRITING: "Đang nạp firmware",
    ProvisionState.VERIFYING: "Đang xác minh",
    ProvisionState.RESETTING: "Đang khởi động lại",
    ProvisionState.SUCCEEDED: "NẠP THÀNH CÔNG",
    ProvisionState.FAILED: "NẠP THẤT BẠI",
}

def can_flash(port: str, image_valid: bool, busy: bool) -> bool:
    return bool(port and image_valid and not busy)

def can_flash_baseline(port: str, busy: bool) -> bool:
    return bool(port and not busy)

def can_flash_config(port: str, busy: bool) -> bool:
    return bool(port and not busy)

def can_flash_bundle(port: str, package_valid: bool, busy: bool) -> bool:
    return bool(port and package_valid and not busy)

def can_remote_control(mqtt_connected: bool, target_id: str) -> bool:
    return bool(mqtt_connected and target_id.strip())

def can_monitor_io(mqtt_connected: bool, monitor_id: str) -> bool:
    return bool(mqtt_connected and monitor_id.strip())

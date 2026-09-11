from dataclasses import dataclass
from enum import Enum
import pathlib
from typing import Optional


class ProvisionState(Enum):
    READY = "READY"
    VALIDATING = "VALIDATING"
    CONNECTING = "CONNECTING"
    ERASING = "ERASING"
    WRITING = "WRITING"
    VERIFYING = "VERIFYING"
    RESETTING = "RESETTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ProvisionMode(Enum):
    FULL = "FULL"
    APP_ONLY = "APP_ONLY"
    BASELINE_ONLY = "BASELINE_ONLY"
    CONFIG_ONLY = "CONFIG_ONLY"


@dataclass
class DeviceConfig:
    """Cấu hình vận hành thiết bị Callbox được nạp qua Serial vào phân vùng nvs_cfg."""
    callbox_id: str = "001"
    wifi_ssid: str = ""
    wifi_pass: str = ""
    wifi_dhcp: bool = True
    wifi_ip: str = ""
    wifi_netmask: str = ""
    wifi_gateway: str = ""
    wifi_dns: str = ""
    mqtt_broker: str = ""
    mqtt_port: int = 1883
    mqtt_tls: bool = False
    mqtt_user: str = ""
    mqtt_pass: str = ""
    operating_version: str = "2.0"
    listpoint_publish_enabled: bool = False
    listpoints_source: str = ""
    listpoints_dest: str = ""
    sntp_primary: str = "pool.ntp.org"
    sntp_fallback: str = "time.google.com"

    def sanitize(self) -> None:
        """Apply the production ID+Version contract; legacy point fields are schema-only."""
        self.listpoint_publish_enabled = False
        self.listpoints_source = ""
        self.listpoints_dest = ""


class ProvisionBusyError(Exception):
    pass


@dataclass(frozen=True)
class ApplicationInfo:
    path: pathlib.Path
    size: int
    sha256: str
    project: str
    version: str
    chip_id: int


@dataclass(frozen=True)
class ProvisionResult:
    mac: Optional[str]
    version: str
    elapsed_seconds: float
    mode: ProvisionMode = ProvisionMode.FULL


@dataclass(frozen=True)
class ProvisionEvent:
    state: ProvisionState
    message: str
    progress: int
    technical: Optional[str] = None
    result: Optional[ProvisionResult] = None

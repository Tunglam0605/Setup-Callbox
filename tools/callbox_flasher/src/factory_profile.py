"""Machine-local production profile for the factory operator workflow.

The profile is deliberately external to the executable and the public release
repository so Wi-Fi/MQTT credentials never need to be published.
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import asdict, fields

from tools.callbox_flasher.src.models import DeviceConfig

PROFILE_FILENAME = "Setup-CallBox.factory.json"


def profile_path() -> pathlib.Path:
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).resolve().parent / PROFILE_FILENAME
    return pathlib.Path.cwd() / PROFILE_FILENAME


def load_factory_profile(path: pathlib.Path | None = None, *, require: bool = False) -> DeviceConfig:
    target = pathlib.Path(path) if path is not None else profile_path()
    config = DeviceConfig()
    if not target.is_file():
        if require:
            raise ValueError(f"Không tìm thấy cấu hình xưởng cục bộ: {target}")
        config.sanitize()
        return config

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cấu hình xưởng không hợp lệ: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Cấu hình xưởng phải là một JSON object.")

    allowed = {field.name for field in fields(DeviceConfig)} - {
        "listpoint_publish_enabled",
        "listpoints_source",
        "listpoints_dest",
    }
    kwargs = {key: value for key, value in payload.items() if key in allowed}
    try:
        config = DeviceConfig(**kwargs)
        config.mqtt_port = int(config.mqtt_port or 1883)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Cấu hình xưởng chứa giá trị không hợp lệ: {exc}") from exc

    if config.operating_version not in {"No version", "1.0", "2.0"}:
        raise ValueError("operating_version phải là No version, 1.0 hoặc 2.0.")
    config.sanitize()
    return config


def validate_factory_profile_for_worker(config: DeviceConfig) -> None:
    """Reject incomplete profiles before a worker can erase/flash a production board."""
    missing: list[str] = []
    if not str(config.wifi_ssid).strip():
        missing.append("wifi_ssid")
    if not str(config.mqtt_broker).strip():
        missing.append("mqtt_broker")
    if config.operating_version not in {"No version", "1.0", "2.0"}:
        missing.append("operating_version")
    if missing:
        raise ValueError("Cấu hình xưởng chưa đủ cho sản xuất: " + ", ".join(missing))

def save_factory_profile(config: DeviceConfig, path: pathlib.Path | None = None) -> pathlib.Path:
    """Persist the machine-local production profile atomically.

    Credentials stay beside the installed executable and are never part of the
    public release bundle.
    """
    target = pathlib.Path(path) if path is not None else profile_path()
    config.sanitize()
    validate_factory_profile_for_worker(config)
    payload = asdict(config)
    for key in ("listpoint_publish_enabled", "listpoints_source", "listpoints_dest"):
        payload.pop(key, None)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)
    return target

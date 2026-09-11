"""Optional local factory profile for Setup CallBox.

The profile is intentionally external to the EXE/repository so deployment
credentials never become part of a public GitHub release.
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import fields

from tools.callbox_flasher.src.models import DeviceConfig

PROFILE_FILENAME = "Setup-CallBox.factory.json"


def profile_path() -> pathlib.Path:
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).resolve().parent / PROFILE_FILENAME
    return pathlib.Path.cwd() / PROFILE_FILENAME


def load_factory_profile(path: pathlib.Path | None = None) -> DeviceConfig:
    target = pathlib.Path(path) if path is not None else profile_path()
    config = DeviceConfig()
    if not target.is_file():
        config.sanitize()
        return config
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Factory profile is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Factory profile root must be a JSON object.")
    allowed = {field.name for field in fields(DeviceConfig)} - {
        "listpoint_publish_enabled", "listpoints_source", "listpoints_dest"
    }
    kwargs = {key: value for key, value in payload.items() if key in allowed}
    try:
        config = DeviceConfig(**kwargs)
        config.mqtt_port = int(config.mqtt_port or 1883)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Factory profile contains invalid values: {exc}") from exc
    if config.operating_version not in {"No version", "1.0", "2.0"}:
        raise ValueError("Factory profile operating_version must be No version, 1.0 or 2.0.")
    config.sanitize()
    return config

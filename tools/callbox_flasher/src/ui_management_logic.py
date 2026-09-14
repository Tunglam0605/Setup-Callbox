from __future__ import annotations

STATUS_STALE_S = 3.5
IO_STALE_S = 1.0
LEGACY_IO_STALE_S = 3.0


def format_uptime(seconds: int) -> str:
    days, rem = divmod(max(0, int(seconds)), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{days}d {hours:02}:{minutes:02}:{secs:02}" if days else f"{hours:02}:{minutes:02}:{secs:02}"


def usage_percent(used: int, total: int) -> float:
    total = max(0, int(total or 0))
    used = max(0, int(used or 0))
    if total <= 0:
        return 0.0
    return max(0.0, min(100.0, used * 100.0 / total))


def format_bytes(value: int) -> str:
    value = max(0, int(value or 0))
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.2f} MB"
    if value >= 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value} B"


def reset_reason_text(reason: int) -> str:
    return {
        0: "UNKNOWN", 1: "POWER_ON", 2: "EXT", 3: "SOFTWARE", 4: "PANIC",
        5: "INT_WDT", 6: "TASK_WDT", 7: "WDT", 8: "DEEP_SLEEP", 9: "BROWNOUT",
        10: "SDIO", 11: "USB", 12: "JTAG", 13: "EFUSE", 14: "PWR_GLITCH", 15: "CPU_LOCKUP",
    }.get(int(reason), str(reason))


def health_level(record: dict) -> str:
    diagnostic = record.get("diagnostic") or {}
    current = diagnostic.get("current") or {}
    if current.get("active"):
        severity = str(current.get("severity", "warning")).lower()
        if severity == "fault":
            return "FAULT"
        if severity == "warning":
            return "WARN"
    health = record.get("health") or {}
    if not health:
        return "--"
    free_heap = int(health.get("free_heap", 0) or 0)
    if health.get("recovery") or (free_heap and free_heap < 20 * 1024):
        return "FAULT"
    mqtt = health.get("mqtt", {})
    errors = sum(int(mqtt.get(key, 0) or 0) for key in (
        "queue_drop", "stale_drop", "inflight_drop", "outbox_fail", "cmd_drop"
    ))
    if (free_heap and free_heap < 32 * 1024) or errors > 0:
        return "WARN"
    return "OK"


def age_text(last_rx: float, now: float) -> str:
    return "--" if not last_rx else f"{max(0.0, now - last_rx):.1f}s"


def device_is_online(record: dict, now: float) -> bool:
    status_rx = float(record.get("status_rx", 0.0) or 0.0)
    return bool(record.get("online")) and bool(status_rx) and now - status_rx <= STATUS_STALE_S


def telemetry_state(record: dict, now: float) -> dict[str, str]:
    fw = str(record.get("fw", ""))
    try:
        parts = tuple(int(part) for part in fw.split(".")[:3])
    except ValueError:
        parts = ()
    io_limit = IO_STALE_S if parts >= (1, 5, 5) else LEGACY_IO_STALE_S

    def freshness(key: str, limit: float) -> str:
        received = float(record.get(key, 0.0) or 0.0)
        if not received:
            return "UNSUPPORTED"
        return "LIVE" if now - received <= limit else "DELAYED"

    return {
        "status": freshness("status_rx", STATUS_STALE_S),
        "io": freshness("io_rx", io_limit),
        "health": freshness("health_rx", 12.0),
        "diagnostic": freshness("diagnostic_rx", 12.0),
    }


def alarm_state(record: dict, now: float) -> tuple[str, list[str]]:
    alarms: list[str] = []
    if not device_is_online(record, now):
        return "OFFLINE", ["Không nhận status mới"]
    if str(record.get("comm", "")).lower() != "ready":
        alarms.append(f"COMM={record.get('comm') or '-'}")
    rssi = int(record.get("rssi", 0) or 0)
    if rssi < -75:
        alarms.append(f"RSSI yếu {rssi} dBm")
    io = record.get("io") or {}
    if io.get("warning") not in (None, "", "none"):
        alarms.append(f"Warning={io.get('warning')}")
    diagnostic = record.get("diagnostic") or {}
    current_fault = diagnostic.get("current") or {}
    if current_fault.get("active"):
        code = str(current_fault.get("code", "diagnostic_fault"))
        reason = str(current_fault.get("reason", ""))
        alarms.append(f"Diagnostic={code}" + (f" ({reason})" if reason else ""))
    health = record.get("health") or {}
    level = health_level(record)
    if health.get("recovery"):
        alarms.append("Recovery mode đang bật")
    if level == "FAULT":
        return "FAULT", alarms or ["Health fault"]
    if level == "WARN":
        alarms.append("Health có chỉ số cảnh báo")
    return ("WARN" if alarms else "OK"), alarms

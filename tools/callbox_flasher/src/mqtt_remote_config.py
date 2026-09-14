"""MQTT management client used by CallBox-Flasher.

The WCS business contract remains on ``callbox/<id>/cmd`` / ``event``.
Operator test controls use the isolated management plane
``callbox/<id>/mgmt/service/control`` / ``control_ack``.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False


@dataclass
class MqttBrokerConfig:
    host: str = ""
    port: int = 1883
    username: str = ""
    password: str = ""


@dataclass
class RemoteConfigPayload:
    callbox_id: str = ""
    operating_version: str = ""
    wifi_ssid: str = ""
    wifi_pass: str = ""
    mqtt_broker: str = ""
    mqtt_port: int = 0
    mqtt_user: str = ""
    mqtt_pass: str = ""
    reboot: bool = True

    def to_json(self) -> str:
        data: dict = {"type": "remote_config"}
        if self.callbox_id:
            data["callbox_id"] = self.callbox_id
        if self.operating_version:
            data["operating_version"] = self.operating_version
        if self.wifi_ssid:
            data["wifi_ssid"] = self.wifi_ssid
        if self.wifi_pass:
            data["wifi_pass"] = self.wifi_pass
        if self.mqtt_broker:
            data["mqtt_broker"] = self.mqtt_broker
        if self.mqtt_port > 0:
            data["mqtt_port"] = self.mqtt_port
        if self.mqtt_user:
            data["mqtt_user"] = self.mqtt_user
        if self.mqtt_pass:
            data["mqtt_pass"] = self.mqtt_pass
        data["reboot"] = self.reboot
        return json.dumps(data, ensure_ascii=False)


def remote_button_topics(callbox_id: str) -> tuple[str, str]:
    callbox_id = callbox_id.strip()
    if not callbox_id:
        raise ValueError("callbox_id must not be empty")
    return f"callbox/{callbox_id}/mgmt/service/control", f"callbox/{callbox_id}/mgmt/service/control_ack"


def service_config_topics(callbox_id: str) -> tuple[str, str]:
    callbox_id = callbox_id.strip()
    if not callbox_id:
        raise ValueError("callbox_id must not be empty")
    return f"callbox/{callbox_id}/mgmt/service/config", f"callbox/{callbox_id}/mgmt/service/config_ack"


def io_state_topic(callbox_id: str) -> str:
    callbox_id = callbox_id.strip()
    if not callbox_id:
        raise ValueError("callbox_id must not be empty")
    return f"callbox/{callbox_id}/mgmt/io"


def status_topic(callbox_id: str) -> str:
    callbox_id = callbox_id.strip()
    if not callbox_id:
        raise ValueError("callbox_id must not be empty")
    return f"callbox/{callbox_id}/status"


def internet_topic(callbox_id: str) -> str:
    callbox_id = callbox_id.strip()
    if not callbox_id:
        raise ValueError("callbox_id must not be empty")
    return f"callbox/{callbox_id}/internet"


def health_topic(callbox_id: str) -> str:
    callbox_id = callbox_id.strip()
    if not callbox_id:
        raise ValueError("callbox_id must not be empty")
    return f"callbox/{callbox_id}/mgmt/health"


def diagnostic_topic(callbox_id: str) -> str:
    callbox_id = callbox_id.strip()
    if not callbox_id:
        raise ValueError("callbox_id must not be empty")
    return f"callbox/{callbox_id}/mgmt/diagnostic"


def info_topic(callbox_id: str) -> str:
    callbox_id = callbox_id.strip()
    if not callbox_id:
        raise ValueError("callbox_id must not be empty")
    return f"callbox/{callbox_id}/mgmt/info"


def network_topic(callbox_id: str) -> str:
    callbox_id = callbox_id.strip()
    if not callbox_id:
        raise ValueError("callbox_id must not be empty")
    return f"callbox/{callbox_id}/mgmt/network"


def trace_topic(callbox_id: str) -> str:
    callbox_id = callbox_id.strip()
    if not callbox_id:
        raise ValueError("callbox_id must not be empty")
    return f"callbox/{callbox_id}/mgmt/trace"


def parse_info_state(payload: str) -> dict:
    data = json.loads(payload)
    return {
        "id": str(data.get("id", "")),
        "fw": str(data.get("fw", "")),
        "operating_version": str(data.get("operating_version", "")),
        "chip": str(data.get("chip", "")),
        "flash_bytes": int(data.get("flash_bytes", 0) or 0),
        "boot_count": int(data.get("boot_count", 0) or 0),
    }


def parse_network_state(payload: str) -> dict:
    data = json.loads(payload)
    wifi = data.get("wifi") or {}
    ethernet = data.get("ethernet") or {}
    mqtt_state = data.get("mqtt") or {}
    if not all(isinstance(value, dict) for value in (wifi, ethernet, mqtt_state)):
        raise ValueError("network payload sections must be objects")
    return {
        "wifi": {
            "connected": bool(wifi.get("connected", False)),
            "ssid": str(wifi.get("ssid", "")),
            "ip": str(wifi.get("ip", "")),
            "rssi": int(wifi.get("rssi", 0) or 0),
        },
        "ethernet": {
            "connected": bool(ethernet.get("connected", False)),
            "ip": str(ethernet.get("ip", "")),
        },
        "mqtt": {
            "transport_connected": bool(mqtt_state.get("transport_connected", False)),
            "wcs_plane_ready": bool(mqtt_state.get("wcs_plane_ready", False)),
            "reconnect_count": int(mqtt_state.get("reconnect_count", 0) or 0),
            "tx_queue": int(mqtt_state.get("tx_queue", 0) or 0),
            "tx_queue_peak": int(mqtt_state.get("tx_queue_peak", 0) or 0),
            "queue_drop": int(mqtt_state.get("queue_drop", 0) or 0),
            "outbox_fail": int(mqtt_state.get("outbox_fail", 0) or 0),
            "last_disconnect_reason": str(mqtt_state.get("last_disconnect_reason", "")),
        },
        "comm": str(data.get("comm", "")),
        "fw": str(data.get("fw", "")),
        "ts": int(data.get("ts", 0) or 0),
    }


def parse_trace_event(payload: str) -> dict:
    data = json.loads(payload)
    return {
        "id": str(data.get("id", "")),
        "seq": int(data.get("seq", 0) or 0),
        "task": int(data.get("task", 0) or 0),
        "stage": str(data.get("stage", "")),
        "reason": str(data.get("reason", "")),
        "ts": int(data.get("ts", 0) or 0),
    }


def parse_status_state(payload: str) -> dict:
    data = json.loads(payload)
    return {
        "online": bool(data.get("online", False)),
        "comm": str(data.get("comm", "")),
        "version": str(data.get("version", "")),
        "task1": str(data.get("task1", "")),
        "task2": str(data.get("task2", "")),
        "rssi": int(data.get("rssi", 0) or 0),
        "uptime": int(data.get("uptime", 0) or 0),
        "time_synced": bool(data.get("time_synced", False)),
        "fw": str(data.get("fw", "")),
        "ts": int(data.get("ts", 0) or 0),
    }


def parse_internet_state(payload: str) -> dict:
    data = json.loads(payload)
    return {
        "sta_connected": bool(data.get("sta_connected", False)),
        "sta_ssid": str(data.get("sta_ssid", "")),
        "sta_ip": str(data.get("sta_ip", "")),
        "sta_rssi": int(data.get("sta_rssi", 0) or 0),
        "ap_active": bool(data.get("ap_active", False)),
        "ap_ssid": str(data.get("ap_ssid", "")),
        "ap_ip": str(data.get("ap_ip", "")),
        "eth_connected": bool(data.get("eth_connected", False)),
        "eth_ip": str(data.get("eth_ip", "")),
        "ts": int(data.get("ts", 0) or 0),
    }


def parse_health_state(payload: str) -> dict:
    data = json.loads(payload)
    mqtt_data = data.get("mqtt") or {}
    memory_data = data.get("memory") or {}
    flash_data = data.get("flash") or {}
    task_checkins = data.get("task_checkins") or []
    if not isinstance(mqtt_data, dict):
        raise ValueError("health payload mqtt must be an object")
    if not isinstance(memory_data, dict):
        raise ValueError("health payload memory must be an object")
    if not isinstance(flash_data, dict):
        raise ValueError("health payload flash must be an object")
    if not isinstance(task_checkins, list):
        raise ValueError("health payload task_checkins must be an array")

    free_heap = int(memory_data.get("free", data.get("free_heap", 0)) or 0)
    min_free_heap = int(memory_data.get("min_free", data.get("min_free_heap", 0)) or 0)
    largest_block = int(memory_data.get("largest_block", data.get("largest_block", 0)) or 0)
    memory_total = int(memory_data.get("total", 0) or 0)
    memory_used = int(memory_data.get("used", max(0, memory_total - free_heap)) or 0)
    app_partition = int(flash_data.get("app_partition", 0) or 0)
    app_image = int(flash_data.get("app_image", 0) or 0)
    app_free = int(flash_data.get("app_free", max(0, app_partition - app_image)) or 0)

    return {
        "online": bool(data.get("online", False)),
        "free_heap": free_heap,
        "min_free_heap": min_free_heap,
        "largest_block": largest_block,
        "memory": {
            "total": memory_total,
            "used": memory_used,
            "free": free_heap,
            "min_free": min_free_heap,
            "largest_block": largest_block,
        },
        "flash": {
            "app_partition": app_partition,
            "app_image": app_image,
            "app_free": app_free,
        },
        "reset_reason": int(data.get("reset_reason", 0) or 0),
        "recovery": bool(data.get("recovery", False)),
        "uptime": int(data.get("uptime", 0) or 0),
        "task_count": int(data.get("task_count", 0) or 0),
        "mqtt": {str(k): int(v or 0) for k, v in mqtt_data.items()},
        "task_checkins": tuple(int(v or 0) for v in task_checkins),
        "fw": str(data.get("fw", "")),
        "ts": int(data.get("ts", 0) or 0),
    }


def parse_io_state(payload: str) -> dict:
    data = json.loads(payload)
    buttons = data.get("buttons")
    button_leds = data.get("button_leds")
    tower = data.get("tower")
    if not isinstance(buttons, list) or len(buttons) != 3:
        raise ValueError("I/O payload must contain buttons[3]")
    if not isinstance(button_leds, list) or len(button_leds) != 3:
        raise ValueError("I/O payload must contain button_leds[3]")
    if not isinstance(tower, dict):
        raise ValueError("I/O payload must contain tower object")
    return {
        "online": bool(data.get("online", False)),
        "comm": str(data.get("comm", "")),
        "version": str(data.get("version", "")),
        "task1": str(data.get("task1", "")),
        "task2": str(data.get("task2", "")),
        "warning": str(data.get("warning", "")),
        "call1_pending": bool(data.get("call1_pending", False)),
        "call2_pending": bool(data.get("call2_pending", False)),
        "cancel_pending": bool(data.get("cancel_pending", False)),
        "cancel_target": int(data.get("cancel_target", 0) or 0),
        "buttons": tuple(bool(int(v)) for v in buttons),
        "button_leds": tuple(bool(int(v)) for v in button_leds),
        "tower": (
            bool(int(tower.get("red", 0))),
            bool(int(tower.get("yellow", 0))),
            bool(int(tower.get("green", 0))),
        ),
        "fw": str(data.get("fw", "")),
        "ts": int(data.get("ts", 0) or 0),
    }


def _parse_diagnostic_event(value) -> dict:
    if not isinstance(value, dict):
        return {
            "id": 0, "active": False, "severity": "info", "source": "system",
            "code": "none", "task": 0, "seq": 0, "reason": "", "ts": 0,
        }
    return {
        "id": int(value.get("id", 0) or 0),
        "active": bool(value.get("a", value.get("active", False))),
        "severity": str(value.get("sev", value.get("severity", "info"))),
        "source": str(value.get("src", value.get("source", "system"))),
        "code": str(value.get("code", "none")),
        "task": int(value.get("task", 0) or 0),
        "seq": int(value.get("seq", 0) or 0),
        "reason": str(value.get("reason", "")),
        "ts": int(value.get("ts", 0) or 0),
    }


def parse_diagnostic_state(payload: str) -> dict:
    data = json.loads(payload)
    current = _parse_diagnostic_event(data.get("current"))
    last = _parse_diagnostic_event(data.get("last"))
    previous_raw = data.get("previous")
    previous = _parse_diagnostic_event(previous_raw) if isinstance(previous_raw, dict) else None
    return {
        "online": bool(data.get("online", False)),
        "current": current,
        "last": last,
        "previous": previous,
        "recent_count": int(data.get("recent_count", 0) or 0),
        "fw": str(data.get("fw", "")),
        "ts": int(data.get("ts", 0) or 0),
    }


def build_remote_button_payload(button: int, request_id: int) -> str:
    if button not in (1, 2, 3):
        raise ValueError("button must be 1, 2, or 3")
    if request_id <= 0 or request_id > 0x7FFFFFFF:
        raise ValueError("request_id must be a positive 31-bit integer")
    return json.dumps(
        {"type": "remote_button", "button": button, "request_id": request_id},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_remote_button_ack(payload: str) -> Optional[tuple[int, int, str, str]]:
    data = json.loads(payload)
    if data.get("type") != "remote_button_ack":
        return None
    return (
        int(data.get("button", 0)),
        int(data.get("request_id", 0)),
        str(data.get("status", "error")),
        str(data.get("reason", "")),
    )


class CallboxRemoteConfigClient:
    """Thread-safe MQTT management client for setup and remote test controls."""

    def __init__(self) -> None:
        if not PAHO_AVAILABLE:
            raise RuntimeError("paho-mqtt chưa được cài. Chạy: pip install paho-mqtt>=1.6")
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._request_id_lock = threading.Lock()
        self._request_id = secrets.randbelow(0x7FFFFFFE) + 1
        self._subscription_groups: dict[str, set[str]] = {
            "io": set(),
            "management": set(),
            "fleet": set(),
        }
        self.on_connect: Optional[Callable[[bool, str], None]] = None
        self.on_ack: Optional[Callable[[str, bool], None]] = None
        self.on_button_ack: Optional[Callable[[str, int, int, str, str], None]] = None
        self.on_io_state: Optional[Callable[[str, dict], None]] = None
        self.on_status_state: Optional[Callable[[str, dict], None]] = None
        self.on_internet_state: Optional[Callable[[str, dict], None]] = None
        self.on_health_state: Optional[Callable[[str, dict], None]] = None
        self.on_diagnostic_state: Optional[Callable[[str, dict], None]] = None
        self.on_info_state: Optional[Callable[[str, dict], None]] = None
        self.on_network_state: Optional[Callable[[str, dict], None]] = None
        self.on_trace_event: Optional[Callable[[str, dict], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, cfg: MqttBrokerConfig) -> None:
        if self._connected:
            self.disconnect()
        # Unique ID avoids broker kick/reconnect ping-pong when multiple tools are open.
        client_id = f"callbox-flasher-rc-{secrets.token_hex(4)}"
        # Do not retry forever when the broker rejects credentials or the initial connect.
        client = mqtt.Client(client_id=client_id, clean_session=True, reconnect_on_failure=False)
        if cfg.username:
            client.username_pw_set(cfg.username, cfg.password)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self._client = client
        self._log(f"Đang kết nối {cfg.host}:{cfg.port}...")
        try:
            client.connect_async(cfg.host, cfg.port, keepalive=30)
            client.loop_start()
        except Exception as exc:
            self._log(f"Lỗi kết nối: {exc}")
            if self.on_connect:
                self.on_connect(False, str(exc))

    def disconnect(self) -> None:
        if self._client:
            try:
                self._client.disconnect()
                self._client.loop_stop()
            except Exception:
                pass
            self._client = None
        self._connected = False
        for group in self._subscription_groups.values():
            group.clear()

    def _set_subscription_group(self, group_name: str, topics: set[str]) -> bool:
        if not self._connected or not self._client:
            return False
        previous_union = set().union(*self._subscription_groups.values())
        previous_group = set(self._subscription_groups[group_name])
        self._subscription_groups[group_name] = set(topics)
        new_union = set().union(*self._subscription_groups.values())
        added = new_union - previous_union
        removed = previous_union - new_union
        for topic in sorted(added):
            result = self._client.subscribe(topic, qos=1)
            if result[0] != mqtt.MQTT_ERR_SUCCESS:
                self._subscription_groups[group_name] = previous_group
                self._log(f"Không subscribe được topic {topic}")
                return False
        for topic in sorted(removed):
            try:
                self._client.unsubscribe(topic)
            except Exception:
                pass
        return True

    def subscribe_io_state(self, callbox_id: str) -> bool:
        try:
            topic = io_state_topic(callbox_id)
            legacy_topic = f"callbox/{callbox_id.strip()}/io"
        except ValueError as exc:
            self._log(str(exc))
            return False
        ok = self._set_subscription_group("io", {topic, legacy_topic})
        if ok:
            self._log(f"Đang giám sát I/O: {topic}")
        return ok

    def subscribe_device_state(self, callbox_id: str) -> bool:
        try:
            topics = {
                status_topic(callbox_id),
                io_state_topic(callbox_id),
                internet_topic(callbox_id),
                health_topic(callbox_id),
                diagnostic_topic(callbox_id),
                info_topic(callbox_id),
                network_topic(callbox_id),
                trace_topic(callbox_id),
                f"callbox/{callbox_id.strip()}/io",
                f"callbox/{callbox_id.strip()}/health",
                f"callbox/{callbox_id.strip()}/internet",
            }
        except ValueError as exc:
            self._log(str(exc))
            return False
        ok = self._set_subscription_group("management", topics)
        if ok:
            self._log(f"Đang quản lý Callbox {callbox_id.strip()}: status + mgmt telemetry (legacy fallback enabled)")
        return ok

    def subscribe_fleet_status(self, enabled: bool = True) -> bool:
        topics = {"callbox/+/status", "callbox/+/mgmt/health", "callbox/+/health"} if enabled else set()
        ok = self._set_subscription_group("fleet", topics)
        if ok:
            self._log("Fleet status + health monitoring enabled" if enabled else "Fleet monitoring disabled")
        return ok

    def _next_request_id(self) -> int:
        with self._request_id_lock:
            self._request_id += 1
            if self._request_id > 0x7FFFFFFF:
                self._request_id = 1
            return self._request_id

    def send_remote_config(self, callbox_id: str, payload: RemoteConfigPayload) -> bool:
        if not self._connected or not self._client:
            self._log("Chưa kết nối broker!")
            return False
        callbox_id = callbox_id.strip()
        if not callbox_id:
            self._log("Callbox ID mục tiêu đang trống.")
            return False
        cmd_topic, ack_topic = service_config_topics(callbox_id)
        subscribe_result = self._client.subscribe(ack_topic, qos=1)
        if subscribe_result[0] != mqtt.MQTT_ERR_SUCCESS:
            self._log(f"Không subscribe được ACK topic {ack_topic}")
            return False
        json_str = payload.to_json()
        self._log(f"→ Gửi remote_config → {cmd_topic}")
        self._log(f"  Payload: {json_str}")
        result = self._client.publish(cmd_topic, json_str, qos=1, retain=False)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def send_remote_button(self, callbox_id: str, button: int) -> tuple[bool, int]:
        if not self._connected or not self._client:
            self._log("Chưa kết nối broker!")
            return False, 0
        try:
            control_topic, ack_topic = remote_button_topics(callbox_id)
        except ValueError as exc:
            self._log(str(exc))
            return False, 0
        if button not in (1, 2, 3):
            self._log(f"Nút điều khiển không hợp lệ: {button}")
            return False, 0
        request_id = self._next_request_id()
        payload = build_remote_button_payload(button, request_id)
        subscribe_result = self._client.subscribe(ack_topic, qos=1)
        if subscribe_result[0] != mqtt.MQTT_ERR_SUCCESS:
            self._log(f"Không subscribe được control ACK topic {ack_topic}")
            return False, request_id
        self._log(f"→ Remote button {button} request_id={request_id} → {control_topic}")
        self._log(f"  Payload: {payload}")
        result = self._client.publish(control_topic, payload, qos=1, retain=False)
        ok = result.rc == mqtt.MQTT_ERR_SUCCESS
        if not ok:
            self._log(f"Publish remote button thất bại (rc={result.rc})")
        return ok, request_id

    def _on_connect(self, client, userdata, flags, rc) -> None:
        ok = rc == 0
        self._connected = ok
        msg = {
            0: "Đã kết nối broker",
            1: "Lỗi: Sai phiên bản protocol",
            2: "Lỗi: Từ chối client ID",
            3: "Lỗi: Broker không khả dụng",
            4: "Lỗi: Sai tài khoản/mật khẩu",
            5: "Lỗi: Không có quyền",
        }.get(rc, f"Lỗi kết nối (rc={rc})")
        self._log(msg)
        if self.on_connect:
            self.on_connect(ok, msg)

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False
        self._log("Đã ngắt kết nối broker")
        if self.on_connect:
            self.on_connect(False, "Đã ngắt kết nối")

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload_str = msg.payload.decode("utf-8", errors="replace")
            parts = msg.topic.split("/")
            callbox_id = parts[1] if len(parts) >= 3 else "?"
            retained = bool(getattr(msg, "retain", False))

            # High-rate telemetry feeds the dashboard directly; do not flood the log console.
            if msg.topic.endswith("/io"):
                if retained:
                    return
                io_state = parse_io_state(payload_str)
                if self.on_io_state:
                    self.on_io_state(callbox_id, io_state)
                return
            if msg.topic.endswith("/status"):
                status_state = parse_status_state(payload_str)
                # A retained online snapshot is historical, not proof that the device is
                # currently online. Retained offline/LWT still clears the dashboard.
                if retained and status_state.get("online"):
                    return
                if self.on_status_state:
                    self.on_status_state(callbox_id, status_state)
                return
            if msg.topic.endswith("/internet"):
                if retained:
                    return
                internet_state = parse_internet_state(payload_str)
                if self.on_internet_state:
                    self.on_internet_state(callbox_id, internet_state)
                return
            if msg.topic.endswith("/mgmt/info"):
                if retained:
                    return
                info_state = parse_info_state(payload_str)
                if self.on_info_state:
                    self.on_info_state(callbox_id, info_state)
                return
            if msg.topic.endswith("/mgmt/network"):
                if retained:
                    return
                network_state = parse_network_state(payload_str)
                if self.on_network_state:
                    self.on_network_state(callbox_id, network_state)
                return
            if msg.topic.endswith("/mgmt/trace"):
                trace_event = parse_trace_event(payload_str)
                if self.on_trace_event:
                    self.on_trace_event(callbox_id, trace_event)
                return
            if msg.topic.endswith("/health"):
                if retained:
                    return
                health_state = parse_health_state(payload_str)
                if self.on_health_state:
                    self.on_health_state(callbox_id, health_state)
                return
            if msg.topic.endswith("/diagnostic"):
                if retained:
                    return
                diagnostic_state = parse_diagnostic_state(payload_str)
                if self.on_diagnostic_state:
                    self.on_diagnostic_state(callbox_id, diagnostic_state)
                return

            self._log(f"MQTT t? {msg.topic}: {payload_str}")
            data = json.loads(payload_str)
            if data.get("type") == "config_ack":
                if self.on_ack:
                    self.on_ack(callbox_id, data.get("status") == "ok")
                return
            parsed = parse_remote_button_ack(payload_str)
            if parsed is not None:
                button, request_id, status, reason = parsed
                if self.on_button_ack:
                    self.on_button_ack(callbox_id, button, request_id, status, reason)
        except Exception as exc:
            self._log(f"Lỗi parse MQTT: {exc}")

    def _log(self, msg: str) -> None:
        if self.on_log:
            self.on_log(msg)

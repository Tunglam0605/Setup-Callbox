"""MQTT client for remote CallBox setup, monitoring and operator control.

The original remote_config flow remains on callbox/{id}/cmd + /event.
New operator controls are isolated on /control, /control_ack and /io so they
cannot change the authoritative WCS command/status contract.
"""
from __future__ import annotations

import json
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


def build_remote_button_payload(button: int, request_id: int) -> str:
    """Build the isolated management command used by firmware v1.5+."""
    if button not in (1, 2, 3):
        raise ValueError("button must be 1, 2 or 3")
    if request_id <= 0:
        raise ValueError("request_id must be positive")
    return json.dumps(
        {"type": "remote_button", "button": button, "request_id": request_id},
        separators=(",", ":"),
    )


def management_topics(callbox_id: str) -> dict[str, str]:
    cid = callbox_id.strip()
    if not cid:
        raise ValueError("callbox_id is required")
    return {
        "status": f"callbox/{cid}/status",
        "io": f"callbox/{cid}/io",
        "control": f"callbox/{cid}/control",
        "control_ack": f"callbox/{cid}/control_ack",
        "event": f"callbox/{cid}/event",
        "cmd": f"callbox/{cid}/cmd",
    }


class CallboxRemoteConfigClient:
    """Backward-compatible remote config client with optional monitoring/control."""

    def __init__(self) -> None:
        if not PAHO_AVAILABLE:
            raise RuntimeError("paho-mqtt chưa được cài. Chạy: pip install paho-mqtt>=1.6")
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._lock = threading.Lock()
        self._watched_callbox_id = ""
        self._last_remote_request_id = 0

        # Existing callbacks.
        self.on_connect: Optional[Callable[[bool, str], None]] = None
        self.on_ack: Optional[Callable[[str, bool], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None

        # New callbacks. They are independent from the existing config flow.
        self.on_status: Optional[Callable[[str, dict], None]] = None
        self.on_io: Optional[Callable[[str, dict], None]] = None
        self.on_control_ack: Optional[Callable[[str, dict], None]] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def watched_callbox_id(self) -> str:
        return self._watched_callbox_id

    def connect(self, cfg: MqttBrokerConfig) -> None:
        if self._connected:
            self.disconnect()

        client_id = f"callbox-flasher-rc-{int(time.time()) % 10000}"
        client = mqtt.Client(client_id=client_id, clean_session=True)
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
        client = self._client
        self._client = None
        self._connected = False
        if client:
            try:
                client.disconnect()
                client.loop_stop()
            except Exception:
                pass

    def watch_callbox(self, callbox_id: str) -> bool:
        """Subscribe to read-only status/io and the isolated control ACK topic."""
        cid = callbox_id.strip()
        if not cid:
            return False

        old_id = self._watched_callbox_id
        self._watched_callbox_id = cid
        if not self._connected or not self._client:
            return True

        if old_id and old_id != cid:
            old = management_topics(old_id)
            for key in ("status", "io", "control_ack"):
                try:
                    self._client.unsubscribe(old[key])
                except Exception:
                    pass

        topics = management_topics(cid)
        for key in ("status", "io", "control_ack"):
            result = self._client.subscribe(topics[key], qos=1)
            if isinstance(result, tuple) and result[0] != mqtt.MQTT_ERR_SUCCESS:
                self._log(f"Không subscribe được {topics[key]}")
                return False
        self._log(f"Theo dõi Callbox {cid}: status + io + control_ack")
        return True

    def send_remote_config(self, callbox_id: str, payload: RemoteConfigPayload) -> bool:
        """Existing behavior: remote_config remains on /cmd and ACK remains on /event."""
        if not self._connected or not self._client:
            self._log("Chưa kết nối broker!")
            return False

        topics = management_topics(callbox_id)
        self._client.subscribe(topics["event"], qos=1)
        json_str = payload.to_json()
        self._log(f"→ Gửi remote_config → {topics['cmd']}")
        result = self._client.publish(topics["cmd"], json_str, qos=1)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def send_remote_button(self, callbox_id: str, button: int) -> Optional[int]:
        """Send one momentary virtual press on the isolated /control topic."""
        if not self._connected or not self._client:
            self._log("Chưa kết nối broker!")
            return None
        if button not in (1, 2, 3):
            raise ValueError("button must be 1, 2 or 3")

        self.watch_callbox(callbox_id)
        request_id = int(time.time() * 1000) & 0x7FFFFFFF
        if request_id <= 0 or request_id == self._last_remote_request_id:
            request_id = (self._last_remote_request_id + 1) & 0x7FFFFFFF
            if request_id <= 0:
                request_id = 1
        self._last_remote_request_id = request_id
        topics = management_topics(callbox_id)
        payload = build_remote_button_payload(button, request_id)
        self._log(f"→ Remote button {button} → {topics['control']} (request_id={request_id})")
        result = self._client.publish(topics["control"], payload, qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            return None
        return request_id

    def _subscribe_watch_topics(self) -> None:
        if self._watched_callbox_id:
            self.watch_callbox(self._watched_callbox_id)

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
        if ok:
            self._subscribe_watch_topics()
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
            data = json.loads(payload_str)
            parts = msg.topic.split("/")
            cid = parts[1] if len(parts) >= 3 else "?"
            leaf = parts[-1] if parts else ""

            if leaf == "event" and data.get("type") == "config_ack":
                ok = data.get("status") == "ok"
                self._log(f"← config_ack từ Callbox {cid}: {data.get('status', '?')}")
                if self.on_ack:
                    self.on_ack(cid, ok)
            elif leaf == "status":
                if self.on_status:
                    self.on_status(cid, data)
            elif leaf == "io":
                if self.on_io:
                    self.on_io(cid, data)
            elif leaf == "control_ack" and data.get("type") == "remote_button_ack":
                self._log(
                    f"← control_ack Callbox {cid}: button={data.get('button')} "
                    f"status={data.get('status')} reason={data.get('reason', '')}"
                )
                if self.on_control_ack:
                    self.on_control_ack(cid, data)
        except Exception as exc:
            self._log(f"Lỗi parse MQTT: {exc}")

    def _log(self, msg: str) -> None:
        if self.on_log:
            self.on_log(msg)

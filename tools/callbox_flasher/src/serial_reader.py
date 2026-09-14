"""Module giao tiếp Serial để truy vấn trạng thái live và đọc cấu hình từ ESP32 Callbox."""

import json
import re
import time
from typing import Optional
import serial

from tools.callbox_flasher.src.models import DeviceConfig


class SerialReaderError(Exception):
    """Ngoại lệ khi đọc hoặc giao tiếp qua cổng Serial với thiết bị."""
    pass


def query_device_status(port: str, baudrate: int = 115200, timeout: float = 3.0) -> dict:
    """Truy vấn trạng thái hoạt động hiện tại của Callbox (Wi-Fi STA, IP, RSSI, MQTT, AP, ID) qua Serial.

    Gửi lệnh: CMD:STATUS
    Kỳ vọng nhận: >>>AUBOT:STATUS:{...}<<<
    """
    pattern = re.compile(r">>>AUBOT:STATUS:(.*?)<<<")
    buffer = ""
    start_time = time.monotonic()

    try:
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baudrate
        ser.timeout = 0.1
        ser.dtr = True
        ser.rts = False
        ser.open()
        if hasattr(ser, "reset_input_buffer"):
            ser.reset_input_buffer()
    except Exception as e:
        raise SerialReaderError(f"Không thể mở cổng {port}: {e}") from e

    try:
        # Gửi ký tự xuống dòng trước để xóa bộ đệm lệnh trên chip, sau đó gửi CMD:STATUS
        ser.write(b"\r\nCMD:STATUS\r\n")
        ser.flush()

        while (time.monotonic() - start_time) < timeout:
            data = ser.read(256)
            if data:
                buffer += data.decode("utf-8", errors="replace")
                match = pattern.search(buffer)
                if match:
                    json_str = match.group(1).strip()
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError as err:
                        raise SerialReaderError(f"Phản hồi trạng thái không phải JSON hợp lệ: {json_str}") from err
            time.sleep(0.05)

        raise SerialReaderError(f"Hết thời gian chờ phản hồi trạng thái từ ESP32 ({timeout}s).")
    finally:
        ser.close()


def query_device_config(port: str, baudrate: int = 115200, timeout: float = 3.0) -> DeviceConfig:
    """Đọc thông tin cấu hình đang lưu trong NVS của chip qua Serial.

    Gửi lệnh: CMD:CONFIG
    Kỳ vọng nhận: >>>AUBOT:CONFIG:{...}<<<
    """
    pattern = re.compile(r">>>AUBOT:CONFIG:(.*?)<<<")
    buffer = ""
    start_time = time.monotonic()

    try:
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baudrate
        ser.timeout = 0.1
        ser.dtr = True
        ser.rts = False
        ser.open()
        if hasattr(ser, "reset_input_buffer"):
            ser.reset_input_buffer()
    except Exception as e:
        raise SerialReaderError(f"Không thể mở cổng {port}: {e}") from e

    try:
        ser.write(b"\r\nCMD:CONFIG\r\n")
        ser.flush()

        while (time.monotonic() - start_time) < timeout:
            data = ser.read(256)
            if data:
                buffer += data.decode("utf-8", errors="replace")
                match = pattern.search(buffer)
                if match:
                    json_str = match.group(1).strip()
                    try:
                        parsed = json.loads(json_str)
                        return DeviceConfig(
                            callbox_id=str(parsed.get("callbox_id", "001")),
                            wifi_ssid=str(parsed.get("wifi_ssid", "")),
                            wifi_pass=str(parsed.get("wifi_pass", "")),
                            wifi_dhcp=bool(parsed.get("wifi_dhcp", 1)),
                            wifi_ip=str(parsed.get("wifi_ip", "")),
                            wifi_netmask=str(parsed.get("wifi_netmask", "")),
                            wifi_gateway=str(parsed.get("wifi_gateway", "")),
                            wifi_dns=str(parsed.get("wifi_dns", "")),
                            mqtt_broker=str(parsed.get("mqtt_broker", "")),
                            mqtt_port=int(parsed.get("mqtt_port", 1883)),
                            mqtt_tls=bool(parsed.get("mqtt_tls", 0)),
                            mqtt_user=str(parsed.get("mqtt_user", "fms")),
                            mqtt_pass=str(parsed.get("mqtt_pass", "")),
                            operating_version=str(parsed.get("version", "No version")),
                            listpoint_publish_enabled=bool(parsed.get("listpoint_publish", 0)),
                            listpoints_source=str(parsed.get("listpoints_source", "")),
                            listpoints_dest=str(parsed.get("listpoints_dest", "")),
                            sntp_primary=str(parsed.get("sntp_primary", "pool.ntp.org")),
                            sntp_fallback=str(parsed.get("sntp_fallback", "time.google.com")),
                        )
                    except json.JSONDecodeError as err:
                        raise SerialReaderError(f"Phản hồi cấu hình không phải JSON hợp lệ: {json_str}") from err
            time.sleep(0.05)

        raise SerialReaderError(f"Hết thời gian chờ phản hồi cấu hình từ ESP32 ({timeout}s).")
    finally:
        ser.close()


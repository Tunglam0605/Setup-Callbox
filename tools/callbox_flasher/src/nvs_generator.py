"""
Module sinh phân vùng NVS nhị phân (nvs_cfg.bin) cho thiết bị CallBox.

Sử dụng thư viện chuẩn esp_idf_nvs_partition_gen để đóng gói toàn bộ
cấu hình vận hành (Callbox ID, Wi-Fi, MQTT, Phiên bản, Danh sách điểm)
vào phân vùng nvs_cfg (offset 0x214000, size 0x20000 = 128KB).
Tuân thủ 100% schema persistence định nghĩa trong callbox_storage_schema.h.
"""

import csv
import io
import os
import pathlib
import tempfile
import types
from typing import Optional

import esp_idf_nvs_partition_gen.nvs_partition_gen as nvs

from tools.callbox_flasher.src.models import DeviceConfig

# Kích thước phân vùng nvs_cfg cố định theo partitions.csv (0x20000 = 131072 bytes)
NVS_PARTITION_SIZE_HEX = "0x20000"
NVS_PARTITION_SIZE_BYTES = 131072
NVS_PARTITION_VERSION = 2
NVS_NAMESPACE = "callbox"


def build_nvs_csv(config: DeviceConfig) -> str:
    """
    Tạo nội dung CSV theo định dạng của ESP-IDF NVS Partition Generator.
    Mọi key đều được kiểm tra độ dài tối đa 15 ký tự theo quy chuẩn NVS ESP32.
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=",", lineterminator="\n")

    # Dòng tiêu đề chuẩn
    writer.writerow(["key", "type", "encoding", "value"])

    # Khai báo namespace "callbox"
    writer.writerow([NVS_NAMESPACE, "namespace", "", ""])

    # 1. Định danh Callbox
    writer.writerow(["callbox_id", "data", "string", str(config.callbox_id or "001")])
    writer.writerow(["web_pass", "data", "string", "aubot"])

    # 2. Cấu hình Wi-Fi chính
    writer.writerow(["wifi_ssid", "data", "string", str(config.wifi_ssid or "")])
    writer.writerow(["wifi_pass", "data", "string", str(config.wifi_pass or "")])
    writer.writerow(["wifi_dhcp", "data", "u8", 1 if config.wifi_dhcp else 0])

    if not config.wifi_dhcp:
        if config.wifi_ip:
            writer.writerow(["wifi_ip", "data", "string", str(config.wifi_ip)])
        if config.wifi_netmask:
            writer.writerow(["wifi_mask", "data", "string", str(config.wifi_netmask)])
        if config.wifi_gateway:
            writer.writerow(["wifi_gw", "data", "string", str(config.wifi_gateway)])
        if config.wifi_dns:
            writer.writerow(["wifi_dns", "data", "string", str(config.wifi_dns)])

    # 3. Wi-Fi Profile 0 (đồng bộ cho danh sách profile nhớ)
    if config.wifi_ssid:
        writer.writerow(["wifi_count", "data", "u8", 1])
        writer.writerow(["wifi0_ssid", "data", "string", str(config.wifi_ssid)])
        writer.writerow(["wifi0_pass", "data", "string", str(config.wifi_pass or "")])
    else:
        writer.writerow(["wifi_count", "data", "u8", 0])

    # 4. Cấu hình MQTT
    writer.writerow(["mqtt_broker", "data", "string", str(config.mqtt_broker or "")])
    writer.writerow(["mqtt_port", "data", "u16", int(config.mqtt_port or 1883)])
    writer.writerow(["mqtt_tls", "data", "u8", 1 if config.mqtt_tls else 0])
    writer.writerow(["mqtt_user", "data", "string", str(config.mqtt_user or "")])
    writer.writerow(["mqtt_pass", "data", "string", str(config.mqtt_pass or "")])

    # 5. Operating Version + legacy NVS compatibility keys.
    # CallBox runtime does not own Source/Destination/Listpoint. Keep the old keys only so
    # older firmware/schema readers can migrate safely; production values are always empty/off.
    writer.writerow(["mode_ver", "data", "string", str(config.operating_version or "No version")])
    writer.writerow(["list_pub", "data", "u8", 0])
    writer.writerow(["lp_src", "data", "string", ""])
    writer.writerow(["lp_dst", "data", "string", ""])

    # 6. SNTP Servers
    writer.writerow(["sntp_primary", "data", "string", str(config.sntp_primary or "pool.ntp.org")])
    writer.writerow(["sntp_fallback", "data", "string", str(config.sntp_fallback or "time.google.com")])

    return output.getvalue()


def generate_nvs_config_bin(
    config: DeviceConfig,
    output_dir: Optional[pathlib.Path] = None,
    filename: str = "nvs_cfg.bin"
) -> pathlib.Path:
    """
    Tạo file nhị phân phân vùng NVS từ đối tượng DeviceConfig.
    Trả về đường dẫn tới file nvs_cfg.bin có kích thước đúng 128KB (0x20000 bytes).
    """
    if output_dir is None:
        temp_dir = tempfile.mkdtemp(prefix="callbox_nvs_")
        target_dir = pathlib.Path(temp_dir)
    else:
        target_dir = output_dir
        target_dir.mkdir(parents=True, exist_ok=True)

    csv_path = target_dir / "nvs_temp.csv"
    bin_path = target_dir / filename

    # Ghi nội dung CSV cấu hình
    csv_content = build_nvs_csv(config)
    csv_path.write_text(csv_content, encoding="utf-8")

    # Gọi generator của ESP-IDF
    gen_args = types.SimpleNamespace(
        size=NVS_PARTITION_SIZE_HEX,
        version=NVS_PARTITION_VERSION,
        output=filename,
        outdir=str(target_dir),
        input=str(csv_path),
    )

    try:
        nvs.generate(gen_args)
    finally:
        # Xóa file CSV tạm thời sau khi tạo xong binary
        if csv_path.is_file():
            try:
                os.remove(csv_path)
            except Exception:
                pass

    if not bin_path.is_file():
        raise RuntimeError(f"Không tạo được file nhị phân NVS tại: {bin_path}")

    actual_size = bin_path.stat().st_size
    if actual_size != NVS_PARTITION_SIZE_BYTES:
        raise ValueError(
            f"Kích thước file NVS không đúng: {actual_size} bytes (yêu cầu đúng {NVS_PARTITION_SIZE_BYTES} bytes)"
        )

    return bin_path

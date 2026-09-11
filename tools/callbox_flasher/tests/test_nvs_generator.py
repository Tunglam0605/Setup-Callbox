import pathlib
import tempfile
import unittest

from tools.callbox_flasher.src.models import DeviceConfig
from tools.callbox_flasher.src.nvs_generator import (
    NVS_PARTITION_SIZE_BYTES,
    build_nvs_csv,
    generate_nvs_config_bin,
)


class TestNvsGenerator(unittest.TestCase):
    def test_build_nvs_csv_contains_all_schema_keys(self):
        config = DeviceConfig(
            callbox_id="042",
            wifi_ssid="MyFactoryWiFi",
            wifi_pass="Secret123",
            wifi_dhcp=True,
            mqtt_broker="wcs.test.vn",
            mqtt_port=1883,
            mqtt_tls=False,
            mqtt_user="myuser",
            mqtt_pass="mypass",
            operating_version="1.0",
            listpoint_publish_enabled=True,
            listpoints_source="0001, 0002",
            listpoints_dest="0003, 0004",
        )
        csv_text = build_nvs_csv(config)

        # Kiểm tra namespace
        self.assertIn("callbox,namespace,,", csv_text)

        # Kiểm tra các key bắt buộc
        self.assertIn("callbox_id,data,string,042", csv_text)
        self.assertIn("wifi_ssid,data,string,MyFactoryWiFi", csv_text)
        self.assertIn("wifi_pass,data,string,Secret123", csv_text)
        self.assertIn("wifi_dhcp,data,u8,1", csv_text)
        self.assertIn("mqtt_broker,data,string,wcs.test.vn", csv_text)
        self.assertIn("mqtt_port,data,u16,1883", csv_text)
        self.assertIn("mode_ver,data,string,1.0", csv_text)
        self.assertIn("list_pub,data,u8,0", csv_text)
        self.assertIn("lp_src,data,string,", csv_text)
        self.assertIn("lp_dst,data,string,", csv_text)
        self.assertNotIn("0001, 0002", csv_text)
        self.assertNotIn("0003, 0004", csv_text)
        self.assertIn("wifi0_ssid,data,string,MyFactoryWiFi", csv_text)
        self.assertIn("wifi0_pass,data,string,Secret123", csv_text)

    def test_build_nvs_csv_version_2_keeps_legacy_listpoint_keys_disabled(self):
        """Version 2.0 luôn tự động tắt xuất bản danh sách điểm (list_pub = 0)."""
        config = DeviceConfig(
            operating_version="2.0",
            listpoints_source="0001, 0002",
            listpoints_dest="0003, 0004",
        )
        csv_text = build_nvs_csv(config)
        self.assertIn("mode_ver,data,string,2.0", csv_text)
        self.assertIn("list_pub,data,u8,0", csv_text)

    def test_build_nvs_csv_no_version_keeps_legacy_listpoint_keys_disabled(self):
        """No version luôn tự động tắt xuất bản danh sách điểm (list_pub = 0)."""
        config = DeviceConfig(
            operating_version="No version",
            listpoints_source="0001, 0002",
        )
        csv_text = build_nvs_csv(config)
        self.assertIn("mode_ver,data,string,No version", csv_text)
        self.assertIn("list_pub,data,u8,0", csv_text)

    def test_generate_nvs_config_bin_creates_exact_128kb_binary(self):
        config = DeviceConfig(
            callbox_id="001",
            wifi_ssid="Factory-Test-WiFi",
            wifi_pass="aubot123",
        )
        with tempfile.TemporaryDirectory() as td:
            out_dir = pathlib.Path(td)
            bin_path = generate_nvs_config_bin(config, output_dir=out_dir)

            self.assertTrue(bin_path.is_file())
            self.assertEqual(bin_path.name, "nvs_cfg.bin")
            self.assertEqual(bin_path.stat().st_size, NVS_PARTITION_SIZE_BYTES)
            self.assertEqual(bin_path.stat().st_size, 0x20000)


if __name__ == "__main__":
    unittest.main()

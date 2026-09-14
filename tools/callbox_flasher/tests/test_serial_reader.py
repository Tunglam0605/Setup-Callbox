"""Kiểm thử đơn vị cho module serial_reader."""

import json
import unittest
from unittest.mock import MagicMock, patch

from tools.callbox_flasher.src.models import DeviceConfig
from tools.callbox_flasher.src.serial_reader import (
    SerialReaderError,
    query_device_config,
    query_device_status,
)


class SerialReaderTests(unittest.TestCase):
    @patch("serial.Serial")
    def test_query_device_status_success(self, mock_serial_cls):
        mock_ser = MagicMock()
        mock_serial_cls.return_value = mock_ser

        # Giả lập phản hồi từ ESP32 kèm các log rác xung quanh
        mock_ser.read.side_effect = [
            b"I (1234) main: boot completed\r\n",
            b">>>AUBOT:STATUS:{\"sta\":1,\"ssid\":\"AubotOffice\",\"rssi\":-42,\"ip\":\"192.168.1.10\",\"mqtt\":1,\"ap\":1,\"client_id\":\"AUBOT-Callbox-001\"}<<<\r\n",
        ]

        status = query_device_status("COM15", timeout=1.0)
        self.assertEqual(status["sta"], 1)
        self.assertEqual(status["ssid"], "AubotOffice")
        self.assertEqual(status["ip"], "192.168.1.10")
        self.assertEqual(status["mqtt"], 1)
        self.assertEqual(status["client_id"], "AUBOT-Callbox-001")
        mock_ser.write.assert_called_with(b"\r\nCMD:STATUS\r\n")

    @patch("serial.Serial")
    def test_query_device_config_success(self, mock_serial_cls):
        mock_ser = MagicMock()
        mock_serial_cls.return_value = mock_ser

        sample_cfg = {
            "callbox_id": "005",
            "wifi_ssid": "AGV_TEST",
            "wifi_pass": "pass123",
            "wifi_dhcp": 1,
            "mqtt_broker": "mqtt.server.local",
            "mqtt_port": 1883,
            "version": "1.0",
            "listpoint_publish": 1,
            "listpoints_source": "SRC1",
            "listpoints_dest": "DST1",
        }
        mock_ser.read.side_effect = [
            f">>>AUBOT:CONFIG:{json.dumps(sample_cfg)}<<<\r\n".encode("utf-8")
        ]

        config = query_device_config("COM15", timeout=1.0)
        self.assertIsInstance(config, DeviceConfig)
        self.assertEqual(config.callbox_id, "005")
        self.assertEqual(config.wifi_ssid, "AGV_TEST")
        self.assertEqual(config.wifi_pass, "pass123")
        self.assertEqual(config.mqtt_broker, "mqtt.server.local")
        self.assertEqual(config.operating_version, "1.0")
        self.assertTrue(config.listpoint_publish_enabled)
        self.assertEqual(config.listpoints_source, "SRC1")
        self.assertEqual(config.listpoints_dest, "DST1")

    @patch("serial.Serial")
    def test_timeout_raises_serial_reader_error(self, mock_serial_cls):
        mock_ser = MagicMock()
        mock_serial_cls.return_value = mock_ser
        mock_ser.read.return_value = b""

        with self.assertRaises(SerialReaderError):
            query_device_status("COM15", timeout=0.1)


if __name__ == "__main__":
    unittest.main()


import json
import tempfile
import unittest
from pathlib import Path

from tools.callbox_flasher.src.factory_profile import load_factory_profile


class FactoryProfileTests(unittest.TestCase):
    def test_missing_profile_uses_public_safe_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = load_factory_profile(Path(temp) / "missing.json")
        self.assertEqual(cfg.wifi_ssid, "")
        self.assertEqual(cfg.wifi_pass, "")
        self.assertEqual(cfg.mqtt_broker, "")
        self.assertEqual(cfg.mqtt_user, "")
        self.assertEqual(cfg.mqtt_pass, "")
        self.assertFalse(cfg.listpoint_publish_enabled)

    def test_private_profile_loads_supported_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "factory.json"
            path.write_text(json.dumps({
                "callbox_id": "042",
                "wifi_ssid": "Factory-Test",
                "wifi_pass": "dummy-wifi-secret",
                "mqtt_broker": "broker.example.test",
                "mqtt_port": 2883,
                "mqtt_user": "dummy-user",
                "mqtt_pass": "dummy-mqtt-secret",
                "operating_version": "1.0"
            }), encoding="utf-8")
            cfg = load_factory_profile(path)
        self.assertEqual(cfg.callbox_id, "042")
        self.assertEqual(cfg.wifi_ssid, "Factory-Test")
        self.assertEqual(cfg.mqtt_broker, "broker.example.test")
        self.assertEqual(cfg.mqtt_port, 2883)
        self.assertEqual(cfg.operating_version, "1.0")
        self.assertFalse(cfg.listpoint_publish_enabled)
        self.assertEqual(cfg.listpoints_source, "")
        self.assertEqual(cfg.listpoints_dest, "")

    def test_profile_rejects_invalid_operating_version(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "factory.json"
            path.write_text('{"operating_version":"9.9"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_factory_profile(path)


if __name__ == "__main__":
    unittest.main()

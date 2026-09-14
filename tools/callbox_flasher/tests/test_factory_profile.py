import json
import tempfile
import unittest
from pathlib import Path

from tools.callbox_flasher.src.factory_profile import load_factory_profile, save_factory_profile, validate_factory_profile_for_worker


class FactoryProfileTests(unittest.TestCase):
    def test_missing_profile_returns_neutral_defaults_for_engineer_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_factory_profile(Path(tmp) / "missing.json")
            self.assertEqual(cfg.wifi_ssid, "")
            self.assertEqual(cfg.wifi_pass, "")
            self.assertEqual(cfg.mqtt_broker, "")
            self.assertEqual(cfg.mqtt_user, "")
            self.assertEqual(cfg.mqtt_pass, "")

    def test_worker_mode_can_require_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                load_factory_profile(Path(tmp) / "missing.json", require=True)

    def test_blank_profile_is_not_factory_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Setup-CallBox.factory.json"
            path.write_text(json.dumps({"operating_version": "2.0"}), encoding="utf-8")
            cfg = load_factory_profile(path, require=True)
            with self.assertRaises(ValueError):
                validate_factory_profile_for_worker(cfg)

    def test_profile_loads_machine_local_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Setup-CallBox.factory.json"
            path.write_text(json.dumps({
                "callbox_id": "0063",
                "wifi_ssid": "PlantNet",
                "wifi_pass": "local-only",
                "mqtt_broker": "broker.local",
                "mqtt_port": 1883,
                "mqtt_user": "operator",
                "mqtt_pass": "local-only",
                "operating_version": "2.0",
            }), encoding="utf-8")
            cfg = load_factory_profile(path, require=True)
            self.assertEqual(cfg.callbox_id, "0063")
            self.assertEqual(cfg.wifi_ssid, "PlantNet")
            self.assertEqual(cfg.mqtt_broker, "broker.local")
            self.assertEqual(cfg.operating_version, "2.0")

    def test_save_factory_profile_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Setup-CallBox.factory.json"
            cfg_path = Path(path)
            from tools.callbox_flasher.src.models import DeviceConfig
            cfg = DeviceConfig(
                callbox_id="001", wifi_ssid="PlantNet", wifi_pass="wifi-secret",
                mqtt_broker="broker.local", mqtt_port=1883, mqtt_user="operator",
                mqtt_pass="mqtt-secret", operating_version="2.0",
            )
            saved = save_factory_profile(cfg, cfg_path)
            self.assertEqual(saved, cfg_path)
            loaded = load_factory_profile(cfg_path, require=True)
            self.assertEqual(loaded.wifi_ssid, "PlantNet")
            self.assertEqual(loaded.mqtt_broker, "broker.local")
            self.assertEqual(loaded.operating_version, "2.0")



if __name__ == "__main__":
    unittest.main()

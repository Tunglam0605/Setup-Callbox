import time
import unittest

from tools.callbox_flasher.src import ui_management_logic
from tools.callbox_flasher.src.ui_management_logic import (
    age_text, alarm_state, format_bytes, format_uptime, health_level, reset_reason_text, telemetry_state, usage_percent,
)


class ManagementLogicTests(unittest.TestCase):
    def test_reset_reason_usb_is_named(self):
        self.assertEqual(reset_reason_text(11), "USB")

    def test_uptime_format(self):
        self.assertEqual(format_uptime(3661), "01:01:01")

    def test_healthy_record_is_ok(self):
        record = {"health": {"free_heap": 48 * 1024, "recovery": False, "mqtt": {}}}
        self.assertEqual(health_level(record), "OK")

    def test_mqtt_drop_is_warning(self):
        record = {"health": {"free_heap": 48 * 1024, "recovery": False, "mqtt": {"queue_drop": 1}}}
        self.assertEqual(health_level(record), "WARN")

    def test_trace_log_drop_does_not_trigger_health_warning(self):
        record = {
            "health": {
                "free_heap": 48 * 1024, "recovery": False,
                "mqtt": {"queue_drop": 8, "management_trace_drop": 8, "wcs_queue_drop": 0, "cmd_drop": 0, "outbox_fail": 0}
            }
        }
        self.assertEqual(health_level(record), "OK")

    def test_recovery_is_fault(self):
        record = {"health": {"free_heap": 48 * 1024, "recovery": True, "mqtt": {}}}
        self.assertEqual(health_level(record), "FAULT")

    def test_alarm_flags_weak_rssi(self):
        now = time.monotonic()
        record = {
            "status_rx": now, "online": True, "comm": "ready", "rssi": -81,
            "health": {"free_heap": 48 * 1024, "recovery": False, "mqtt": {}},
        }
        level, alarms = alarm_state(record, now)
        self.assertEqual(level, "WARN")
        self.assertTrue(any("RSSI" in item for item in alarms))

    def test_age_text(self):
        self.assertEqual(age_text(0.0, 10.0), "--")

    def test_usage_percent_and_bytes(self):
        self.assertAlmostEqual(usage_percent(128, 256), 50.0)
        self.assertEqual(usage_percent(1, 0), 0.0)
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(2 * 1024 * 1024), "2.00 MB")

    def test_diagnostic_fault_overrides_health(self):
        record = {
            "health": {"free_heap": 48 * 1024, "recovery": False, "mqtt": {}},
            "diagnostic": {"current": {"active": True, "severity": "fault", "code": "wcs_call_rejected", "reason": "locked"}},
        }
        self.assertEqual(health_level(record), "FAULT")

    def test_diagnostic_warning_is_reported_by_alarm(self):
        import time
        now = time.monotonic()
        record = {
            "status_rx": now, "online": True, "comm": "ready", "rssi": -45,
            "health": {"free_heap": 48 * 1024, "recovery": False, "mqtt": {}},
            "diagnostic": {"current": {"active": True, "severity": "warning", "code": "call_ack_timeout", "reason": "wcs_ack_timeout"}},
        }
        level, alarms = alarm_state(record, now)
        self.assertEqual(level, "WARN")
        self.assertTrue(any("call_ack_timeout" in item for item in alarms))

    def test_stale_io_is_telemetry_only_not_device_health_warning(self):
        now = time.monotonic()
        record = {
            "status_rx": now, "online": True, "io_rx": now - 2.0, "comm": "ready", "rssi": -45,
            "health": {"free_heap": 48 * 1024, "recovery": False, "mqtt": {}},
            "fw": "1.5.6",
        }
        self.assertEqual(alarm_state(record, now), ("OK", []))
        self.assertEqual(telemetry_state(record, now)["io"], "DELAYED")

    def test_legacy_io_uses_three_second_threshold(self):
        now = time.monotonic()
        record = {"io_rx": now - 2.5, "fw": "1.5.4"}
        self.assertEqual(telemetry_state(record, now)["io"], "LIVE")

    def test_management_network_does_not_override_missing_online_status(self):
        now = time.monotonic()
        record = {
            "network_rx": now,
            "network": {"mqtt": {"transport_connected": True, "wcs_plane_ready": False}},
            "comm": "syncing", "rssi": -50,
            "health": {"free_heap": 48 * 1024, "recovery": False, "mqtt": {}},
        }
        level, alarms = alarm_state(record, now)
        self.assertEqual(level, "OFFLINE")
        self.assertIn("Không nhận status mới", alarms)

    def test_management_details_require_fresh_online_status(self):
        self.assertTrue(hasattr(ui_management_logic, "device_is_online"), "device_is_online is missing")
        device_is_online = ui_management_logic.device_is_online
        now = time.monotonic()
        network_only = {
            "network_rx": now,
            "network": {"mqtt": {"transport_connected": True}},
        }
        explicit_offline = {"status_rx": now, "online": False}
        fresh_online = {"status_rx": now, "online": True}
        stale_online = {"status_rx": now - 4.0, "online": True}

        self.assertFalse(device_is_online(network_only, now))
        self.assertFalse(device_is_online(explicit_offline, now))
        self.assertTrue(device_is_online(fresh_online, now))
        self.assertFalse(device_is_online(stale_online, now))


if __name__ == "__main__":
    unittest.main()

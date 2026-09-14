"""Unit tests for mqtt_remote_config module."""
import json
import unittest

from tools.callbox_flasher.src.mqtt_remote_config import (
    CallboxRemoteConfigClient, MqttBrokerConfig, RemoteConfigPayload,
    build_remote_button_payload, diagnostic_topic, health_topic, info_topic, io_state_topic, internet_topic, network_topic, trace_topic,
    parse_diagnostic_state, parse_health_state, parse_info_state, parse_internet_state, parse_io_state, parse_network_state, parse_remote_button_ack, parse_status_state, parse_trace_event,
    remote_button_topics, service_config_topics, status_topic,
)


class TestRemoteConfigPayload(unittest.TestCase):
    def test_payload_partial_serialization(self):
        payload = RemoteConfigPayload(
            callbox_id="CALLBOX-01",
            operating_version="1.0",
            reboot=False,
        )
        json_str = payload.to_json()
        data = json.loads(json_str)

        self.assertEqual(data["type"], "remote_config")
        self.assertEqual(data["callbox_id"], "CALLBOX-01")
        self.assertEqual(data["operating_version"], "1.0")
        self.assertFalse(data["reboot"])
        self.assertNotIn("wifi_ssid", data)
        self.assertNotIn("mqtt_broker", data)

    def test_payload_full_serialization(self):
        payload = RemoteConfigPayload(
            callbox_id="002",
            operating_version="2.0",
            wifi_ssid="Plant_WiFi",
            wifi_pass="Secret123",
            mqtt_broker="10.0.0.5",
            mqtt_port=1883,
            mqtt_user="callbox",
            mqtt_pass="pass456",
            reboot=True,
        )
        json_str = payload.to_json()
        data = json.loads(json_str)

        self.assertEqual(data["type"], "remote_config")
        self.assertEqual(data["callbox_id"], "002")
        self.assertEqual(data["operating_version"], "2.0")
        self.assertEqual(data["wifi_ssid"], "Plant_WiFi")
        self.assertEqual(data["wifi_pass"], "Secret123")
        self.assertEqual(data["mqtt_broker"], "10.0.0.5")
        self.assertEqual(data["mqtt_port"], 1883)
        self.assertEqual(data["mqtt_user"], "callbox")
        self.assertEqual(data["mqtt_pass"], "pass456")
        self.assertTrue(data["reboot"])

    def test_broker_config_defaults(self):
        broker = MqttBrokerConfig()
        self.assertEqual(broker.host, "")
        self.assertEqual(broker.port, 1883)
        self.assertEqual(broker.username, "")


class TestRemoteButtonManagement(unittest.TestCase):
    def test_topics_are_isolated_from_wcs_command_plane(self):
        self.assertEqual(remote_button_topics("0063"), ("callbox/0063/mgmt/service/control", "callbox/0063/mgmt/service/control_ack"))
        self.assertEqual(service_config_topics("0063"), ("callbox/0063/mgmt/service/config", "callbox/0063/mgmt/service/config_ack"))

    def test_io_state_topic_and_payload_parser(self):
        self.assertEqual(io_state_topic("0063"), "callbox/0063/mgmt/io")
        payload = json.dumps({
            "online": True, "comm": "IDLE", "version": "2.0",
            "task1": "IDLE", "task2": "CALLING", "warning": "NONE",
            "buttons": [1, 0, 1], "button_leds": [1, 1, 0],
            "tower": {"red": 0, "yellow": 1, "green": 1},
            "fw": "1.5.2", "ts": 123,
        })
        state = parse_io_state(payload)
        self.assertEqual(state["buttons"], (True, False, True))
        self.assertEqual(state["button_leds"], (True, True, False))
        self.assertEqual(state["tower"], (False, True, True))
        self.assertEqual(state["comm"], "IDLE")
        self.assertEqual(state["task2"], "CALLING")

    def test_parse_io_state_rejects_missing_arrays(self):
        with self.assertRaises(ValueError):
            parse_io_state('{"online":true}')

    def test_payload_matches_firmware_contract(self):
        self.assertEqual(json.loads(build_remote_button_payload(2, 12345)), {"type": "remote_button", "button": 2, "request_id": 12345})

    def test_payload_rejects_invalid_values(self):
        with self.assertRaises(ValueError): build_remote_button_payload(4, 1)
        with self.assertRaises(ValueError): build_remote_button_payload(1, 0)

    def test_parse_remote_button_ack(self):
        parsed = parse_remote_button_ack('{"type":"remote_button_ack","status":"ok","button":1,"request_id":99,"reason":"queued"}')
        self.assertEqual(parsed, (1, 99, "ok", "queued"))
        self.assertIsNone(parse_remote_button_ack('{"type":"config_ack","status":"ok"}'))


    def test_connect_disables_automatic_reconnect_on_initial_failure(self):
        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.on_connect = None
                self.on_disconnect = None
                self.on_message = None
            def username_pw_set(self, username, password):
                self.username = username
                self.password = password
            def connect_async(self, host, port, keepalive):
                self.connect_args = (host, port, keepalive)
            def loop_start(self):
                self.loop_started = True

        from unittest.mock import patch
        from tools.callbox_flasher.src.mqtt_remote_config import MqttBrokerConfig
        with patch("tools.callbox_flasher.src.mqtt_remote_config.mqtt.Client", FakeClient):
            client = CallboxRemoteConfigClient()
            client.connect(MqttBrokerConfig(host="broker.local", port=1883, username="u", password="p"))
            self.assertFalse(client._client.kwargs["reconnect_on_failure"])
            self.assertTrue(client._client.kwargs["client_id"].startswith("callbox-flasher-rc-"))
            self.assertGreater(len(client._client.kwargs["client_id"]), len("callbox-flasher-rc-"))

    def test_request_ids_are_positive_unique_and_wrap_safely(self):
        client = CallboxRemoteConfigClient.__new__(CallboxRemoteConfigClient)
        import threading
        client._request_id_lock = threading.Lock()
        client._request_id = 0x7FFFFFFE
        self.assertEqual(client._next_request_id(), 0x7FFFFFFF)
        self.assertEqual(client._next_request_id(), 1)

    def test_send_remote_button_subscribes_before_qos1_publish(self):
        import threading
        from tools.callbox_flasher.src import mqtt_remote_config as module

        class PublishResult:
            rc = module.mqtt.MQTT_ERR_SUCCESS

        class FakeClient:
            def __init__(self):
                self.calls = []

            def subscribe(self, topic, qos):
                self.calls.append(("subscribe", topic, qos))
                return module.mqtt.MQTT_ERR_SUCCESS, 11

            def publish(self, topic, payload, qos, retain):
                self.calls.append(("publish", topic, json.loads(payload), qos, retain))
                return PublishResult()

        client = CallboxRemoteConfigClient.__new__(CallboxRemoteConfigClient)
        client._connected = True
        client._client = FakeClient()
        client._request_id_lock = threading.Lock()
        client._request_id = 100
        client.on_log = None
        ok, request_id = client.send_remote_button("0063", 1)
        self.assertTrue(ok)
        self.assertEqual(request_id, 101)
        self.assertEqual(client._client.calls[0], ("subscribe", "callbox/0063/mgmt/service/control_ack", 1))
        self.assertEqual(client._client.calls[1][0:2], ("publish", "callbox/0063/mgmt/service/control"))
        self.assertEqual(client._client.calls[1][2], {"type": "remote_button", "button": 1, "request_id": 101})
        self.assertEqual(client._client.calls[1][3:], (1, False))


    def test_health_topic_and_parser(self):
        self.assertEqual(health_topic("0063"), "callbox/0063/mgmt/health")
        state = parse_health_state(json.dumps({
            "online": True, "free_heap": 50000, "min_free_heap": 34000,
            "largest_block": 31000,
            "memory": {"total": 180000, "used": 130000, "free": 50000, "min_free": 34000, "largest_block": 31000},
            "flash": {"app_partition": 2097152, "app_image": 1280000, "app_free": 817152},
            "reset_reason": 1, "recovery": False,
            "mqtt": {"queue_drop": 2, "cmd_drop": 1, "outbox_fail": 0},
            "task_checkins": [10, 11, 12, 13, 14, 15, 16], "fw": "1.5.4", "ts": 123
        }))
        self.assertEqual(state["free_heap"], 50000)
        self.assertEqual(state["memory"]["total"], 180000)
        self.assertEqual(state["memory"]["used"], 130000)
        self.assertEqual(state["flash"]["app_partition"], 2097152)
        self.assertEqual(state["flash"]["app_image"], 1280000)
        self.assertEqual(state["mqtt"]["queue_drop"], 2)
        self.assertEqual(state["task_checkins"][6], 16)
        self.assertFalse(state["recovery"])


    def test_diagnostic_topic_and_parser(self):
        self.assertEqual(diagnostic_topic("0063"), "callbox/0063/mgmt/diagnostic")
        state = parse_diagnostic_state(json.dumps({
            "online": True,
            "current": {"id": 7, "a": True, "sev": "fault", "src": "wcs", "code": "wcs_call_rejected", "task": 1, "seq": 385, "reason": "locked", "ts": 123},
            "last": {"id": 7, "a": True, "sev": "fault", "src": "wcs", "code": "wcs_call_rejected", "task": 1, "seq": 385, "reason": "locked", "ts": 123},
            "previous": {"id": 6, "a": True, "sev": "warning", "src": "mqtt", "code": "call_ack_timeout", "task": 2, "seq": 372, "reason": "qos1_sent_no_wcs_ack", "ts": 100},
            "recent_count": 8, "fw": "1.5.6", "ts": 124,
        }))
        self.assertTrue(state["current"]["active"])
        self.assertEqual(state["current"]["code"], "wcs_call_rejected")
        self.assertEqual(state["current"]["reason"], "locked")
        self.assertEqual(state["previous"]["seq"], 372)
        self.assertEqual(state["recent_count"], 8)

    def test_management_status_and_internet_parsers(self):
        self.assertEqual(status_topic("0063"), "callbox/0063/status")
        self.assertEqual(internet_topic("0063"), "callbox/0063/internet")
        status = parse_status_state('{"online":true,"comm":"ready","version":"2.0","task1":"idle","task2":"called","rssi":-51,"uptime":3661,"time_synced":true,"fw":"1.5.2","ts":123}')
        self.assertTrue(status["online"])
        self.assertEqual(status["comm"], "ready")
        self.assertEqual(status["rssi"], -51)
        self.assertEqual(status["uptime"], 3661)
        internet = parse_internet_state('{"sta_connected":true,"sta_ssid":"AGV1","sta_ip":"192.168.1.20","sta_rssi":-55,"ap_active":false,"ap_ssid":"","ap_ip":"","eth_connected":true,"eth_ip":"10.0.0.2","ts":124}')
        self.assertTrue(internet["sta_connected"])
        self.assertEqual(internet["sta_ip"], "192.168.1.20")
        self.assertTrue(internet["eth_connected"])

    def test_management_info_network_trace_helpers_and_parsers(self):
        self.assertEqual(info_topic("0063"), "callbox/0063/mgmt/info")
        self.assertEqual(network_topic("0063"), "callbox/0063/mgmt/network")
        self.assertEqual(trace_topic("0063"), "callbox/0063/mgmt/trace")
        info = parse_info_state('{"id":"0063","fw":"1.5.6","operating_version":"2.0","chip":"ESP32-S3","flash_bytes":16777216,"boot_count":7}')
        self.assertEqual(info["fw"], "1.5.6")
        self.assertEqual(info["boot_count"], 7)
        network = parse_network_state('{"wifi":{"connected":true,"ssid":"Plant","ip":"10.0.0.2","rssi":-55},"ethernet":{"connected":false,"ip":""},"mqtt":{"transport_connected":true,"wcs_plane_ready":false,"reconnect_count":3,"tx_queue":1,"tx_queue_peak":4,"queue_drop":2,"outbox_fail":0},"comm":"syncing","ts":12}')
        self.assertTrue(network["mqtt"]["transport_connected"])
        self.assertFalse(network["mqtt"]["wcs_plane_ready"])
        self.assertEqual(network["wifi"]["ssid"], "Plant")
        trace = parse_trace_event('{"seq":385,"task":1,"stage":"wcs_rejected","reason":"locked","ts":123}')
        self.assertEqual(trace["stage"], "wcs_rejected")
        self.assertEqual(trace["seq"], 385)

    def test_management_subscription_group_preserves_remote_io(self):
        class FakeClient:
            def __init__(self):
                self.subscribed = []
                self.unsubscribed = []
            def subscribe(self, topic, qos=0):
                self.subscribed.append((topic, qos))
                return (0, 1)
            def unsubscribe(self, topic):
                self.unsubscribed.append(topic)
                return (0, 1)

        client = CallboxRemoteConfigClient()
        fake = FakeClient()
        client._client = fake
        client._connected = True
        self.assertTrue(client.subscribe_io_state("0063"))
        self.assertTrue(client.subscribe_device_state("001"))
        self.assertIn(("callbox/0063/mgmt/io", 1), fake.subscribed)
        self.assertIn(("callbox/001/status", 1), fake.subscribed)
        for topic in ("info", "health", "network", "io", "diagnostic", "trace"):
            self.assertIn((f"callbox/001/mgmt/{topic}", 1), fake.subscribed)
        self.assertIn(("callbox/001/io", 1), fake.subscribed)
        self.assertIn(("callbox/001/health", 1), fake.subscribed)
        self.assertIn(("callbox/001/internet", 1), fake.subscribed)
        self.assertNotIn("callbox/0063/mgmt/io", fake.unsubscribed)
        self.assertTrue(client.subscribe_device_state("002"))
        self.assertNotIn("callbox/0063/mgmt/io", fake.unsubscribed)
        self.assertIn("callbox/001/status", fake.unsubscribed)
        self.assertIn("callbox/001/io", fake.unsubscribed)

    def test_fleet_subscription_uses_wildcard_without_overwriting_detail(self):
        class FakeClient:
            def __init__(self): self.subscribed=[]; self.unsubscribed=[]
            def subscribe(self, topic, qos=0): self.subscribed.append((topic,qos)); return (0,1)
            def unsubscribe(self, topic): self.unsubscribed.append(topic); return (0,1)
        client=CallboxRemoteConfigClient(); fake=FakeClient(); client._client=fake; client._connected=True
        self.assertTrue(client.subscribe_device_state("0063"))
        self.assertTrue(client.subscribe_fleet_status(True))
        self.assertIn(("callbox/+/status",1), fake.subscribed)
        self.assertIn(("callbox/+/health",1), fake.subscribed)
        self.assertNotIn("callbox/0063/status", fake.unsubscribed)
        self.assertTrue(client.subscribe_fleet_status(False))
        self.assertIn("callbox/+/status", fake.unsubscribed)
        self.assertIn("callbox/+/health", fake.unsubscribed)
        self.assertNotIn("callbox/0063/status", fake.unsubscribed)

    def test_retained_online_snapshot_is_ignored_but_retained_offline_is_delivered(self):
        class Message:
            topic = "callbox/0063/status"
            retain = True

            def __init__(self, online):
                self.payload = json.dumps({"online": online, "comm": "ready"}).encode()

        client = CallboxRemoteConfigClient()
        states = []
        client.on_status_state = lambda callbox_id, state: states.append((callbox_id, state["online"]))

        client._on_message(None, None, Message(True))
        client._on_message(None, None, Message(False))

        self.assertEqual(states, [("0063", False)])

if __name__ == "__main__":
    unittest.main()

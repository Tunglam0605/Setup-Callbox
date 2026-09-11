"""Unit tests for mqtt_remote_config module."""
import json
import unittest
from unittest.mock import patch

from tools.callbox_flasher.src.mqtt_remote_config import (
    RemoteConfigPayload,
    MqttBrokerConfig,
    build_remote_button_payload,
    management_topics,
    CallboxRemoteConfigClient,
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


class TestRemoteOperationsContract(unittest.TestCase):
    def test_management_topics_are_isolated_from_wcs_contract(self):
        topics = management_topics("001")
        self.assertEqual(topics["control"], "callbox/001/control")
        self.assertEqual(topics["control_ack"], "callbox/001/control_ack")
        self.assertEqual(topics["io"], "callbox/001/io")
        self.assertEqual(topics["cmd"], "callbox/001/cmd")
        self.assertEqual(topics["status"], "callbox/001/status")

    def test_remote_button_payload(self):
        data = json.loads(build_remote_button_payload(2, 12345))
        self.assertEqual(data, {"type": "remote_button", "button": 2, "request_id": 12345})

    def test_remote_button_rejects_invalid_button(self):
        with self.assertRaises(ValueError):
            build_remote_button_payload(4, 1)

    def test_remote_button_rejects_non_positive_request_id(self):
        with self.assertRaises(ValueError):
            build_remote_button_payload(1, 0)
        with self.assertRaises(ValueError):
            build_remote_button_payload(1, -1)


class _PublishResult:
    def __init__(self, rc=0):
        self.rc = rc


class _FakeMqttClient:
    def __init__(self):
        self.subscriptions = []
        self.unsubscriptions = []
        self.publishes = []

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))
        return (0, len(self.subscriptions))

    def unsubscribe(self, topic):
        self.unsubscriptions.append(topic)
        return (0, 1)

    def publish(self, topic, payload, qos=0):
        self.publishes.append((topic, payload, qos))
        return _PublishResult(0)


class TestRemoteClientIsolation(unittest.TestCase):
    def _client(self):
        client = CallboxRemoteConfigClient()
        client._connected = True
        client._client = _FakeMqttClient()
        return client

    def test_existing_remote_config_stays_on_cmd_and_event(self):
        client = self._client()
        ok = client.send_remote_config("001", RemoteConfigPayload(operating_version="1.0"))
        self.assertTrue(ok)
        self.assertIn(("callbox/001/event", 1), client._client.subscriptions)
        self.assertEqual(client._client.publishes[-1][0], "callbox/001/cmd")
        payload = json.loads(client._client.publishes[-1][1])
        self.assertEqual(payload["type"], "remote_config")

    def test_remote_button_only_uses_management_control_topic(self):
        client = self._client()
        request_id = client.send_remote_button("001", 1)
        self.assertIsNotNone(request_id)
        subscribed = {topic for topic, _ in client._client.subscriptions}
        self.assertTrue({
            "callbox/001/status",
            "callbox/001/io",
            "callbox/001/control_ack",
        }.issubset(subscribed))
        self.assertEqual(client._client.publishes[-1][0], "callbox/001/control")
        self.assertNotEqual(client._client.publishes[-1][0], "callbox/001/cmd")

    def test_remote_button_request_ids_remain_positive_and_unique_same_millisecond(self):
        client = self._client()
        with patch("tools.callbox_flasher.src.mqtt_remote_config.time.time", return_value=1000.0):
            first = client.send_remote_button("001", 1)
            second = client.send_remote_button("001", 2)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertGreater(first, 0)
        self.assertGreater(second, 0)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()

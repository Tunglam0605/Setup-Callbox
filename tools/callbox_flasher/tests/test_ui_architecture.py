import inspect
import re
import time
import unittest
from pathlib import Path

from tools.callbox_flasher.src.ui import FlasherApp
from tools.callbox_flasher.src.ui_flash import FlashWorkflowMixin
from tools.callbox_flasher.src.ui_management import ManagementUiMixin
from tools.callbox_flasher.src.ui_management_resources import ManagementResourcesUiMixin
from tools.callbox_flasher.src.ui_mqtt_session import MqttSessionMixin
from tools.callbox_flasher.src.ui_production import ProductionUiMixin
from tools.callbox_flasher.src.ui_shell import ShellUiMixin
from tools.callbox_flasher.src.ui_remote import RemoteMqttUiMixin
from tools.callbox_flasher.src.ui_updates import UpdateUiMixin
from tools.callbox_flasher.src.ui_worker import WorkerUiMixin

SRC = Path(__file__).resolve().parents[1] / "src"


class UiArchitectureTests(unittest.TestCase):
    def test_flasher_app_is_composed_from_feature_mixins(self):
        mro = FlasherApp.__mro__
        for mixin in (ShellUiMixin, ProductionUiMixin, FlashWorkflowMixin, MqttSessionMixin, RemoteMqttUiMixin, ManagementUiMixin, WorkerUiMixin, UpdateUiMixin):
            self.assertIn(mixin, mro)

    def test_orchestrator_stays_small(self):
        lines = (SRC / "ui.py").read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), 160)
        self.assertLessEqual(len(inspect.getsource(ShellUiMixin._setup_ui).splitlines()), 40)

    def test_feature_modules_stay_bounded(self):
        limits = {
            "ui_shell.py": 260,
            "ui_production.py": 800,
            "ui_flash.py": 450,
            "ui_mqtt_session.py": 180,
            "ui_remote.py": 650,
            "ui_management.py": 400,
            "ui_management_logic.py": 140,
            "ui_theme.py": 260,
            "ui_state.py": 100,
            "ui_worker.py": 360,
            "ui_updates.py": 180,
        }
        for filename, limit in limits.items():
            with self.subTest(filename=filename):
                lines = (SRC / filename).read_text(encoding="utf-8").splitlines()
                self.assertLessEqual(len(lines), limit)

    def test_mqtt_connection_lifecycle_has_single_ui_owner(self):
        session = (SRC / "ui_mqtt_session.py").read_text(encoding="utf-8")
        remote = (SRC / "ui_remote.py").read_text(encoding="utf-8")
        management = (SRC / "ui_management.py").read_text(encoding="utf-8")
        self.assertIn("self.mqtt_client.connect(cfg)", session)
        self.assertIn("self.mqtt_client.disconnect()", session)
        self.assertNotIn("self.mqtt_client.connect(cfg)", remote)
        self.assertNotIn("self.mqtt_client.disconnect()", remote)
        self.assertNotIn("self.mqtt_client.connect(cfg)", management)
        self.assertNotIn("self.mqtt_client.disconnect()", management)

    def test_gui_sources_have_no_bom_or_double_escaped_unicode(self):
        for path in sorted(SRC.glob("ui*.py")):
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            with self.subTest(filename=path.name):
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn("\\\\u", text)
                self.assertNotIn("\ufffd", text)

    def test_gui_sources_do_not_contain_known_mojibake_patterns(self):
        bad = re.compile(r"(?:Ch\?a|\?ang|\?i\?u|theo d\?i|TR\?NG|TH\?I|N\?P|TH\?NH|C\?NG)")
        for path in sorted(SRC.glob("ui*.py")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(filename=path.name):
                self.assertIsNone(bad.search(text))

    def test_management_io_dispatch_survives_remote_panel_error(self):
        class App(ManagementUiMixin):
            management_calls = 0
            logs = []

            def _on_mqtt_io_state(self, _callbox_id, _state):
                raise RuntimeError("remote panel failed")

            def _on_management_io_state(self, _callbox_id, _state):
                self.management_calls += 1

            def _mqtt_log_append(self, message):
                self.logs.append(message)

        app = App()
        try:
            MqttSessionMixin._dispatch_mqtt_io_state(app, "001", {"buttons": (False,) * 3})
        except RuntimeError:
            pass
        self.assertEqual(app.management_calls, 1)
        self.assertTrue(any("remote panel failed" in line for line in app.logs))

    def test_offline_device_io_is_not_cached(self):
        class Target:
            def get(self): return "001"

        class App(ManagementUiMixin):
            _fleet_devices = {"0063": {"online": False, "status_rx": time.monotonic()}}
            mgmt_target_id_var = Target()

        app = App()
        app._on_management_io_state("0063", {"buttons": (True, False, False)})
        self.assertNotIn("io", app._fleet_devices["0063"])

    def test_changing_target_clears_visible_snapshot(self):
        class Value:
            def __init__(self, value): self.value = value
            def set(self, value): self.value = value
            def get(self): return self.value

        class Label:
            def __init__(self, text): self.text = text
            def config(self, **kwargs): self.text = kwargs.get("text", self.text)
            def cget(self, _key): return self.text

        class Root:
            def after(self, _delay, _callback): return 1
            def after_cancel(self, _identifier): pass

        class App(ManagementUiMixin, ManagementResourcesUiMixin):
            _mgmt_event_values = {"comm": "syncing"}
            _mgmt_subscribe_after_id = None
            root = Root()
            mgmt_vars = {"comm": Value("syncing"), "ram_used": Value("209 KB"), "io_rate": Value("10.0")}
            mgmt_io_indicators = {"green": Label("GREEN\nON")}
            mgmt_io_rate_label = Label("I/O rate: 10.0 Hz")
            mgmt_online_badge = Label("ONLINE")
            _mgmt_io_count = 8
            _mgmt_io_rate = 10.0

            def _reset_management_diagnostic(self): pass
            def _management_resubscribe(self): pass

        app = App()
        app._management_target_changed()
        self.assertEqual({key: var.get() for key, var in app.mgmt_vars.items()}, {"comm": "--", "ram_used": "--", "io_rate": "--"})
        self.assertEqual(app.mgmt_io_indicators["green"].text, "GREEN\n--")
        self.assertEqual(app.mgmt_io_rate_label.text, "I/O rate: -- Hz")


if __name__ == "__main__":
    unittest.main()

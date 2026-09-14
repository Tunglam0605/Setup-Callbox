import unittest
import threading
import time
from unittest.mock import patch

from tools.callbox_flasher.src.ui import can_flash, can_flash_baseline, can_flash_bundle, can_flash_config, can_monitor_io, can_remote_control
from tools.callbox_flasher.src.app import main
from tools.callbox_flasher.src.app_version import __version__


class AppTests(unittest.TestCase):
    def test_tool_version(self):
        self.assertEqual(__version__, "1.3.6")

    def test_remote_control_requires_mqtt_and_target_id(self):
        self.assertFalse(can_remote_control(False, "0063"))
        self.assertFalse(can_remote_control(True, ""))
        self.assertFalse(can_remote_control(True, "   "))
        self.assertTrue(can_remote_control(True, "0063"))

    def test_remote_control_ready_message_shows_management_control_topic(self):
        import tkinter as tk
        from tools.callbox_flasher.src.ui import FlasherApp

        root = tk.Tk()
        root.withdraw()
        try:
            app = FlasherApp(root)
            app.mqtt_is_connected = True
            app.mqtt_client = type("ConnectedClient", (), {"connected": True})()
            app.rc_target_id_var.set("0063")

            app._update_remote_button_state()

            self.assertEqual(
                app.lbl_remote_button_status.cget("text"),
                "Sẵn sàng điều khiển Callbox 0063  →  callbox/0063/mgmt/service/control",
            )
        finally:
            root.destroy()

    def test_io_monitor_requires_mqtt_and_monitor_id(self):
        self.assertFalse(can_monitor_io(False, "0063"))
        self.assertFalse(can_monitor_io(True, ""))
        self.assertFalse(can_monitor_io(True, "   "))
        self.assertTrue(can_monitor_io(True, "0063"))

    def test_io_monitor_waiting_message_shows_management_io_topic(self):
        import tkinter as tk
        from tools.callbox_flasher.src.ui import FlasherApp

        root = tk.Tk()
        root.withdraw()
        try:
            app = FlasherApp(root)
            app.mqtt_is_connected = True
            app.mqtt_client = type(
                "ConnectedClient",
                (),
                {"connected": True, "subscribe_io_state": lambda self, callbox_id: True},
            )()
            app.rc_monitor_id_var.set("0063")

            app._subscribe_remote_io_state()

            self.assertEqual(
                app.lbl_io_summary.cget("text"),
                "Đang theo dõi callbox/0063/mgmt/io - chờ dữ liệu...",
            )
        finally:
            root.destroy()

    def test_remote_config_confirmation_shows_management_config_topic(self):
        import tkinter as tk
        from tools.callbox_flasher.src.ui import FlasherApp

        root = tk.Tk()
        root.withdraw()
        try:
            app = FlasherApp(root)
            app.mqtt_is_connected = True
            app.mqtt_client = type("ConnectedClient", (), {"connected": True})()
            app.rc_target_id_var.set("0063")

            with patch(
                "tools.callbox_flasher.src.ui_remote.messagebox.askyesno",
                return_value=False,
            ) as confirm:
                app._on_mqtt_send_config_click()

            confirmation_text = confirm.call_args.args[1]
            self.assertIn("• Topic: callbox/0063/mgmt/service/config", confirmation_text)
            self.assertNotIn("• Topic: callbox/0063/cmd", confirmation_text)
        finally:
            root.destroy()

    def test_remote_config_send_button_shows_management_config_topic(self):
        import tkinter as tk
        from tools.callbox_flasher.src.ui import FlasherApp

        root = tk.Tk()
        root.withdraw()
        try:
            app = FlasherApp(root)

            self.assertEqual(
                app.btn_rc_send.cget("text"),
                "🚀 GỬI CẤU HÌNH QUA MQTT (callbox/<ID>/mgmt/service/config)",
            )
        finally:
            root.destroy()

    def test_self_test_validates_embedded_assets_without_opening_tk(self):
        self.assertEqual(main(["--self-test"]), 0)

    def test_bundle_enablement_requires_valid_embedded_package(self):
        self.assertFalse(can_flash_bundle(port="", package_valid=True, busy=False))
        self.assertFalse(can_flash_bundle(port="COM7", package_valid=False, busy=False))
        self.assertFalse(can_flash_bundle(port="COM7", package_valid=True, busy=True))
        self.assertTrue(can_flash_bundle(port="COM7", package_valid=True, busy=False))

    def test_flash_enablement_requires_port_valid_image_and_idle(self):
        self.assertFalse(can_flash(port="", image_valid=True, busy=False))
        self.assertFalse(can_flash(port="COM7", image_valid=False, busy=False))
        self.assertFalse(can_flash(port="COM7", image_valid=True, busy=True))
        self.assertTrue(can_flash(port="COM7", image_valid=True, busy=False))

    def test_baseline_enablement_only_requires_port_and_idle(self):
        self.assertFalse(can_flash_baseline(port="", busy=False))
        self.assertFalse(can_flash_baseline(port="COM7", busy=True))
        self.assertTrue(can_flash_baseline(port="COM7", busy=False))

    def test_config_enablement_only_requires_port_and_idle(self):
        self.assertFalse(can_flash_config(port="", busy=False))
        self.assertFalse(can_flash_config(port="COM7", busy=True))
        self.assertTrue(can_flash_config(port="COM7", busy=False))

    def test_ui_default_config_values(self):
        import tkinter as tk
        from tools.callbox_flasher.src.ui import FlasherApp
        root = tk.Tk()
        root.withdraw()
        try:
            app = FlasherApp(root)
            cfg = app._get_device_config_from_ui()
            self.assertEqual(cfg.wifi_pass, "")
            self.assertEqual(cfg.mqtt_user, "")
            self.assertEqual(cfg.mqtt_pass, "")
            self.assertEqual(cfg.wifi_ssid, "")
            self.assertEqual(cfg.mqtt_broker, "")
            self.assertEqual(cfg.callbox_id, "001")
            self.assertEqual(cfg.operating_version, "2.0")
            self.assertFalse(cfg.listpoint_publish_enabled)
        finally:
            root.destroy()

    def test_increment_callbox_id(self):
        import tkinter as tk
        from tools.callbox_flasher.src.ui import FlasherApp
        root = tk.Tk()
        root.withdraw()
        try:
            app = FlasherApp(root)
            app.cfg_id_var.set("001")
            app._increment_callbox_id()
            self.assertEqual(app.cfg_id_var.get(), "002")
            app.cfg_id_var.set("099")
            app._increment_callbox_id()
            self.assertEqual(app.cfg_id_var.get(), "100")
            app.cfg_id_var.set("CB-05")
            app._increment_callbox_id()
            self.assertEqual(app.cfg_id_var.get(), "CB-06")
        finally:
            root.destroy()

    def test_auto_detect_firmware_loads_valid_image(self):
        import tkinter as tk
        from tools.callbox_flasher.src.ui import FlasherApp
        root = tk.Tk()
        root.withdraw()
        try:
            app = FlasherApp(root)
            # When callbox_sews.bin is in assets or build, app_info should be automatically detected
            if app.app_info is not None:
                self.assertEqual(app.app_info.project, "callbox_sews")
                self.assertGreater(app.app_info.size, 0)
        finally:
            root.destroy()

    def test_management_overview_scrolls_at_minimum_engineer_window_height(self):
        import tkinter as tk
        from tools.callbox_flasher.src.ui import FlasherApp

        root = tk.Tk()
        root.withdraw()
        try:
            app = FlasherApp(root)
            app._show_engineer_mode()
            root.geometry("1180x760")
            root.update_idletasks()

            overview_page = app._engineer_pages["overview"]
            canvases = [
                child for child in overview_page.winfo_children()
                if isinstance(child, tk.Canvas)
            ]
            self.assertEqual(len(canvases), 1, "Overview must provide a vertical scroll viewport")

            canvas = canvases[0]
            overview_inner = app._engineer_page_inner["overview"]
            body = next(
                child for child in overview_inner.winfo_children()
                if isinstance(child, tk.PanedWindow)
            )
            right_pane = root.nametowidget(body.panes()[1])
            self.assertGreaterEqual(
                body.winfo_height(),
                right_pane.winfo_reqheight(),
                "Overview body must include the full right pane instead of clipping lower cards",
            )

            canvas.yview_moveto(1.0)
            root.update_idletasks()
            self.assertGreater(canvas.yview()[0], 0.0, "Overview content must scroll to its lower cards")
        finally:
            root.destroy()

    def test_close_does_not_wait_for_blocked_mqtt_disconnect(self):
        from tools.callbox_flasher.src.ui import FlasherApp

        release_disconnect = threading.Event()

        class BlockingMqttClient:
            on_connect = object()
            on_ack = object()
            on_button_ack = object()
            on_io_state = object()
            on_status_state = object()
            on_internet_state = object()
            on_health_state = object()
            on_diagnostic_state = object()
            on_info_state = object()
            on_network_state = object()
            on_trace_event = object()
            on_log = object()

            def disconnect(self):
                release_disconnect.wait(2)

        class Root:
            destroyed = False

            def destroy(self):
                self.destroyed = True

        app = FlasherApp.__new__(FlasherApp)
        app.root = Root()
        app.controller = type("Controller", (), {"busy": False})()
        client = BlockingMqttClient()
        app.mqtt_client = client

        started = time.monotonic()
        app._on_close()
        elapsed = time.monotonic() - started
        release_disconnect.set()

        self.assertLess(elapsed, 0.2)
        self.assertTrue(app.root.destroyed)
        self.assertIsNone(app.mqtt_client)
        self.assertIsNone(client.on_connect)
        self.assertIsNone(client.on_log)


if __name__ == "__main__":
    unittest.main()



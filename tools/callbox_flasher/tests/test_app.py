import unittest

from tools.callbox_flasher.src.ui import can_flash, can_flash_baseline, can_flash_config
from tools.callbox_flasher.src.app import main


class AppTests(unittest.TestCase):
    def test_self_test_validates_embedded_assets_without_opening_tk(self):
        self.assertEqual(main(["--self-test"]), 0)

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
        from unittest.mock import patch
        from tools.callbox_flasher.src.models import DeviceConfig
        from tools.callbox_flasher.src.ui import FlasherApp
        root = tk.Tk()
        root.withdraw()
        try:
            # Isolate this test from an optional machine-local factory profile.
            with patch("tools.callbox_flasher.src.ui.load_factory_profile", return_value=DeviceConfig()):
                app = FlasherApp(root)
            cfg = app._get_device_config_from_ui()
            self.assertEqual(cfg.wifi_pass, "")
            self.assertEqual(cfg.mqtt_user, "")
            self.assertEqual(cfg.mqtt_pass, "")
            self.assertEqual(cfg.wifi_ssid, "")
            self.assertEqual(cfg.callbox_id, "001")
            self.assertEqual(cfg.operating_version, "2.0")
            self.assertFalse(cfg.listpoint_publish_enabled)
        finally:
            root.destroy()

    def test_remote_debug_controls_are_locked_by_default(self):
        import tkinter as tk
        from unittest.mock import patch
        from tools.callbox_flasher.src.models import DeviceConfig
        from tools.callbox_flasher.src.ui import FlasherApp
        root = tk.Tk()
        root.withdraw()
        try:
            with patch("tools.callbox_flasher.src.ui.load_factory_profile", return_value=DeviceConfig()):
                app = FlasherApp(root)
            root.update_idletasks()
            self.assertFalse(app.rc_remote_test_enable_var.get())
            self.assertEqual(str(app.btn_rc_remote_1["state"]), "disabled")
            self.assertEqual(str(app.btn_rc_remote_2["state"]), "disabled")
            self.assertEqual(str(app.btn_rc_remote_cancel["state"]), "disabled")
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


if __name__ == "__main__":
    unittest.main()

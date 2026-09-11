import pathlib
import threading
import time
import unittest
from unittest.mock import Mock

from tools.callbox_flasher.src.controller import ProvisionController
from tools.callbox_flasher.src.esptool_adapter import FlashToolError, ProbeResult
from tools.callbox_flasher.src.image_validator import ImageValidationError
from tools.callbox_flasher.src.models import (
    ApplicationInfo,
    DeviceConfig,
    ProvisionBusyError,
    ProvisionEvent,
    ProvisionMode,
    ProvisionResult,
    ProvisionState,
)


FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "callbox_sews.bin"


class FakeAdapter:
    def __init__(self):
        self.calls = []
        self.block_probe = False
        self.release_probe = threading.Event()
        self.fail_at = None

    def probe(self, port, log):
        self.calls.append("probe")
        if self.block_probe:
            self.release_probe.wait(2)
        if self.fail_at == "probe":
            raise FlashToolError("Lỗi kết nối probe")
        return ProbeResult(mac="aa:bb:cc:dd:ee:ff")

    def erase(self, port, manifest, log):
        self.calls.append("erase")
        if self.fail_at == "erase":
            raise FlashToolError("Lỗi xóa flash")

    def erase_otadata(self, port, manifest, log):
        self.calls.append("erase_otadata")
        if self.fail_at == "erase_otadata":
            raise FlashToolError("Lỗi xóa otadata")

    def write(self, port, manifest, application, log, nvs_config=None):
        self.calls.append("write")
        if self.fail_at == "write":
            raise FlashToolError("Lỗi ghi flash")

    def write_app(self, port, manifest, application, log):
        self.calls.append("write_app")
        if self.fail_at == "write_app":
            raise FlashToolError("Lỗi ghi app")

    def write_config(self, port, manifest, nvs_config, log):
        self.calls.append("write_config")
        if self.fail_at == "write_config":
            raise FlashToolError("Lỗi ghi config")

    def verify(self, port, manifest, application, log, nvs_config=None):
        self.calls.append("verify")
        if self.fail_at == "verify":
            raise FlashToolError("Lỗi xác minh flash")

    def verify_app(self, port, manifest, application, log):
        self.calls.append("verify_app")
        if self.fail_at == "verify_app":
            raise FlashToolError("Lỗi xác minh app")

    def verify_config(self, port, manifest, nvs_config, log):
        self.calls.append("verify_config")
        if self.fail_at == "verify_config":
            raise FlashToolError("Lỗi xác minh config")

    def write_baseline(self, port, manifest, log):
        self.calls.append("write_baseline")
        if self.fail_at == "write_baseline":
            raise FlashToolError("Lỗi ghi baseline")

    def verify_baseline(self, port, manifest, log):
        self.calls.append("verify_baseline")
        if self.fail_at == "verify_baseline":
            raise FlashToolError("Lỗi xác minh baseline")

    def reset(self, port, manifest, log):
        self.calls.append("reset")
        if self.fail_at == "reset":
            raise FlashToolError("Lỗi khởi động lại")



class ProvisionControllerTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.adapter = FakeAdapter()

    def make_controller(self, validator=None):
        return ProvisionController(adapter=self.adapter, validator=validator)

    def test_success_revalidates_then_runs_every_hardware_phase(self):
        controller = self.make_controller()
        thread = controller.start("COM7", FIXTURE, self.events.append)
        thread.join(2)
        self.assertEqual(self.adapter.calls, ["probe", "erase", "write", "verify", "reset"])
        self.assertEqual(self.events[-1].state, ProvisionState.SUCCEEDED)
        self.assertIsNotNone(self.events[-1].result)
        self.assertEqual(self.events[-1].result.mac, "aa:bb:cc:dd:ee:ff")
        self.assertFalse(controller.busy)

    def test_success_app_only_runs_app_phases_without_full_erase(self):
        controller = self.make_controller()
        thread = controller.start("COM7", FIXTURE, self.events.append, mode=ProvisionMode.APP_ONLY)
        thread.join(2)
        self.assertEqual(self.adapter.calls, ["probe", "erase_otadata", "write_app", "verify_app", "reset"])
        self.assertEqual(self.events[-1].state, ProvisionState.SUCCEEDED)
        self.assertIsNotNone(self.events[-1].result)
        self.assertEqual(self.events[-1].result.mode, ProvisionMode.APP_ONLY)
        self.assertIn("CẬP NHẬT APP THÀNH CÔNG", self.events[-1].message)
        self.assertFalse(controller.busy)

    def test_success_baseline_only_runs_without_application(self):
        controller = self.make_controller()
        thread = controller.start("COM7", None, self.events.append, mode=ProvisionMode.BASELINE_ONLY)
        thread.join(2)
        self.assertEqual(self.adapter.calls, ["probe", "write_baseline", "verify_baseline", "reset"])
        self.assertEqual(self.events[-1].state, ProvisionState.SUCCEEDED)
        self.assertIsNotNone(self.events[-1].result)
        self.assertEqual(self.events[-1].result.mode, ProvisionMode.BASELINE_ONLY)
        self.assertIn("NẠP BOOTLOADER / SETUP THÀNH CÔNG", self.events[-1].message)
        self.assertFalse(controller.busy)

    def test_invalid_image_never_erases(self):
        controller = self.make_controller(validator=Mock(side_effect=ImageValidationError("bad")))
        controller.start("COM7", pathlib.Path("bad.bin"), self.events.append).join(2)
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(self.events[-1].state, ProvisionState.FAILED)
        self.assertIn("bad", self.events[-1].message)
        self.assertFalse(controller.busy)

    def test_second_job_is_rejected_while_first_is_active(self):
        self.adapter.block_probe = True
        controller = self.make_controller()
        first = controller.start("COM7", FIXTURE, self.events.append)
        with self.assertRaisesRegex(ProvisionBusyError, "đang nạp"):
            controller.start("COM8", FIXTURE, self.events.append)
        self.adapter.release_probe.set()
        first.join(2)
        self.assertFalse(controller.busy)

    def test_failure_at_each_phase_stops_execution(self):
        for phase in ["probe", "erase", "write", "verify", "reset"]:
            with self.subTest(phase=phase):
                self.events.clear()
                self.adapter.calls.clear()
                self.adapter.fail_at = phase
                controller = self.make_controller()
                thread = controller.start("COM7", FIXTURE, self.events.append)
                thread.join(2)
                self.assertEqual(self.events[-1].state, ProvisionState.FAILED)
                self.assertFalse(controller.busy)
                self.assertEqual(self.adapter.calls[-1], phase)

    def test_success_config_only_provisions_nvs_partition(self):
        controller = self.make_controller()
        cfg = DeviceConfig(callbox_id="007", wifi_ssid="FactoryWiFi")
        thread = controller.start(
            "COM7",
            None,
            self.events.append,
            mode=ProvisionMode.CONFIG_ONLY,
            config=cfg,
        )
        thread.join(2)
        self.assertEqual(self.adapter.calls, ["probe", "write_config", "verify_config", "reset"])
        self.assertEqual(self.events[-1].state, ProvisionState.SUCCEEDED)
        self.assertIn("NẠP CẤU HÌNH THÀNH CÔNG", self.events[-1].message)
        self.assertEqual(self.events[-1].result.mode, ProvisionMode.CONFIG_ONLY)
        self.assertIn("007", self.events[-1].result.version)
        self.assertFalse(controller.busy)

    def test_config_only_without_config_fails(self):
        controller = self.make_controller()
        thread = controller.start(
            "COM7",
            None,
            self.events.append,
            mode=ProvisionMode.CONFIG_ONLY,
            config=None,
        )
        thread.join(2)
        self.assertEqual(self.events[-1].state, ProvisionState.FAILED)
        self.assertIn("cấu hình thiết bị", self.events[-1].message)
        self.assertFalse(controller.busy)

    def test_full_provision_with_config_writes_and_verifies_nvs(self):
        controller = self.make_controller()
        cfg = DeviceConfig(callbox_id="088")
        thread = controller.start(
            "COM7",
            FIXTURE,
            self.events.append,
            mode=ProvisionMode.FULL,
            config=cfg,
        )
        thread.join(2)
        self.assertEqual(self.adapter.calls, ["probe", "erase", "write", "verify", "reset"])
        self.assertEqual(self.events[-1].state, ProvisionState.SUCCEEDED)
        self.assertIn("NẠP BOARD MỚI THÀNH CÔNG", self.events[-1].message)
        self.assertFalse(controller.busy)


if __name__ == "__main__":
    unittest.main()

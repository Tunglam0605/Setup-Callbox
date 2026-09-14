from types import SimpleNamespace
import unittest

from tools.callbox_flasher.src.ports import (
    PortInfo,
    automatic_port,
    discover_ports,
)


class PortTests(unittest.TestCase):
    def test_one_usb_port_is_auto_selected(self):
        ports = (PortInfo("COM7", "USB Serial", 0x303A, 0x1001, "ABC"),)
        self.assertEqual(automatic_port(ports), "COM7")

    def test_multiple_ports_require_explicit_selection(self):
        ports = (
            PortInfo("COM7", "USB Serial", 0x303A, 1, None),
            PortInfo("COM8", "USB Serial", 0x1A86, 2, None),
        )
        self.assertIsNone(automatic_port(ports))

    def test_zero_ports_returns_none(self):
        self.assertIsNone(automatic_port(()))

    def test_system_only_port_is_not_treated_as_board(self):
        raw = SimpleNamespace(
            device="COM3",
            description="Intel Active Management Technology - SOL",
            vid=None,
            pid=None,
            serial_number=None,
        )
        self.assertEqual(discover_ports(lambda: [raw]), ())

    def test_usb_port_discovery_sorting(self):
        p1 = SimpleNamespace(
            device="COM10",
            description="USB Serial Device",
            vid=0x303A,
            pid=0x1001,
            serial_number="123",
        )
        p2 = SimpleNamespace(
            device="COM2",
            description="Silicon Labs CP210x USB to UART Bridge",
            vid=0x10C4,
            pid=0xEA60,
            serial_number="456",
        )
        found = discover_ports(lambda: [p1, p2])
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].device, "COM2")
        self.assertEqual(found[1].device, "COM10")


if __name__ == "__main__":
    unittest.main()


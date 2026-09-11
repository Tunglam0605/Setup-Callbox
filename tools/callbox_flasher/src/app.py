import argparse
import pathlib
import sys
import tkinter as tk
from typing import Sequence

from tools.callbox_flasher.src.app_version import __version__
from tools.callbox_flasher.src.flash_manifest import load_baseline_manifest
from tools.callbox_flasher.src.self_update import apply_verified_update
from tools.callbox_flasher.src.ui import FlasherApp, can_flash


def _apply_update_helper(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Apply a verified Setup CallBox update")
    parser.add_argument("--apply-update", action="store_true")
    parser.add_argument("--target", required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(list(argv))
    try:
        apply_verified_update(
            pathlib.Path(sys.executable),
            pathlib.Path(args.target),
            args.parent_pid,
            args.expected_sha256,
            relaunch=True,
        )
        return 0
    except Exception as error:
        print(f"Update apply FAILED: {error}", file=sys.stderr)
        return 2


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if "--version" in argv or "--print-version" in argv:
        print(__version__)
        return 0

    if "--apply-update" in argv:
        return _apply_update_helper(argv)

    if "--self-test" in argv:
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.AttachConsole(-1)
            except Exception:
                pass
        try:
            manifest = load_baseline_manifest()
            manifest.verify_assets()
            import esptool
            stub_dir = pathlib.Path(esptool.__file__).parent / "targets" / "stub_flasher"
            s3_stubs = list(stub_dir.glob("*/esp32s3.json"))
            if not s3_stubs:
                raise RuntimeError(f"ESP32-S3 stub flasher missing in {stub_dir}")
            from tools.callbox_flasher.src.models import DeviceConfig
            from tools.callbox_flasher.src.nvs_generator import generate_nvs_config_bin
            import tempfile
            with tempfile.TemporaryDirectory() as tmp_dir:
                bin_path = generate_nvs_config_bin(DeviceConfig(), pathlib.Path(tmp_dir))
                if not bin_path.exists() or bin_path.stat().st_size != 0x20000:
                    raise RuntimeError("NVS generator self-test failed: invalid size")

            print(
                f"Self-test OK: Setup CallBox v{__version__}, baseline {manifest.baseline_version}, "
                f"{len(manifest.images)} images verified, stub flasher OK, NVS generator OK."
            )
            return 0
        except Exception as error:
            print(f"Self-test FAILED: {error}", file=sys.stderr)
            return 1

    root = tk.Tk()
    app = FlasherApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

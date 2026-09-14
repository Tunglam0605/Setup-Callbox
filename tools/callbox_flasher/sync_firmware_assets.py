from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import subprocess

TOOL_ROOT = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TOOL_ROOT.parents[1]
BUILD = REPO_ROOT / "build_flash"
ASSETS = TOOL_ROOT / "assets"
MANIFEST = ASSETS / "baseline-manifest.json"
FIRMWARE_HEADER = REPO_ROOT / "components" / "callbox" / "include" / "callbox_mqtt.h"

FILES = {
    "bootloader.bin": BUILD / "bootloader" / "bootloader.bin",
    "partition-table.bin": BUILD / "partition_table" / "partition-table.bin",
    "ota_data_initial.bin": BUILD / "ota_data_initial.bin",
    "callbox_sews.bin": BUILD / "callbox_sews.bin",
}

def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git_package_version() -> str:
    try:
        short = subprocess.check_output(["git", "-C", str(REPO_ROOT), "rev-parse", "--short=7", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(REPO_ROOT), "status", "--porcelain"], text=True).strip())
        return f"package-{short}{'-dirty' if dirty else ''}"
    except Exception:
        return "package-local"


def firmware_version() -> str:
    text = FIRMWARE_HEADER.read_text(encoding="utf-8")
    match = re.search(r'#define\s+CALLBOX_FIRMWARE_VERSION\s+"([^"]+)"', text)
    if not match:
        raise RuntimeError(f"CALLBOX_FIRMWARE_VERSION not found in {FIRMWARE_HEADER}")
    return match.group(1).strip()

def main() -> int:
    missing = [str(src) for src in FILES.values() if not src.is_file()]
    if missing:
        raise SystemExit("Missing firmware build outputs: " + ", ".join(missing))
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, src in FILES.items():
        shutil.copy2(src, ASSETS / name)

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data["baseline_version"] = git_package_version()
    data["firmware_version"] = firmware_version()
    by_name = {item["filename"]: item for item in data["images"]}
    for name in ("bootloader.bin", "partition-table.bin", "ota_data_initial.bin"):
        target = ASSETS / name
        item = by_name[name]
        item["size"] = target.stat().st_size
        item["sha256"] = sha256(target)
    app = ASSETS / "callbox_sews.bin"
    data["application"] = {
        "offset": "0x10000",
        "filename": "callbox_sews.bin",
        "size": app.stat().st_size,
        "sha256": sha256(app),
    }
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Synced firmware package: {data['baseline_version']} | firmware v{data['firmware_version']}")
    for name in FILES:
        p = ASSETS / name
        print(f"  {name}: {p.stat().st_size} bytes sha256={sha256(p)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

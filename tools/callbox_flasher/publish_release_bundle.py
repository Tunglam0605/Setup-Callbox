from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

from tools.callbox_flasher.src.app_version import MIN_FIRMWARE_TOOL_VERSION, __version__
from tools.callbox_flasher.src.flash_manifest import load_baseline_manifest
from tools.callbox_flasher.src.image_validator import validate_application

REPOSITORY = "Tunglam0605/Setup-Callbox"
RAW_BASE = f"https://raw.githubusercontent.com/{REPOSITORY}/main"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_verified(source: Path, target: Path) -> tuple[int, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target.stat().st_size, sha256(target)



def validate_public_bundle(output: Path) -> None:
    """Fail closed if source code, tests, credentials, or unexpected files enter the public bundle."""
    allowed_root = {
        ".gitignore",
        "README.md",
        "Setup-CallBox.exe",
        "Setup-CallBox.exe.sha256",
        "release-manifest.json",
        "firmware",
    }
    forbidden_suffixes = {".py", ".pyc", ".ps1", ".spec", ".c", ".h", ".cpp", ".hpp"}
    forbidden_names = {"Setup-CallBox.factory.json", "Setup-CallBox.factory.example.json"}
    root_names = {item.name for item in output.iterdir()}
    unexpected = sorted(root_names - allowed_root)
    if unexpected:
        raise RuntimeError(f"Unexpected public release files: {unexpected}")
    for path in output.rglob("*"):
        if not path.is_file():
            continue
        if path.name in forbidden_names or path.suffix.lower() in forbidden_suffixes:
            raise RuntimeError(f"Forbidden public release file: {path.relative_to(output)}")
        lowered = path.name.lower()
        if any(token in lowered for token in ("credential", "secret", "password")):
            raise RuntimeError(f"Sensitive-looking public release file: {path.relative_to(output)}")
        if path.suffix.lower() in {".md", ".json", ".gitignore"} or path.name.endswith(".sha256"):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise RuntimeError(f"Public text is not UTF-8: {path.relative_to(output)}") from exc
            for bad in ("N?P", "C?P NH?T", "Ch?a", "?ang", "�"):
                if bad in text:
                    raise RuntimeError(f"Mojibake in public release file {path.relative_to(output)}: {bad}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate source-free Setup-Callbox public release bundle")
    tool_root = Path(__file__).resolve().parent
    parser.add_argument("--output", type=Path, default=tool_root / "dist" / "public-release")
    parser.add_argument("--exe", type=Path, default=tool_root / "dist" / "Setup-CallBox.exe")
    args = parser.parse_args()

    output = args.output.resolve()
    exe = args.exe.resolve()
    if not exe.is_file():
        raise SystemExit(f"Setup-CallBox.exe not found: {exe}")

    manifest = load_baseline_manifest()
    manifest.verify_assets()
    validate_application(manifest.application.path)
    firmware_version = manifest.firmware_version
    version_dir = f"v{firmware_version}"
    fw_out = output / "firmware" / version_dir

    if output.exists():
        import stat
        shutil.rmtree(output, onerror=lambda func, path, _: (os.chmod(path, stat.S_IWRITE), func(path)))
    fw_out.mkdir(parents=True, exist_ok=True)

    public_exe = output / "Setup-CallBox.exe"
    tool_size, tool_sha = copy_verified(exe, public_exe)
    (output / "Setup-CallBox.exe.sha256").write_text(
        f"{tool_sha}  Setup-CallBox.exe\n", encoding="ascii"
    )

    role_by_filename = {
        "bootloader.bin": "bootloader",
        "partition-table.bin": "partition_table",
        "ota_data_initial.bin": "ota_data",
    }
    public_images = []
    for image in manifest.images:
        role = role_by_filename.get(image.filename)
        if role is None:
            raise SystemExit(f"Unexpected baseline image: {image.filename}")
        target = fw_out / image.filename
        size, digest = copy_verified(image.path, target)
        public_images.append({
            "role": role,
            "offset": hex(image.offset),
            "filename": image.filename,
            "size": size,
            "sha256": digest,
            "url": f"{RAW_BASE}/firmware/{version_dir}/{image.filename}",
        })

    app_target = fw_out / manifest.application.filename
    app_size, app_sha = copy_verified(manifest.application.path, app_target)
    public_application = {
        "role": "application",
        "offset": hex(manifest.application.offset),
        "filename": manifest.application.filename,
        "size": app_size,
        "sha256": app_sha,
        "url": f"{RAW_BASE}/firmware/{version_dir}/{manifest.application.filename}",
    }

    firmware_manifest = {
        "schema_version": 1,
        "package_version": firmware_version,
        "firmware_version": firmware_version,
        "chip": manifest.chip,
        "flash_size": manifest.flash_size,
        "flash_mode": manifest.flash_mode,
        "flash_frequency": manifest.flash_frequency,
        "baud": manifest.baud,
        "images": public_images,
        "application": public_application,
    }
    fw_manifest_path = fw_out / "firmware-manifest.json"
    fw_manifest_path.write_text(json.dumps(firmware_manifest, indent=2) + "\n", encoding="utf-8")
    fw_manifest_sha = sha256(fw_manifest_path)
    (fw_out / "firmware-manifest.json.sha256").write_text(
        f"{fw_manifest_sha}  firmware-manifest.json\n", encoding="ascii"
    )

    release_manifest = {
        "schema_version": 1,
        "channel": "stable",
        "published_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "tool": {
            "version": __version__,
            "filename": "Setup-CallBox.exe",
            "size": tool_size,
            "sha256": tool_sha,
            "url": f"{RAW_BASE}/Setup-CallBox.exe",
        },
        "firmware": {
            "package_version": firmware_version,
            "firmware_version": firmware_version,
            "min_tool_version": MIN_FIRMWARE_TOOL_VERSION,
            "manifest_url": f"{RAW_BASE}/firmware/{version_dir}/firmware-manifest.json",
        },
    }
    (output / "release-manifest.json").write_text(
        json.dumps(release_manifest, indent=2) + "\n", encoding="utf-8"
    )

    readme_lines = [
        "# Setup CallBox - Public Release",
        "",
        "Public **binary-only** release channel for AUBOT Setup CallBox.",
        "Production firmware/tool source code is maintained in a private repository.",
        "",
        "## Stable package",
        "",
        f"- Tool: **v{__version__}**",
        f"- Firmware: **v{firmware_version}**",
        f"- Minimum compatible tool for this firmware: **v{MIN_FIRMWARE_TOOL_VERSION}**",
        "- Target: ESP32-S3, 16 MB flash",
        "",
        "## Factory operator",
        "",
        "1. Download `Setup-CallBox.exe`.",
        "2. Open the tool and connect one Callbox by USB.",
        "3. Enter the Callbox ID.",
        "4. Press **NẠP CALLBOX**.",
        "",
        "The tool automatically checks this repository for a newer verified firmware package.",
        "A tool-update button is shown only when a newer compatible tool exists.",
        "If GitHub is unavailable, the last verified cached package or the package embedded in the EXE is used.",
        "",
        "Factory Wi-Fi/MQTT credentials are stored only in a machine-local `Setup-CallBox.factory.json` and are never published here.",
        "",
        "## Public contents",
        "",
        "```text",
        "Setup-CallBox.exe",
        "Setup-CallBox.exe.sha256",
        "release-manifest.json",
        "firmware/",
        f"  {version_dir}/",
        "    firmware-manifest.json",
        "    firmware-manifest.json.sha256",
        "    bootloader.bin",
        "    partition-table.bin",
        "    ota_data_initial.bin",
        "    callbox_sews.bin",
        "```",
        "",
        "No Python source, firmware source, tests, build scripts, credentials, or factory profiles belong in this repository.",
        "",
    ]
    (output / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")
    (output / ".gitignore").write_text(
        "Setup-CallBox.factory.json\n*.part\n*.update-new\n*.update-backup\n",
        encoding="utf-8",
    )

    validate_public_bundle(output)

    print(f"Public release bundle: {output}")
    print(f"Tool v{__version__}: {tool_size} bytes sha256={tool_sha}")
    print(f"Firmware v{firmware_version}: {app_size} bytes sha256={app_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

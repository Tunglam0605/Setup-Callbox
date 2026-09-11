# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
spec_dir = os.path.abspath(SPECPATH)
repo_root = os.path.abspath(os.path.join(spec_dir, "..", ".."))

hidden_imports = (
    collect_submodules("esptool")
    + collect_submodules("esp_idf_nvs_partition_gen")
    + collect_submodules("paho")
    + [
        "serial.tools.list_ports",
        "serial.tools.list_ports_windows",
        "paho.mqtt.client",
    ]
)

datas = [
    (os.path.join(spec_dir, "assets"), "assets"),
] + collect_data_files("esptool") + collect_data_files("esp_idf_nvs_partition_gen")

a = Analysis(
    [os.path.join(spec_dir, "src", "app.py")],
    pathex=[repo_root],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tools.callbox_flasher.tests", "tests", "setuptools", "pkg_resources"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Setup-CallBox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(spec_dir, "assets", "app.ico"),
)

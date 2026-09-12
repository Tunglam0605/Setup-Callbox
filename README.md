# Setup CallBox - Public Release

Public **binary-only** release channel for AUBOT Setup CallBox.
Production firmware/tool source code is maintained in a private repository.

## Stable package

- Tool: **v1.3.0**
- Firmware: **v1.5.3**
- Minimum compatible tool for this firmware: **v1.2.0**
- Target: ESP32-S3, 16 MB flash

## Factory operator

1. Download `Setup-CallBox.exe`.
2. Open the tool and connect one Callbox by USB.
3. Enter the Callbox ID.
4. Press **NẠP CALLBOX**.

The tool automatically checks this repository for a newer verified firmware package.
A tool-update button is shown only when a newer compatible tool exists.
If GitHub is unavailable, the last verified cached package or the package embedded in the EXE is used.

Factory Wi-Fi/MQTT credentials are stored only in a machine-local `Setup-CallBox.factory.json` and are never published here.

## Public contents

```text
Setup-CallBox.exe
Setup-CallBox.exe.sha256
release-manifest.json
firmware/
  v1.5.3/
    firmware-manifest.json
    firmware-manifest.json.sha256
    bootloader.bin
    partition-table.bin
    ota_data_initial.bin
    callbox_sews.bin
```

No Python source, firmware source, tests, build scripts, credentials, or factory profiles belong in this repository.

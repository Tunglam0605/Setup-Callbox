# Setup CallBox

**AUBOT Setup CallBox** is the Windows production/setup utility for the ESP32-S3 CallBox platform.

This repository contains the portable GUI, embedded firmware/baseline assets, tests, and the GitHub Release workflow used by the built-in updater.

## Current source candidate

- Setup CallBox tool: **v1.1.0**
- Embedded CallBox application: **v1.5.1** (`callbox_sews`, firmware commit `f9ed879`)
- Target: Waveshare ESP32-S3 PoE ETH 8DI/8DO / ESP32-S3, 16 MB flash
- Windows artifact: `Setup-CallBox.exe`
- Candidate EXE SHA-256: `58D380ACDA65A39A2A2CA94F4417AEFC6902703CD92CCC6F11F767541B16B979`

> v1.1.0 is kept as a candidate until real-device MQTT remote-control acceptance is completed. The existing flashing/configuration paths remain unchanged.

## Compatibility principle

The authoritative WCS contract remains unchanged:

```text
callbox/{id}/event
callbox/{id}/cmd
callbox/{id}/status
callbox/{id}/internet
```

The new operator/maintenance plane is isolated on separate topics:

```text
callbox/{id}/control       Setup tool -> CallBox remote button command
callbox/{id}/control_ack   CallBox -> Setup tool management ACK
callbox/{id}/io            CallBox -> Setup tool I/O and mission telemetry
```

A failure of the optional `control` subscription must not change WCS readiness. `callbox/{id}/cmd` remains the only authoritative WCS command path.

The existing `remote_config` feature is also retained exactly on `callbox/{id}/cmd` with ACK on `callbox/{id}/event` for backward compatibility.

## Main functions

- Detect the correct ESP32-S3 serial port.
- `CONFIG_ONLY`: write and verify CallBox NVS configuration.
- `FULL`: factory/full board provisioning.
- `APP_ONLY`: update only the application while retaining CallBox configuration.
- `BASELINE_ONLY`: provision bootloader/partition/OTA baseline.
- Read `CMD:STATUS` and `CMD:CONFIG` from a connected CallBox.
- Existing remote configuration over MQTT.
- Monitor CallBox online/COMM state, operating version, firmware version and Task 1/Task 2.
- Monitor button LEDs, Cancel state and red/yellow/green tower outputs from `callbox/{id}/io`.
- Send remote **Button 1 / Button 2 / Cancel** commands through `callbox/{id}/control`.
- Built-in **Update** button for the Windows GUI.

## Remote-control safety model

Physical buttons are the production-authoritative input. WebUI and Setup EXE buttons are DEBUG/TEST helpers only. Firmware drains physical button events before virtual app events, and the Operator Input Arbiter suppresses virtual clicks while or immediately after the corresponding physical control is active. Virtual inputs never suppress a physical press.

Setup CallBox starts with remote DEBUG/TEST controls disabled. A technician must explicitly enable DEBUG/TEST before Button 1 / Button 2 / Cancel can be sent remotely, and only one remote request may be in flight at a time.

Remote button commands do **not** publish business Orders directly. Firmware converts a valid management command into the same `APP_EVENT_VIRTUAL_BUTTON_PRESS` used by the WebUI virtual button path, then Mission Manager applies the normal admission/state-machine rules.

The GUI additionally requires:

- broker connected;
- CallBox `online=true`;
- `COMM=READY`;
- fresh `/io` telemetry, which also prevents enabling controls on older firmware without the v1.5 management plane;
- explicit operator confirmation before each remote Button 1 / Button 2 / Cancel action.

`control_ack=ok` means the button event was queued into Mission Manager. It does **not** mean WCS has accepted the business task. WCS acceptance is still reflected later by the normal task lifecycle (`queued`, `assigned`, `locked`, `completed`, etc.).

## Version 1.0 / 2.0 behavior

- Operating Version **1.0**: physical/remote Button 1 and Button 2 both address Task 1; both task LEDs mirror Task 1.
- Operating Version **2.0**: Button 1 -> Task 1 and Button 2 -> Task 2 independently.
- Cancel follows the existing Mission Manager rules; remote Cancel does not bypass lock/admission logic.

## Verification status

Current local gates:

- CallBox firmware host contract: **101/101 PASS**.
- CallBox firmware ESP32-S3 build: **PASS**.
- Setup CallBox unit tests: **74/74 PASS**.
- Packaged EXE `--self-test`: **PASS**.
- GUI startup smoke test: **PASS**.

Real-device MQTT remote-control acceptance is still required before tagging v1.1.0 as a production release.

## GUI self-update

The GUI checks the latest release from:

`https://github.com/Tunglam0605/Setup-Callbox/releases/latest`

When a newer stable version exists:

1. Click **Update** in the GUI header.
2. The tool downloads `Setup-CallBox.exe` and `Setup-CallBox.exe.sha256` from the immutable GitHub Release.
3. The downloaded EXE size and SHA-256 are verified.
4. The new EXE starts in update-helper mode.
5. The current GUI exits.
6. The helper replaces the old EXE and opens the updated application.

The updater is blocked while ESP32 flashing is active.

### Release security scope

The updater verifies HTTPS GitHub Release URLs, expected release asset names, asset size, and SHA-256. `Setup-CallBox.factory.json` is a machine-local private provisioning profile and is explicitly ignored by Git.

## Build locally

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\callbox_flasher\build.ps1
```

Output:

```text
tools\callbox_flasher\dist\Setup-CallBox.exe
```

Verification:

```powershell
.\tools\callbox_flasher\dist\Setup-CallBox.exe --version
.\tools\callbox_flasher\dist\Setup-CallBox.exe --self-test
```

## Tests

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m unittest discover -s tools\callbox_flasher\tests -p "test_*.py" -v
```

## Publish a stable update

Only after hardware acceptance:

1. Ensure `__version__` matches the intended release tag.
2. Run all source, package and hardware gates in `RELEASE-CHECKLIST.md`.
3. Commit and push `main`.
4. Create and push the matching tag, for example:

```powershell
git tag v1.1.0
git push origin v1.1.0
```

GitHub Actions will run tests, build the portable EXE, verify the package, generate the SHA-256 sidecar, and publish the GitHub Release.

## Repository layout

```text
.github/workflows/release.yml       GitHub Release pipeline
tools/callbox_flasher/src/          Application and updater source
tools/callbox_flasher/assets/       Firmware/baseline/icon assets
tools/callbox_flasher/tests/        Unit tests
tools/callbox_flasher/dist/         Local packaged EXE (ignored)
tools/callbox_flasher/build.ps1     Windows package build
Setup-CallBox.exe                   Candidate/public portable artifact
Setup-CallBox.exe.sha256            SHA-256 sidecar
```

## Related project

CallBox firmware/platform repository:

`https://github.com/Tunglam0605/Callbox-Aubot`

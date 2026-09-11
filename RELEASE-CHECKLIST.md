# Setup CallBox Release Checklist

## Source gate

- [ ] `app_version.py` matches the release tag.
- [ ] Git working tree is clean before tagging.
- [ ] All unit tests pass.
- [ ] `git diff --check` passes.
- [ ] `Setup-CallBox.factory.json` is ignored and is not staged.
- [ ] Public example/profile files contain no deployment credentials.

## Compatibility gate

- [ ] Existing `remote_config` still publishes to `callbox/{id}/cmd` and receives `config_ack` on `callbox/{id}/event`.
- [ ] Existing WCS `/event`, `/cmd`, `/status`, `/internet` contract is unchanged.
- [ ] Remote Button 1 / Button 2 / Cancel only use `callbox/{id}/control`.
- [ ] Management ACK only uses `callbox/{id}/control_ack`.
- [ ] I/O telemetry only uses `callbox/{id}/io`.
- [ ] Failure/rejection of the optional control subscription does not clear WCS `COMM_READY` or MQTT operational state.
- [ ] Older firmware without `/io` keeps remote buttons disabled in Setup CallBox.

## Package gate

- [ ] `Setup-CallBox.exe` builds successfully.
- [ ] `Setup-CallBox.exe --version` matches the release version.
- [ ] `Setup-CallBox.exe --self-test` passes.
- [ ] GUI launches without an early process exit.
- [ ] SHA-256 sidecar is generated from the final EXE.
- [ ] GitHub Release contains exactly the expected Windows update assets.

## Hardware acceptance

Before production rollout:

- [ ] Detect an actual ESP32-S3 CallBox.
- [ ] `APP_ONLY` flash + verify + reboot passes with embedded firmware v1.5.1.
- [ ] `CONFIG_ONLY` NVS write + verify + reboot passes.
- [ ] `CMD:CONFIG` confirms ID + Operating Version after reboot.
- [ ] Wi-Fi/MQTT reconnect is confirmed.
- [ ] Existing physical Button 1 / Button 2 / Cancel behavior is unchanged.
- [ ] Existing WCS `accepted -> queued -> assigned -> locked -> completed` lifecycle is unchanged.
- [ ] `/status` payload consumed by WCS remains backward compatible.

## Remote MQTT acceptance

- [ ] Setup tool watches one target ID and receives `/status` + `/io`.
- [ ] Remote controls stay disabled while device is offline, syncing, or `/io` is stale.
- [ ] Version 1.0 shows Button 2 as Task 1 and both task LEDs mirror Task 1.
- [ ] Version 2.0 shows Button 1 -> Task 1 and Button 2 -> Task 2.
- [ ] Remote Button 1 produces the same Mission Manager path as physical Button 1.
- [ ] Remote Button 2 produces the same Mission Manager path as physical Button 2.
- [ ] Remote Cancel follows the same admission/lock rules as physical Cancel.
- [ ] `control_ack=ok` is presented as queue admission, not as WCS task acceptance.
- [ ] Tower red/yellow/green and button LEDs shown in GUI match the real outputs.
- [ ] Disconnecting the Setup tool has no effect on CallBox/WCS operation.
- [ ] Denying the `control` topic at the broker leaves WCS operation normal.

## Updater acceptance

- [ ] Current release reports no update when it is latest.
- [ ] An older packaged EXE detects a newer GitHub Release.
- [ ] Downloaded EXE SHA-256 verification passes.
- [ ] Bad SHA-256 is rejected.
- [ ] Update is blocked during active ESP32 flashing.
- [ ] Helper replaces the old EXE and relaunches the new version.

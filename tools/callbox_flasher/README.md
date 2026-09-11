# CallBox Flasher / Setup Tool

Source package for **Setup CallBox v1.1.0**.

Key guarantees:

- Existing USB production/configuration modes are retained.
- Existing MQTT `remote_config` remains on `/cmd` + `/event`.
- New remote operator controls are isolated on `/control`, `/control_ack`, and `/io`.
- Embedded application asset is CallBox firmware v1.5.1 built from commit `f9ed879`.

Build from repository root or run `build.ps1` in this directory. The build script creates a clean virtual environment, runs the complete unit-test suite, packages `Setup-CallBox.exe`, then runs the packaged self-test.

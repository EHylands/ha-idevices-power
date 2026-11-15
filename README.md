# iDevices HomeKit Power

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)

Adds **Power** (W) and **Energy** (kWh) sensors for iDevices switches and
outlets that are paired with Home Assistant's built-in
[HomeKit Device](https://www.home-assistant.io/integrations/homekit_controller/)
integration.

iDevices switches report their power use in a vendor-specific HomeKit service
that the built-in integration ignores. This integration reads that service over
the pairing Home Assistant already has, so you don't need to pair the switch a
second time, and the built-in integration is left unmodified.

## Features

- **Power** and **Energy** sensors for every paired iDevices switch, shown on
  the switch's existing device page.
- **Energy dashboard ready.** The Energy sensor is a `total_increasing` kWh
  sensor.
- **Automatic discovery.** Set it up once. Switches you pair later get sensors
  within one polling interval, with no restart.
- **Automatic cleanup.** Deleting a switch from the HomeKit Device integration
  also deletes its sensors.
- **Independent switches.** All switches are read in parallel. A switch that
  can't be read only makes its own sensors unavailable.
- **Configurable polling interval** (default 30 seconds).

## Supported devices

Any HomeKit device that exposes the iDevices power service
`6747C101-FAC9-4D62-ADF4-E764D0A8B39D` is picked up automatically.

| Device | Model | Firmware | Status |
| --- | --- | --- | --- |
| iDevices Outdoor Switch | IDEV0004 | 1.9.11 | Tested |

Other iDevices switches and outlets with power metering will probably work too,
but have not been tested. If you try one, please
[open an issue](https://github.com/EHylands/ha-idevices-power/issues) to say
whether it worked.

## Requirements

- Home Assistant **2026.10.0** or newer.
- The switch paired with the **HomeKit Device** integration
  (**Settings → Devices & services**) and online.

## Installation

### HACS (recommended)

1. In HACS, open the **⋮** menu → **Custom repositories**.
2. Add `https://github.com/EHylands/ha-idevices-power` with type
   **Integration**.
3. Search for **iDevices HomeKit Power**, install it, and restart Home
   Assistant.

### Manual

1. Copy `custom_components/idevices_power` from this repository into your Home
   Assistant configuration directory, so that you have
   `<config>/custom_components/idevices_power/manifest.json`.
2. Restart Home Assistant.

## Setup

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **iDevices HomeKit Power**.
3. The dialog lists the switches it found. Select **Submit** to add them all.

You only add the integration once. Switches paired afterwards are added
automatically.

## Sensors

Each switch gets two sensors. They are named after the switch, for example
`sensor.outdoor_switch_power`.

| Sensor | Unit | State class | HomeKit characteristic | Conversion |
| --- | --- | --- | --- | --- |
| Power | W | `measurement` | `6747C102-FAC9-4D62-ADF4-E764D0A8B39D` (milliwatts) | ÷ 1,000 |
| Energy | kWh | `total_increasing` | `6747C103-FAC9-4D62-ADF4-E764D0A8B39D` (millijoules) | ÷ 3,600,000,000 |

To track usage, add the Energy sensor under **Settings → Dashboards → Energy →
Individual devices**.

## Options

Select **Configure** on the integration entry to change:

| Option | Default | Range | Description |
| --- | --- | --- | --- |
| Polling interval | 30 s | 5–3600 s | How often the switches are read. They never push power readings, so this sets how fresh the values are. |

The new interval applies immediately, without a restart.

## How it works

1. The built-in HomeKit Device integration keeps a live, encrypted connection to
   each paired device, identified by its HomeKit pairing ID.
2. On every poll, this integration goes through those connections and looks for
   the iDevices power service in each device's accessory list. Devices without
   it are skipped and are never contacted.
3. For each device that has the service, it reads the power and energy
   characteristics in a single request over the existing connection.
4. The sensors are attached to the device that the HomeKit Device integration
   created, so they appear alongside the switch's other entities.

## Troubleshooting

### "No paired HomeKit device with iDevices power metering was found"

The switch is not paired with the HomeKit Device integration, or it is offline.
Check that it appears under **Settings → Devices & services → HomeKit Device**
and isn't showing an error, then try again.

### Sensors are unavailable

The switch couldn't be read on the last poll, usually because it dropped off
Wi-Fi. The sensors recover on their own once the switch responds again. The log
records one message when a switch becomes unreachable and one when it is back.

### Duplicate Power/Energy sensors, or entity IDs ending in `_2`

An older modified copy of the HomeKit Device integration is still installed in
`<config>/custom_components/homekit_controller`. Delete that folder, restart,
and remove its leftover Power and Energy entities.

### Debug logging

Add this to `configuration.yaml` and restart:

```yaml
logger:
  logs:
    custom_components.idevices_power: debug
```

## Removal

1. Go to **Settings → Devices & services → iDevices HomeKit Power**, open the
   **⋮** menu and select **Delete**. The switches themselves are not affected.
2. Uninstall the integration from HACS, or delete
   `<config>/custom_components/idevices_power`, then restart.

## Limitations

- **Relies on Home Assistant internals.** The HomeKit Device integration has no
  public API for sharing its connections, so this integration depends on its
  internals. All of that code is in `hkc.py`. A future Home Assistant release
  could break it. If that happens the sensors stop updating, but the switches
  keep working.
- **Energy resolution.** The switch reports energy with about six significant
  digits, so the Energy sensor moves in small steps (about 2.8 Wh on the tested
  switch) instead of changing smoothly.
- **Polled, not pushed.** Readings are only as fresh as the polling interval.
- **Not exposed.** The service has other characteristics that this integration
  doesn't expose: on-time (`6747C104`), a lifetime seconds counter
  (`6747C105`), and what appears to be an energy counter reset (`6747C106`).

## Development

Install the test dependencies and run the tests from the repository root:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

The tests use
[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
with a stand-in for the HomeKit Device connection, so you don't need a real
switch to run them.

## License

[MIT](LICENSE)

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

- **Power** and **Energy** sensors for each paired iDevices switch, shown on
  the switch's existing device page.
- **One entry per switch.** Each switch is added, configured and removed on its
  own.
- **Discovered automatically.** Paired switches that report power show up as
  **Discovered** in Devices & services, ready to add.
- **Energy dashboard ready.** The Energy sensor is a `total_increasing` kWh
  sensor.
- **Automatic cleanup.** Deleting a switch from the HomeKit Device integration
  also deletes its entry here.
- **Configurable polling interval** per switch (default 30 seconds).

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

Each switch is added separately.

**From discovery:** paired iDevices switches that report power appear under
**Settings → Devices & services → Discovered** as *iDevices HomeKit Power*.
Select **Add** on each one you want. Discovery comes from the network
announcements of devices whose model starts with `IDEV`. Once one switch has
been added, any other paired device with the iDevices power service is offered
too, whatever its model name.

**Manually:** go to **Settings → Devices & services → Add integration**, search
for **iDevices HomeKit Power** and pick a switch from the list. Repeat for each
switch.

### Upgrading from 0.1.0

Version 0.1.0 used a single entry for all switches. When you upgrade, that entry
is removed and each switch appears as discovered. Add them again from
**Discovered**. The sensors should come back with the same entity IDs, so
history and the Energy dashboard carry on.

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

Select **Configure** on a switch's entry to change:

| Option | Default | Range | Description |
| --- | --- | --- | --- |
| Polling interval | 30 s | 5–3600 s | How often the switch is read. It never pushes power readings, so this sets how fresh the values are. |

The new interval applies immediately, without a restart.

## How it works

1. The built-in HomeKit Device integration keeps a live, encrypted connection to
   each paired device, identified by its HomeKit pairing ID.
2. Each entry stores one pairing ID. Discovery only offers a device if it is
   paired with the HomeKit Device integration and has the iDevices power
   service in its accessory list.
3. On every poll, the entry finds that device's connection and reads the power
   and energy characteristics in a single request over it.
4. The sensors are attached to the device that the HomeKit Device integration
   created, so they appear alongside the switch's other entities.

## Troubleshooting

### "No paired HomeKit device with iDevices power metering was found"

The switch is not paired with the HomeKit Device integration, or it is offline.
Check that it appears under **Settings → Devices & services → HomeKit Device**
and isn't showing an error, then try again.

### A switch isn't discovered

Discovery only offers devices that are paired with the HomeKit Device
integration, connected, and reporting power. Wall Switches without power
metering are skipped on purpose. If a switch that does report power is missing,
add it manually with **Add integration**.

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

1. Go to **Settings → Devices & services → iDevices HomeKit Power**. For each
   switch, open its **⋮** menu and select **Delete**. The switches themselves
   are not affected.
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

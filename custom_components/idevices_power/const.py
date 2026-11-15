"""Constants for the iDevices HomeKit Power integration."""

DOMAIN = "idevices_power"

CONF_HKID = "hkid"

DEFAULT_SCAN_INTERVAL = 30  # seconds

# After the switch turns on or off, read power this many times, this far apart,
# to follow the reading as it settles.
SWITCH_READ_COUNT = 5
SWITCH_READ_INTERVAL = 2  # seconds

# Vendor power metering service exposed by iDevices switches and outlets.
SERVICE_POWER = "6747C101-FAC9-4D62-ADF4-E764D0A8B39D"
CHAR_POWER = "6747C102-FAC9-4D62-ADF4-E764D0A8B39D"  # milliwatts
CHAR_ENERGY = "6747C103-FAC9-4D62-ADF4-E764D0A8B39D"  # millijoules

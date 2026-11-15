"""Constants for the iDevices HomeKit Power integration."""

DOMAIN = "idevices_power"

DEFAULT_SCAN_INTERVAL = 30  # seconds

# Vendor power metering service exposed by iDevices switches and outlets.
SERVICE_POWER = "6747C101-FAC9-4D62-ADF4-E764D0A8B39D"
CHAR_POWER = "6747C102-FAC9-4D62-ADF4-E764D0A8B39D"  # milliwatts
CHAR_ENERGY = "6747C103-FAC9-4D62-ADF4-E764D0A8B39D"  # millijoules

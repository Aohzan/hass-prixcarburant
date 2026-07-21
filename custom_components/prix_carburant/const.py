"""Constants for the Prix Carburant integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "prix_carburant"
PLATFORMS: Final = [Platform.BUTTON, Platform.SENSOR]

CONF_MAX_KM: Final = "max_km"
CONF_FUELS: Final = "fuels"
CONF_STATIONS: Final = "stations"
CONF_MANUAL_STATIONS: Final = "manual_stations"
CONF_DISPLAY_ENTITY_PICTURES: Final = "display_entity_pictures"
CONF_API_SSL_CHECK: Final = "api_ssl_check"

DEFAULT_NAME: Final = "Prix Carburant"
DEFAULT_MAX_KM: Final = 15
DEFAULT_SCAN_INTERVAL: Final = 4

ATTR_ADDRESS: Final = "address"
ATTR_POSTAL_CODE: Final = "postal_code"
ATTR_BRAND: Final = "brand"
ATTR_CITY: Final = "city"
ATTR_DISTANCE: Final = "distance"
ATTR_FUELS: Final = "fuels"
ATTR_FUEL_TYPE: Final = "fuel_type"
ATTR_UPDATED_DATE: Final = "updated_date"
ATTR_DAYS_SINCE_LAST_UPDATE: Final = "days_since_last_update"
ATTR_PRICE: Final = "price"
ATTR_SHORTAGE_SINCE: Final = "shortage_since"

ATTR_GAZOLE: Final = "Gazole"
ATTR_SP95: Final = "SP95"
ATTR_SP98: Final = "SP98"
ATTR_E10: Final = "E10"
ATTR_E85: Final = "E85"
ATTR_GPL: Final = "GPLc"
FUELS = [ATTR_E10, ATTR_E85, ATTR_SP95, ATTR_SP98, ATTR_GAZOLE, ATTR_GPL]

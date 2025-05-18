# Changelog

## [3.14.0](https://github.com/Aohzan/hass-prixcarburant/compare/3.13.0...3.14.0) (2025-05-18)

### Features

* station update ([10cde2a](https://github.com/Aohzan/hass-prixcarburant/commit/10cde2a27385a7eb798646386d0b93e6ed959290))

## [3.13.0](https://github.com/Aohzan/hass-prixcarburant/compare/3.12.0...3.13.0) (2025-05-08)

### Features

* update stations data ([#104](https://github.com/Aohzan/hass-prixcarburant/issues/104)) ([622db9e](https://github.com/Aohzan/hass-prixcarburant/commit/622db9e210686513002b78df410e0ad9055c8c57))

## [3.12.0](https://github.com/Aohzan/hass-prixcarburant/compare/3.11.0...3.12.0) (2025-05-08)

### Features

* update stations data ([#103](https://github.com/Aohzan/hass-prixcarburant/issues/103)) ([9ec1959](https://github.com/Aohzan/hass-prixcarburant/commit/9ec19593f403559fe138dca2982edda5844fedfd))

## [3.11.0](https://github.com/Aohzan/hass-prixcarburant/compare/3.10.2...3.11.0) (2025-05-06)

### Features

* add station 38490012 ([#101](https://github.com/Aohzan/hass-prixcarburant/issues/101)) ([f459999](https://github.com/Aohzan/hass-prixcarburant/commit/f4599996a87c6cdcd86a14f0bfaefe43294b4fc9))

## [3.10.2](https://github.com/Aohzan/hass-prixcarburant/compare/3.10.1...3.10.2) (2025-04-28)

### Bug Fixes

* Update in stations_name.json and update in tools.py ([#100](https://github.com/Aohzan/hass-prixcarburant/issues/100)) ([97f4e7b](https://github.com/Aohzan/hass-prixcarburant/commit/97f4e7b0e9d17f55ee6b1c57c10f48a5fc273024))

## [3.10.1](https://github.com/Aohzan/hass-prixcarburant/compare/3.10.0...3.10.1) (2025-04-28)

### Bug Fixes

* Update station Pontault & Ferrieres ([#99](https://github.com/Aohzan/hass-prixcarburant/issues/99)) ([884f921](https://github.com/Aohzan/hass-prixcarburant/commit/884f92110fee0fe02f01008b36b1a71181b8cf98))

## [3.10.0](https://github.com/Aohzan/hass-prixcarburant/compare/3.9.1...3.10.0) (2025-04-24)

### Features

* add option to ignore API's certificate verification ([#97](https://github.com/Aohzan/hass-prixcarburant/issues/97)) ([b28e90b](https://github.com/Aohzan/hass-prixcarburant/commit/b28e90b09e9f586995519baa8ba10401e44d832e))

## [3.9.1](https://github.com/Aohzan/hass-prixcarburant/compare/3.9.0...3.9.1) (2025-04-24)

### Bug Fixes

* options configflow error ([2ecd341](https://github.com/Aohzan/hass-prixcarburant/commit/2ecd341a53e8eedbae77b065bbe52d7063616762))

## [3.9.0](https://github.com/Aohzan/hass-prixcarburant/compare/3.8.2...3.9.0) (2025-04-22)

### Features

* add release ([4da949d](https://github.com/Aohzan/hass-prixcarburant/commit/4da949d9c39f5bb2e639ab7745d7fbf02229ec68))

## 3.8.2

* Fix deprecated code

## 3.8.1

* Fix error when attribues is empty

## 3.8.0

* Normalize name, address and city of stations if put in uppercase or lowercase exclusively
* Allow to override station data from local file (address, postal code, city, brand, logo)
* Add fuel type on sensor attributes
* Add icon for service
* Sensor entity will now restore last value after a restart if price is not available

## 3.7.0

* Add lat/lon to the output of the service call

## 3.6.0

* Fix event loop warning
* Move entity picture in tools

## 3.5.6

* Update stations

## 3.5.5

* Update stations

## 3.5.4

* fix changed API URL (revert to 3.5.1)

## 3.5.3

* add E.Leclerc Violaines

## 3.5.2

* fix changed API URL

## 3.5.1

* fix Auchan and Carrefour icons

## 3.5.0

* add icon for service

## 3.4.1

* fix station id

## 3.4.0

* Update stations and logo db

## 3.3.1

* Fix config flow migration to 3.2.0 version

## 3.3.0

* Update station and logo db

## 3.2.0

* Fix auto-update
* Add scan interval option (default to 4 hours)
* Add option to use brand logo as entity picture or not (default to yes)

## 3.1.1

* Fix the since days calculation

## 3.1.0

* Add Auchan logo

## 3.0.0

* Migrate to the last gouv API (v2.1) : fastest update as only nearest fuel station are updated
* Store stations name/brand in local file to allow update by community
* Restrict yaml configuration to static list only
* Add `brand` atribute
* Add entity pictures
* Add `button.prix_carburant_refresh_prices` entity to ask to refresh prices
* Add `prix_carburant.find_nearest_stations` service "Prix Carburant: Trouver les stations proches"

## 2.5.0

* Replace `async_setup_platforms` deprecated method
* Bump requirement

## 2.4.0

* Add `days_since_last_update` attribute

## 2.3.0

* Added in HACS
* Update distance calcul function
* Add distance in attributes

## 2.2.2

* Fix current fuel selected in options

## 2.2.1

* Fix updated date

## 2.2.0

* Add latitude, longitude and last update date in attributes
* Allow to select some fuels

## 2.1.0

* Add config from UI
* Get stations from home location

## 2.0.0

* Refactor from upstram
* Add config flow w/ device management
* One sensor by fuel
* Only from yaml for now

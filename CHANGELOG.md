# CHANGELOG

## 3.5.7

- Modifications de stations sur la rive droite de Bordeaux
- Modifications de noms
- Ajout de stations manquantes

## 3.5.6

- Update stations

## 3.5.5

- Update stations

## 3.5.4

- fix changed API URL (revert to 3.5.1)

## 3.5.3

- add E.Leclerc Violaines

## 3.5.2

- fix changed API URL

## 3.5.1

- fix Auchan and Carrefour icons

## 3.5.0

- add icon for service

## 3.4.1

- fix station id

## 3.4.0

- Update stations and logo db

## 3.3.1

- Fix config flow migration to 3.2.0 version

## 3.3.0

- Update station and logo db

## 3.2.0

- Fix auto-update
- Add scan interval option (default to 4 hours)
- Add option to use brand logo as entity picture or not (default to yes)

## 3.1.1

- Fix the since days calculation

## 3.1.0

- Add Auchan logo

## 3.0.0

- Migrate to the last gouv API (v2.1) : fastest update as only nearest fuel station are updated
- Store stations name/brand in local file to allow update by community
- Restrict yaml configuration to static list only
- Add `brand` atribute
- Add entity pictures
- Add `button.prix_carburant_refresh_prices` entity to ask to refresh prices
- Add `prix_carburant.find_nearest_stations` service "Prix Carburant: Trouver les stations proches"

## 2.5.0

- Replace `async_setup_platforms` deprecated method
- Bump requirement

## 2.4.0

- Add `days_since_last_update` attribute

## 2.3.0

- Added in HACS
- Update distance calcul function
- Add distance in attributes

## 2.2.2

- Fix current fuel selected in options

## 2.2.1

- Fix updated date

## 2.2.0

- Add latitude, longitude and last update date in attributes
- Allow to select some fuels

## 2.1.0

- Add config from UI
- Get stations from home location

## 2.0.0

- Refactor from upstram
- Add config flow w/ device management
- One sensor by fuel
- Only from yaml for now

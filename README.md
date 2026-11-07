# Intégration Prix Carburant pour Home-Assistant

![GitHub release (with filter)](https://img.shields.io/github/v/release/aohzan/hass-prixcarburant) ![GitHub](https://img.shields.io/github/license/aohzan/hass-prixcarburant) [![Donate](https://img.shields.io/badge/$-support-ff69b4.svg?style=flat)](https://github.com/sponsors/Aohzan) [![Marketplace](https://img.shields.io/badge/Marketplace-Default-41BDF5.svg)](https://www.home-assistant.io/integrations/marketplace/)

This a _custom component_ for [Home Assistant](https://www.home-assistant.io/).
The `prix_carburant` integration allows you to get information and prices from [gouv API](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/table/).

:exclamation: [README complet en français](README.fr.md) :fr: :exclamation:

## Installation

### Marketplace

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Aohzan&repository=hass-prixcarburant&category=integration)

Settings > Marketplace > search for "Prix Carburant" > Install.

### Manually

Copy the directory `prix_carburant` in `config/custom_components` of your Home-Assistant.

## Configuration

### From UI

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=prix_carburant)

Or go to Settings > Devices & services > Add integration and select Prix Carburant.

### From configuration.yaml

Deprecated: the stations are imported once as manual stations of the integration (maximum distance 0), then managed from its options. Remove the platform from configuration.yaml after the import.

```yaml
sensor:
  - platform: prix_carburant
    # IDs from https://www.prix-carburants.gouv.fr/
    stations:
      - 12345678
      - 34567890
```

## Contributing

### Stations Data

The `stations_name.json` file contains information about gas stations with their IDs, names, and brands. If you want to contribute by adding or updating station information:

1. Fork the repository
2. Edit the `custom_components/prix_carburant/stations_name.json` file
3. Create a pull request

A GitHub workflow will automatically validate the JSON structure and format. If the PR only modifies the stations_name.json file and passes validation, it will be automatically approved and merged.

### Commit messages

When contributing to the codebase, please follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) format for commit messages. This helps maintain a clear and consistent commit history, and is used to automatically generate release notes.

## Crédits

Thanks to https://github.com/max5962/prixCarburant-home-assistant for base code.

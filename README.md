# Intégration Prix Carburant pour Home-Assistant

![GitHub release (with filter)](https://img.shields.io/github/v/release/aohzan/hass-prixcarburant) ![GitHub](https://img.shields.io/github/license/aohzan/hass-prixcarburant) [![Donate](https://img.shields.io/badge/$-support-ff69b4.svg?style=flat)](https://github.com/sponsors/Aohzan) [![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)

This a _custom component_ for [Home Assistant](https://www.home-assistant.io/).
The `prix_carburant` integration allows you to get information and prices from [gouv API](https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/table/).

:exclamation: [README complet en français](README.fr.md) :fr: :exclamation:

## Installation

### HACS

HACS > Integrations > Explore & Download Repositories > Prix Carburant > Download this repository with HACS

### Manually

Copy the directory `prix_carburant` in `config/custom_components` of your Home-Assistant.

## Configuration

### From UI

Search `Prix Carburant` in Integration.

### From configuration.yaml

```yaml
sensor:
    - platform: prix_carburant
    # IDs from https://www.prix-carburants.gouv.fr/
      stations:
        - 12345678
        - 34567890
```

## Crédits

Thanks to https://github.com/max5962/prixCarburant-home-assistant for base code.

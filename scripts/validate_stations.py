#!/usr/bin/env python3
"""Validate the stations_name.json file."""

import json
import logging
import sys
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


def _validate_station_entry(station_id: str, station_data: dict) -> str | None:
    """Validate a single station entry. Returns error message or None."""
    checks: list[tuple[bool, str]] = [
        (isinstance(station_id, str), f"Station ID {station_id} should be a string."),
        (
            isinstance(station_data, dict),
            f"Station data for {station_id} should be a dictionary.",
        ),
        (
            "name" in station_data,
            f"Station {station_id} is missing the 'name' property.",
        ),
        (
            "brand" in station_data,
            f"Station {station_id} is missing the 'brand' property.",
        ),
        (
            isinstance(station_data.get("name"), str),
            f"Station {station_id} 'name' should be a string.",
        ),
        (
            isinstance(station_data.get("brand"), str),
            f"Station {station_id} 'brand' should be a string.",
        ),
    ]
    for passed, message in checks:
        if not passed:
            return message

    for coord_key in ("latitude", "longitude"):
        if coord_key in station_data:
            try:
                float(station_data[coord_key])
            except TypeError, ValueError:
                return f"Station {station_id} '{coord_key}' should be a float."
    return None


def validate_stations_json(file_path: Path) -> bool | None:
    """Validate the stations_name.json file."""
    try:
        with file_path.open(encoding="UTF-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            _LOGGER.error("The JSON file should contain a dictionary.")
            return False

        for station_id, station_data in data.items():
            if error := _validate_station_entry(station_id, station_data):
                _LOGGER.error(error)
                return False

    except json.JSONDecodeError:
        _LOGGER.exception("Invalid JSON format")
        return False
    except OSError:
        _LOGGER.exception("Error reading file")
        return False
    else:
        _LOGGER.info("The stations_name.json file is valid.")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) != 2:
        _LOGGER.info("Usage: python validate_stations.py <path_to_stations_name.json>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        _LOGGER.error("File %s does not exist.", file_path)
        sys.exit(1)

    if not validate_stations_json(file_path):
        sys.exit(1)

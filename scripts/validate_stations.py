#!/usr/bin/env python3
"""Validate the stations_name.json file."""

import json
import sys
from pathlib import Path


def validate_stations_json(file_path):
    """Validate the stations_name.json file."""
    try:
        # Load the JSON file
        with open(file_path, "r", encoding="UTF-8") as file:
            data = json.load(file)

        # Check if the data is a dictionary
        if not isinstance(data, dict):
            print("Error: The JSON file should contain a dictionary.")
            return False

        # Check each station entry
        for station_id, station_data in data.items():
            # Check if the station ID is a string
            if not isinstance(station_id, str):
                print(f"Error: Station ID {station_id} should be a string.")
                return False

            # Check if the station data is a dictionary
            if not isinstance(station_data, dict):
                print(f"Error: Station data for {station_id} should be a dictionary.")
                return False

            # Check if the station has a name
            if "name" not in station_data:
                print(f"Error: Station {station_id} is missing the 'name' property.")
                return False

            # Check if the station has a brand
            if "brand" not in station_data:
                print(f"Error: Station {station_id} is missing the 'brand' property.")
                return False

            # Check if name and brand are strings
            if not isinstance(station_data["name"], str):
                print(f"Error: Station {station_id} 'name' should be a string.")
                return False

            if not isinstance(station_data["brand"], str):
                print(f"Error: Station {station_id} 'brand' should be a string.")
                return False

        print("The stations_name.json file is valid.")
        return True

    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format: {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_stations.py <path_to_stations_name.json>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"Error: File {file_path} does not exist.")
        sys.exit(1)

    if not validate_stations_json(file_path):
        sys.exit(1)
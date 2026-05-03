#!/usr/bin/env python3
"""
Clean stations_name.json.

Keeps entries that were manually overridden by users (targeted non-automated commits).
Removes entries already present in the OSM CSV file that were not user-overridden.

A commit is considered a "user override" only if it changed fewer than
MAX_BULK_CHANGES stations (bulk commits are initial imports or mass renames,
not individual user fixes).

Changed station IDs per commit are detected by comparing the JSON file content
between parent and child commits, so name/brand-only edits are correctly captured.
"""

import csv
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
STATIONS_JSON = REPO_ROOT / "custom_components/prix_carburant/stations_name.json"
STATIONS_OSM_CSV = REPO_ROOT / "custom_components/prix_carburant/stations_name_osm.csv"

AUTOMATED_COMMIT_PATTERN = re.compile(
    r"^chore: (?:update stations data|automatic update of stations data)$"
)
# Commits changing more entries than this threshold are bulk operations, not user overrides
MAX_BULK_CHANGES = 50


def get_all_commits_for_file(filepath: str) -> list[tuple[str, str]]:
    """Return list of (hash, subject) for all commits touching the file."""
    result = subprocess.run(  # noqa: S603
        ["git", "log", "--format=%H\t%s", "--", filepath],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    commits = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:  # noqa: PLR2004
            commits.append((parts[0], parts[1]))
    return commits


def get_json_at_commit(commit_hash: str, filepath: str) -> dict:
    """Return parsed JSON content of filepath at a given commit, or {} on error."""
    result = subprocess.run(  # noqa: S603
        ["git", "show", f"{commit_hash}:{filepath}"],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def get_ids_changed_in_commit(commit_hash: str, filepath: str) -> set[str]:
    """
    Return station IDs whose data changed between a commit's parent and itself.

    Compares full JSON content so name/brand-only edits are detected, not just
    additions of new station keys.
    """
    parent_data = get_json_at_commit(f"{commit_hash}^", filepath)
    current_data = get_json_at_commit(commit_hash, filepath)
    changed: set[str] = set()
    for sid in set(parent_data) | set(current_data):
        if parent_data.get(sid) != current_data.get(sid):
            changed.add(sid)
    return changed


def get_osm_station_ids(csv_path: Path) -> dict[str, dict]:
    """Return dict of station_id -> {name, brand} from OSM CSV."""
    osm_stations = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            station_id = row.get("ref:FR:prix-carburants", "").strip()
            name = row.get("name", "").strip()
            brand = row.get("brand", "").strip()
            if station_id and name:
                osm_stations[station_id] = {"name": name, "brand": brand}
    return osm_stations


def main() -> None:
    """Run the station JSON cleanup process."""
    # Load current stations_name.json
    with STATIONS_JSON.open(encoding="utf-8") as f:
        stations = json.load(f)

    logger.info("Current stations_name.json entries: %d", len(stations))

    # Load OSM stations
    osm_stations = get_osm_station_ids(STATIONS_OSM_CSV)
    logger.info("OSM CSV entries with name: %d", len(osm_stations))

    # Get all commits for the file
    rel_path = "custom_components/prix_carburant/stations_name.json"
    commits = get_all_commits_for_file(rel_path)
    logger.info("Total commits: %d", len(commits))

    # Find user-overridden IDs from targeted (non-bulk, non-automated) commits
    user_override_ids: set[str] = set()
    automated_count = 0
    bulk_count = 0
    user_commit_count = 0

    for commit_hash, subject in commits:
        if AUTOMATED_COMMIT_PATTERN.search(subject):
            automated_count += 1
            continue
        changed_ids = get_ids_changed_in_commit(commit_hash, rel_path)
        if len(changed_ids) > MAX_BULK_CHANGES:
            bulk_count += 1
            continue
        user_commit_count += 1
        user_override_ids.update(changed_ids)

    logger.info(
        "Automated commits: %d, Bulk commits (>%d changes): %d, Targeted user commits: %d",
        automated_count,
        MAX_BULK_CHANGES,
        bulk_count,
        user_commit_count,
    )
    logger.info("Station IDs from targeted user commits: %d", len(user_override_ids))

    # Build cleaned JSON
    # Keep if: not in OSM (no alternative source)
    #       or: in OSM but explicitly overridden by a targeted user commit
    # Remove if: in OSM and not a user override
    kept: dict = {}
    removed: list[str] = []

    for station_id, data in stations.items():
        in_osm = station_id in osm_stations
        is_user_override = station_id in user_override_ids
        # Compare only keys present in OSM data (name, brand) to avoid false
        # positives from extra override fields (e.g. latitude, longitude, city)
        data_differs = in_osm and any(
            data.get(k) != v for k, v in osm_stations[station_id].items()
        )

        if not in_osm or is_user_override or data_differs:
            kept[station_id] = data
        else:
            removed.append(station_id)

    logger.info("\nResults:")
    logger.info(
        "  Kept (user overrides in OSM):   %d",
        sum(1 for sid in kept if sid in user_override_ids and sid in osm_stations),
    )
    logger.info(
        "  Kept (data differs from OSM):   %d",
        sum(
            1
            for sid in kept
            if sid in osm_stations
            and sid not in user_override_ids
            and kept[sid] != osm_stations[sid]
        ),
    )
    logger.info(
        "  Kept (not in OSM):              %d",
        sum(1 for sid in kept if sid not in osm_stations),
    )
    logger.info("  Removed (in OSM, data matches): %d", len(removed))
    logger.info("  Total kept: %d", len(kept))

    if "--dry-run" in sys.argv:
        logger.info("\nDry run - no changes written.")
        if removed[:10]:
            logger.info("Sample removed IDs (in OSM, data matches): %s", removed[:10])
        return

    # Write cleaned JSON
    with STATIONS_JSON.open("w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)
        f.write("\n")

    logger.info("\nWrote cleaned stations_name.json with %d entries.", len(kept))


if __name__ == "__main__":
    main()

"""Download, decompress, and strip unused columns from the OSM stations CSV."""

import bz2
import csv
import io
import logging
from pathlib import Path
from urllib.request import urlopen

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

OSM_CSV_URL = (
    "https://www.data.gouv.fr/api/1/datasets/r/fcab3bd4-6c6d-4b73-95d2-cfd5e04ee651"
)
OUTPUT_FILE = (
    Path(__file__).parent.parent
    / "custom_components/prix_carburant/stations_name_osm.csv"
)
KEEP_COLUMNS = {"ref:FR:prix-carburants", "name", "brand", "operator", "branch"}


def main() -> None:
    """Download and filter the OSM stations CSV."""
    logger.info("Downloading %s ...", OSM_CSV_URL)
    with urlopen(OSM_CSV_URL) as response:  # noqa: S310
        raw = response.read()

    content = bz2.decompress(raw).decode("utf-8")
    reader = csv.DictReader(io.StringIO(content))
    cols = [c for c in reader.fieldnames if c in KEEP_COLUMNS]

    rows = [{k: row[k] for k in cols} for row in reader]

    with OUTPUT_FILE.open("w", encoding="utf-8", newline="\n") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Written %d rows to %s", len(rows), OUTPUT_FILE)


if __name__ == "__main__":
    main()

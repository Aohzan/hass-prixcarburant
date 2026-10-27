"""Check the translations of the integration.

strings.json is the source of truth: translations/en.json must be identical,
and every other translation must have exactly the same keys.

Usage:
    python scripts/check_translations.py        # check
    python scripts/check_translations.py --fix  # copy strings.json to en.json
"""

import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent


def flatten(data: dict, prefix: str = "") -> set[str]:
    """Return the dotted keys of the translation strings."""
    keys = set()
    for key, value in data.items():
        if isinstance(value, dict):
            keys |= flatten(value, f"{prefix}{key}.")
        else:
            keys.add(f"{prefix}{key}")
    return keys


def main() -> None:
    """Run the script."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fix", action="store_true", help="copy strings.json to translations/en.json"
    )
    args = parser.parse_args()

    (component,) = (
        path.parent for path in ROOT.glob("custom_components/*/manifest.json")
    )
    strings_path = component / "strings.json"
    english_path = component / "translations" / "en.json"
    strings = json.loads(strings_path.read_text(encoding="utf-8"))

    if args.fix:
        shutil.copyfile(strings_path, english_path)

    errors = []
    if json.loads(english_path.read_text(encoding="utf-8")) != strings:
        errors.append(f"{english_path.relative_to(ROOT)} differs from strings.json")

    reference = flatten(strings)
    for path in sorted(english_path.parent.glob("*.json")):
        keys = flatten(json.loads(path.read_text(encoding="utf-8")))
        name = path.relative_to(ROOT)
        errors.extend(f"{name}: missing {key}" for key in sorted(reference - keys))
        errors.extend(f"{name}: unknown {key}" for key in sorted(keys - reference))

    if errors:
        raise SystemExit("\n".join(errors))
    print("Translations are consistent")


if __name__ == "__main__":
    main()

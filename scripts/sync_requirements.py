"""Pin the manifest requirements to the versions locked in uv.lock.

uv.lock is the source of truth for the libraries pinned with "==" in
manifest.json: Dependabot bumps them there, and the release copies their
locked versions to the manifest.

Home Assistant installs the requirements with its package constraints, so a
library must not need a newer version of a package pinned by the core. The
check resolves them with the constraints of the oldest supported version,
the homeassistant lower bound in the dev group of pyproject.toml.

Usage:
    python scripts/sync_requirements.py          # update manifest.json
    python scripts/sync_requirements.py --check  # check against Home Assistant
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
PINNED = re.compile(r"^(?P<name>[A-Za-z0-9._-]+)==(?P<version>\S+)$")
CONSTRAINTS_URL = (
    "https://raw.githubusercontent.com/home-assistant/core/"
    "{version}/homeassistant/package_constraints.txt"
)


def normalize(name: str) -> str:
    """Normalize a package name (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_requirements(requirements: list[str]) -> list[str]:
    """Return the requirements, the pinned ones at their locked version."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked: dict[str, set[str]] = {}
    for package in lock["package"]:
        locked.setdefault(normalize(package["name"]), set()).add(package["version"])

    result = []
    for requirement in requirements:
        if match := PINNED.match(requirement):
            versions = locked.get(normalize(match["name"]))
            if not versions:
                raise SystemExit(f"{match['name']} is not in uv.lock")
            if len(versions) > 1:
                raise SystemExit(f"{match['name']} has several locked versions")
            requirement = f"{match['name']}=={versions.pop()}"
        result.append(requirement)
    return result


def oldest_homeassistant() -> str:
    """Return the oldest supported Home Assistant version."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for requirement in pyproject["dependency-groups"]["dev"]:
        if match := re.fullmatch(r"homeassistant>=(\S+)", requirement):
            return match[1]
    raise SystemExit(
        "No homeassistant>= requirement in the dev group of pyproject.toml"
    )


def check(requirements: list[str]) -> None:
    """Resolve the requirements as Home Assistant installs them."""
    version = oldest_homeassistant()
    python_version = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    with tempfile.TemporaryDirectory() as tmp:
        constraints = Path(tmp) / "package_constraints.txt"
        with urllib.request.urlopen(CONSTRAINTS_URL.format(version=version)) as resp:
            constraints.write_bytes(resp.read())
        result = subprocess.run(
            [
                "uv",
                "pip",
                "compile",
                "--quiet",
                "--no-header",
                "--python-version",
                python_version,
                "--constraint",
                str(constraints),
                "-",
            ],
            input="\n".join(requirements),
            text=True,
            check=False,
        )
    if result.returncode:
        raise SystemExit(
            f"{', '.join(requirements)} can't be installed with the package "
            f"constraints of Home Assistant {version}"
        )
    print(f"{', '.join(requirements)} can be installed on Home Assistant {version}")


def main() -> None:
    """Run the script."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the requirements against Home Assistant instead of updating",
    )
    args = parser.parse_args()

    (manifest_path,) = ROOT.glob("custom_components/*/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    requirements = locked_requirements(manifest["requirements"])

    if args.check:
        check(requirements)
    elif requirements != manifest["requirements"]:
        manifest["requirements"] = requirements
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Updated {manifest_path} requirements: {', '.join(requirements)}")


if __name__ == "__main__":
    main()

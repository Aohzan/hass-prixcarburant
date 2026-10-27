#!/usr/bin/env bash

set -e

if [ $# -ne 1 ]; then
    echo "Missing version"
    echo "Usage: $0 version"
    exit 1
fi

ROOT=$(realpath "$(dirname "$0")/..")
CUSTOM_COMPONENT="${ROOT}/custom_components/$(ls "${ROOT}/custom_components" | head -n 1)"
MANIFEST=${CUSTOM_COMPONENT}/manifest.json

echo "Setting version to ${1} in ${MANIFEST}"
cat <<<$(jq ".version=\"${1}\"" "${MANIFEST}") >"${MANIFEST}"

python3 "${ROOT}/scripts/sync_requirements.py"

echo "Creating release zip"
cd "${CUSTOM_COMPONENT}" && zip "${ROOT}/release.zip" -r ./

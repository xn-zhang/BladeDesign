#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/openfoam-bridge"
python3 -m unittest discover -s bridge/tests -v
for source in web/*.js bridge/*.mjs; do node --input-type=module --check < "$source"; done
node --test ../tests/*.test.mjs
python3 bridge/package.py
python3 ../scripts/check_package.py

#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd -- "${root}"
# shellcheck disable=SC1091
source scripts/activate_myfenics_surrogate_wsl.sh
exec python -m src.forward_data.cli run "$@"

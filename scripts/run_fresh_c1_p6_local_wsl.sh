#!/usr/bin/env bash
# User-authorized local WSL2 profile; delegates to the shared fixed-budget entry.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# -ne 3 ]]; then
  echo "usage: $0 LOCAL_WSL2_PREFIX NEW_RUN_DIRECTORY TOTAL_DEADLINE_UTC" >&2
  exit 64
fi
exec "$script_dir/run_fresh_c1_p6_native.sh" "$1" "$2" "$3" local_wsl2_authorized

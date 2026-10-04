#!/usr/bin/env bash
# Explicitly authorized local WSL2 activation; all ABI pins remain unchanged.
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo "usage: activate_local_wsl_complex.sh PREFIX RUN_LOCAL_ABI_RECEIPT RUN_LOCAL_JIT_CACHE" >&2
  return 64 2>/dev/null || exit 64
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/activate_native_complex.sh" "$1" "$2" "$3" local_wsl2_authorized

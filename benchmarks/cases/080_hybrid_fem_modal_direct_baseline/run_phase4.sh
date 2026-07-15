#!/usr/bin/env sh
set -eu

if [ -z "${VERIFIED_CLEAN_SHA:-}" ]; then
  echo "VERIFIED_CLEAN_SHA must be the full clean Phase 4 code commit." >&2
  exit 2
fi

exec mpiexec -n 4 python -m benchmarks.run_task032_phase4_propagation \
  --verified-clean-sha "${VERIFIED_CLEAN_SHA}" \
  --length-nm 100 \
  --first-length-nm 37 \
  --output benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/propagation_phase4.json

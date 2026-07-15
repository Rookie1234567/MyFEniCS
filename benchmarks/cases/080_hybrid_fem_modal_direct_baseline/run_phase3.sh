#!/usr/bin/env sh
set -eu

if [ -z "${VERIFIED_CLEAN_SHA:-}" ]; then
  echo "VERIFIED_CLEAN_SHA must be the full clean Phase 3 code commit." >&2
  exit 2
fi

exec mpiexec -n 4 python -m benchmarks.run_task032_phase3_modes \
  --verified-clean-sha "${VERIFIED_CLEAN_SHA}" \
  --basis-h-nm 10 \
  --tracking-h-nm 10 \
  --output benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/modes_phase3.json

#!/usr/bin/env sh
set -eu

if [ -z "${VERIFIED_CLEAN_SHA:-}" ]; then
  echo "VERIFIED_CLEAN_SHA must be the full clean Phase 6 code commit." >&2
  exit 2
fi

exec mpiexec -n 4 python -m benchmarks.run_task032_phase6_augmented \
  --verified-clean-sha "${VERIFIED_CLEAN_SHA}" \
  --h-nm 5 \
  --requested-modes 6 \
  --near-degenerate-tolerance 1e-6 \
  --block-rotation-tolerance 1e-6 \
  --output benchmarks/cases/080_hybrid_fem_modal_direct_baseline/records/hybrid_phase6_m6.json

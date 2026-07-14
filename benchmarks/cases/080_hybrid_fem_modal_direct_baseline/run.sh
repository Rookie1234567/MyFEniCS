#!/usr/bin/env sh
set -eu

LEVEL="${LEVEL:-h5}"
RESULTS_ROOT="${RESULTS_ROOT:-benchmarks/artifacts/cases/080/full3d_reference/${LEVEL}}"

case "${LEVEL}" in
  h5) PRESET=3d_target_grating_direct_h5 ;;
  h3) PRESET=3d_target_grating_direct_h3 ;;
  *) echo "LEVEL must be h5 or h3" >&2; exit 2 ;;
esac

exec mpiexec -n 4 python src/main.py \
  --preset "${PRESET}" \
  --results-root "${RESULTS_ROOT}" \
  --full3d-reference-export \
  --full3d-reference-plane-z 10 30 60 90 110 \
  --full3d-reference-sample-count-x 40 \
  --full3d-reference-sample-count-y 20

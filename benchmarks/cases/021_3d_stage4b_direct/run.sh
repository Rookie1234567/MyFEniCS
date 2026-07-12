#!/bin/sh
set -eu

H_VALUE="${H_VALUE:-5}"
case "$H_VALUE" in
  5) PRESET=3d_target_grating_direct_h5 ;;
  3) PRESET=3d_target_grating_direct_h3 ;;
  *) echo "Only canonical target h=5 or h=3 is allowed here; h=2 is reviewed-only." >&2; exit 2 ;;
esac

mpiexec -n 4 python src/main.py --preset "$PRESET" \
  --results-root "benchmarks/artifacts/cases/021/h${H_VALUE}"

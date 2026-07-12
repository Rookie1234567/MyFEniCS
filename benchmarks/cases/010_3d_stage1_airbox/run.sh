#!/bin/sh
set -eu
mpiexec -n 2 python src/main.py --preset 3d_stage1_airbox_smoke \
  --results-root benchmarks/artifacts/cases/010

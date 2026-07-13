#!/bin/sh
set -eu
python src/main.py --preset 2d_tm_pml_floquet_smoke \
  --results-root benchmarks/artifacts/cases/001

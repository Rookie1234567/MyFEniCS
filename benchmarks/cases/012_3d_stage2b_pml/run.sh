#!/bin/sh
set -eu
python src/main.py --preset 3d_stage2b_pml_smoke \
  --results-root benchmarks/artifacts/cases/012

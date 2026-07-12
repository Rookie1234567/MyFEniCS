#!/bin/sh
set -eu
python src/main.py --preset 3d_stage2a_floquet_smoke \
  --results-root benchmarks/artifacts/cases/011

#!/bin/sh
set -eu
python src/main.py --preset 3d_stage2c_fresnel_smoke \
  --results-root benchmarks/artifacts/cases/013

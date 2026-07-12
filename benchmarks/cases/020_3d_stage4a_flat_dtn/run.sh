#!/bin/sh
set -eu
python src/main.py --preset 3d_stage4a_flat_layer_direct \
  --results-root benchmarks/artifacts/cases/020

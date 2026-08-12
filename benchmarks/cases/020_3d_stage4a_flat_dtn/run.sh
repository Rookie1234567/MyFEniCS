#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
CASE_ROOT="$ROOT/benchmarks/artifacts/cases/020"
mkdir -p "$CASE_ROOT"
cd "$CASE_ROOT"
exec python "$ROOT/scripts/run_case.py" \
  "$ROOT/input/smoke/3d_stage4a_flat_layer_direct.dat"

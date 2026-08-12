#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
CASE_ROOT="$ROOT/benchmarks/artifacts/cases/001"
mkdir -p "$CASE_ROOT"
cd "$CASE_ROOT"
exec python "$ROOT/scripts/run_case.py" \
  "$ROOT/input/smoke/2d_tm_pml_floquet_smoke.dat"

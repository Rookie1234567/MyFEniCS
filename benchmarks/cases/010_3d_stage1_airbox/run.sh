#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
CASE_ROOT="$ROOT/benchmarks/artifacts/cases/010"
mkdir -p "$CASE_ROOT"
cd "$CASE_ROOT"
exec python "$ROOT/scripts/run_case.py" \
  "$ROOT/input/official/stage1_airbox_smoke_mpi2.dat"

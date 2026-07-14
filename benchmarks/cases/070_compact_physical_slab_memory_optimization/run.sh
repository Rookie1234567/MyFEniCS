#!/usr/bin/env sh
set -eu

mpiexec -n 4 python -m benchmarks.run_task031_memory_forensics \
  --h-nm "${H_NM:-5}" --num-slabs 16 --overlap-layers 0.125 \
  --ksp-type fgmres --smoother-ksp-type gmres --restart 90 \
  --max-it "${MAX_IT:-5000}" --monitor-stride 90 \
  --matrix-free-fine --compact-lifecycle --no-certify-pc \
  --case-label "${CASE_LABEL:-task031_reproduction}" \
  --run-dir "${RUN_DIR:-/tmp/task031_reproduction}" \
  --verified-clean-sha "${VERIFIED_CLEAN_SHA:?set VERIFIED_CLEAN_SHA}"

#!/bin/sh
set -eu

: "${H2_GATE_JSON:?Set H2_GATE_JSON to a passing Task029 h2 gate record}"
PROFILE="${PROFILE:-default}"
POLL_INTERVAL="${POLL_INTERVAL:-0.25}"

python -m benchmarks.run_direct_memory_forensics \
  --h-nm 2 \
  --mpi-size 4 \
  --profile "$PROFILE" \
  --poll-interval "$POLL_INTERVAL" \
  --h2-gate-json "$H2_GATE_JSON" \
  --artifact-root benchmarks/artifacts/cases/050

#!/bin/sh
set -eu

PROFILE="${PROFILE:-default}"
POLL_INTERVAL="${POLL_INTERVAL:-0.25}"

python -m benchmarks.run_direct_memory_forensics \
  --h-nm 3 \
  --mpi-size 4 \
  --profile "$PROFILE" \
  --poll-interval "$POLL_INTERVAL" \
  --artifact-root benchmarks/artifacts/cases/050

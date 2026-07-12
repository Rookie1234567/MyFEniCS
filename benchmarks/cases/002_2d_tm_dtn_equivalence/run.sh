#!/bin/sh
set -eu

: "${SOURCE_COMMIT:?Set SOURCE_COMMIT to the source commit being tested}"
IMAGE_NAME="${IMAGE_NAME:-myfenics-stage4:task28}"
IMAGE_DIGEST="${IMAGE_DIGEST:-sha256:qualified-local-image}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-benchmarks/artifacts/cases/002}"
RECORD_DIR="${RECORD_DIR:-benchmarks/artifacts/cases/002/candidate_records}"

python -m benchmarks.run_2d_canonical \
  --case 002 \
  --artifact-root "$ARTIFACT_ROOT" \
  --record-dir "$RECORD_DIR" \
  --source-commit "$SOURCE_COMMIT" \
  --container-image "$IMAGE_NAME" \
  --container-digest "$IMAGE_DIGEST"

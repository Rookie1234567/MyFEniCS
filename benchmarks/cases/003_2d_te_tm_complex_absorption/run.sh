#!/bin/sh
set -eu

: "${SOURCE_COMMIT:?Set SOURCE_COMMIT to the source commit being tested}"
: "${IMAGE_DIGEST:?Set IMAGE_DIGEST to the tested image digest}"
IMAGE_NAME="${IMAGE_NAME:-myfenics-stage4:task28}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-benchmarks/artifacts/cases/003}"
RECORD_DIR="${RECORD_DIR:-benchmarks/artifacts/cases/003/candidate_records}"

for VARIANT in tm te; do
  python -m benchmarks.run_2d_canonical \
    --case 003 --variant "$VARIANT" \
    --artifact-root "$ARTIFACT_ROOT" \
    --record-dir "$RECORD_DIR" \
    --source-commit "$SOURCE_COMMIT" \
    --container-image "$IMAGE_NAME" \
    --container-digest "$IMAGE_DIGEST"
done

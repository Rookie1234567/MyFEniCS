#!/bin/sh
set -eu

H_VALUES="${H_VALUES:-5}"
for H_VALUE in $H_VALUES; do
  TAG=$(printf '%s' "$H_VALUE" | tr '.' 'p')
  mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
    --config benchmarks/configs/workstation_p2.json \
    --h-nm "$H_VALUE" \
    --case-label "case031_candidate_h${TAG}" \
    --results-dir benchmarks/artifacts/cases/031 \
    --record "benchmarks/artifacts/cases/031/candidate_records/h${TAG}.json"
done

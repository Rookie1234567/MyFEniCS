#!/usr/bin/env sh
set -eu

python -m benchmarks.run_task033_resource_matrix \
  --output-json benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/resource_matrix.json \
  --output-csv benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/resource_matrix.csv

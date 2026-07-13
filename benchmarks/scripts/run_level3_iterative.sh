#!/bin/sh
set -eu

for h in 5 3 2; do
  tag=$(printf '%s' "$h" | tr '.' 'p')
  mpiexec -n 4 python -m benchmarks.run_workstation_iterative \
    --config benchmarks/configs/workstation_p2.json \
    --h-nm "$h" \
    --results-dir benchmarks/artifacts/iterative \
    --record "benchmarks/records/workstation_p2_h${tag}_mpi4.json"
done

python -m benchmarks.check_benchmarks

#!/bin/sh
set -eu

mpiexec -n 4 python -m benchmarks.run_task030_multilevel_hcurl \
  --config benchmarks/cases/060_multilevel_hcurl_iterative_solver/config.json \
  "$@"

#!/usr/bin/env bash
set -euo pipefail

echo "Case094 is gated. Run P0 through P10 in task.md order."
echo "Heavy data/checkpoints/logs belong under benchmarks/artifacts/cases/094."
echo "Formal FE runs: MPI4 complex FEniCS; training/runtime screen: fenics-ml GPU 0."
echo "Do not run h3/h2 or shared/expert lanes before their explicit gates."

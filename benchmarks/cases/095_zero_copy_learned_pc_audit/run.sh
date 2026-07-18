#!/usr/bin/env bash
set -euo pipefail

echo "Case095 is gated. Run P0 through P8 in task.md order."
echo "Heavy records belong under benchmarks/artifacts/cases/095 and remain ignored."
echo "Formal FEniCS runs use MPI4 complex wrapper; ML replay uses fenics-ml."
echo "Do not train full16, run learned-active global, h3/h2, or branch operations."

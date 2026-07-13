#!/bin/sh
set -eu

common_args="--stage-case stage4_block_grating --case oblique --nedelec-degree 2 --visualization-degree 2 --period-x 50 --period-y 25 --air-height 130 --substrate-thickness 10 --grating-width-x 17 --grating-width-y 25 --grating-height 120 --incident-theta-deg 80 --incident-phi-deg 0 --polarization-kind s --stage4-boundary-model dtn_port --stage4-dtn-order-policy auto_propagating --no-diffraction-compute-modal-diagnostic --results-root benchmarks/artifacts/direct"

for h in 5 3; do
  mpiexec -n 4 python -m src.runners.run_3d_cases $common_args --mesh-target-size "$h"
done

if [ "${1:-}" = "--include-resource-heavy-h2" ] || [ "${BENCHMARK_INCLUDE_DIRECT_H2:-0}" = "1" ]; then
  echo "WARNING: h=2 direct historically required about 20.53 GB total RSS."
  mpiexec -n 4 python -m src.runners.run_3d_cases $common_args --mesh-target-size 2
else
  echo "Skipping resource-heavy h=2 direct; pass --include-resource-heavy-h2 explicitly."
fi

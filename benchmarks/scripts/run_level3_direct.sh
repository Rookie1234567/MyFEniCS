#!/bin/sh
set -eu
common_args="--stage-case stage4_block_grating --case oblique --nedelec-degree 2 --visualization-degree 2 --period-x 50 --period-y 25 --air-height 130 --substrate-thickness 10 --grating-width-x 17 --grating-width-y 25 --grating-height 120 --incident-theta-deg 80 --incident-phi-deg 0 --polarization-kind s --stage4-boundary-model dtn_port --stage4-dtn-order-policy auto_propagating --no-diffraction-compute-modal-diagnostic"
for h in 5 3 2; do
  mpiexec -n 4 python -m src.runners.run_3d_cases $common_args --mesh-target-size "$h"
done

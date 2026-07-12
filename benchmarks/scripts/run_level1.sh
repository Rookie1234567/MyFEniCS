#!/bin/sh
set -eu

python -m compileall -q src benchmarks
python -m unittest discover -s src/test -p 'test_*.py'

python -m src.runners.run_cases \
  --formulation port_total --constraint-backend manual \
  --port-boundary-model dtn --port-dtn-assembly auxiliary \
  --polarization-type TM --nedelec-degree 1 --visualization-degree 1 \
  --period-x 10 --air-height 5 --substrate-thickness 5 \
  --grating-width 5 --grating-height 2 --lambda0 13.5 \
  --n-air 1 --n-substrate 1 --n-grating 1 --mesh-target-size 2 \
  --no-generate-png-plots --results-root benchmarks/artifacts/level1/2d_smoke

mpiexec -n 2 python -m src.runners.run_3d_cases \
  --stage-case stage1_airbox --case normal --nedelec-degree 1 \
  --visualization-degree 1 --period-x 10 --period-y 10 \
  --air-height 5 --substrate-thickness 5 --mesh-target-size 5 \
  --results-root benchmarks/artifacts/level1/3d_stage1

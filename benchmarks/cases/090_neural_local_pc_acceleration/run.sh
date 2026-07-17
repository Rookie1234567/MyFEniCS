#!/usr/bin/env sh
set -eu

exec /home/fenics/miniforge3/envs/fenics-ml/bin/python \
  -m benchmarks.run_neural_local_pc \
  --mode toy-smoke \
  --device "${NEURAL_DEVICE:-cuda:0}" \
  --artifact-root "${ARTIFACT_ROOT:-benchmarks/artifacts/cases/090/toy_smoke}"

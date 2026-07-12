#!/bin/sh
set -eu
mpiexec -n 4 python -m benchmarks.run_workstation_iterative --h-nm 5 --record benchmarks/records/workstation_p2_h5_mpi4.json
mpiexec -n 4 python -m benchmarks.run_workstation_iterative --h-nm 2 --record benchmarks/records/workstation_p2_h2_mpi4.json

#!/bin/sh
set -eu

python -m unittest src.test.test_22_condensed_dtn src.test.test_23_physical_slab_two_level
mpiexec -n 4 python -m unittest src.test.test_22_condensed_dtn src.test.test_23_physical_slab_two_level
python -m benchmarks.check_benchmarks

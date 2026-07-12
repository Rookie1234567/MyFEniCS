#!/bin/sh
set -eu
mpiexec -n 4 python -m unittest src.test.test_22_condensed_dtn src.test.test_23_physical_slab_two_level

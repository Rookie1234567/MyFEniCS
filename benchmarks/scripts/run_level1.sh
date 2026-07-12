#!/bin/sh
set -eu
python -m py_compile src/solvers/condensed_dtn.py src/solvers/physical_slab_two_level.py src/solvers/stage4_runtime.py benchmarks/run_workstation_iterative.py
python -m unittest src.test.test_22_condensed_dtn src.test.test_23_physical_slab_two_level

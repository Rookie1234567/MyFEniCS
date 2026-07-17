# Changed Files

- `src/solvers/local_slab_solver.py`: portable CSR and stable ILU/Jacobi/backend contract.
- `src/solvers/neural_local_pc.py`: frozen POD-MLP, checksum, safety, fallback and ILU+NN correction.
- `src/solvers/physical_slab_two_level.py`: opt-in operator/sample observers and local backend factory.
- `benchmarks/neural_pc/`: dataset, capture, GPU training and evaluation tools.
- `benchmarks/run_neural_local_pc.py`: reproducible toy runner.
- `benchmarks/run_workstation_iterative.py`: explicit capture/checkpoint/lane research flags.
- `src/test/test_31_neural_local_pc.py`: pure safety/action tests.
- `src/test/test_32_neural_slab_petsc_adapter.py`: owner-computes adapter test.
- `benchmarks/cases/090_neural_local_pc_acceleration/`: case contract/config/run entry.
- `docs/para_task001_neural_local_pc_acceleration/outcomes/`: current evidence and Gate decisions.
- `scripts/wsl_python_complex.sh`, `scripts/install_wsl_pycharm_wrapper.sh`: persistent complex FE interpreter with isolated complex MPC extension.
- `notes/quick_start/wsl_pycharm_fenics_gpu_guide.md`: Windows PyCharm WSL solver/trainer/MPI instructions.
- `src/test/test_26_documentation_contract.py`: Case090 documentation contract registration.

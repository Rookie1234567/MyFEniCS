# Merge Recommendation

Current decision: do not merge the neural runtime or claim solver acceleration. The branch is at `h5_numeric_pass_engineering_negative`: one-slab ILU+NN preserved true residual/RTA and reduced iterations by 0.813%, but solve/total time became 4.419x/2.888x baseline.

Potential selective-merge candidates are the local solver protocol, portable CSR/data schema, independent-run validation, bounded capture, checksum/fail-closed logic, telemetry, tests and WSL/PyCharm documentation. Checkpoints, datasets, the one-slab runtime profile and ordinary-default changes must not be merged.

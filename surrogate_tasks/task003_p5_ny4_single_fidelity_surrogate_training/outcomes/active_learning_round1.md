# Task003 active-learning Round 1

`ACTIVE_LEARNING_ROUND1_PLAN.json` is bound to candidate-pool tuple hash
`a9831ffc1055732660bee859382f623e8558560634d9ac98702cfe355ff09fcd`, frozen
feature B, and clean FEM baseline SHA
`10e3356ba8364286a452077f71d7e3b92ea24cd5`. The independent checker in
`benchmarks/cases/121_task003_active_learning_round1/checker.py` passed all
checks before FEM: exactly eight unique points, no training/validation/audit
near-duplicates, and coverage of low-grazing, cutoff, high-azimuth and
interior regimes.

The formal campaign used `S_PROD_FULL3D_STATIC_P5_H10_NY4`, route
`full3d_static_uniform_n1curl_p5_h10_ny4`, mesh `(6,4,14)`, MPI2/thread1 and
compact-surrogate output. The first attempt stopped before solving because
the sandbox exposed a read-only FEniCS JIT cache; this was an explained
environment failure, not a numerical Gate result. With XDG/MPL caches moved to
`/tmp`, the same point was retried and all eight points completed
`measured_pass`, with zero swap and complete cleanup.

The retry campaign manifest and raw artifacts are under the ignored
`benchmarks/artifacts/cases/121_task003_active_learning_round1_retry_cachefix`
directory; eight deterministic adapter records are retained under
`benchmarks/cases/121_task003_active_learning_round1/records/`.

No second or third active-learning round was started.

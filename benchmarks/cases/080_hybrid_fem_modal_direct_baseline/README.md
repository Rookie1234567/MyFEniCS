# Case080: Hybrid FEM-modal direct baseline

## Current status

```text
Phase 1 full-3D h5/h3 reference = complete
Phase 2 cross-section eigenproblem = clean MPI4 formal record complete
Phase 3 classification/biorthogonality = MPI4 research passed; clean record pending
Hybrid augmented/Schur direct = pending
ordinary default changed = false
```

This case is the canonical Task032 evidence bundle. It freezes the existing
full-3D direct reference and now contains the Phase 2 distributed cross-section
QEP and Phase 3 classification/biorthogonality implementation; it does not
claim that stable propagation, coupling or a Hybrid solve exists.

## 22 项合同

| 项目 | 值 |
|---|---|
| 1. ID | `080_hybrid_fem_modal_direct_baseline` |
| 2. 当前证明 | Phase 1 clean h5/h3 reference；Phase 2 clean mixed QEP；Phase 3 research Poynting/衰减分类、left/right Q' 双正交、近简并 block、正反 identity 和 angle tracking |
| 3. 尚不证明 | Phase 3 clean formal identity、稳定 100 nm 传播、接口耦合、augmented/Schur、一致性、截断收敛或内存收益 |
| 4. 几何 | 50 x 25 x 140 nm regular double-periodic cell；17 x 25 x 120 nm Si block |
| 5. 材料 | 13.5 nm Si，`0.999002304859+0.00182649365j` |
| 6. 入射 | theta=80 degrees、10 degrees grazing、phi=0、S polarization |
| 7. FE | p2 Nédélec；h5/h3 full-3D reference |
| 8. 边界 | double Floquet + auxiliary Fourier-DtN |
| 9. 外部 modal identity | 80 unknowns，top/bottom 各 40；不等于未来内部截面模式数 |
| 10. 域分解 | 中间 z=10--110 nm；匹配接口 z=10/110 nm |
| 11. solver | MPI4 MUMPS direct LU；Task032 不新增迭代法 |
| 12. reference planes | z=10/30/60/90/110 nm |
| 13. sample grid | periodic cell-centred 40 x 20 |
| 14. field dtype | PETSc/NumPy complex128 |
| 15. interface trace | z=10 从 +z cell，z=110 从 -z cell；均取中间区域侧 |
| 16. memory guard | frozen E/H payload 384000 bytes；fail closed above 64 MiB |
| 17. numeric Gate | true residual `<=1e-9`、absolute closure `<=1e-9` |
| 18. archive Gate | schema/shape/planes/dtype/sides + six SHA-256 identities |
| 19. provenance | Phase 1 clean `c468c728...`；Phase 2 clean `33211a4...`；image digest、command、host 与 UTC time |
| 20. heavy artifacts | `benchmarks/artifacts/cases/080/`，gitignored |
| 21. reference policy | h5 fast development；h3 primary；不宣称 h5--h3 mesh convergence |
| 22. ordinary default | 不改变；reference exporter 显式 opt-in |

## 物理问题

The run uses the current regular 50 x 25 nm double-periodic Si grating at
13.5 nm, theta=80 degrees from the normal (10 degrees grazing), phi=0, S
polarization, p2 Nédélec elements, 80 external Fourier-DtN unknowns and MPI4
MUMPS direct solve.  The middle modal region is z=10--110 nm.

## 参数说明

`config.json` freezes the physics, split and structured field request.
`expected/gates.json` freezes source/image identity, residual, closure, R/T/A,
archive and payload limits.  `expected.json` also states that h5--h3 grid
convergence is not claimed.

## 当前证据

The existing rank-local VTU/PVD files remain the full volume field.  The
opt-in NPZ contains complex128 E/H on z=10/30/60/90/110 nm and explicit x/y
tangential E/H traces at z=10/110.  z=10 uses the +z cell and z=110 the -z
cell, so both interface traces are taken from the middle region.

Heavy artifacts stay below ignored `benchmarks/artifacts/cases/080/`.  The two
JSON records in `records/` retain clean commit, command, image digest, material,
residual, R/T/A, closure, schema and artifact hashes.

The clean h5 run has 44,698 FE DoF, residual `9.733991e-12` and
`R/T/A=0.0890216029/0.4425882787/0.4683901184`.  The clean h3 run has 198,438
FE DoF, residual `9.923386e-12` and
`R/T/A=0.0046130314/0.5836533572/0.4117336114`.  Both closure errors are below
`1.3e-13`; h3 agrees with the historical direct record to about `2.3e-14` or
better.

The Phase 2 clean MPI4 record uses source
`33211a4ac6d4f6717351197a93c506e1adec609f`. Air h5/h3/h2/h1.5 beta
errors decrease strictly as `29.5323%/5.58859%/1.12629%/0.454640%`.
The lossy h2 beta is `0.0773232064+0.00511171935j 1/nm` with `1.19656%`
analytic error; the current Stage4 x/y material at h3 gives
`0.0753551902+0.00178364869j 1/nm`. Across selected modes the maximum QEP
relative residual is `1.8177e-15`, reciprocal-pair error is `7.50e-16`, and
electric-L2 norm error is `4.44e-16`. The automatic benchmark checker passes
277/277 gates.

## CLI 或测试

Inside the qualified complex128 DOLFINx image:

```bash
LEVEL=h5 sh benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run.sh
LEVEL=h3 sh benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run.sh
mpiexec -n 4 python -m unittest -v src.test.test_32_task032_cross_section_qep
mpiexec -n 4 python -m benchmarks.run_task032_phase2_qep --verified-clean-sha <full-sha>
VERIFIED_CLEAN_SHA=<full-sha> sh benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase2.sh
```

The formal host command mounts the repository at `/work` in
`myfenics-stage4:task28` and executes the same inner command.  The formal Phase
1 source commit is `c468c728a4e71d4e532002c6d001ad7d0e9cd163`; the formal Phase
2 source commit is `33211a4ac6d4f6717351197a93c506e1adec609f`.

Phase 3 research uses `run_phase3.sh` for the eventual clean record. The dirty
MPI4 h10 rehearsal passed air, homogeneous lossy and current Stage4 x/y
materials, air reciprocal pairing and 80 to 79.8 degree tracking. h10 is a
classification contract; it is not the beta-accuracy or final Hybrid mesh.

## 代码路径与理论

The call chain is `src/main.py -> run_3d_cases -> Stage-4 direct solve ->
postprocess_3d -> full3d_reference`.  The future consumer chain is
`cross-section eigenmodes -> modal trace projection -> augmented/Schur direct
solve -> Case080 comparison`.  The mathematical split and field comparison
conventions are documented in
`notes/theory/hybrid_fem_modal_domain_decomposition.md`.

## 结果解释

h5 is intentionally a fast development scale.  Its R/T/A differs strongly
from h3, so Case080 does not claim h5--h3 mesh convergence.  The h3 values
match the pre-Task032 direct h3 record and are the primary full-3D reference;
h5 remains useful for fast Hybrid implementation and truncation loops.

The internal `total_peak_rss_mb` field is the sum of per-rank historical peaks,
not a simultaneous memory measurement.  It is retained only as an upper-bound
diagnostic and is not the Task032 memory authority.

The Phase 2 record likewise reports per-rank process-lifetime historical peaks
(maximum `231.277 MB`), not simultaneous total memory. No final Hybrid memory
claim is made before external stage sampling.

## PyCharm

Use the existing Docker interpreter and run `src/main.py` with the argument
list from `run.sh`.  A single-rank IDE debug run is allowed for debugging only;
formal Case080 reference identity requires MPI4.

## 限制

This is numerical reference evidence for the frozen current model, not
experimental validation. Phase 3 now supplies a research Poynting/Q'
biorthogonal basis and near-degenerate subspace tracking, but its clean formal
record is still pending. Stable propagation, interface coupling and Hybrid
direct solvers remain pending. It does not add h/p adaptivity, a new iterative
solver, nonmatching interfaces, material scans or shorter wavelengths.

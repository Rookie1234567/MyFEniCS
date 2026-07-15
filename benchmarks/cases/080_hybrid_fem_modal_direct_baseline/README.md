# Case080: Hybrid FEM-modal direct baseline

## Current status

```text
Phase 1 full-3D h5/h3 reference = complete
Phase 2 cross-section eigenproblem = clean MPI4 formal record complete
Phase 3 classification/biorthogonality = clean MPI4 formal record complete
Phase 4 stable two-sided propagation = clean MPI4 formal record complete
Phase 5 matched trace/projection = clean MPI4 formal record complete
Phase 6e real-QEP h5/M6 augmented integration = clean-source MPI4 integration record complete
Phase 6f--9 h5/h3 physical field, M160 funnel and Modal-Schur = clean formal records pass
Phase 10 six-path memory forensics = clean formal records pass, zero swap
parameter entry S/P smoke = 30/30 pass
h2 = locked by mandatory two-method prediction gate; not run
classification = hybrid_direct_engineering_success
checker = 302/302 passed
ordinary default changed = false
```

This case is the canonical Task032 evidence bundle. It freezes the existing
full-3D direct reference and now contains the Phase 2 distributed cross-section
QEP, Phase 3 classification/biorthogonality, Phase 4 stable-propagation clean
and Phase 5 matched-trace/projection clean records. Final records add h5/h3
M120/M160 physical fields, volume absorption, mode funnels, augmented/Schur
equivalence, six independent memory paths, parameter smoke and the fail-closed
h2 decision.

## 22 项合同

| 项目 | 值 |
|---|---|
| 1. ID | `080_hybrid_fem_modal_direct_baseline` |
| 2. 当前证明 | Phase 1--10：clean h5/h3 reference、QEP/mode/propagation/trace、h5/h3 M160 field/RTA/absorption、Modal-Schur、截断漏斗、参数 smoke 与六路径内存 |
| 3. 尚不证明 | h5--h3 网格收敛、整个 1--10° production qualification、h2 实测或 h2 strong-memory success |
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
| 17. numeric Gate | full residual、interface E/H、volume absorption、selected planes、R/T/A、order funnel、augmented/Schur equivalence |
| 18. archive Gate | schema/shape/planes/dtype/sides + six SHA-256 identities |
| 19. provenance | Phase 1--6 历史 clean SHA；final fields `7357744...`；memory `793354a...`；实际 image ID、command、host 与 UTC time |
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

Heavy artifacts stay below ignored `benchmarks/artifacts/cases/080/`.
Lightweight JSON records in `records/` retain clean commit, command, image digest, material,
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
VERIFIED_CLEAN_SHA=<full-sha> sh benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase3.sh
VERIFIED_CLEAN_SHA=<full-sha> sh benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase4.sh
mpiexec -n 4 python -m unittest -v src.test.test_35_task032_modal_trace_projection
VERIFIED_CLEAN_SHA=<full-sha> sh benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase5.sh
VERIFIED_CLEAN_SHA=<full-sha> sh benchmarks/cases/080_hybrid_fem_modal_direct_baseline/run_phase6.sh
mpiexec -n 4 python -m benchmarks.run_task032_phase6_augmented --verified-clean-sha <full-sha> --compare-modal-schur --h-nm 3 --requested-modes 160 --candidate-modes 320 --output <record.json>
python -m benchmarks.run_task032_phase8_funnel --records <m120.json> <m160.json> --output <funnel.json>
python benchmarks/check_benchmarks.py --no-write
```

The formal host command mounts the repository at `/work` in
`myfenics-stage4:task28` and executes the same inner command.  The formal Phase
1 source commit is `c468c728a4e71d4e532002c6d001ad7d0e9cd163`; the formal Phase
2 source commit is `33211a4ac6d4f6717351197a93c506e1adec609f`.

The formal Phase 3 record uses clean source
`72dca66b70515bcf6ccef239005afa43028df72b`. MPI4 h10 passes air,
homogeneous lossy and current Stage4 x/y materials, air reciprocal pairing and
80 to 79.8 degree tracking. Air/lossy biorthogonality errors are about `1e-15`,
the patterned error is `2.46e-10`, and the maximum tracking principal angle is
`0.005918 rad`. The full Case080 checker passes 282/282 gates. h10 is a
classification contract; it is not the beta-accuracy or final Hybrid mesh.

The formal Phase 4 record uses clean source
`9206e9c964db387448551cdefdc88081ef705441` and the exact Phase 3 record hash.
MPI4 validates a 100 nm reflection-free two-port block for air, homogeneous
lossy and current Stage4 modes. The maximum composition error is `9.43e-16`,
air independently solved reciprocity beta/factor errors are
`3.64e-16/2.78e-15`, and all directed factor magnitudes are at most one.
Strong evanescence underflows to zero without overflow; growing and ambiguous
branches fail closed. The full Case080 checker passes 286/286 gates.

The formal Phase 5 record uses clean source
`b565ac4610dee08a2d313060b7cb26b48145370d`. MPI4 validates matched p2
Nédélec traces at z=10/110 nm, explicit opposite local/modal normals, Stage4
left/right coefficient round trip and an air near-degenerate trace subspace.
There are 18 facets and 162 trace DoF per interface. The maximum affine trace
error is `6.62e-15`; Gram condition is `30.4995`; coefficient/reconstruction
errors are `3.78e-16/4.69e-16`. Only sparse trace mass, distributed mode
columns and a 2x2 Gram block are stored; no dense interface square or full
field/mode gather is formed. The full Case080 checker passes 290/290 gates.

The Phase 6 clean-source integration record uses
`5c1f12e610dd8c6040389c44c31584ab7fba66cd`. MPI4 delivers six modes per
direction from raw SLEPc counts 8/8, uses three near-degenerate block inverses,
and solves a `13744 x 13744` MPI AIJ with MUMPS. The true residual is
`1.8590e-12`; combined interface-E and bottom/top variational FE-modal traction
residuals are `1.3090e-13` and `2.6770e-12/1.5094e-12`. External
`R/T/A=0.0890167705/0.4425771168/0.4684061127`; h5 Hybrid-minus-full-3D deltas
remain below `2e-5`. All 10 runner gates and the full Case080 `294/294` checker
pass. This M6 record remains an intentionally historical integration boundary;
the final M120/M160 records below provide the physical-field qualification.

Final clean h5/h3 M160 records use source `735774473e54415ab5393f2d2cbc9c8d7d2a24e6`.
Both M120->M160 funnels pass the strong total and significant-order gates. h3
`Hybrid-full3D R/T/A` deltas are
`-2.1150e-7/-2.4170e-6/+2.6285e-6`; selected-plane field errors remain below
`7.80e-4`, and volume absorption differs by `2.6285e-6`. Augmented and Modal-Schur
agree below their `1e-9` algebra gates without dense interface-square storage.

Six clean memory records use source `793354af0ac72cbfe1c6eb1030b2438afe10c101`.
h3 augmented/Schur-fast/Schur-minimal peaks are `3.853/3.998/3.224 GiB`, all
zero swap. The memory-minimal lifecycle reduces h3 worker RSS by `16.31%`.
Two independent h2 predictions still exceed the 4/5 GiB unlock gates, so h2
was not run. The final checker passes `302/302`.

## 代码路径与理论

The reference call chain is `src/main.py -> run_3d_cases -> Stage-4 direct solve ->
postprocess_3d -> full3d_reference`.  The Hybrid chain is now
`cross-section eigenmodes -> modal trace projection -> augmented or Modal-Schur
direct -> physical E/H and absorption -> external R/T/A and diffraction output`.
The mathematical split and field comparison
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
(maximum `231.277 MB`), not simultaneous total memory. Final memory authority
comes only from the six external stage-sampled records summarized above.

## PyCharm

Use the existing Docker interpreter and run `src/main.py` with the argument
list from `run.sh`.  A single-rank IDE debug run is allowed for debugging only;
formal Case080 reference identity requires MPI4.

## 限制

This is numerical reference evidence for the frozen current model, not
experimental validation. Phase 3 supplies a clean-recorded Poynting/Q'
biorthogonal basis and near-degenerate subspace tracking. Phase 4 supplies a
clean-recorded stable two-port propagation block, and Phase 5 supplies a
clean-recorded matched-interface trace/projection block. The h5/h3 M160 field,
truncation, Schur and memory evidence is complete. h2 is deliberately locked by
the mandatory prediction gate, so no h2 measured peak or strong-memory
classification is claimed. Task032 does not add h/p adaptivity, a new iterative solver,
nonmatching interfaces, material scans or shorter wavelengths.

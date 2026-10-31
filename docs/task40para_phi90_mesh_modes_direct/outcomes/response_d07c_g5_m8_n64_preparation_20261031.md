# D07C-G5 M8/N64：静态准备与主审包

## 范围与身份

G5 是用户授权的 0.7 nm p6 凝聚直接法候选：以 D07C-G3 为父，x/z 轴逐位保持，仅细化 y 轴。当前记录用于源码与启动包审核；本次准备没有创建网格、carrier、矩阵、factor 或 FE solve，也没有执行 fresh 或提交 systemd 服务。

| 项目 | 冻结候选 |
|---|---|
| model / run | `si_block_phi90_50x50_17x20_h120` / `task40para_phi90_0p7_D07C_G5_M8_N64_p6_direct_v1` |
| profile | `task40para_phi90_0p7_D07C_G5_M8_N64_p6_direct_v1` |
| input SHA-256 | `64432c6556e699287a3d0d23ed30f7947d406b0874c2f43c100f91c81529701c` |
| physical SHA-256 | `130186c779bf7f31901638365946a797ec2a448b761dd795035bbda0de156213` |
| formal resolved SHA-256 | `53682d695d532ccb3fc39ad1389bffc2f32da3a278b65f475be34b58dfe1bff6` |
| expected output parent | `results/si_block_phi90_50x50_17x20_h120/task40para_phi90_0p7_D07C_G5_M8_N64_p6_direct_v1__full3d_direct__mpi1__Mna` (absent during preparation) |

The formal hashes above came from `load_and_resolve` with the real expected output parent. They are not test-temp resolved hashes. The source commit and the final source-file/package hashes are in the accompanying external launch-review package.

## Mesh and finite operator

The production axis planner gives `[6,167,8]` = 8,016 hexahedral cells. x/z are exactly the G3 axes; y alone changes. Segment counts are x `2/2/2`, y `50/67/50`, z `2/4/2`. The y steps are 0.3 nm in the two outer slabs and 20/67 = 0.298507462686… nm in the grating slab. The maximum static cell aspect ratio is about 100.5; the minimum static cell volume is about 12.3134 nm³. These are axis-derived planning values, not live mesh/Jacobian QA.

| Axis | Count | SHA-256 of little-endian f64 coordinates | Relationship |
|---|---:|---|---|
| x | 6 | `bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361` | unchanged from G3 |
| y | 167 | `74af9a44ba3f37d6dd9f473680c404d70773da2031fdd788db9f61d026e6f24a` | G5-only refinement |
| z | 8 | `b603d8672fe0097d827859e5b4cab92ad139ba71427d4f75fa421bbd8bc25501` | unchanged from G3 |

Independent interval-midpoint classification predicts air/substrate/grating tags `5476/2004/536`. The focused test checks the actual planner coordinate arrays and fake midpoint tags; final actual mesh/tag/Jacobian evidence must still come from the standard run.

The finite signed rectangle remains `m=-8…8, n=-64…1`, top/bottom s/p: 4,488 modes, production SHA `e4cef2ecadaab2563a46592dfe31df04aa47bc113f3a69e1ac0ecd70cebf2ef0`, with 4,360 propagating and 4,426 power-carrying modes. Surface quadrature is q81; q161 remains an independent reference check only. Volume quadrature is q15/default from the production FFCx/Basix metadata. Sparse assembly uses `scale_homogeneous_relative_only_v1` at `1e-13`.

The primary G5 mesh comparison is G3 M8/N64, which uses the same signed keys and differs in y mesh only. G3 M8/N96 is separate finite-window context: the saved G3 N64→N96 comparison passed all three gates, but comparing G5 N64 directly with N96 would change both mesh and mode window. The retained comparison JSON SHA is `03c07e8b829405e90fa582dd5cfdb01c7b35a0b8945778720c41e3ffd74e5a3d`; no NPZ, VTU, or resource stream was reread for this preparation.

The candidate still excludes high-`|m|` propagating modes and is not full DtN. Keep `FULL_DTN_NOT_VERIFIED` and canonical sidewall `NOT_MEASURED`.

## Gates and execution contract

Single-run gates remain condensed residual `<=1e-9`, active-rectangle A6 `<=1e-6`, and energy balance/volume `<=1e-5`, with one symbolic/numeric factor and at most two same-factor correction solves. The comparison gates remain global R/T/A_balance/A_volume absolute delta `<=1e-5`; every signed and power-carrying channel R/T absolute delta `<=1e-6`; boundary complex amplitudes and same-coordinate complex E/H relative L2 `<=1e-4`, without phase fitting.

For G5 only, large VTX/VTU/PVD visualization files are disabled. `export_fields`, direct field recovery, energy metrics, modal outputs, and the explicit reference-sample NPZ remain enabled. This is an output-storage policy; it does not change the operator or solve and does not promise a lower peak RSS.

The launch package retains the Task40 host-available 64 GiB floor, no fixed RSS cap, swap observe-only, PSS/USS disabled, CPU9 parent / CPU24 worker, MPI1/math1, worker NUMA interleave 0-1, canonical shared heavy lock, and independent systemd `Restart=no`. Fresh admission and live resource checks are still required. This preparation authorizes no launch by itself; the run waits for main package review and its exact fresh PASS.

## Evidence

- Static plan and formal loader/mode identities: [G5 static plan](records/d07c_g5_m8_n64_static_case_plan_v1.json), SHA-256 `9f04273f52e73dc53245b9b3cc0ae388aa1fd6f28eb8271c5ee91586bf6721d7`.
- Focused G5 test: `5 passed`; G5 plus existing D07C mode, mesh, host-floor, refinement, and manifest-worker tests: `31 passed`.
- New test Ruff, changed-file compileall, and `git diff --check` passed. Full-file Ruff still reports pre-existing diagnostics in legacy modules; diagnostic counts match the baseline after accounting for line shifts.
- No FE run, mesh construction, factorization, or systemd submission occurred during G5 preparation.

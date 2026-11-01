# D07C-G6 M8/N64：静态准备与主审包

## 范围与身份

G6 是 G5 完成后新授权的 y-only 网格加密候选。它保留 G5 的 x/z 轴、材料、入射、p6 凝聚直接法和 M8/N64 有限模态窗口，只将完整 y 周期细化到 0.25 nm。本记录用于源码、输入、live mesh QA 和启动契约审核；本次实际构建了临时 QA 网格，但没有启动 FE assembly、carrier、矩阵、factor 或 solve，也没有执行 fresh 或提交服务。

| 项目 | 冻结候选 |
|---|---|
| model / run | `si_block_phi90_50x50_17x20_h120` / `task40para_phi90_0p7_D07C_G6_M8_N64_p6_direct_v1` |
| profile | `task40para_phi90_0p7_D07C_G6_M8_N64_p6_direct_v1` |
| input SHA-256 | `19af7675364dae2c86cf1fa7ad05506ea51dc5f23cd1829d31adeb9b48bc15b1` |
| physical SHA-256 | `6c2b170e4e2b7cc72628f43fb5a249d0c4305b3d7eadfa3f27d57c2589785387` |
| formal resolved SHA-256 | `28691da53d1bd791e6a8fc322a84b75c4026291ad441f7a675aa70f24de30ee7` |
| expected output parent | `results/si_block_phi90_50x50_17x20_h120/task40para_phi90_0p7_D07C_G6_M8_N64_p6_direct_v1__full3d_direct__mpi1__Mna` (absent during preparation) |
| code baseline | `6232ea6daacea31a83867dd7725823ffcefdc1fb`; final clean G6 source commit is bound by the external review package |

Formal hashes came from the production `load_and_resolve` path with the G6 result parent. The physical hash includes the discretization section, so it changes with the y-axis definition; the G6 regression separately verifies that normalized geometry, materials, incidence, boundary, method, execution, and output are unchanged from G5. The machine record also contains the parent commit, per-file SHA-256 values, source-file bundle SHA-256, and the representative worker argv template.

## Mesh 与有限模态窗口

The production axis planner gives `[6,200,8]` = 9,600 hexahedral cells. G6 matches G5 x/z exactly and changes y alone. The y axis has 201 coordinates over 0–50 nm with an exact 0.25 nm step. The primary mesh comparison is G5 M8/N64; G3 M8/N96 remains separate finite-window context.

| Axis | Cells | SHA-256 of little-endian f64 coordinates | Relationship |
|---|---:|---|---|
| x | 6 | `bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361` | unchanged from G5 |
| y | 200 | `b7422d323609a23b128a49be40ae337c796fa78b7b9abc36d53b7f8ef1a815aa` | G6 refinement; 0.25 nm step |
| z | 8 | `b603d8672fe0097d827859e5b4cab92ad139ba71427d4f75fa421bbd8bc25501` | unchanged from G5 |

The real DOLFINx mesh builder and `_task40_d07c_mesh_evidence` both passed: actual axes match the frozen plan, the cell count is 9,600, and material tags are air/substrate/grating `6560/2400/640`. The temporary builder output contains XDMF/HDF5 and its partition note; no VTK/VTU/VTX/PVD files were written. The static plan reports a maximum cell aspect ratio of 120 and minimum cell volume 10.3125 nm³; these planner values are distinct from the live axes/tag check.

The production inventory remains `m=-8…8, n=-64…1`: 4,488 modes, 4,360 propagating, 4,426 power-carrying, SHA-256 `e4cef2ecadaab2563a46592dfe31df04aa47bc113f3a69e1ac0ecd70cebf2ef0`. Surface quadrature is q81; q161 is an independent reference only. Volume quadrature is q15/default. Sparse assembly uses `scale_homogeneous_relative_only_v1` at `1e-13`. This finite signed window excludes other auto-propagating orders; keep `FULL_DTN_NOT_VERIFIED` and canonical sidewall `NOT_MEASURED`.

## Output 与资源契约

The input retains full field recovery, energy metrics, modal amplitudes, diffraction orders, and the full3d reference-sample NPZ. It disables large VTX/VTU/PVD visualization output; this is a storage choice and does not imply lower peak RSS.

The production profile enforces a 64 GiB host-available floor, no fixed RSS cap, swap observe-only, PSS/USS sampling disabled, MPI1, one math thread, and NUMA interleave across nodes 0–1. The G6 observational-neighbor route is bound to the exact G6 profile/run and a SHA-256 scope. It has G6-specific member locks, one-shot reservation, attempt cache, and worker-side cache verification. CPU assignment samples load and selects separate low-load physical cores for the supervisor and worker; ownership is non-exclusive and there are no fixed CPU IDs.

Completed G5 is a resource observation only: process-tree peak RSS `646,509,973,504` bytes, elapsed `53,161.7188` seconds, process-tree peak swap 0. This does not set a G6 cap or produce a G6 memory estimate; the 19.76% cell-count increase must not be used as a linear RSS extrapolation.

The entrypoint uses the qualified Task40 PORD64 activation and the shared interpreter resolved by that activation. Its observed ABI is Python `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/.venv/bin/python` (real path `/usr/bin/python3.12`), PETSc 3.19.6 with complex128 scalars and 8-byte integers, and DOLFINx/Basix 0.10.0. The runtime command template is:

```text
source /home/fenics/Projects/Maxwell3D-Lab/task40_d07c_g6_exec/scripts/activate_task40_phi90_pord64.sh
exec /home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/.venv/bin/python /home/fenics/Projects/Maxwell3D-Lab/task40_d07c_g6_exec/scripts/run_case.py /home/fenics/Projects/Maxwell3D-Lab/task40_d07c_g6_exec/input/task40para_phi90_mesh_modes_direct/d07c_g6_m8_nminus64_to1_p6_direct.dat
```

The inner worker route is MPI1 → `numactl --interleave=0,1` → `taskset -c <sampled worker CPU>` → the same qualified interpreter. The final package binds `--expected-source-sha` to the exact clean G6 freeze commit; the worker run directory and sampled CPU are selected at launch time. No fresh or solver command has been executed.

## Gates 与验证

Single-run gates remain condensed residual `<=1e-9`, active-rectangle A6 `<=1e-6`, and energy balance/volume `<=1e-5`. The comparison gates remain global R/T/A absolute delta `<=1e-5`; each signed and power-carrying channel R/T absolute delta `<=1e-6`; boundary complex amplitudes and same-coordinate complex E/H relative L2 `<=1e-4`, without phase fitting.

- G5 observational-admission regression, G5 output contract, and G6 contract/live mesh: `17 passed in 4.13s`.
- The production mode inventory passed with the exact 4,488-mode SHA and expected propagating/power-carrying counts.
- Changed Python modules passed `compileall`; the new G6 contract test and observational join passed Ruff. The Task38 worker passed Ruff with its pre-existing `BLE001` broad-boundary exception ignored; changed files passed the E4/E7/E9/F checks and `git diff --check`.
- No full solver, FE matrix assembly, carrier, factorization, or systemd submission was started. G6 still needs the exact package main PASS and a new full fresh PASS before any run.

The machine-readable plan is [G6 static plan](records/d07c_g6_m8_n64_static_case_plan_v1.json), SHA-256 `625096f857465dd9f896c3ca122cf66e1812f7054b52f15cf1a860142f2dfdf7`.

# Task035b outcomes summary

## 最终状态

```text
status = PARTIAL_WITH_CONTROLLED_NEGATIVES
geometry = Task034 fixed rectangular block grating only
formal_MPI = 8
ordinary_default_changed = false
irregular_geometry = out_of_scope_by_user / not_run / not_a_completion_gate
hybrid_eligible_candidate_count = 0
selective_master_merge = completed_at_1fb144d3ca50208c22b5f0733e140bfac8d9c47c
current_branch = codex/20260726-task35b-high-order-local-hp-resource-envelope
hybrid_static_H1_A = controlled_negative
```

Task035b 完成了同网格 p4/p5/p6 资格化、entity DoF 分解、exact
assembly-time cell condensation、MUMPS 生命周期与 exact preallocation
优化、multi-goal DWR、252-cell physical smoothness signal、classifier v3、
真实 regionwise physical row reduction、tetra h-vs-p 顺序竞争，以及
Review V2 要求的 cold/warm setup、MPI1/2/4/8 direct memory 和三条
assembled iterative screen。

工程主线取得明确正结果：消除完整高阶矩阵、inactive rows、重复 tensor、
preallocation 浪费和 factor 生命周期后，rows、NNZ、factor、peak memory
与时间全部下降。Review V1 又完成了 12 通道 reference v1、16 个独立
Hermitian adjoint、mesh/topology、phase、trace 与 DtN/port 根因假设判别
和最小方向性恢复；Review V2 进一步完成了 setup cache、direct rank
memory ledger、assembled iterative negatives 与 selective-trace
fixture/correctness wiring。

科学主线仍没有完整 same-error positive candidate。预算内最强点仍是
fixed p5-trace/p6-interior h13 directional-z 的 89,740 DoF、10/12
power、10/12 complex amplitude，但仍未满足 12/12 + 12/12。随后两个
有界 z-node 判别点 h13 top2 redistribution 与 h14 exact-reverse 的实际
结果分别只有 8/12 + 8/12 和 7/12 + 8/12；任何先验投影都没有被写成
实测。因此按合同 Hybrid eligible 仍为 0，Full3D–Hybrid closure、M funnel
和 0.7 nm / 2 TiB resource model v3 均未运行。

Review V3 随后完成 Task035/035b 文件级选择性合并，并在新分支把静态
凝聚接入 Task032/033 Hybrid。p2/h5 H1-A 证明 static Full3D 与 standard
Full3D、static Hybrid 与 standard Hybrid 均达到逐通道 12/12 + 12/12
等价，M120→M160 也已收敛；但 static Full3D ↔ static Hybrid 只有
Task033 相对口径的 **3/12 power + 2/12 amplitude**，strict absolute
audit 为 **2/12 + 2/12**。这是新的 Hybrid 同离散 numerical Gate，
不是静态凝聚误差。Review V3 明确规定 H1-B 只在 H1-A 全通过后运行，
所以 p2/h3、高阶典型点、h13 seed 与 adaptive Hybrid 均没有启动。

## 权威基线

h10 structured hexa 为 `(6,3,14)`、252 cells。最新 MPI8
exact-preallocation/projection record：

| degree | FE DoF | active rows | matrix/factor NNZ | build/setup/solve | R00 / R / T / Aclosure | residual |
|---:|---:|---:|---:|---:|---:|---:|
| p4 | 53,084 | 21,824 | 8,184,464 / 40,151,936 | 35.64 / 13.36 / — s | 0.001872161 / 0.001882317 / 0.596619520 / 0.401498163 | `2.35e-11` |
| p5 | 101,815 | 35,000 | 20,140,928 / 101,062,900 | 24.72 / 36.48 / 0.077 s | 0.000785714 / 0.000794886 / 0.602483954 / 0.396721160 | `1.25e-11` |
| p6 | 173,802 | 51,272 | 41,989,040 / 202,441,352 | 102.32 / 102.54 / 0.167 s | 0.000753761 / 0.000762881 / 0.602701634 / 0.396535485 | `1.26e-11` |

p6/h10 是 best available global-p discrete reference，不是 continuum
reference。COMSOL independent direct-solver trend center 为
`R00≈0.000752895 / R≈0.000762014 / T≈0.6027075 /
Aclosure≈0.3965305`，只用于跨软件趋势核验。

## 高阶内存与装配

| path | active rows | matrix NNZ | factor NNZ | peak | conclusion |
|---|---:|---:|---:|---:|---|
| historical full p6/h10 | 173,882 | 210,353,120 | 386,625,292 | 35.024 GiB | full-matrix control |
| post-assembly p6 Schur | 60,482 | 52,058,162 | 243,270,308 | 29.212 GiB | numerical pass；生命周期重叠 |
| assembly-time Schur + factor retain | 51,272 | 41,989,040 | 205,445,192 | 16.998 GiB | engineering positive |
| release without heap trim | 51,272 | 41,989,040 | 202,763,336 | 16.351 GiB | engineering positive |
| release + heap trim | 51,272 | 41,989,040 | 211,651,232 | 15.964 GiB | isolated resource authority |
| latest dedup/preallocated projection pair p6 | 51,272 | 41,989,040 | 202,441,352 | pair 19.977 GiB | build 102.32 s |

post-assembly prototype 降 rows 但仍保留 full matrix 和高 Schur fill，因此
memory 只下降 16.6%。最终 assembly-time path 不再分配完整矩阵；factor
release + `malloc_trim` 使 MUMPS 峰值不再与后处理叠加。latest projection
pair 相对旧 assembly-time pair 从 1202.85 s 降到 324.78 s，核心收益来自
tensor reuse 与 exact preallocation，而非放宽数值 Gate。

ordinary default 始终未修改；这些均为 opt-in research path。

### Review V2 setup-only authority

下表的 `non-KSP build` 是与 KSP 区间互斥的总 build envelope；它不是
outer wall time。其内部 Python/function-space/tensor/Aii/Schur/
preallocation/insertion/DtN phase clocks 允许嵌套，不能相加或直接换算成
互斥占比。`common solver`、MUMPS symbolic+numeric、backsolve、residual
和 postprocess 另行计时。当前已获得完整 inclusive phase ledger，但
Review V2 所要求的内部互斥 phase-share 仍为 `partial_not_authoritative`。
cold 为 `read_write` 重建/写入，warm 为同一 identity 下的 `read_only`
命中；两者都不是 accuracy candidate，也不能单独获得 12-channel 或
Hybrid credit。

| setup-only pair | DoF / rows | matrix/factor NNZ | non-KSP build cold/warm | common solver cold/warm | MUMPS setup cold/warm | peak cold/warm | true residual cold/warm |
|---|---:|---:|---:|---:|---:|---:|---:|
| h15 canonical orientation | 74,890 / 16,880 | 9,196,772 / 26,555,200 | 19.242 / 6.141 s | 37.595 / 19.489 s | 5.939 / 6.164 s | 4.602 / 4.453 GiB | `8.10e-12` / `1.28e-11` |
| h13 canonical orientation | 89,740 / 20,120 | 11,014,172 / 35,746,600 | 19.410 / 6.696 s | 45.568 / 26.899 s | 13.421 / 12.834 s | 5.030 / 5.016 GiB | `3.94e-12` / `5.51e-12` |

h15 cold non-KSP build 相对 Review V2 的 61.61 s authority 为
`3.2019x` 加速，达到至少 2x 和 25–30 s 优选目标；warm build 也低于
10 s。h13 在只剩 260 DoF 预算余量的真实最佳 accuracy 网格上仍达到
19.410/6.696 s，但 factor NNZ 相对 h15 增长 `1.346x`，MUMPS numeric
成本并没有随 rows/NNZ 线性增长。warm cache 复用消除了 tensor、Aii 和
local-Schur 重建，却不会消除每个新数值系统仍需执行的 MUMPS numeric
factorization。

权威记录分别为：

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v2.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h13_canonical_orientation_symbolic_numeric_cold_warm_mpi8_v1.json`

### Review V2 direct memory rank study

冻结 h15、74,890 Full3D-equivalent DoF、16,880 active rows 和
9,195,812 used NNZ 后，cold direct MPI rank study 为：

| MPI | process-tree RSS peak | rank PSS sum | rank USS sum | factor NNZ | common solver | MUMPS symbolic+numeric | true residual |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1.295 GiB | 1.257 GiB | 1.243 GiB | 26,854,000 | 76.007 s | 29.969 s | `5.12e-12` |
| 2 | 2.158 GiB | 2.013 GiB | 1.918 GiB | 28,507,400 | 74.913 s | 19.437 s | `1.37e-11` |
| 4 | 3.100 GiB | 2.723 GiB | 2.612 GiB | 26,575,000 | 61.849 s | 12.400 s | `4.96e-12` |
| 8 | 4.711 GiB | 3.876 GiB | 3.758 GiB | 27,916,600 | 53.901 s | 6.527 s | `7.41e-12` |

四点均无 swap，且 R/T 与 operator identity 闭合。MPI1 是本 rank study
最低实测 direct process-tree RSS，MPI8 是最快 common-solver 点。历史
5.8–6.4 GiB 因而不是该 condensed 系统的内存下限；但 1.295 GiB 也只是
同一 source/cache/profile 下的最低实测 direct 点，不是理论下限，更不是
accuracy-qualified factor-free floor。solve 后出现的 50 threads/rank 位于
solver release 之后的 PyVista/VTK/TBB postprocess pool；MUMPS 阶段仍是
预期的约 3 threads/rank。
CPU affinity 与 MUMPS ordering 在这批 rank records 中未记录，因此 rank
study 对这两项的资格化状态为 `partial_not_recorded`。

权威记录为：

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_direct_mpi1_2_4_8_resource_floor_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_memory_floor_factor_inventory_ledger_v2.json`

## 规则几何压缩候选

| candidate | DoF / rows | matrix/factor NNZ | peak | scalar/vector + field | significant power/amplitude | decision |
|---|---:|---:|---:|---|---|---|
| global p6/h15 | 84,492 / 24,704 | 19,207,136 / 59,616,320 | 12.000 GiB pair | pass | 6/12；8/12 | controlled negative |
| fixed p5-trace/p6-interior h15 | 74,890 / 16,880 | 9,195,812 / 27,916,600 | 5.803 GiB | pass | 6/12；7/12 | controlled negative |
| fixed h14 directional-z | 82,315 / 18,500 | 10,104,512 / 31,347,000 | 6.376 GiB | pass | 7/12；9/12 | positive z signal，仍 negative |
| fixed h13 directional-z | 89,740 / 20,120 | 11,013,212 / 36,273,200 | 6.411 GiB | pass | 10/12；10/12 | best budget-in，仍 negative |
| h13 top2 z redistribution | 89,740 / 20,120 | 11,013,212 / 36,273,200 | 5.886 GiB | pass | 8/12；8/12 | bounded z-node controlled negative |
| h14 exact-reverse of h13 top2 | 82,315 / 18,500 | 10,104,512 / 32,338,600 | 5.958 GiB | pass | 7/12；8/12 | bounded reverse controlled negative；z-node lane closed |
| fixed h15 x-only | 87,195 / 19,680 | 10,728,434 / 33,056,800 | 6.590 GiB | pass | 5/12；6/12 | controlled negative |
| h14 R5-slab bisect | 89,740 / 20,120 | 11,013,212 / 36,273,200 | 6.463 GiB | pass | 5/12；9/12 | count regression；预先指定 R5-slab lane closed |
| global p6/h14 discriminator | 92,850 / 27,080 | 21,110,096 / 67,325,792 | 12.587 GiB pair | pass | 9/12；12/12 | diagnostic only；over cap 2,850 |
| p4-trace p4/p6-interior h10 | 88,994 / 21,824 | 8,184,464 / 42,888,832 | 6.072 GiB | fail | 0/12；0/12 | valid exact-sequence accuracy negative |
| p5-trace p4/p6 N62 h10 | 89,755 / 35,000 | 20,140,928 / 101,062,900 | 9.271 GiB | fail | 0/12；0/12 | non-exact-sequence negative |

global p6/h15 相对 h10 p6 达到 `2.057x` DoF 压缩。fixed h15 候选处于
65k–75k 优选区间，exact preallocation 将 mallocs 从 13,856 降至 0、
unused NNZ 从 3,498,879 降至 288,768、build 从 231.15 s 降至
61.61 s，peak 从 6.105 GiB 降至 5.803 GiB；used NNZ、factor 和物理
结果不变。方向性 z 加密把预算内通道结果推进到 10/12 + 10/12；
fixed-trace x control 与 global-p5 y mechanism control 均无有效恢复，后者
不是 same-space y 排除；DtN q31 和 scaled evanescent-buffer 也无有效恢复，
但没有覆盖 external funnel。global p6/h14 给出 full-trace measured positive
marginal，但完整 trace 超预算。h13 top2 与 h14 exact-reverse 是一次正向和
一次反向的有界 z-node 判别，不是扫描；其实际通道计数分别回退到 8/8 和
7/8，因此 z-node lane 已关闭。Review V2 后 physical selective-trace 已有
actual storage expansion、exact-sequence/periodic owner plan、Stage-4
recovery/residual wiring 和 owner-aware MatShell 的 fixture/correctness
能力，但 actual h14 channel-DWR selection、formal MPI8 PDE 和 measured
candidate count 仍全部为 0。所有点仍不得越过 diffraction-channel Gate。

预算内最佳点与两个 bounded z-node negative 的权威记录为：

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_directional_z_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_top2_phase_redistribution_mpi8_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h14_exact_reverse_h13_top2_mpi8_v1.json`

p4-trace h10 是结构合格的精度负结果；p5-trace/p4-interior 的 curl
nullity `112` 小于 expected gradient dimension `178`，缺 66 个 gradient
modes，因此 N62 不能作为第二个有效 accuracy negative。N18 共享同一错误
低空间，未运行。

## DWR、smoothness 与 classifier v3

p4/p5 same-mesh DWR 使用三个独立 Hermitian adjoint，DWR effectivity 与 1
的最大差小于 `1.7e-11`。theta=0.5 marker：

| indicator | cells | captured | R5 Jaccard |
|---|---:|---:|---:|
| strict R00 | 84 | 0.5055 | 0.6897 |
| strict R | 84 | 0.5059 | 0.6897 |
| T | 78 | 0.5160 | 0.8077 |
| relative R/T | 81 | 0.5091 | 0.7778 |
| tolerance-normalized R/T | 78 | 0.5126 | 0.8077 |
| R5 | 63 | 0.5115 | — |

normalized marker 保留 strict R00 audit，避免只优化 `R_total`。

latest p5/p6 projection record 在 252/252 cells 上得到：

| signal | min | median | max |
|---|---:|---:|---:|
| hierarchical p6/p5 physical decay | 0.16201 | 0.16289 | 0.16783 |
| coefficient decay，diagnostic only | 0.14644 | 0.14723 | 0.15164 |
| p4 projection defect | 0.03436 | 0.03448 | 0.03848 |
| p5 projection defect | 0.00655 | 0.00657 | 0.00755 |
| p5/p4 defect decay | 0.18988 | 0.19086 | 0.19644 |

classifier v3 在 periodic transitive aggregation 后给出
`p-up=102 / p-keep=150 / h-refine=0 / p-down=0`。它通过 synthetic
smooth/interface/corner/high-frequency、periodic 和 MPI2 collective
fail-fast fixtures，但仍为 `production_qualified=false`：旧 signal record
不含最新 N1E/Piola/roundtrip/hash-scope 字段，且没有独立 target
phase-resolution 与 same-patch actual h-vs-p authority。

Review V1 的 channel batch 另完成 6 个失败功率目标和 10 个失败复振幅
Re/Im 目标的独立 Hermitian adjoint：16/16 通过，最大 adjoint residual
`4.21e-13`，最大 direct-adjoint relative error `2.52e-11`。但当前
cell/edge/face 量是 recovered-dual coefficient sensitivity proxy：
`actual_enriched_residual_available=false / residual_weighted=false /
actual_dwr_indicator=false`，不得称为 missing-trace DWR。

## Task035 inherited h/p control

tetra h50 顺序代理：

| endpoint | cells | DoF / rows | NNZ | R/T/Avolume vector error | strict-R error |
|---|---:|---:|---:|---:|---:|
| base p5 | 180 | 15,405 / 15,485 | 3,726,879 | `2.2032e-2` | `1.5130e-3` |
| one-local-h p5 | 1,248 | 101,210 / 101,290 | 23,913,006 | `6.3581e-4` | `4.3764e-4` |
| fixed-mesh p6 | 1,248 | 167,784 / 167,864 | 57,609,056 | `1.0224e-4` | `5.1371e-5` |

local-h 的 vector-error gain/added DoF 较高，p-up 的 strict-R gain/added
DoF 较高；没有单一 winner。final p6 的 vector control pass，但 strict-R
ratio 为 1.421 且 DoF 超过 90k。该记录是 sequential global marginal
proxy，不是 same-patch authority。

structured hexa 没有 conforming hanging-node/transition path；tetra selected
p6 physical-reduction 又未实现。既有 h50/h37.5 refined p5 已为
101k–129k DoF。因此这条 Task035 继承的“tetra local-h 后 selected-p6”
组合以 `stopped_by_gate_architecture_and_budget` 结束，不重复 Task035
heavy cases。它与 Review V1 的 structured-z Lane A 和 selective-trace
Lane B 不是同一命名空间。

## Review V1/V2 channel recovery 与 selective capability

| batch | evidence | result |
|---|---|---|
| significant channel reference v1 | 12 通道 power/amplitude/phase 与 p/h spread | frozen best-available same-code；production false |
| channel adjoints | 6 power + 10 amplitude-component goals | 16/16 Hermitian pass；localization 仍是 proxy |
| z directional Lane A | h15→h14→h13 | 6/7→7/9→10/10；明确正信号 |
| bounded z-node discriminators | h13 top2；h14 exact-reverse | actual 8/8 与 7/8；不能用 projected count 替代实测；lane closed |
| x/y controls | fixed-trace x-only 与 global-p5 y-only | 5/6 与 3/1；指定 controls 不支持继续，y 不是 same-space 排除 |
| port/DtN | q31、unsafe unscaled buffer stop、scaled buffer1 | tested q31/scaled buffer 为负；external funnel 未运行 |
| frozen R5 slab split | 只二分最大 R5 slab | 5/9，新增 `R(-7,0)` power regression；关闭预先指定 split lane，其他 node distributions 未运行 |
| full trace discriminator | global p6/h14 | 9/12 power、12/12 amplitude；92,850 DoF over cap |
| inverse trace/interior exchange | p6 trace + p5/p4 interior | 分别缺 101/149 gradient modes；PDE 未运行 |
| physical selective trace | actual storage/exact-sequence/Stage-4/MatShell fixtures | correctness capability；actual h14 DWR/PDE/candidate count 仍为 0 |
| condensed iterative | three formal assembled screens | 三条均为 residual controlled negative；无 official outputs |
| inversion-aware selection | no frozen parameters/noise/instrument authority | not run；12 通道 Gate 保持 |

physical trace 的 fixture/correctness capability 不表示已经把 trace 信号转换成
正式 subset。当前实现已证明 inactive missing rows 不进入矩阵，并在
serial/MPI2 小 fixture 上验证 actual expansion、periodic/Floquet pullback、
generalized recovery/residual 和 MatShell action；但没有 frozen h14
actual-channel DWR selection，也没有 formal MPI8 selective PDE、12-channel
结果、DoF、NNZ 或 memory measurement。相关能力证据为：

- `src/test/test_147_task035b_actual_selective_trace_expansion.py`
- `src/test/test_153_task035b_physical_channel_dwr_trace_selection.py`
- `src/test/test_157_task035b_actual_physical_discrete_gradient_authority.py`
- `src/test/test_171_task035b_actual_selective_trace_stage4_wiring.py`
- `src/test/test_172_task035b_selective_p6_trace_matrix_free.py`
- `src/test/test_174_task035b_stage4_pre_release_capture.py`

### Review V2 assembled iterative controlled negatives

三条正式 screen 均使用 programmatic opt-in profile，不使用 raw PETSc options；
三者都没有 global MUMPS/direct factor，但“global factor-free”不等于完全没有
factor storage：ASM 与 physical z-slab profile 仍分别使用 local ILU，后者
还使用 80×80 dense coarse LU。

| profile | iterations / reason | terminal reduced residual | recovered true residual | disclosed factor storage | peak / swap | official output |
|---|---:|---:|---:|---|---:|---|
| GMRES + Jacobi | 200 / `DIVERGED_MAX_IT` | 0.861662 | 0.861661 | global factor NNZ 0 | 3.921 GiB / 0 | none |
| FGMRES + ASM/ILU(0) | 200 / `DIVERGED_MAX_IT` | 0.999661 | 0.999659 | global 0；local ILU active，v1 NNZ unavailable | 4.462 GiB / 0 | none |
| FGMRES + z-slab ILU(0) + DtN trace Galerkin | 200 / `DIVERGED_MAX_IT` | 0.996265 | 0.996263 | global 0；local ILU 9,576,512；coarse 80×80 | 3.885 GiB / 0 | none |

三条都未达到三 decade reduction、terminal `<=1e-3` 或 full true residual
Gate。它们的较低 RSS 只能作为 controlled-negative resource evidence，
不能称为 accuracy-qualified factor-free memory floor。历史前两条 screen
曾在 common flow 拒绝未收敛 KSP 前写出带 `status=ok` 的 diagnostic port
文件；这些文件已由 caveat record 明确取消 official authority，原始失败
artifact 仍保留：

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_factor_free_iterative_mpi8_v1.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/h15_physical_slab_dtn_iterative_formal_screen_mpi8_v2.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/condensed_iterative_failed_output_caveat_v1.json`

owner-aware selected-p6 MatShell 当前只是 assembled-action oracle 下的
serial/MPI2 correctness capability；没有 formal matrix-free PDE、独立
低存储 preconditioner 或 accuracy-qualified matrix-free memory result。

## Hybrid 与 0.7 nm

```text
selected candidate = null
Hybrid eligible candidate count = 0
Hybrid static H1-A p2/h5 = controlled_negative
H1-A M funnel = M120/M160 run; converged but channel closure failed
h13-seed Hybrid closure = not_run_by_h1a_review_prerequisite
adaptive Hybrid = not_run_by_h1a_review_prerequisite
0.7 nm PDE = not_run
0.7 nm / 2 TiB resource model v3 = not_run_by_selected_candidate_gate
predicted simultaneous peak = null
production feasibility = unknown
```

H1-A 的 static Full3D/Hybrid 总量、残差、接口和 selected field norms
分别通过，但显著通道同离散闭合失败。M160 的相对 `1e-3` 失败功率为
`T(-5,-4,-2,-1)` 与 `R(-7,-5,-4,-2,-1)`；失败复振幅还包括
`T(-7)`。M120 与 M160 的 12 通道彼此为 12/12 + 12/12，因此不运行
M240。完整实际值、冻结 tolerance 和资源对照见
`outcomes/hybrid_static_condensation_h1.md`。

规划敏感性仍保留
`N_local,0.7=N_equiv,13.5*7173.104956*f_H`。90k/75k/70k/65k 与
`f_H=.30/.35/.40` 映射到约 139.9M–258.2M local FE DoF，但没有
accuracy credit。Task034 current Hybrid layout 的 dense multi-RHS 单组件
已远超 2 TiB；Task035b 没有 selected layout，不能把 cumulative component
envelope 冒充 simultaneous peak，也不能宣称 0.7 nm 已可行或已证明不可行。

## Scope 与交付

| item | status |
|---|---|
| fixed rectangular block Review V2 batch | `partial_with_controlled_negatives`；证据批次收口，完整研究 Gate 未通过 |
| irregular G1/G2/Phase F | `out_of_scope_by_user / not_run / not_a_completion_gate` |
| candidate ledger | 68 行 JSON/CSV，保留 controls、failures、capability-only 和 stopped lanes |
| negative/failure preservation | complete |
| physical selective execution | fixture/correctness capability only；actual DWR/PDE count 0 |
| assembled iterative | three formal controlled negatives；official output count 0 |
| Hybrid static H1-A | p2/h5 M120/M160 已运行；same-discretization 3/12 + 2/12，`controlled_negative` |
| Hybrid/resource bridge | `Hybrid eligible = 0`；h13/adaptive Hybrid 与 resource model v3 not run |
| ordinary default | unchanged |

证据索引见：

- `outcomes/reference_and_resource_target.md`
- `outcomes/high_p_memory_anatomy.md`
- `outcomes/local_hp_capability.md`
- `outcomes/regular_geometry_compression.md`
- `outcomes/negative_results.md`
- `outcomes/resource_projection_0p7nm.md`
- `outcomes/hybrid_static_condensation_h1.md`
- `outcomes/all_candidates.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/`

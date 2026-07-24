# Task035b 高阶 p6 内存构成与 exact static condensation

## 2026-07-24 真实 regionwise-p 候选：资源正信号、精度受控负结果

Task035b 已在同一 h10 hexa 网格和 classifier geometry hash 上正式运行
`p4 shared trace + 147-cell p4 interior + 105-cell p6 interior`。这是真实
physical local-p：inactive p6 interior modes 没有进入矩阵，完整 p6 matrix
和完整 trace matrix 都未分配；低阶 cell 直接调用 p4 kernel，不是先算 p6
再把系数置零。

| MPI8 h10 metric | global p6 canonical | regionwise candidate | change |
|---|---:|---:|---:|
| Full3D-equivalent active DoF | 173,802 | **88,994** | -48.80% |
| solved rows（含 80 DtN） | 51,272 | **21,824** | -57.44% |
| matrix NNZ | 41,989,040 | **8,184,464** | -80.51% |
| factor NNZ | 211,651,232 | **42,888,832** | -79.74% |
| process-tree peak | 15.964 GiB | **6.072 GiB** | -61.97% |
| direct condensed build | 770.89 s | **175.43 s** | -77.24% |
| MUMPS setup / solve | 142.12 / 0.202 s | **11.45 / 0.038 s** | -91.95% / -81.16% |
| total solve-case elapsed | 967.09 s | **222.34 s** | -77.01% |

candidate 达到 `<=90,000` minimum DoF 目标；相对 global p6 为
`1.953x` 压缩，略低于单独的 `>=2x` 表述，但 minimum 合同是二者满足其一。
MUMPS factor 释放后，8-rank simultaneous RSS 从 6,162.70 MiB 降到
4,310.28 MiB，实际归还 1,852.42 MiB。由此确认此前“rows 下降但内存不降”
不是不可避免的高阶现象；当完整 matrix、inactive rows 和 factor 生命周期
真正移除后，NNZ、factor、memory 与时间都按正确方向下降。

资源通过不等于精度通过。本候选 full explicit true residual 为
`1.1657e-11`，geometry/tag/periodic/orientation Gate 全部通过，但所有正式
精度层级均为负：

| observable / Gate | global p6 | candidate | same-code p5-p6 tolerance | status |
|---|---:|---:|---:|---|
| R00_total | 0.0007537612 | 0.0010465702 | 0.0000319529 | fail |
| R_total | 0.0007628815 | 0.0010605766 | 0.0000320046 | fail |
| T_total | 0.6027016340 | 0.5988458026 | 0.0002176801 | fail |
| A_closure | 0.3965354845 | 0.4000936209 | 0.0001856755 | fail |
| normalized R/T/Aclosure vector | reference radius 1.732 | 27.704 | — | fail |
| significant orders / complex amplitudes | 12 channels | 12/12 fail | p5-p6 spread | fail |
| selected volume complex-E relative L2 | — | 9.8467% | 0.5183% | fail |
| material-interface complex-E relative L2 | — | 9.7778% | 0.5220% | fail |

因此 `p4 fixed trace + p4/p6 interior` lane 已按连续研究规则关闭，记录状态为
`actual_regionwise_p_controlled_negative`，不得接入 Hybrid。负结果表明当前
主要精度瓶颈是 p4 shared trace，而不是 MUMPS 或 residual。

下一条可检验路线改为 `p5 shared trace + p4 low interior + selected p6
interior`。其 Full3D-equivalent 预算为
`68,551 + 342 * N_p6_cells`：`N_p6_cells <= 62` 可保持 `<=90k`，
`N_p6_cells <= 18` 可保持 `<=75k`。这需要先资格化 p5-trace/p4-interior
低阶 local kernel 与对 p5-trace/p6-interior空间的 exact embedding；在通过
单元/MPI 等价测试前不得启动下一次 heavy PDE。

正式记录：
`benchmarks/cases/095_high_order_local_hp_resource_envelope/records/regionwise_p4trace_p6interior_h10_mpi8.json`。

## 2026-07-24 assembly-time condensation 与生命周期闭环

旧 prototype “自由度下降但内存没有同比下降”的主因已经消除。当前
research-only 路径在 cell assembly 时直接形成
`C_K^H (A_tt - A_ti A_ii^-1 A_it) C_K`，只分配最终 Floquet-independent
trace + DtN 系统；不再先装配 173,802-row full FE matrix，也不分配
60,402-row full trace Schur、embedded slave identity rows 或
base-to-augmented matrix copy。

| MPI8 p6/h10 路径 | active rows | matrix NNZ | formal peak | peak 所在阶段 |
|---|---:|---:|---:|---|
| global full p6 | 173,882 | 210,353,120 | 35.024 GiB | R5 localization，factor 仍保留 |
| post-assembly exact condensation | 60,482 | 52,058,162 | 29.212 GiB | R5 localization，full/Schur 生命周期重叠 |
| assembly-time，factor 保留 | 51,272 | 41,989,040 | 16.998 GiB | R5 localization |
| assembly-time，销毁 factor、未 trim heap | 51,272 | 41,989,040 | 16.351 GiB | R5 localization |
| assembly-time，销毁 factor + heap trim | 51,272 | 41,989,040 | **15.964 GiB** | **MUMPS/求解验证阶段** |

相对 global full p6，最终 active rows 减少 70.51%，assembled NNZ
减少 80.04%，全程进程树 memory authority 减少 54.42%。最终系统仍由
173,802 个 p6 FE unknown 的 exact cell Schur 得到；`51,272 =
51,192 independent trace + 80 DtN auxiliary`，不是 zero masking。

最后一条正式记录绑定 clean source
`0f8924ac4bacc8a17dc67fb0af2871ea61471c56`，固定 mesh、tag 和 geometry
hash，使用 MPI8、0 swap。MUMPS/求解验证阶段外部采样峰值为
16,347.64 MiB；释放 KSP/MUMPS factor、system Mat、RHS 和 solution 后，
8 个 rank 的 `glibc malloc_trim(0)` 均成功：

| lifecycle 点 | simultaneous MPI rank RSS |
|---|---:|
| heap trim 前 | 16,182.89 MiB |
| heap trim 后 | 11,233.94 MiB |
| 实际归还 Linux | **4,948.95 MiB** |
| field output 后 | 12,146.61 MiB |
| R/T/Avolume 后 | 12,548.60 MiB |
| 随后的 R5 localization 外部峰值 | 13,311.62 MiB |

因此后处理不再与已释放的 MUMPS factor heap pages 叠加，也不再超过
MUMPS 阶段。`malloc_trim` 只在
`direct_release_solver_before_postprocess=True` 的资格化
assembly-time research 路径执行；ordinary default 仍为 `False`。

### 当前正式数值与成本

| 项目 | MPI8 p6/h10 assembly-time + trim |
|---|---:|
| full FE / solved rows | 173,802 / 51,272 |
| matrix / factor NNZ | 41,989,040 / 211,651,232 |
| average / maximum row width | 818.95 / 1,398 |
| direct condensed build | 770.89 s |
| compiled cell-kernel evaluations | 285.37 s |
| local Schur | 26.30 s |
| local sparse insertion | 260.84 s |
| final parallel Mat assembly | 396.33 s |
| MUMPS setup / solve | 142.12 s / 0.202 s |
| p6 elapsed | 967.09 s |
| full explicit true residual | `1.3574e-11` |
| R / T / A_volume | `0.000762881475137` / `0.602701633985772` / `0.396535484542744` |
| port-volume closure error | `3.653e-12` |

装配仍比 MUMPS 慢，但已经从旧 full p6 base assembly 的约
2,195.6 s 降到 direct condensed build 770.9 s。剩余热点不是矩阵规模
错误，而是 Python 驱动的逐 cell kernel/Schur/Mat insertion 以及 PETSc
final assembly；后续性能 lane 应把这些操作编译化或批量化，不能通过
放宽 residual/R/T/A Gate 换取时间。

### 新 evidence

- canonical pass:
  `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_mpi8.json`
- retained-factor lifecycle:
  `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_retained_postprocess_mpi8.json`
- factor destroyed but allocator not trimmed:
  `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p1_p6_h10_p6_assembly_time_condensed_independent_released_without_heap_trim_mpi8.json`
- raw canonical evidence:
  `benchmarks/artifacts/task035/actual_global_r5/hexahedron_p1_p6_h10_pols_mpi8_20260724T030451Z_single_mesh_pair_condense_p6_assembly_time_p6_independent_p6/`

## 历史 post-assembly prototype

以下部分保留最初 post-assembly condensation 的真实对照，用于解释为什么
仅降低 solved rows、但保留 full assembly 和 factor 生命周期时，内存收益
有限；它不再代表当前最优实现。

| 项目 | global p6 full | exact p6 condensed | 结论 |
|---|---:|---:|---|
| source SHA | `c1040a0197d3e113576c9dc1e8d3ae13a5fa66b2` | `0f4b786d618c37e1c572a4f596a9235e53d73161` | 两者均为 clean committed SHA |
| mesh | h10 hexa `(6,3,14)`, 252 cells | 相同 | mesh/cell-tag/facet-tag hashes 相同 |
| MPI | 8 | 8 | formal resource identity 相同 |
| FE / augmented rows | 173,802 / 173,882 | 173,802 / 60,482 active | 113,400 cell-interior rows 被物理消去 |
| matrix NNZ | 210,353,120 | 52,058,162 | -75.25% |
| factor NNZ | 386,625,292 | 243,270,308 | -37.08% |
| fill | 1.838 | 4.673 | Schur 更稠密 |
| formal memory authority | 35.024 GiB | 29.212 GiB | -16.59% |
| full explicit residual | `2.018e-11` | `1.959e-11` | 均通过 `1e-9` Gate |
| p6 elapsed | 2,526.7 s | 2,495.3 s | 无可信 wall-time 加速 |

这是两个 clean SHA 上的单次 MPI8 实测对照。ordinary full-system path 在新
SHA 上默认关闭 condensation，矩阵 rows/NNZ 和 official observables 均保持
一致；但 MUMPS ordering/factor inventory 存在 run-to-run 波动，例如两次
p5 control 的 factor NNZ 相差约 5.8%。因此 factor NNZ 和 peak-memory
降幅是当前实测工程信号，不应写成统计置信区间或逐位确定量。

## 身份与实现边界

本结果只研究 Task034 fixed rectangular block grating，不含任何不规则几何。
condensed solve 在同一实际 mesh instance 上执行，并保持：

- mesh SHA-256
  `f0eef2aa28e86014b661a921993bcfd45e6db1892da350402f2be11ec64dd857`；
- cell-tag SHA-256
  `42f511fc7ffddcbc2972d641018e16a845f48c11067ccd9a9686695ad5cfc131`；
- facet-tag SHA-256
  `0adbcfed35e1840460f826cb1ca1695ed87c0c3960e2073377d2f50871c3c0bd`；
- exact Basix periodic orientation/mapping、80 个 DtN auxiliary unknowns；
- ordinary `stage4_cell_static_condensation=False` default 不变。

实现逐 cell 形成

```text
S = A_tt - sum_K A_ti(K) A_ii(K)^-1 A_it(K)
g = b_t  - sum_K A_ti(K) A_ii(K)^-1 b_i(K)
```

求解 60,482-row trace system 后重新逐 cell 恢复 113,400 个 interior
unknowns，再用原完整 173,882-row operator 显式重算 residual。没有
max-p zero masking，也没有保留 all-cell dense factor cache。

## 为什么 DoF 大降但 MUMPS 内存没有同比下降

实测给出四个互补原因：

1. 当前 prototype 从已经装配的完整 p6 sparse matrix 开始，未消除
   2,195.58 s full base assembly 及其生命周期峰值。
2. trace Schur 的 average row width 为 860.7；虽然低于 full p6 的
   1,209.7，但相对 60,482 rows 已显著稠密。
3. factor fill 从 1.838 增到 4.673，所以 rows -65.22% 只换来
   factor NNZ -37.08%。
4. Schur build 期间 full matrix、transpose copy 和 condensed matrix
   存在生命周期重叠；正式 memory authority 因而只从 35.024 GiB 降到
   29.212 GiB。

Schur build 共 84.69 s：

| 子阶段 | MPI8 max time |
|---|---:|
| transpose | 1.69 s |
| local dense solves | 15.22 s |
| Schur insertion | 26.14 s |
| final parallel assembly | 57.99 s |
| full recovery | 7.75 s |

子阶段存在重叠，不能把这些 max-time 数简单相加解释为总 wall time。

## 物理等价 Gate

| observable | global p6 full | exact p6 condensed | absolute delta |
|---|---:|---:|---:|
| R_total | 0.000762881475130 | 0.000762881475131 | `9.41e-16` |
| T_total | 0.602701633983078 | 0.602701633983515 | `4.38e-13` |
| A_volume | 0.396535484541640 | 0.396535484541834 | `1.94e-13` |

该历史 lane 是明确正信号：物理等价、full residual、rows、NNZ、
factor NNZ 和 memory 均通过。后续 assembly-time 路径已经达到“完整 p6
global matrix 不存在”，但仍不构成 local-p/regionwise-p 完成证明。

## Evidence

- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h10_mpi8.json`
- `benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h10_p6_condensed_mpi8.json`
- raw ignored evidence:
  `benchmarks/artifacts/task035/actual_global_r5/hexahedron_p5_p6_h10_pols_mpi8_20260723T143152Z_single_mesh_pair_condense_p6/`

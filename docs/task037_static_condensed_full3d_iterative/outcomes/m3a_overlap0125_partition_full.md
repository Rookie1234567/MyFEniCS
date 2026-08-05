# M3a overlap 0.125 partition-weighted：MPI4 Full3D full solve

> 后续状态：MPI1/2/8 full runs 已完成，same-candidate MPI identity 与资源曲线见
> [M3a MPI scaling comparison](m3a_mpi_scaling_comparison.md)。本文继续作为 MPI4
> anchor 的不可变细节记录；其中“只有 MPI4 full”的历史范围说明已被后续报告取代。

## 结论

这是固定 p6/h10、13.5 nm、S 偏振模型上的一次正式 MPI4 full solve。静态凝聚先在单元内消去 interior DoFs，再只对 active trace 与 DtN auxiliary unknowns 做迭代；预条件器使用 16 个 owner-local slab、0.125 overlap、partition-of-unity 权重、two-color ILU(0)、两步 GMRES 和 75D wave coarse。该流程没有形成 global A/F 或 global direct factor。

solver、物理量、canonical field 和 fresh-mesh H(curl) 范数均通过；内存通过 Task37 的绝对 `<=10.30 GiB` Gate，但没有达到工程目标 `<=7.36 GiB`。因此分类为 `NUMERICAL_SUCCESS_RESOURCE_REVIEW`，不是 production-qualified。

## 身份与来源

| 项目 | 值 |
|---|---|
| source | `2631a4c47258c9def919530787e409774b8ce029`（canonical fix，parent `151ba7ba`） |
| model | p6 Nédélec / h10 / 13.5 nm / theta normal 80° / phi 0 / S |
| mesh / MPI | 252 cells / MPI4 |
| artifact | `benchmarks/artifacts/task037/m3a_overlap0125_partition_full_p6_h10_mpi4_2631a4c4` |
| watchdog | `task037_m3a_overlap0125_partition_full_pass`，return 0，official=true，failures=[] |
| environment | `source scripts/activate_myfenics_wsl.sh`；`/home/Projects/MyFEniCS/.venv/bin/python`；PETSc complex128/int32；OMP_NUM_THREADS=1 |
| worker command | 已逐项绑定在 [compact record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_m3a_overlap0125_partition_full_v1.json) 的 `provenance.worker_command` |

## 数值 Gate

| 项目 | 实测值 |
|---|---:|
| KSP / iterations | `CONVERGED_RTOL` / 365 |
| reported relative | `9.923273241434768e-7` |
| condensed true / full augmented true | `9.923273236187206e-7` / `9.923273236187206e-7` |
| full FE true residual | `9.923273535279698e-7` |
| eliminated interior max abs | `1.1140981751262269e-12` |
| limit | `1e-6` |

本次 M3a MPI4 full 的当前运行 checkpoint 仅按 raw artifact 记录：iteration 20 的 reported residual 为 `0.04660098472046792`；该值不是历史 screen 的替代物。正式 full 的 final values 见上表。

## 按候选区分的 screen 证据

| 候选/运行 | 步数 | 结果 | 内存 | 含义 |
|---|---:|---:|---:|---|
| M3a overlap .125 partition, MPI8 historical screen | 20 | reported `0.04000947850823184`；condensed true `0.040009478508230854` | `11.7366867065 GiB` | resource negative；不代表 full |
| old F3 overlap .25 candidate | 100 | `0.000608485581260` | old record | separate historical candidate |
| old F3 overlap .25 candidate | 200 | `3.5885919793e-5` | old record | separate historical candidate |
| M3a overlap .125 partition, MPI4 current full | full | final `9.9232732e-7` | `8.265838623046875 GiB` | current formal full |

因此旧 F3 overlap .25 的 100/200 数据不应被读成 M3a 做过 100/200 screen；M3a MPI8 的 20-step 结果也不应被读成 full success。

## 结构与无全局矩阵证据

| Gate | 结果 |
|---|---|
| slabs / overlap / interpolation | 16 / `0.125` / `partition` |
| partition weights | per-row unity error `0.0`；range `0.25–0.5` |
| smoother | two-color；2-step GMRES；ILU(0)；factor-only |
| coarse | 75D wave coarse |
| global A/F / global Schur / direct factor | false / false / 0 |
| retained slab matrices | 0 after factorization；每个 owner-local slab matrix 都是 setup 中逐个形成、factor 后释放，不是从未组装 |
| factor rows / stored NNZ | `127656` / `91415952` |
| factor CSR payload lower bound | `1828829728 bytes` |
| coarse basis storage | `9481648 bytes` |
| operator / coarse / one-level applies | `1178 / 365 / 2190` |

## 物理可观测量

| 量 | M3a MPI4 | Direct MPI8 v2 | 绝对差 |
|---|---:|---:|---:|
| `R_total` | 0.0007628813414779686 | 0.000762881475132771 | 1.336548023948e-10 |
| `T_total` | 0.6027016365247442 | 0.6027016339861171 | 2.538627086324e-9 |
| `A_balance` | 0.3965354821337779 | 0.3965354845387501 | 2.404972221370e-9 |
| `A_volume_total` | 0.396535483656842 | 0.3965354845429724 | 8.861303912866e-10 |
| energy closure | 1.5230641192687244e-9 | 4.222400207254395e-12 | descriptive |

12/12 significant diffraction powers和12/12 outgoing boundary complex amplitudes均通过。完整机器可审计值保存在 record 的 `channels_12` 数组；以下列出每项差值，标签按权威 `T(... )_s`/`R(... )_s`：

| 通道 | power 绝对差 | 振幅绝对差 |
|---|---:|---:|
| `T(-7,0)_s` | 6.435329459041241e-10 | 1.5885285516517524e-7 |
| `T(-5,0)_s` | 8.387831389343993e-12 | 1.0841938545357455e-8 |
| `T(-4,0)_s` | 1.490046165947734e-12 | 9.689945465355527e-10 |
| `T(-2,0)_s` | 6.79409544904769e-11 | 8.92523413273925e-9 |
| `T(-1,0)_s` | 3.989673981539665e-12 | 1.1133487413049537e-7 |
| `T(0,0)_s` | 3.2419746887057954e-9 | 2.241988748055756e-9 |
| `R(-7,0)_s` | 3.42351870761007e-10 | 2.3497820161653558e-7 |
| `R(-5,0)_s` | 9.108363592788594e-13 | 1.4078385183876074e-9 |
| `R(-4,0)_s` | 2.0189856278331934e-11 | 8.173520358168358e-9 |
| `R(-2,0)_s` | 5.959492870658859e-11 | 1.4541802688443106e-8 |
| `R(-1,0)_s` | 3.864837877264724e-10 | 1.1720287656763255e-7 |
| `R(0,0)_s` | 4.4037722904052834e-11 | 1.1688596100845196e-9 |

## 规范化场与新鲜网格范数

`60402` 个 active canonical packets 是由 `51192` 个 independent active coordinates 展开/恢复得到的完整 original-trace packets；这不代表线性系统行数增加。Full FE packets 为 `173802`。

| 比较 | 数量 | relative L2 | max abs | Gate |
|---|---:|---:|---:|---|
| active Direct MPI8 vs M3a MPI4 | 60402 / 60402 | 1.2553898016411866e-6 | 4.625555666881793e-5 | pass <=1e-5 |
| full FE Direct MPI8 vs M3a MPI4 | 173802 / 173802 | 7.880394026823442e-7 | 4.625555666881793e-5 | pass <=1e-5 |

missing/extra/duplicate 均为 0。full-FE 分组 relative L2：cell interior `3.9365767477e-7`；non-Floquet edge `3.3065297416e-6`；non-Floquet face `6.2302185081e-7`；Floquet edge `4.4843834146e-6`；Floquet face `8.3934712195e-7`。

Fixed-field relative L2：

| field | relative L2 |
|---|---:|
| E | 5.5794096947e-7 |
| H | 3.2460978491e-7 |
| E_t | 7.2175703519e-7 |
| H_t | 1.1814035455e-6 |

同一 fresh p6/h10 mesh、MPI4、252 cells、173802 DoFs 的 offline H(curl) norm Gate：relative_l2 `3.449938833419635e-7`、relative_curl_l2 `3.278099243754906e-7`、relative_tangential_trace_mass `7.099902806903749e-7`、relative_hcurl `3.419997826589739e-7`，均 <=1e-5。命令和 `/tmp` 未跟踪状态绑定在 record，耗时 `339.75918469496537 s`；这不是 PDE solve。

## 资源与嵌套计时

| 口径 | M3a MPI4 | Direct MPI8 v2 |
|---|---:|---:|
| process-tree authority | 8.265838623046875 GiB | 15.059223175048828 GiB |
| worker RSS/PSS/USS | 8449.6406 / 7505.6914 / 7209.0938 MiB | 15406.0078 / 13373.5186 / 13062.9414 MiB |
| swap | 0 | 0 |
| core setup / solve / recovery / total | 126.837074135 / 393.260218908 / 0.046614531 / 520.189155098 s | — |
| Stage4 DtN linear solve | 520.194362622 s | — |
| Stage4 assembly + solve | 686.207802555 s | 202.038149475 s |
| cell recovery | 0.242816302 s | 0.1273 s |
| full residual | 1.537617817 s | 0.902063056 s |
| canonical export / postprocess | 4.954428790 / 8.297736085 s | 2.592369830 / 9.141699396 s |
| parent whole wall | 701.650490339 s | 218.851869611 s |

这些是嵌套 scope，不能相加。derived memory ratio M3a/Direct = `0.5488887791199146`，reduction `45.111122088008536%`；cross-MPI descriptive wall ratio = `3.206052073423701`。Direct 是 MPI8、M3a 是 MPI4；M3a 虽通过 absolute `10.30 GiB`，仍高于 half of new Direct `7.529611587524414 GiB`，所以工程 50% memory Gate 未通过。

## 边界

ordinary defaults 未变化。历史 M2c、M3a MPI8 screen20 resource-negative、M4d high-order patch oracle negative 均保留，不覆盖。M3a full 只有 MPI4，故没有 same-candidate MPI4/8 identity 证据；canonical/physical comparison 证明本次 MPI4 iterative 与 MPI8 Direct 的离散物理解一致。full repository pytest 未再运行，状态为 `not_run_by_user_efficiency_policy / not_verified`。不启动 Task037b、Hybrid、0.7 nm、hp 或新的 PDE screen。

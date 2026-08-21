# D3/D4 two-level contraction：受控停止记录

## 结论

本文件记录 Review V3 的 hard stop。D2 在 p6/h10、MPI1 的 rank-64 trace-harmonic
construction 阶段未能完成固定的 slab-0 interior CG，因此没有合法的 `Z`、`AZ` 或
coarse `E`。D3/D4 没有运行；以下所有 rho、online 内存和 T6-S 数值均是
`not_run_by_D2_rank64_hard_stop`，不是数值失败，也不是通过。

这里的“两级”是一个通俗的分工：冻结的 Candidate A one forward+backward smoother
处理局部、短距离误差；trace-harmonic coarse correction 处理跨 slab 的长距离误差。
`Z` 是由真实界面和辅助能量选出的少量全局方向，`AZ` 是 exact physical action 对
这些方向的作用，`E=Z^H A Z` 是最多 64×64 的小型 coarse operator。owner-local
sharding 表示每个 MPI rank 只保存自己的行，不复制完整 basis，也不做 FE-sized
numeric allgather。由于本次 D2 连 `Z` 都没有构造完，这些仍只是已批准的算法定义，
不是本次测量结果。

## D2 formal 现场

| 项目 | 实际值 |
|---|---|
| source SHA | `cc8de60cc3e21b647aafb29ac9c10b46919823e7` |
| case | `p6-h10-mpi1`，MPI1，唯一一次 attempt |
| wall / monotonic marker elapsed | `557.385958733 s` / `510.287976466 s` |
| markers | `preflight → mesh_mpc_topology → trace_basis_build → failure` |
| failure | `slab 0 interior CG did not converge: -3` |
| PETSc interpretation | `KSP_DIVERGED_ITS`，固定 `max_it=500` 用尽 |
| process-tree peak / swap | `3,013,468,160 B` / `0 B` |
| termination | `natural_exit`，worker `rc=1`，不是 12 GiB hard stop |
| generated Z/AZ/E | 全部未得到 |

CG 是在固定局部辅助问题中逐步降低残差的迭代方法；`DIVERGED_ITS` 只说明规定
的迭代次数用完仍未达到收敛条件。它不意味着 Maxwell 物理问题永远不可解，但在
当前合同下不能增加 inner steps、换参数或重跑。Review V3 hard stop #7/#12 因此
关闭本批次后续路线。

## 五类 source 与 D3 结果矩阵

| source | coarse-only rho | Candidate A + coarse rho | Gate | 状态 |
|---|---:|---:|---:|---|
| physical RHS | not run | not run | `<=0.60` | `not_run_by_D2_rank64_hard_stop` |
| gradient-dominated | not run | not run | `<=0.90` | `not_run_by_D2_rank64_hard_stop` |
| curl-dominated | not run | not run | `<=0.90` | `not_run_by_D2_rank64_hard_stop` |
| checkerboard / high-frequency | not run | not run | `<=0.75` | `not_run_by_D2_rank64_hard_stop` |
| R3 qualified long-tail residual | not run | not run | `<=0.70` | `not_run_by_D2_rank64_hard_stop` |

D3 原本要求先看 coarse-only 是否相对 identity 有至少 20% 的明确改善，再组合
Candidate A；这两个判断都未发生。Candidate A 仍只能作为完全冻结的 one
forward+backward smoother oracle：two slabs、transmission、local GMRES restart/
max-it=8/8 和参数均不变，不能据此重新宣称 standalone production qualification。

## D0 预算不是 D2 measured pass

`N=173802`、complex128 full vector 为 `2,780,832 B`。固定 rank ladder 的纯
`Z+AZ` 数字载荷为：

| rank | Z+AZ exact array bytes | MiB（1024²） |
|---:|---:|---:|
| 16 | 88,986,624 | 84.864 |
| 32 | 177,973,248 | 169.729 |
| 48 | 266,959,872 | 254.593 |
| 64 | 355,946,496 | 339.457 |

D0 允许的 coarse metadata/work budget 是 `<=64,000,000 B`，因此 rank64 的
`355,946,496 + 64,000,000 = 419,946,496 B` 只是 derived/budget preflight；
它不是本次 D2 的 simultaneous retained measurement。D2 没有生成 `Z/AZ/E`，
也没有测出 online `<2 GB`。本次 3.013 GB 仅属于 construction/JIT 阶段，不能
作为 D3 online Gate 或完整 PDE workflow 结论。

## D4 与后续边界

| 项目 | 状态 |
|---|---|
| D2 MPI2 | `not_run_by_D2_rank64_hard_stop` |
| D3 coarse-only / two-level | `not_run_by_D2_rank64_hard_stop` |
| D4 T6-S 20/100/150/200 | `not_run_by_D2_rank64_hard_stop` |
| T6-F / EH / RTA | `not_run` |
| T7–T9 / full 0.7 nm PDE | `not_run` |

Candidate C 的源码与其 formal resource negative evidence继续作为 research archive，
分类 `DO_NOT_RERUN / DO_NOT_OPTIMIZE / DO_NOT_MERGE`；不把它改写成算法数值失败。
D2 adaptive coarse production core/runner/checker 因 rank64 未资格化，同样列为
`research-only / do-not-merge`。D1 p2/p3 trace-harmonic small-fixture oracle
正证据不受本次 D2 controlled negative 影响。

## Evidence

raw 为 ignored artifact，compact worker record 位于预定 outcomes 路径（当前 closure
尚未提交，工作树显示为未跟踪）。

| artifact | path | SHA-256 |
|---|---|---|
| worker record | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/d2_worker_p6_h10_mpi1_v1.json` | `ef98ba1e7c478b6c6a8297baf599aa34c1849188f3b1668f0cdaf63e4e95635d` |
| watchdog raw | `benchmarks/artifacts/task038_extra_full3d_iterative_d2/cc8de60/p6_h10_mpi1_v1/watchdog.raw.json` | `4313d5a3112db849a1b80c2ea2adae6fbe3c30f47da554c48ff9771a7c620a10` |
| watchdog compact | `benchmarks/artifacts/task038_extra_full3d_iterative_d2/cc8de60/p6_h10_mpi1_v1/watchdog.compact.json` | `53d6b314af83fafc8a0d13f14542229072869139914e031573574a262c877d7d` |
| worker log | `benchmarks/artifacts/task038_extra_full3d_iterative_d2/cc8de60/p6_h10_mpi1_v1/worker.log` | `c5dd34f422162cd4a5dc84a3e01052e71427292d905f5e95f20d2e5b9e9f133b` |

独立 checker 对这份 controlled-negative record 返回 `passed=false`，错误为
`record schema or stage is invalid`；这是 fail-closed 缺失成功 schema 的证据，不能
当作 PASS。没有修改代码、没有重跑、没有启动 MPI2/D3/D4。

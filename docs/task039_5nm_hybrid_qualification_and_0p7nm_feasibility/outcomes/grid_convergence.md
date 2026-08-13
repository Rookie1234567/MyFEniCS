# Task39：网格收敛边界

## 结论表

本任务只获得 p6/h10 fixed-grid stress anchor。由于

```math
h/\lambda = 10/5 = 2,
```

该网格用于压力测试 solver、动态外部通道和资源接线，不是 accuracy-qualified 的
5 nm 离散答案，也不是 continuum reference。

| h (nm) | Full3D iterative | M_robust | Hybrid direct vs Full3D | Hybrid iterative | RSS / MPI8 | 状态 |
| ---: | --- | --- | --- | --- | --- | --- |
| 10 | 4000 步 `DIVERGED_MAX_IT`，reported residual `0.1552648200050503` | `not_established` | M480 仅 diagnostic，H z=10/z=60 失败 | `not_run` | T3 direct 15.591 GiB；T4 iterative 11.749 GiB；T5 measured 见 M 表 | stress anchor only |
| 7.5 | `not_run` | `not_available` | `not_run` | `not_run` | `not_available` | blocked |
| 5 | `not_run` | `not_available` | `not_run` | `not_run` | `not_available` | blocked |

## 阶段停止原因

T7 的 p6/h7.5 reference/Hybrid qualification 未启动：T4 Full3D iterative 在冻结的
4000 步上限仍有约 0.155 residual，不能提供 Phase B 的 Full3D iterative reference；
同时 T5 没有建立 `M_robust_h10`。T8 的 p6/h5 和 MPI1 minimum-memory lane 继承同一
前置阻断。两阶段都没有 h/λ 拟合点，不能把 h10 值写成 5 nm accuracy-qualified
结果，也不能伪造资源估计为实测值。

T3 direct 的 p6/h10 authority、T4 负结果和 T5 M 漏斗分别见
[fixed-grid record](fixed_grid_full3d_reference.md)、
[T5 outcome](hybrid_m_convergence.md) 和
[T4 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t4_full3d_iterative_mpi8_negative_v1.json)。
T9 的 p6/h1 只是组件级 derived engineering scaling，见
[0.7 nm feasibility](feasibility_0p7nm.md)，不补充任何 h7.5/h5 实测点。

最终不报告 `5NM_DISCRETIZATION_NOT_CONVERGED_BY_P6H5`，因为 h5 根本没有启动；
当前更准确的状态是 Phase B `not_run/blocked`。

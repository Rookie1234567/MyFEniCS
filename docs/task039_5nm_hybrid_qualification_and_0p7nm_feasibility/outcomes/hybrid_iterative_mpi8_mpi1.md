# T6：Hybrid iterative MPI8/MPI1 边界

## 结论

T6 的 MPI8 和 MPI1 均为 `not_run/not_available`。这不是一次未记录的失败运行，
而是按任务书停止的阶段：T5 没有建立 `M_robust_h10`，且 M960 在形成 solution
之前的 canonicalized negative-trace authority 失败，因此没有合法的 M960 direct
observable/reference 可供 T6 比较。M480 不能冒充 M960。

| lane | 状态 | iterations | residual | RSS/PSS/USS | wall | 原因 |
| --- | --- | --- | --- | --- | --- | --- |
| Hybrid iterative MPI8 | `not_run` | `not_available` | `not_available` | `not_available` | `not_available` | `M_robust_h10=not_established`；没有合法 M960 direct reference |
| Hybrid iterative MPI1 | `not_run` | `not_available` | `not_available` | `not_available` | `not_available` | MPI1 只有在 MPI8 Hybrid iterative 通过后才可运行；前置 lane 未启动 |

Hybrid iterative 是在 Hybrid 方程上用矩阵作用和右侧 FGMRES（不把完整全局矩阵全部
存成一个对象）迭代求解，并用 block-LDU/局部 ILU 等既有预条件结构减少内存；它不是
本阶段已经测得的结果。T6 没有填入 0、空的迭代数或假定资源值。

## T5 传递条件

T5 的唯一选择结果为：

```text
M_robust_h10 = not_established
classification = 5NM_HYBRID_MODEL_NOT_ESTABLISHED_BY_M960_AT_P6H10
production_validation_allowed = false
blocked_by = T4_5NM_FULL3D_ITERATIVE_NUMERICAL_NEGATIVE_AT_P6H10
```

M120 和 M240 的 sampled-interface E own Gate 分别失败；M480 的 own residual、exact
traction、projection 和 closure 通过，但与 T3 direct 的 Full3D diagnostic 在 H 的
z=10 和 z=60 平面失败；M960 的 `raw_relative_error=1.678e-11` 超过 `1e-12`，没有
进入 direct solve、recovery、R/T/A 或 checker。完整事实见
[T5 M convergence record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json)
和 [T5 outcome](hybrid_m_convergence.md)。

因此不得使用 `TASK039_ITERATIVE_SOLVER_PASS_HYBRID_MODEL_FAIL_AT_5NM`：Task39
Hybrid iterative 根本没有运行。也不得用 M480 的资源、场或 QEP 数字填充 T6。

## 固定合同与后续边界

若未来获得新的审查授权，T6 必须先以正式数字 `M_robust_h10` 生成 MPI8 输入，
沿用 restart=90、max_it=6000、五项 `rtol=5e-9`、zero initial、whole-endcap
ILU(0)、two-pass 和 exact traction；只有 MPI8 通过后才可运行完全相同物理合同的
MPI1 minimum-memory lane。本次 T10 不启动这些工作。

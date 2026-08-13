# Task39 执行回应（T10 Stage A 草稿）

## 任务范围与执行结果

Task39 的执行分支为
`codex/20260812-task39-5nm-hybrid-0p7nm-feasibility`。本回应只依据已提交的五个
compact records 和 outcomes，不读取 ignored raw 来补写缺失数字。

| 阶段 | 结果 | 依据 |
| --- | --- | --- |
| T0 | inherited audit/material/resource contracts completed | existing outcomes |
| T1 | finite 5 nm profiles、provenance、dispatch 和 focused contracts completed | T1 commits、`test_268` |
| T2 | 5 nm A0 capacity/inventory authority completed | [T2 record](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t2_a0_preflight_v1.json) |
| T3 | Full3D direct MPI8 authority established | [T3 outcome](outcomes/fixed_grid_full3d_reference.md) |
| T4 | Full3D iterative numerical negative at p6/h10 | [T4 record](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t4_full3d_iterative_mpi8_negative_v1.json) |
| T5 | Hybrid direct M120→M960 funnel completed without establishing M robust | [T5 outcome](outcomes/hybrid_m_convergence.md) |
| T6 | MPI8/MPI1 not_run | [T6 boundary](outcomes/hybrid_iterative_mpi8_mpi1.md) |
| T7/T8 | not_run/blocked | [grid boundary](outcomes/grid_convergence.md) |
| T9 | component-only 0.7 nm feasibility completed; no full PDE | [T9 outcome](outcomes/feasibility_0p7nm.md) |
| T10 | Stage A docs drafted; final gates pending | [test summary](outcomes/test_summary.md) |

## 结论边界

T3 direct 的 p6/h10 运行建立了固定网格 solver/capacity authority；这不等于 5 nm
网格收敛，也不等于 Hybrid accuracy。T4 的 Full3D iterative 在冻结的 4000 步仍以
约 0.155 residual 负结束，形成 wavelength-robustness negative。T5 M480 虽 own
Gate 通过，但 Full3D diagnostic 的 H 在 z=10 和 z=60 失败；M960 在 solution 前
失败，所以 `M_robust_h10` 仍未建立。

T6 必须使用已经建立的数字 M，并要求 MPI8 先通过后才能进入 MPI1；前置条件不满足，
因此两个 lane 都 `not_run`。T7/T8 需要 Phase B 的 h7.5/h5 reference，不能以 h10
stress anchor 冒充。T9 只允许空气侧 component enumeration 和容量推导；由于 0.7 nm
substrate optical constants 缺失，完整 PDE 被 fail-closed。

最终并列分类为：

```text
TASK039_5NM_FIXED_GRID_SOLVER_CAPACITY_QUALIFIED_ONLY
TASK039_FULL3D_ITERATIVE_WAVELENGTH_ROBUSTNESS_FAIL_AT_5NM
5NM_HYBRID_MODEL_NOT_ESTABLISHED_BY_M960_AT_P6H10
HYBRID_DIRECT_DIAGNOSTIC_FAIL
0P7NM_MATERIAL_INPUT_INCOMPLETE
0P7NM_FE_FACTOR_OR_CACHE_EXCEEDS_256GIB_BUDGET
0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN
0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN
0P7NM_CONVERGENCE_RISK_UNRESOLVED
```

不得使用 `TASK039_5NM_FULL3D_HYBRID_ACCURACY_AND_MEMORY_QUALIFIED`、
`TASK039_ITERATIVE_SOLVER_PASS_HYBRID_MODEL_FAIL_AT_5NM` 或
`CURRENT_ARCHITECTURE_PLAUSIBLE`。

## 复现与待审查 Gate

所有重要身份、604 external keys、T3 的 33 significant channels、selected E/H、
canonical、DoF/rows/NNZ、RSS/PSS/USS/swap 和阶段 wall 的入口见
[summary](outcomes/summary.md)、[T3 fixed-grid outcome](outcomes/fixed_grid_full3d_reference.md)、
[T5 outcome](outcomes/hybrid_m_convergence.md) 和
[resource ledger](outcomes/resource_ledger.md)。

T10 Stage A 尚未运行 final Task-focused suite、MPI1/2/4 launcher contract、最终静态
Gate、`check_benchmarks --no-write` 或 repository `python -m pytest -q`；这些均保持
`pending`。本执行未运行完整 0.7 nm PDE，未恢复 neural/learned 路线，未修改 master，
未创建其他分支或 worktree。待主对话审查后，再决定是否仅运行任务书允许的最终 Gate。

# Case093 benchmark freeze decision

## 冻结状态

```text
status = canonical_partial_with_user_approved_reduced_scope
selected_reference = p4/h5
reference_identity = best_available_discrete_reference_for_case093
grid_convergence_proven = false
continuum_reference = false
ordinary_default_changed = false
```

canonical anchors 为 p2/h2、p3/h3、p4/h5；每个 anchor 均有 MPI8 Full3D official
result、Hybrid M160 funnel 与 same-degree closure。MPI identity 使用用户批准的代表性
p3/h5 S 点覆盖 Full3D/Hybrid 的 MPI1/8/16，另保留 MPI32 exploratory。

## 为什么是 partial

Task034 补充任务书原始范围要求每个 degree 的 S/P canonical anchor 与逐 degree MPI
矩阵。用户随后明确缩减为 S 主线、一个 p2/h5 P 可计算示例、一个代表性 p3/h5 MPI
矩阵。因此本 Case 可以关闭 adaptive 前置 Gate，但不能声称原补充书未缩减范围完整
PASS。

## Adaptive unlock

Case093 checker 重算并通过以下六项：p2 uniform measured decision、p3 uniform measured
decision、p4 same-degree closure、离散参考冻结、observable/checker 可用、MPI8 baseline
选定。由此允许进入 Phase G measured adaptive compression；任何 adaptive success 仍须
按同一 observable vector 与 p4/h5 离散参考比较。

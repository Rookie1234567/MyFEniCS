# 传递算子验证

状态：`passed_as_infrastructure`，但 `failed_as_solver_coarse_space`。

## MPI4 目标规模结果

| 项 | 结果 |
|---|---:|
| fine full / active DoF | 44,698 / 40,800 |
| coarse full / active / removed slaves | 1,067 / 792 / 275 |
| transfer shape | 44,698 × 792 |
| transfer nnz | 145,998 |
| column norm range | 1.137073–1.792694 |
| zero columns | 0 |
| adjoint identity relative error | `1.586e-15` |
| fresh/cache action relative error | `6.410e-15` |
| fresh build time | 88.833 s |

serial 与 MPI2 测试覆盖 active-column assembly、slave backsubstitution、Floquet homogenize、Hermitian restriction 和 cache round-trip；coarse Galerkin action 在 serial/MPI2 通过。MPI4 目标记录证明材料面对齐、x/y/corner Floquet trace、无零列和 fresh/cache action 一致。

当前没有宣称 curl-commuting 投影达到理论机器精度；已验证的是 N1curl 函数插值、约束一致性、伴随恒等式和 coarse action。下一代真正 h-GMG 仍需专门的 commuting projection 与近核/梯度子空间设计。

禁止路径：直接对不同网格调用 DOLFINx `interpolation_matrix`。探针证明该 API 假设同一 mesh cell 对应，会留下大量零行。

# 3D 直接求解 profile

## 配置入口

`SimulationConfig3D.petsc_direct_solver_profile_requested` 只接受 `default/mumps_ooc/mumps_blr`。runner argparse 使用相同 choices，main preset 再翻译为该 flag，三层必须同步。

## `common_3d_solve.py`

| 函数 | 作用 |
|---|---|
| `_direct_lu_petsc_options` | `preonly+lu+error_if_not_converged` |
| `_has_petsc_package` | 查询外部包 |
| `_available_parallel_lu_solver_type` | MPI 默认只选 MUMPS |
| `_mumps_ooc_minimal_options` | OOC 与工作空间 |
| `_mumps_blr_minimal_options` | BLR 与 `1e-5` 阈值 |
| `_apply_petsc_option_dict` | 用户 option 最后覆盖 profile |
| `_prepare_direct_lu_options_for_comm` | 解析 profile/MPI/包可用性 |
| `_linear_system_diagnostics` | 求解后真残差 |
| `_petsc_matrix_stats` | rows/nnz/norm/storage 估计 |

## OOC 生命周期

`_prepare_mumps_ooc_runtime` 把环境变量指向当前 case 目录。成功由 `_cleanup_mumps_ooc_directory_on_success` 删除临时文件；失败由 `_retain_mumps_ooc_directory_on_failure` 记录现场。清理仅发生在 solver/PETSc 对象释放后，避免仍打开因子文件。

## 失败语义

`DirectSolveFailure` 携带 failure stage、PETSc exception、矩阵/向量/KSP、backend 和 timing，case flow 先写 failure summary 再销毁。MPI 无并行 LU 时是环境失败，不是物理不收敛。

## BLR 语义

BLR 依然返回 direct residual 和 factor backend；文档/UI 不得把其 KSP iteration 写成迭代求解次数。profile option 被额外覆盖后，应在 summary 保存最终 PETSc options。

测试：`test_18` profile/options，`test_19` OOC 清理；case 030 记录 direct fallback 边界。

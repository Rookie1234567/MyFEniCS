# Task029 direct object lifecycle inventory

本表对应 H1–H3/H7。对象所有权以当前公共 Stage4 auxiliary DtN 路径为准；ordinary default 不提前释放 base 或 factor，Task29 候选只能显式 opt-in。

| 对象 | owner / creation site | 最后用途 | baseline destroy site | 峰值共存区间 | Task29 判定 |
|---|---|---|---|---|---|
| constrained `A_base` | `solve_stage4_dtn_port_total_field`；`dolfinx_mpc.assemble_matrix` | `_copy_base_matrix_to_augmented` 完成逐行复制 | 函数返回后的 Python/PETSc 清理 | base copy 至 KSPSetUp、solve、RTA | H1 候选在 copy 后显式 destroy |
| `b_base` | 同函数；`_assemble_mpc_vector` | `_augmented_vec_from_base` 完成复制 | 函数返回后 | 与 `b_aug`、factor 同存 | 与 `A_base` 一并释放 |
| `A_aug` | `_copy_base_matrix_to_augmented` | true residual、common flow matrix stats/diagnostics | case flow 返回后 | DtN coupling、KSPSetUp、solve、postprocess | 必须保留到 residual/diagnostics；不提前删 |
| `b_aug` | `_augmented_vec_from_base` | true residual、common flow diagnostics | case flow 返回后 | KSPSetUp 至 postprocess | 必须保留到 diagnostics |
| `x_aug` | `_solve_augmented_system` 的 `b_aug.duplicate()` | residual、FE field reconstruction、auxiliary R/T amplitudes、common diagnostics | case flow 返回后 | solve 至 postprocess | required；不能为省内存删除证据 |
| KSP + factor | `_solve_augmented_system` | solve 后 common flow 读取 reason/type/factor package | case flow 返回后 | KSPSetUp 主峰至 postprocess | H7 只影响尾部平台，本任务不作为主峰候选 |
| residual Vec | `_linear_residual` / `_linear_system_diagnostics` | norm 计算 | helper 内立即 destroy / 退出 | residual checkpoint | 短生命周期且必需 |
| FE reconstruction `x_fe` | `_assign_fe_solution_from_augmented` | `fem_petsc.assign` + MPC backsubstitution | helper 内显式 destroy | solve 后短暂 | 已正确释放 |
| incident traction Vec | DtN source assembly | owned nonzero entries提取 | 立即显式 destroy | coupling assembly | 已正确释放 |
| reusable surface component Vec | `_ReusableSurfaceComponentAssembler.assemble_entries` | owned entries提取 | `finally` 中显式 destroy | 每个 mode component assembly | 已正确释放；缓存的是 NumPy entries |
| unconstrained diagnostic Mat | `_assemble_unconstrained_matrix_stats`，仅显式诊断 | matrix stats | helper 内显式 destroy | diagnostic-only | ordinary default 不创建 |
| assemble-only `A/b/x/KSP` | diagnostic path | diagnostic summary | 返回/调用者清理 | assemble-only | 不属于 full-solve candidate |
| failure `A/b/x/KSP` | `DirectSolveFailure` 临时持有 | failure summary、PETSc error、matrix diagnostics 写盘 | `DirectSolveFailure.cleanup()` | 异常报告期间 | Task29 改为写盘后幂等显式清理 |

## H1 所有权证明

`A_aug` 和 `b_aug` 已拥有独立 PETSc storage；复制完成后，DtN coupling 只写入 augmented 对象，KSP、true residual、FE reconstruction 和 official R/T/A 也只读取 augmented system。`base_matrix_stats` 是普通 Python 字典，不依赖活的 `A_base`。因此 `direct_release_base_after_augmentation=true` 时销毁 `A_base/b_base` 不改变矩阵、右端项或数学模型。

## H2/H3 否定证据

h5/h3 baseline 的 base/augmented `nz_allocated == nz_used`、`nz_unneeded == 0`、`mallocs == 0`；当前可见 PETSc 信息没有支持预分配重写的正信号。ordinary default 的 `unconstrained_matrix_stats` 为 `null`、`matrix_diagnostics_assemble_only=false`，不存在额外默认诊断矩阵。需要保留的 residual、field reconstruction 和 surface vectors 均有明确短生命周期。

## H7 边界

h3 factor/KSP 在 field output 期间仍被引用，但 field-output cgroup current 约 8026.98 MB，低于 KSPSetUp 全局峰值 8353.73 MB；field output 相对 solve 后仅增加约 112.51 MB。提前销毁 factor 可降低尾部平台，却不能消除已经发生的 factorization 主峰，因此本轮不把它当作 20% 峰值候选。

# CODEX TASK 20260709：p=2 h=2 Schur/FE-response PC preflight and productionization bridge

## 0. 任务定位

Task022 是 Task021 的巩固任务，不是重新探索求解器路线。

Task021 已在目标模型上证明：

```text
target p=2 h=5 baseline residual = 2.025767e-1
SPILU coupled PC m=1 residual    = 9.865457e-7
SPILU block Schur PC residual    = 2.430285e-7
exact FE-block Schur residual    = 8.155352e-12
```

因此 Task022 的目标是把这个重大突破推进到下一层：

```text
p=2 h=2 preflight
+ matrix-free support for memory pressure
+ PETSc/MPI-safe PC 设计
+ converged solution official R/T/A validation
```

ChatGPT 不创建分支。Codex 如需新分支，应自行从 review 后合适 base 创建。

---

## 1. 必须使用的 physical model

继续使用目标模型，不得回到 default100：

```text
domain size = 50 x 25 x 140 nm
period = 50 x 25 nm
grating size = 17 x 25 x 120 nm
substrate thickness = 10 nm
top air above grating = 10 nm
air_height parameter = 130 nm
theta_from_z = 80 deg
phi = 0 deg
polarization = s, E along y
material n = 0.999002304859 + 0.00182649365j
boundary = double Floquet x/y + auxiliary DtN port
power source = dtn_port_modal_amplitudes + A_volume
```

---

## 2. 主线候选

Task022 只推进两个 Schur / FE-response 候选和一个 matrix-free 支撑方向，不再重新微调失败路线。

### Candidate A：SPILU coupled PC m=1

理由：

```text
只使用 top (0,0) s dominant auxiliary mode；
p=2 h=5 residual = 9.865457e-7；
结构最小，更适合 h=2 preflight。
```

### Candidate B：SPILU block Schur PC

理由：

```text
full aux block Schur 结构最接近真实 block preconditioner；
p=2 h=5 residual = 2.430285e-7；
2 个 history points 达到 production-like。
```

### Support C：matrix-free FE action / MatShell support

理由：

```text
matrix-free 可以降低 assembled FE matrix / matvec 的存储压力；
它不能直接让 exact FE-block Schur 变便宜，因为 Schur 仍需要近似 A_FE^{-1}；
但它可以作为 h=2 及更细网格的 MatShell 基础设施，和 SPILU/ASM/AMS/HX/BLR 等近似 FE inverse 组合。
```

### 上界参考：exact FE-block Schur

只作为研究上界，不得包装成低内存 production method。

---

## 3. 不再继续的方向

不要继续：

```text
aux-only PC
diag FE response
Jacobi baseline parameter tuning
fixed top_bottom_y sampled Schur
Petrov W / right-only lifted correction
Route A row-index layer proxy
Route B diagonal sweeping proxy
h=1.5 / h=1 before h=2 preflight
```

---

## 4. Matrix-free 的正确定位

Matrix-free 值得探索，但必须定位准确。

### 4.1 它能解决什么

```text
1. 减少 assembled FE matrix 存储；
2. 为 p=2 h=2 及更细网格提供 FE MatShell matvec；
3. 避免 h=2/h=1.5 时 AIJ matrix 和复制到 SciPy CSR 成为主要内存瓶颈；
4. 作为 PETSc Krylov 外层算子的基础。
```

### 4.2 它不能直接解决什么

```text
1. matrix-free 只给 A_FE x，不自动给 A_FE^{-1} r；
2. exact FE-block Schur 的核心成本是求解 A_FE^{-1}，不是只做 matvec；
3. 因此 matrix-free 不能直接把 exact FE-block Schur 变成低内存方法；
4. 仍然需要近似 FE inverse：SPILU、ASM+ILU、AMS/HX-smoothed response、MUMPS/BLR、multigrid 或 external factor service。
```

### 4.3 本任务中的使用原则

```text
先用 assembled h=2 做 Schur/FE-response preflight；
如果 assembled A 或 SciPy CSR conversion 成为瓶颈，立即进入 matrix-free support stage；
matrix-free 只作为 matvec/storage 层，不替代 FE inverse / PC；
所有 matrix-free 结果都必须和 assembled matvec 对照。
```

---

## 5. Stage A：p=2 h=5 reproducibility lock

先复现 Task021 的 p=2 h=5 结果，确认代码和结果稳定。

必须复现：

```text
SPILU coupled PC m=1 residual < 1e-6
SPILU block Schur PC residual < 1e-6
exact FE-block Schur residual << 1e-6 as upper bound
```

输出：

```text
outcomes/h5_reproducibility.csv
outcomes/h5_residual_history.csv
```

若 h=5 不能复现，不进入 h=2。

---

## 6. Stage B：p=2 h=2 assemble and resource preflight

目标：在目标模型 p=2 h=2 上建立矩阵和资源边界。

必须输出：

```text
outcomes/h2_resource_preflight.csv
```

字段至少包括：

```text
p,h_nm,rows,nnz,n_fe,n_aux,rss_upper_gb,assembly_time_s,dtn_assembly_s,estimated_aij_mb,scipy_csr_conversion_s,scipy_csr_rss_delta_gb,notes
```

如果 h=2 assembled matrix / conversion to SciPy CSR 触发内存边界，必须记录具体阶段，不要继续硬跑。

---

## 7. Stage C：p=2 h=2 dominant auxiliary mode mapping

目标：确认 h=2 下主导 auxiliary mode 是否仍为 top `(0,0)` s。

输出：

```text
outcomes/h2_aux_mode_mapping.csv
outcomes/h2_residual_decomposition.csv
```

必须记录：

```text
local aux index
global row
side
Rayleigh order
polarization
propagating
aux residual magnitude
fraction of aux residual norm
fraction of total residual norm
```

如果主导 mode 不再是 top `(0,0)` s，应更新 m=1 candidate，不得硬套 h=5 index。

---

## 8. Stage D：p=2 h=2 Candidate A preflight

测试 SPILU coupled PC m=1。

最低测试：

```text
FE response = SPILU drop=1e-3 fill=12
coarse modes = dominant aux mode only
outer solver = GCROT(m,k) or PETSc equivalent
max history / maxiter: adaptive, but record true residual every step
```

输出：

```text
outcomes/h2_spilu_coupled_m1_summary.csv
outcomes/h2_spilu_coupled_m1_history.csv
```

Gate：

```text
minimum useful: residual < 1e-2 或 improvement >= 2x
strong: residual <= 2e-3 或 improvement >= 10x
production-like: residual <= 1e-6
```

如果 m=1 正信号不足，可测试 m=2 / m=4，但必须记录为什么扩维。

---

## 9. Stage E：p=2 h=2 Candidate B preflight

测试 SPILU block Schur PC。

输出：

```text
outcomes/h2_spilu_block_schur_summary.csv
outcomes/h2_spilu_block_schur_history.csv
```

必须记录：

```text
FE factorization time
FE fill nnz
SPILU drop/fill settings
coarse/block Schur dimension
true residual history
memory peak
failure stage if any
```

如果 block Schur h=2 内存超过 workstation 上限，停止并记录，不要跳 h=1.5。

---

## 10. Stage F：matrix-free FE action / MatShell support

本 stage 是新增的内存巩固方向，服务 Candidate A/B，不单独作为 solver 成功路线。

### 10.1 触发条件

进入本 stage 的条件之一：

```text
h=2 assembled A 或 SciPy CSR conversion 接近 workstation 内存上限；
h=2 SPILU fill-in 过大；
准备把 serial SciPy prototype 迁移为 PETSc/MPI-safe PC；
计划未来进入 h=1.5 或 h=1。
```

### 10.2 最低验证

必须至少验证：

```text
assembled FE matvec vs matrix-free FE action relative error <= 1e-10 on p=2 h=5 or smaller representative target-geometry case；
MatShell action works with complex PETSc scalar type；
DtN auxiliary coupling still uses explicit small aux block or matrix-free wrapper；
true residual can be computed consistently。
```

输出：

```text
outcomes/matrix_free_fe_action_equivalence.csv
outcomes/matrix_free_memory_projection.md
outcomes/matshell_design_notes.md
```

### 10.3 与 exact Schur 的关系

必须在报告中明确：

```text
matrix-free 不会直接降低 exact FE-block Schur 的求逆成本；
exact FE-block Schur 仍需 A_FE^{-1}，需要 direct factorization 或等效内解；
matrix-free 的价值在于避免显式存储 A_FE，并为近似内解 / Krylov inner solve / ASM / AMS-HX / BLR 提供 matvec。
```

---

## 11. Stage G：PETSc/MPI-safe PC design

无论 h=2 是否完全跑通，都必须输出生产化设计文档。

输出：

```text
outcomes/petsc_pc_design.md
outcomes/migration_risk_register.md
```

必须回答：

```text
1. serial SciPy SPILU 如何迁移到 PETSc PCShell / MatShell？
2. FE block solve 用 PETSc ILU、ASM+ILU、MUMPS/BLR、hypre AMS/HX-smoothed response，还是 external factor service？
3. matrix-free FE MatShell 如何接入 outer KSP 和 inner FE-response solve？
4. 如何避免 same-process PETSc selected FE-AMS lifecycle 风险？
5. 如何在 MPI 下处理 FE block / auxiliary block ownership？
6. 如何把 true residual 和 official R/T/A 接回 existing Stage4 pipeline？
```

---

## 12. Stage H：official R/T/A validation at h=5

在 h=5 converged iterative solution 上输出 official R/T/A，并与 direct/reference 对比。

输出：

```text
outcomes/h5_iterative_official_rta.csv
outcomes/h5_iterative_vs_direct_rta.csv
```

如果当前 research runner 还不能输出 field solution 或 R/T/A，必须记录缺失接口，并在 next decision 中列为 blocking item。

---

## 13. Gate decision

输出：

```text
outcomes/gate_decision.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
```

必须明确：

```text
1. h=5 是否稳定复现 production-like？
2. h=2 是否达到 minimum / strong / production-like？
3. Candidate A 和 B 谁更适合 productionization？
4. h=2 失败是否由内存、factorization、mode selector、FE response、matrix-free gap 或 integration 引起？
5. 是否允许 h=1.5 preflight？
6. 是否可以开始 PETSc/MPI implementation task？
7. matrix-free 是否应进入下一阶段主线，还是仅作为后续 h<2 支撑？
```

---

## 14. 合并策略

默认：

```text
merge_docs: yes, after review
merge_code: no by default
merge_research_runner: optional, opt-in only
production_default_change: no
```

只有当 PETSc/MPI-safe PC 和 official R/T/A validation 通过后，才能讨论 production default solver。

---

## 15. 最终目标句

任务结束时必须回答：

```text
Task021 的 DtN auxiliary FE-response / Schur 预条件器能否从目标模型 p=2 h=5 推进到 p=2 h=2 preflight，并判断 matrix-free FE action 是否能作为 h=2/h<2 的内存支撑和 PETSc/MPI production PC 基础？
```

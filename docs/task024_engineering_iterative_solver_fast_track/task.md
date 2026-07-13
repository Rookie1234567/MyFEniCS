# CODEX TASK 20260710：engineering iterative solver fast track

## 0. 目标

Task024 不再做开放式求解器全扫，目标是尽快交付一个可用、可调用、可继续扩展的工程迭代求解器。

当前结论：

```text
p=2 h=5：PETSc/MPI FieldSplit/Schur + FE response 已 production-like，official R/T/A 已与 direct 闭环。
p=2 h=2：矩阵装配和 top (0,0) s mode selector 均正常，失败点是低内存近似 A_FE^{-1}。
plain ASM/ILU 太弱；local LU/MUMPS 足够强但 h=2 太慢。
```

ChatGPT 不创建分支。Codex 如需新分支，应自行创建。

## 1. Physical model

必须继续使用：

```text
domain = 50 x 25 x 140 nm
period = 50 x 25 nm
grating = 17 x 25 x 120 nm
substrate / top air = 10 nm / 10 nm
theta_from_z = 80 deg, phi = 0 deg
polarization = s, E along y
material n = 0.999002304859 + 0.00182649365j
boundary = double Floquet x/y + auxiliary DtN port
```

## 2. 总体策略

按以下顺序推进：

```text
Track A：先固化 h=5 opt-in engineering solver。
Track B：主攻 real-split same-H1 AMS/HX FE-response service，突破 h=2。
Track C：若 AMS/HX 早期 gate 失败，启动 COMSOL-inspired GMG-lite FE response。
Fallback：selected-response LU/MUMPS/BLR cache，只作 reference/fixed-operator fallback。
```

禁止继续无边界扫描 plain ASM/ILU、独立 SOR/Jacobi/Vanka 或直接进入 h=1.5。

## 3. 固定数学结构

保持：

```math
\begin{bmatrix}A_{FE}&C\\D&A_{aux}\end{bmatrix}
\begin{bmatrix}x_{FE}\\x_{aux}\end{bmatrix}
=
\begin{bmatrix}b_{FE}\\b_{aux}\end{bmatrix}.
```

selected mode 的 FE response：

```math
q_j \approx -A_{FE}^{-1}C_j,
\qquad
z_j=\begin{bmatrix}q_j\\e_j\end{bmatrix}.
```

Task024 只改进 `A_FE^{-1}` 的低内存近似，不改变 FE-response + auxiliary Schur 主结构。

## 4. Stage A：h=5 工程求解器固化

把已成功的 PETSc FieldSplit/Schur + FE LU/local LU 做成正式入口可显式选择的 opt-in profile，不修改 ordinary default。

必须通过：

```text
true residual <= 1e-6
official R/T/A 与 direct 绝对差 <= 1e-8
closure error <= 1e-8
MPI=1 和 MPI=4 均通过
peak RSS、setup time、solve time 有记录
失败时有清晰 fallback 信息
```

输出：

```text
outcomes/h5_engineering_profile_regression.csv
outcomes/h5_mpi_consistency.csv
outcomes/h5_official_rta_regression.csv
outcomes/h5_failure_and_fallback.md
```

通过后可标记：

```text
h=5 opt-in engineering solver available
```

不能标记为 production default。

## 5. Stage B：real-split same-H1 AMS/HX FE-response service

这是第一突破主线。

建立服务：

```text
input: selected FE RHS C_j
output: filtered q_j ≈ -A_FE^{-1}C_j
```

把 complex FE block 转成 real 2x2 block，并复用 Task013 已验证的 same-H1 AMS/HX auxiliary data。

要求：

```text
AMS hierarchy 在进程启动早期构造一次并复用；
使用独立 PETSc options prefix；
避免 repeated setup/destroy；
必要时采用 isolated worker，但接口必须明确。
```

只做有限 response sweep：

```text
inner steps = 1,3,5,10,20
inner rtol = 1e-1,1e-2,1e-3
damping = 0.25,0.5,1.0
先 m=1；m=1 positive 后才测试 m=2/4
```

记录：

```text
inner true residual
relative FE column cancellation = ||A_FE q_j + C_j|| / ||C_j||
与 h=5 LU reference response 的相关性
one-shot coupled residual
outer true residual
peak RSS、setup/reuse/apply time
```

输出：

```text
outcomes/ams_hx_service_design.md
outcomes/ams_hx_hierarchy_lifecycle.csv
outcomes/ams_hx_response_quality_h5.csv
outcomes/ams_hx_response_quality_h2.csv
outcomes/ams_hx_outer_solver_history.csv
```

### AMS/HX gates

h=5 selected response：

```text
column cancellation < 1e-2，或 one-shot residual 明显优于 ASM/ILU
```

h=5 coupled solve：

```text
residual <= 1e-6，R/T/A 与 direct 差 <= 1e-8
```

h=2 selected response：

```text
column cancellation < 1e-2，或 one-shot residual 小于 ASM/ILU 结果的一半
peak RSS < 14 GB
```

h=2 solver：

```text
minimum: residual < 1e-2 或 improvement >= 2x
strong: residual <= 2e-3 或 improvement >= 10x
production-like: residual <= 1e-6
```

Task024 最低突破目标是 h=2 minimum。

## 6. Stage C：COMSOL-inspired GMG-lite FE response

只有 AMS/HX 在早期 gate 失败或被生命周期阻塞时启动。

COMSOL 成功结构参考：

```text
right-preconditioned TFQMR/GMRES
5-level GMG, V-cycle
pre smoother: SOR + Vanka
post smoother: SOR + SOR Vector
coarse solve: MUMPS
```

不要求逐项复刻，但必须复现：

```text
局部/高频误差由 patch smoother 处理；
全局低频误差进入 coarse space；
只在小粗层使用直接解。
```

先做 selected RHS FE response，不先做完整 outer solver。

最小候选：

```text
h=5 fine -> h=10 coarse，或 p=2 fine -> p=1 coarse
patch ASM/local LU 或 edge-patch smoother
coarse PETSc LU/MUMPS
```

必须先验证 H(curl) transfer，再测试 response quality。

输出：

```text
outcomes/gmg_lite_design.md
outcomes/gmg_transfer_validation.csv
outcomes/gmg_smoother_ablation.csv
outcomes/gmg_response_quality_h5.csv
outcomes/gmg_response_quality_h2.csv
```

h=5 selected response gate：

```text
column cancellation < 1e-2，或 one-shot residual 明显优于 ASM/ILU
```

只有 h=5 positive 才进入 h=2。

## 7. Matrix-free

Matrix-free 不是独立 solver。只有 AMS/HX 或 GMG 已提供有效 inner PC 后才接入：

```text
matrix-free A_FE action + AMS/HX inner PC
或 matrix-free A_FE action + GMG inner PC
+ explicit small auxiliary Schur
```

禁止再次测试 matrix-free + weak/no inner PC。

输出：

```text
outcomes/matrix_free_with_strong_inner_pc.csv
outcomes/matrix_free_memory_gain.md
```

## 8. Engineering fallback

若 AMS/HX 和 GMG-lite 都不能让 h=2 达到 minimum，交付：

```text
external selected-response LU/MUMPS/BLR service
cache q_j for fixed operator / repeated RHS
reuse factorization or response columns
```

必须明确：它不是通用低内存方案，只是固定算子工程 fallback。

输出：

```text
outcomes/selected_response_cache_fallback.md
outcomes/fallback_vs_direct.csv
```

## 9. 决策漏斗

必须按顺序执行：

```text
A. h=5 engineering profile + R/T/A regression
B. AMS/HX h=5 selected response
C. AMS/HX h=5 coupled solve
D. AMS/HX h=2 selected response
E. AMS/HX h=2 outer solve
F. AMS/HX 对应 early gate 失败时启动 GMG-lite
G. 强 inner PC 成立后才加 matrix-free
H. 两条低内存路线均失败时交付 fallback
```

## 10. 统一记录

每个 case 记录：

```text
p,h,MPI ranks,rows,nnz,n_FE,n_aux
outer solver/PC, inner solver/PC
selected modes
inner residual/cancellation
outer true residual history
R/T/A if converged
setup time, solve time, peak RSS
failure stage
```

残差统一使用：

```math
\|Ax-b\|/\|b\|.
```

## 11. 必须输出

```text
outcomes/summary.md
outcomes/h5_engineering_profile_regression.csv
outcomes/h5_mpi_consistency.csv
outcomes/h5_official_rta_regression.csv
outcomes/ams_hx_service_design.md
outcomes/ams_hx_hierarchy_lifecycle.csv
outcomes/ams_hx_response_quality_h5.csv
outcomes/ams_hx_response_quality_h2.csv
outcomes/ams_hx_outer_solver_history.csv
outcomes/gmg_lite_design.md
outcomes/gmg_transfer_validation.csv
outcomes/gmg_smoother_ablation.csv
outcomes/gmg_response_quality_h5.csv
outcomes/gmg_response_quality_h2.csv
outcomes/matrix_free_with_strong_inner_pc.csv
outcomes/selected_response_cache_fallback.md
outcomes/gate_decision.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
outcomes/parameters.json
```

## 12. summary.md 必答

```text
1. h=5 opt-in engineering profile 是否可调用、可回归、可输出 official R/T/A？
2. MPI=1/4 是否一致？
3. AMS/HX hierarchy 是否能稳定构造并复用？
4. AMS/HX h=5/h=2 response cancellation 是多少？
5. AMS/HX + auxiliary Schur 是否达到 h=2 minimum/strong？
6. GMG-lite transfer/smoother/coarse solve 是否跑通？
7. GMG-lite response 是否优于 ASM/ILU？
8. matrix-free 是否与强 inner PC 结合并产生实际收益？
9. 当前最快可用工程 solver 是什么？
10. 当前最有希望推进 h<2 的路线是什么？
```

## 13. Merge strategy

```text
merge_docs: yes after review
merge_h5_opt_in_profile: yes only after engineering gate
merge_h2_experimental_profiles: no default
production_default_change: no
```

## 14. 最终目标句

```text
是否已经交付稳定可调用的 h=5 工程迭代求解器，并且 real-split AMS/HX 或 COMSOL-inspired GMG-lite 至少有一条路线能在 14 GB 内把 p=2 h=2 推进到 minimum useful？
```

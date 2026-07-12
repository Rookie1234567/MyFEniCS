# CODEX TASK 20260709：PETSc/MPI-safe FE-response PC for DtN auxiliary Schur correction

## 0. 任务定位

Task023 是 Task022 后的核心工程化任务。

Task021 证明了数学结构：

```text
DtN auxiliary residual-aware mode selector
+ FE response
+ Schur / block preconditioner
```

能在目标模型 p=2 h=5 上达到 production-like residual。

Task022 证明了 h=2 的真正瓶颈：

```text
h=2 matrix/CSR 可完成；
h=2 主导 mode 仍为 top (0,0) s；
serial SciPy SPILU factorization 无法鲁棒推进到 h=2；
真正问题是如何低内存、可并行地近似 A_FE^{-1}。
```

因此 Task023 的目标是：

```text
用 PETSc/MPI-safe 方式实现和比较多种低内存 FE-response 近似，替代 serial SciPy SPILU/SPLU。
```

ChatGPT 不创建分支。Codex 若需要新分支，应自行从合适 base 创建。

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

## 2. 最高优先级原则

本任务不是重新探索所有旧路线，而是围绕同一个问题走到底：

```text
如何低内存、可并行、可工程化地近似 A_FE^{-1}，从而构造有效 FE response。
```

Codex 可以尝试多条 FE-response 近似路线，但每条路线都必须做到：

```text
1. 有最小可判定 prototype；
2. 有 h=5 residual benchmark；
3. 若 h=5 有正信号，必须推进到 h=2 preflight；
4. 如果失败，必须定位失败阶段并提出可验证修复；
5. 不得只写“后续可尝试”。
```

对于有物理意义和正信号的路线，要继续深入，直到：

```text
production-like success
strong success
明确失败
资源边界
或需要单独工程化任务
```

---

## 3. 目标模型下的固定物理 slow mode

默认从 Task021/Task022 已确认的主导 mode 开始：

```text
side = top
Rayleigh order = (0,0)
polarization = s
local aux index = 38
```

但每次 h=5/h=2 run 都必须重新验证 mode mapping，不得盲目硬编码 index。

输出：

```text
outcomes/mode_mapping_validation.csv
```

---

## 4. Stage A：reduced solution reconstruction and h=5 official R/T/A

这是第一优先级。Task021/022 已经验证 reduced linear residual，但还没有把 converged reduced vector 回填到 Stage4 field。

目标：

```text
把 h=5 converged reduced vector scatter / reconstruct 回原始 H(curl) Function；
调用现有 official dtn_port_modal_amplitudes + A_volume 后处理；
与 direct/reference h=5 R/T/A 对比。
```

输出：

```text
outcomes/h5_reduced_solution_reconstruction.md
outcomes/h5_iterative_official_rta.csv
outcomes/h5_iterative_vs_direct_rta.csv
```

如果不能完成，必须记录缺失接口：

```text
MPC backsubstitution
FE/aux splitting
Function vector ownership
field reconstruction
postprocess API gap
```

没有 h=5 R/T/A 闭环前，不得声称 production solver 完成。

---

## 5. Stage B：PETSc MatShell / PCShell skeleton

目标：把 serial SciPy prototype 的 Schur/FE-response structure 迁移到 PETSc framework。

必须实现或设计：

```text
MatShell: reduced Stage4 action, or FE MatShell + explicit small aux coupling
PCShell: apply Schur/FE-response preconditioner
true residual monitor: ||Ax-b||/||b||
auxiliary mode selector: top (0,0) s but verified by mapping
debug option: compare MatShell action vs assembled action on h=5
```

输出：

```text
outcomes/petsc_shell_skeleton.md
outcomes/matshell_vs_assembled_action.csv
outcomes/pcshell_apply_smoke.csv
```

Gate：

```text
MatShell action relative error <= 1e-10 on h=5 or representative target case
PCShell apply does not crash and produces finite correction
```

---

## 6. Stage C：Route 1 - PETSc ASM/GASM + local ILU/LU FE response

目标：用 PETSc 原生 domain decomposition 近似 `A_FE^{-1}`。

候选：

```text
PCASM + sub_pc_type ilu
PCASM + sub_pc_type lu, if local blocks small enough
PCGASM if available
vary overlap = 0,1,2
vary local solver fill / levels if supported
```

测试：

```text
h=5: reproduce residual < 1e-6 if possible
h=2: if h=5 positive, run resource and residual preflight
```

输出：

```text
outcomes/route1_asm_ilu_summary.csv
outcomes/route1_asm_ilu_history.csv
outcomes/route1_asm_ilu_resource.csv
```

失败时必须说明：

```text
local ILU too weak
local factor memory too high
overlap too small
parallel ownership issue
MatShell/PCShell integration issue
```

---

## 7. Stage D：Route 2 - AMS/HX-smoothed FE response

这是本任务重点路线。

理由：

```text
A_FE 是 H(curl) Maxwell FE block；
AMS/HX 与 Nédélec / H(curl) 空间物理结构匹配；
过去 AMS/HX 单独解 full coupled system 不够强，但现在角色不同：只需要近似 selected FE response q_j = -A_FE^{-1} C_j；
与 DtN auxiliary slow mode selector 结合后，可能比普通 global AMS/HX 更有效。
```

候选实现：

```text
real-split AMS/HX-smoothed FE response
complex FE response with safe PETSc options, if available
AMS/HX as inner KSP preconditioner for A_FE q = -C_j
AMS/HX + low iteration filtered response, not exact solve
AMS/HX + auxiliary Schur coarse correction
```

必须测试不同 response strength：

```text
inner iterations = 1, 3, 5, 10, 20
rtol loose = 1e-1, 1e-2, 1e-3
optional damping/scaling of q_j
```

目标不是把 inner FE solve 解到很精确，而是获得有用的 filtered FE response。

输出：

```text
outcomes/route2_ams_hx_fe_response_summary.csv
outcomes/route2_ams_hx_fe_response_history.csv
outcomes/route2_response_quality.csv
outcomes/route2_lifecycle_risk.md
```

必须特别记录：

```text
是否复现 task013 FE-only AMS/HX 正信号；
是否避免 task017-task019 same-process selected FE-AMS lifecycle 风险；
是否需要 isolated worker 或 PETSc options prefix；
h=5 是否达到 strong / production-like；
h=2 是否有正信号。
```

---

## 8. Stage E：Route 3 - MUMPS/BLR or direct/compressed FE inner solve

目标：作为强对照和 fallback，不包装为最终低内存路线。

候选：

```text
PETSc KSPPREONLY + MUMPS for FE block
MUMPS BLR if available through PETSc options
reuse factorization across PC applies
one-time FE response build for selected modes
```

用途：

```text
validate PETSc shell integration
provide h=2 strong reference if memory allows
compare against ASM/AMS/HX response quality
```

输出：

```text
outcomes/route3_mumps_blr_inner_summary.csv
outcomes/route3_mumps_blr_resource.csv
```

如果内存接近直接法，不应作为 final low-memory candidate，但可保留为 engineering fallback。

---

## 9. Stage F：Route 4 - matrix-free FE MatShell + inner Krylov

目标：探索 matrix-free 作为 h=2/h<2 的 memory support。

注意：matrix-free 不是独立 solver，也不会直接提供 `A_FE^{-1}`。它必须配合 inner Krylov + inner PC。

候选组合：

```text
matrix-free A_FE action + ASM/ILU inner PC
matrix-free A_FE action + AMS/HX inner PC
matrix-free A_FE action + BLR/direct fallback for coarse/small blocks
```

最低验证：

```text
matrix-free A_FE action vs assembled A_FE action relative error <= 1e-10
inner FE-response solve produces finite q_j
outer Schur/FE-response correction lowers true residual
```

输出：

```text
outcomes/route4_matrix_free_inner_krylov_summary.csv
outcomes/route4_matrix_free_action_equivalence.csv
outcomes/route4_memory_projection.md
```

---

## 10. Stage G：Route 5 - hybrid FE response strategies

Codex 可以组合路线，但必须有明确动机。

允许组合：

```text
AMS/HX-smoothed response + one dominant aux mode
ASM/ILU response + auxiliary Schur correction
MUMPS/BLR response as fallback only for selected modes
matrix-free action + AMS/HX inner + explicit 80-dof aux Schur
```

不允许组合：

```text
盲目堆多个 PC 而不记录贡献；
为了追 residual 无限制增加内存；
把 exact Schur 当 production low-memory；
未通过 h=5 就直接 h=2/h=1.5。
```

输出：

```text
outcomes/route5_hybrid_ranking.csv
outcomes/route5_component_ablation.csv
```

---

## 11. Gate thresholds

所有 gate 使用完整真实残差：

```text
||A x - b|| / ||b||
```

统一判据：

```text
minimum useful: residual < 1e-2 或 improvement >= 2x
strong: residual <= 2e-3 或 improvement >= 10x
production-like: residual <= 1e-6
```

必须区分：

```text
h=5 proof-of-concept
h=2 preflight
production implementation
```

---

## 12. 必须输出文件

```text
docs/task023_petsc_mpi_fe_response_pc/outcomes/summary.md
docs/task023_petsc_mpi_fe_response_pc/outcomes/mode_mapping_validation.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/h5_reduced_solution_reconstruction.md
docs/task023_petsc_mpi_fe_response_pc/outcomes/h5_iterative_official_rta.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/h5_iterative_vs_direct_rta.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/petsc_shell_skeleton.md
docs/task023_petsc_mpi_fe_response_pc/outcomes/matshell_vs_assembled_action.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/pcshell_apply_smoke.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/route1_asm_ilu_summary.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/route2_ams_hx_fe_response_summary.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/route2_response_quality.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/route2_lifecycle_risk.md
docs/task023_petsc_mpi_fe_response_pc/outcomes/route3_mumps_blr_inner_summary.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/route4_matrix_free_inner_krylov_summary.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/route4_matrix_free_action_equivalence.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/route5_hybrid_ranking.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/gate_decision.csv
docs/task023_petsc_mpi_fe_response_pc/outcomes/solver_profile_ranking.md
docs/task023_petsc_mpi_fe_response_pc/outcomes/merge_recommendation.md
docs/task023_petsc_mpi_fe_response_pc/outcomes/next_decision.md
docs/task023_petsc_mpi_fe_response_pc/outcomes/parameters.json
```

`raw_runs/` 只允许轻量日志，不提交大型 matrix、mesh、XDMF、VTU、HDF5 或 results。

---

## 13. summary.md 必须回答

```text
1. h=5 reduced solution 是否能回填并输出 official R/T/A？
2. PETSc MatShell / PCShell skeleton 是否跑通？
3. 哪种 FE response 近似最有希望低内存近似 A_FE^{-1}？
4. ASM/ILU 在 h=5/h=2 表现如何？
5. AMS/HX + FE response 是否比旧 AMS/HX 全局路线更有效？
6. MUMPS/BLR 是可用 fallback 还是太接近直接法？
7. matrix-free 是否只作为 support，还是能进入 inner Krylov 主线？
8. h=2 是否达到 minimum / strong / production-like？
9. 失败点属于 mode selector、FE response、MatShell/PCShell、MPI ownership、内存还是 R/T/A reconstruction？
10. 下一步是否进入 production implementation task？
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

只有满足以下条件才讨论 production path：

```text
h=5 official R/T/A 回填成功；
PETSc/MPI-safe PCShell 稳定；
h=2 至少 minimum useful，最好 strong；
true residual monitor 可靠；
没有大型临时文件进入 Git。
```

---

## 15. 最终目标句

任务结束时必须回答：

```text
在目标模型上，哪一种 PETSc/MPI-safe FE response 近似最有希望低内存替代 A_FE^{-1}，并把 Task021 的 Schur/FE-response 突破从 h=5 proof-of-concept 推进到 h=2 可工程化 preflight？
```

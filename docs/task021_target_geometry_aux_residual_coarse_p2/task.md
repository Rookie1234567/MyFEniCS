# CODEX TASK 20260709：target-geometry p=2 DtN auxiliary residual-aware coarse correction

## 0. 任务定位

本任务继续在 Codex 已创建的执行分支上书写任务书：

```text
codex/20260709-task20-wave-solver-search
```

ChatGPT 不创建分支。Codex 若需要新执行分支，应自行从合适 base 创建。

Task021 是 Task020 的后续。Task020 的结论是：

```text
Route C: DtN auxiliary residual-aware adaptive coarse correction
```

是唯一值得继续的 p=2 方向。但 Task020 用的是 `default100 rectangular block grating` 算法沙盒，不是项目目标物理模型。因此 Task021 必须切回目标物理模型继续解决 p=2。

---

## 1. 必须使用的 physical model

Task021 的硬性几何和物理设置如下，来自 task008 official benchmark：

```text
domain size = 50 x 25 x 140 nm
period = 50 x 25 nm
grating size = 17 x 25 x 120 nm
substrate thickness = 10 nm
top air above grating = 10 nm
air_height parameter = 130 nm
theta_from_z = 80 deg
phi = 0 deg
incident plane = x-z
polarization = s, E along y
material n = 0.999002304859 + 0.00182649365j for grating and substrate
boundary = double Floquet x/y + auxiliary DtN port
power source = dtn_port_modal_amplitudes + A_volume
```

禁止把 Task020 的 `default100 / 100 x 100 / 50 x 50 x 50` 算法沙盒继续当作目标模型。

---

## 2. 当前判断

Task020 可以说明：

```text
p=1 default100 linear solver prototype 已经能达到 production-like residual。
p=2 default100 只达到 minimum useful，还没达到 strong。
```

但由于 physical model 不同，Task021 必须重新验证：

```text
target geometry p=1 h=5 / p=2 h=5 baseline
target geometry auxiliary residual top-mode selector
target geometry p=2 h=5 auxiliary coarse correction
```

本任务主目标：

```text
在目标几何 p=2 h=5 上，把 DtN auxiliary residual-aware adaptive coarse correction 从 minimum useful 推进到 strong gate。
```

strong gate：

```text
final true residual <= 2e-3 或 improvement >= 10x
```

production-like gate：

```text
final true residual <= 1e-6
```

所有 gate 必须使用完整真实残差：

```text
||A x - b|| / ||b||
```

不得使用 PETSc reported residual 替代。

---

## 3. 本任务不再主攻的方向

除非 Task021 主线失败并且审查同意，否则不要继续：

```text
fixed top_bottom_y sampled Schur
Petrov W expansion
right additive PC with true-FE basis
full 708-mode Schur
Route A row-index layer proxy
Route B diagonal-preflight slab sweep
p=2 h=2 preflight before p=2 h=5 strong gate
production R/T/A output from unconverged iterative solver
```

Route D matrix-free 只作为后续基础设施，不作为本任务独立求解路线。

---

## 4. 最高优先级执行规则

```text
无效方向：用最小必要证据记录后停止，不做无意义参数微调。
弱正方向：继续加深到明确成功、明确失败、或资源边界。
强正方向：继续推进到 production-like gate 或下一层规模验证，不停在“可以试试”。
只要 p=2 h=5 仍未达到 strong gate，就不要进入 p=2 h=2。
```

如果某个子方向出现 p=2 h=5 正信号，必须继续追踪：

```text
mode selector 稳定性
coarse dimension m
residual history
true residual decomposition
memory / wall time
是否需要 FE response
是否可以做成 PETSc PC
```

---

## 5. Stage A：target geometry baseline and resource preflight

目标：在目标模型上建立 p=1 h=5 和 p=2 h=5 的 baseline。

必须输出：

```text
outcomes/target_geometry_resource_preflight.csv
outcomes/target_geometry_baseline_reproduction.csv
```

字段至少包括：

```text
case,p,h_nm,domain,period,grating,theta_from_z,polarization,n_complex,nnz_complex,n_fe,n_aux,rss_upper_gb,baseline_solver,baseline_residual,history_points,elapsed_s,status,notes
```

必须确认：

```text
period = 50 x 25 nm
aux mode count should match target model scale, not default100 708 modes
geometry matches 17 x 25 x 120 nm grating
```

如果发现代码配置仍然落回 default100，立即停止并修正配置。

---

## 6. Stage B：target auxiliary residual mode mapping

目标：找出目标几何 p=2 h=5 residual-dominant DtN auxiliary modes 的物理含义。

Task020 的 default100 index `177` 不可直接外推到目标模型。Task021 必须重新映射：

```text
local aux index
global aux row
top/bottom side
Rayleigh order (mx,my)
polarization / vector component
propagating or evanescent
aux residual magnitude
fraction of total residual
```

必须输出：

```text
outcomes/target_aux_mode_mapping.csv
outcomes/target_residual_decomposition.csv
```

如果当前 code 无法映射 aux index 到 side/order/polarization，必须先补 mapping 工具，而不是继续用裸 index。

---

## 7. Stage C：aux-only residual-aware coarse correction

目标：在目标几何 p=2 h=5 上复现 Task020 的正信号，但用目标模型的 residual top modes。

测试 coarse dimensions：

```text
m = 1, 2, 4, 8, 16
```

构造：

```text
Z_aux = [e_j1, e_j2, ..., e_jm]
alpha = argmin ||r - A Z_aux alpha||
```

先做 one-shot residual minimization，再做 Krylov / residual correction integration。

输出：

```text
outcomes/target_aux_only_coarse_sweep.csv
outcomes/target_aux_only_history_summary.csv
```

判断：

```text
minimum useful: residual < 1e-2 或 improvement >= 2x
strong: residual <= 2e-3 或 improvement >= 10x
```

如果 aux-only 已经 strong，则记录并进入 Stage F。若只 minimum，则进入 Stage D。

---

## 8. Stage D：add FE response to selected auxiliary modes

目标：把 aux-only coarse 从 minimum 推向 strong。

对 selected aux mode `j` 构造 coupled basis：

```text
z_j = [q_j; e_j]
```

其中 `q_j` 是 FE response approximation。至少测试以下三类：

```text
1. q_j = 0                       # aux-only baseline
2. q_j ≈ -P_FE^{-1} C_j           # AMS/HX-smoothed or positive Maxwell proxy
3. q_j ≈ selected iterative FE response, loose filtered solve
```

注意：Task018/Task019 已经说明“越精确 FE solve 不一定越好”。因此 Task021 应把 FE response 看作 filtered physical response，而不是盲目追求 exact solve。

输出：

```text
outcomes/target_coupled_aux_fe_response_sweep.csv
outcomes/target_fe_response_quality.csv
```

如果 same-process PETSc selected FE-AMS 再次出现 lifecycle risk，不要把它作为主路径。可以用 isolated process / offline diagnostic，但必须标记为 research-only。

---

## 9. Stage E：PETSc PC / solver-like integration

目标：把 best coarse correction 变成 solver-like process，而不是只停在 one-shot。

至少测试：

```text
initial correction + continuation
residual-corrected outer loop
right or left PC prototype, only if mathematically consistent
augmentation/projection prototype if cheap
```

输出：

```text
outcomes/target_solver_like_integration.csv
outcomes/target_residual_corrected_cycles.csv
outcomes/target_ksp_history_summary.csv
```

必须记录：

```text
true residual before/after each correction
coarse dimension
selected modes
coarse matrix condition
continuation iterations
memory and wall time
```

---

## 10. Stage F：gate decision and optional p=2 h=2 preflight proposal

如果目标几何 p=2 h=5 达到 strong gate：

```text
可以写 p=2 h=2 preflight proposal
但本任务不直接跑 full p=2 h=2 validation
```

如果达到 production-like：

```text
提出 official R/T/A validation task
```

如果 p=2 h=5 仍只能 minimum 或弱正：

```text
不要进入 p=2 h=2；继续改进 mode selector / FE response / PC integration，或建议回到 BLR/H-matrix/direct fallback。
```

输出：

```text
outcomes/gate_decision.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
```

---

## 11. 必须输出文件

```text
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/summary.md
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_geometry_resource_preflight.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_geometry_baseline_reproduction.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_aux_mode_mapping.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_residual_decomposition.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_aux_only_coarse_sweep.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_aux_only_history_summary.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_coupled_aux_fe_response_sweep.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_fe_response_quality.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_solver_like_integration.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_residual_corrected_cycles.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/target_ksp_history_summary.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/gate_decision.csv
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/solver_profile_ranking.md
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/merge_recommendation.md
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/next_decision.md
docs/task021_target_geometry_aux_residual_coarse_p2/outcomes/parameters.json
```

`raw_runs/` 只保留轻量日志，不提交大型矩阵、网格、XDMF、VTU、HDF5 或 results。

---

## 12. summary.md 必须回答

```text
1. 是否确认使用了目标模型 50 x 25 x 140 nm / 17 x 25 x 120 nm？
2. 目标几何 p=1 h=5 是否能达到 production-like linear residual？
3. 目标几何 p=2 h=5 baseline residual 是多少？
4. p=2 residual-dominant auxiliary modes 是哪些物理模式？
5. aux-only coarse 是否达到 minimum / strong？
6. 加入 FE response 后是否提升到 strong？
7. solver-like integration 是否稳定？
8. 是否允许 p=2 h=2 preflight？
9. 是否建议合并代码？仅 research runner 还是 production path？
10. 如果失败，失败属于 mode selector、FE response、PC integration、资源边界还是物理模型差异？
```

---

## 13. 合并策略

默认：

```text
merge_docs: yes, after review
merge_code: no by default
merge_research_runner: optional, opt-in only
production_default_change: no
```

任何未达到 p=2 h=5 strong gate 的 solver 不得接入 production Stage4 默认路径。

---

## 14. 最终目标句

任务结束时必须回答：

```text
在目标 50 x 25 x 140 nm / 17 x 25 x 120 nm 模型上，DtN auxiliary residual-aware adaptive coarse correction 是否能把 p=2 h=5 reduced Stage4 system 推进到 strong gate，并为 p=2 h=2 preflight 提供依据？
```

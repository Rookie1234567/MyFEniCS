# CODEX TASK 20260709：branch hygiene and wave-aware solver search

## 0. 定位

本任务书保存在当前 research evidence 分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

Task020 的实际执行分支必须由 Codex 自行创建；ChatGPT 不创建分支。

Task020 分两大阶段：

```text
Phase I  : branch hygiene / selective docs merge audit
Phase II : four-route wave-aware preconditioner search
```

当前 task013-task019 分支保留了大量有价值的负结果和路线演化证据，但 p=2 h=5 上 low-dimensional `top_bottom_y` sampled Schur 已经失败。因此失败代码留在 research branch；可保留的主要是文档、审查报告、总结、gate 表和理论 notes。

---

## 1. 已知背景

上一轮关键结论：

```text
Task018: p=1 h=5 residual-corrected true-FE sampled Schur 成功，best residual 1.6616e-3，改善 12.914x。
Task019: p=2 h=5 required top_bottom_y sampled Schur 失败，best required one-shot 仅 1.0018x；最强低维扩展仅 1.0804x。
```

Task019 审查结论：

```text
p=1 成功的 residual-corrected top_bottom_y true-FE sampled Schur 不能直接扩展到 p=2 h=5。
low-dimensional sampled Schur 可作为诊断证据，但不应继续作为 p=2 主求解路线。
```

所以 Task020 的 solver search 应转向四类更全局的传播方向感知方法：

```text
Route A: impedance domain decomposition / optimized Schwarz
Route B: layered sweeping / moving-PML style preconditioner
Route C: two-level weighted Schwarz + adaptive coarse space
Route D: matrix-free high-order FE matvec support for physics preconditioners
```

---

## 2. 总体执行规则

```text
无效方向：用最小必要证据记录后停止，不做无意义参数微调。
弱正方向：继续加深到明确成功、明确失败、或资源边界。
强正方向：继续推进到 production-like gate 或下一层规模验证，不停在“可以试试”。
四条 solver 路线都必须至少做最小可判定 prototype，除非某条路线已经达到 production-like 1e-6 并可直接进入 official validation。
如果某路线只在 p=1 成功，必须 gated 到 p=2 h=5；不能只写“建议后续测试”。
```

统一 gate：

```text
minimum useful : final true residual < 1e-2 或 improvement >= 2x
strong         : final true residual <= 2e-3 或 improvement >= 10x
production-like: final true residual <= 1e-6
```

所有 gate 必须基于完整真实残差：

```text
||A x - b|| / ||b||
```

---

## 3. Phase I：branch hygiene / selective docs merge audit

Codex 必须审查：

```text
master
codex/20260707-real-split-ams-hx-qualification
其它可访问的 codex/* research branches
```

必须输出：

```text
outcomes/branch_audit.md
outcomes/selective_merge_manifest.csv
outcomes/failed_code_keepout.md
outcomes/docs_merge_plan.md
```

`selective_merge_manifest.csv` 字段至少包括：

```text
source_branch,path,type,decision,reason,risk,merge_target
```

默认可合并为 docs-only 候选：

```text
docs/task*/task.md
docs/task*/review_report.md
docs/task*/outcomes/summary.md
docs/task*/outcomes/next_decision.md
docs/task*/outcomes/merge_recommendation.md
docs/task*/outcomes/gate_decision.csv
notes/theory/*.md
notes/reference/*.md
small bibliography files
small negative-result evidence tables
```

默认不合入 master：

```text
failed solver research runners
offline SciPy selected FE RHS production hooks
same-process PETSc selected FE-AMS selected RHS code
failed sampled-Schur solver code
large raw_runs
matrix or mesh dumps
ordinary Stage4 solver default changes from research branches
```

Phase I 必须回答：

```text
1. 不合并 current research branch 是否影响 master？
2. 哪些文档、review、summary、negative-result evidence 值得保留？
3. 哪些 failed solver code 必须只留在原研究分支？
4. 是否建议 docs-only merge？
5. Phase II 的 clean base 应该是什么？
```

---

## 4. Phase II：baseline and resource preflight

Phase II 必须从 clean base 执行，不能直接继承 failed sampled-Schur code。Codex 自行创建执行分支。

先建立 baseline：

```text
case A: default100 p=1 h=5 reduced Stage4, assembled if feasible
case B: default100 p=2 h=5 reduced Stage4, export/preflight if feasible
```

输出：

```text
outcomes/baseline_reproduction.csv
outcomes/resource_preflight.csv
```

记录：

```text
matrix size
RSS
true residual for baseline iterative profile if run
reference direct/BLR availability
```

---

## 5. Route A：impedance domain decomposition / optimized Schwarz

目标：构造 time-harmonic Maxwell 的 impedance transmission / optimized Schwarz 原型。

思路：

```text
沿 z 或物理层切少量子域；
子域边界使用 impedance / Robin / approximate outgoing 条件；
用 additive 或 multiplicative Schwarz 传递界面信息；
AMS/HX 只作为局部 smoother 或子域工具。
```

候选形式：

```text
P_A^{-1} r = sum_i R_i^T A_i_imp^{-1} R_i r
```

最低 prototype：

```text
local extracted submatrix + diagonal/ILU/LU fallback
assembled layer block solve
simplified Robin mass boundary term proxy
```

如果 additive variant 有正信号，继续测试：

```text
top -> bottom sweep
bottom -> top sweep
symmetric sweep
```

输出：

```text
outcomes/routeA_impedance_ddm_summary.csv
outcomes/routeA_interface_diagnostics.csv
outcomes/routeA_history_summary.csv
```

---

## 6. Route B：layered sweeping / moving-PML style preconditioner

目标：利用 grating + substrate + air + top/bottom port 的 z 方向传播结构，构造 sweeping-like approximate inverse。

思路：

```text
按 z slab 切分；
做 forward / backward / symmetric sweep；
界面使用 impedance、Robin 或 moving-PML inspired local solve；
必要时用 shifted / absorbing slab proxy。
```

候选 shifted slab proxy：

```text
A_slab_shifted = curlcurl - k0^2 (1 + i sigma) eps mass
```

注意：shifted/absorbing slab 只是 preconditioner，不是物理解。

输出：

```text
outcomes/routeB_sweeping_summary.csv
outcomes/routeB_slab_diagnostics.csv
outcomes/routeB_history_summary.csv
```

---

## 7. Route C：two-level weighted Schwarz + adaptive coarse space

目标：不再固定 `top_bottom_y` 两个模态，而是从 residual、interface trace、local diagnostics 中自适应构造 coarse vectors。

Level 1 smoother：

```text
P_smooth^{-1} = sum_i W_i R_i^T A_i^{-1} R_i W_i
```

Level 2 coarse candidates：

```text
Rayleigh/Floquet residual-dominant modes
FE residual snapshots after smoothing
interface trace residuals
small local eigen or singular-vector diagnostics if affordable
```

粗空间：

```text
Z_adapt = [z_1, ..., z_m]
alpha = argmin ||r - A Z_adapt alpha||
```

维度限制：

```text
start m <= 4
if positive, m <= 16
never full 708-mode Schur in this task
```

输出：

```text
outcomes/routeC_two_level_schwarz_summary.csv
outcomes/routeC_adaptive_coarse_candidates.csv
outcomes/routeC_history_summary.csv
```

---

## 8. Route D：matrix-free high-order support

Route D 不是独立收敛路线，只服务 Route A/B/C。只有当 p=2 assembled matrix memory/setup time 阻碍 A/B/C 继续时，才进入较深实现。

最低目标：

```text
matrix-free matvec correctness on p=1 / tiny case
assembled vs matrix-free matvec relative error <= 1e-10
p=2 h=5 memory reduction path
preconditioner matrices remain low-order / subdomain / coarse only
```

输出：

```text
outcomes/routeD_matrix_free_summary.csv
outcomes/routeD_matvec_equivalence.csv
outcomes/routeD_memory_projection.md
```

---

## 9. Best-route continuation

完成四条 minimum smoke 后：

```text
选择当前 best route；
继续加深到明确失败、strong gate、production-like gate 或 p=2 h=5 resource boundary。
```

如果某路线 p=1 通过 strong gate，必须 gated 到 p=2 h=5。

如果所有路线 p=1 都 fail minimum gate，建议停止 workstation low-memory iterative solver 主线，并回到 BLR/direct/H-matrix 或更大工程重构。

如果某路线 p=2 h=5 达到 strong gate，可以提出 p=2 h=2 preflight task，但本任务不直接运行 full p=2 h=2。

---

## 10. 必须输出文件

```text
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/summary.md
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/branch_audit.md
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/selective_merge_manifest.csv
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/failed_code_keepout.md
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/docs_merge_plan.md
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/baseline_reproduction.csv
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/resource_preflight.csv
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/routeA_impedance_ddm_summary.csv
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/routeB_sweeping_summary.csv
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/routeC_two_level_schwarz_summary.csv
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/routeD_matrix_free_summary.csv
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/best_route_continuation.csv
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/adaptive_experiment_log.csv
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/gate_decision.csv
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/solver_profile_ranking.md
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/merge_recommendation.md
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/next_decision.md
docs/task020_branch_hygiene_and_wave_solver_search/outcomes/parameters.json
```

`raw_runs/` 只保留轻量日志，不提交大型矩阵或网格文件。

---

## 11. summary.md 必须回答

```text
1. Branch hygiene 审查了哪些分支？
2. 哪些 docs 建议合并？哪些 failed code 明确不合并？
3. 四条 solver 路线是否都完成最低 smoke？
4. 哪条路线在 p=1 default100 上最好？
5. 是否有路线达到 minimum / strong / production-like gate？
6. 是否有路线进入 p=2 h=5？结果如何？
7. 是否需要 matrix-free 才能继续？
8. 是否允许 p=2 h=2 preflight？
9. 是否建议合并代码？仅 research runner 还是 production path？
10. 如果所有路线失败，是否建议停止 workstation low-memory iterative solver 主线？
11. 如果有路线成功，下一步怎样工程化？
```

---

## 12. 合并策略

默认：

```text
merge_code: no
merge_docs: yes, selective
production_default_change: no
```

允许合并 code 的唯一情况：

```text
research runner only;
opt-in;
不改变 ordinary Stage4 direct/BLR/default solver；
不输出未收敛 official R/T/A；
不依赖 failed sampled-Schur branch code。
```

---

## 13. 最终目标句

任务结束时必须回答：

```text
在搁置 low-dimensional sampled-Schur 分支后，impedance DDM、sweeping、two-level adaptive Schwarz、matrix-free+physics PC 四条路线中，是否存在能把 Stage4 p=1/p=2 reduced system 推向稳定低内存迭代求解的方向？
```

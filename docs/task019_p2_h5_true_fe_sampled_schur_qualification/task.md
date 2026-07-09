# CODEX TASK 20260708：p=2 h=5 qualification for residual-corrected true-FE sampled Schur

## 0. 任务定位

本任务继续在现有研究分支上执行，不新建分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task019_p2_h5_true_fe_sampled_schur_qualification/
├── task.md
├── outcomes/
└── review_report.md
```

Task019 是 Task018 的 gated escalation。Task018 已经在 default100 `p=1 h=5` 上把 true-FE sampled Schur 的 one-shot 正信号转化为稳定的 residual-corrected solver-like process，并达到 strong gate：

```text
baseline FE-AMS + aux identity residual = 2.145878536207579e-2
best residual_outer_zero residual       = 1.6616234679826358e-3
improvement                             = 12.914348993956336x
```

Task019 的目标是验证同一主线是否能扩展到 reduced Stage4 `p=2 h=5`。

---

## 1. 核心问题

Task019 必须回答：

```text
Task018 的 residual-corrected true-FE sampled Schur process，能否在 p=2 h=5 上保持至少 minimum useful signal，并最好达到 strong signal？
```

这里的 process 指：

```text
repeat:
    run bounded FE-AMS segment
    compute true residual r = b - A x
    solve min_alpha ||r - A Z alpha||
    update x <- x + omega Z alpha
until stagnation or gate reached
```

其中：

```text
Z = top_bottom_y selected / filtered FE response basis
selected FE RHS solver = SciPy GMRES + diagonal preconditioner, rtol=1e-2
```

---

## 2. 最高优先级执行规则

本任务延续 Task018 的 adaptive execution rule：

```text
无效方向：用最小必要证据记录后停止，不继续微调。
正信号方向：立即沿该方向继续推进，不停在“可以试试”的报告句式。
如果 p=2 h=5 某个配置出现正信号，必须继续追踪它的稳定性、迭代次数、残差历史、资源成本和失败边界。
如果 p=2 h=5 出现反弹或无改善，必须定位是 one-shot basis 问题、outer-loop 集成问题、selected FE RHS 问题，还是资源/生命周期问题。
```

本任务不是固定 checklist；Codex 可以在任务边界内自适应新增局部实验。

---

## 3. 必须阅读的输入

开始前必须读取：

```text
docs/task018_true_fe_sampled_schur_krylov_integration/review_report.md
docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/summary.md
docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/solver_profile_ranking.md
docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/selected_fe_rhs_solve_sweep.csv
docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/initial_correction_summary.csv
docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/residual_corrected_loop_summary.csv
docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/gate_decision.csv
docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/next_decision.md
docs/task018_true_fe_sampled_schur_krylov_integration/outcomes/run_log.txt
src/studies/run_stage4_true_fe_sampled_schur_krylov.py
src/studies/run_stage4_real_split_block_pc.py
```

---

## 4. 继续关闭的方向

Task019 不允许首轮运行：

```text
full p=2 h=2
h=1.5
full 708-mode Schur
Petrov W expansion
right additive PC with true-FE basis
PETSc selected FE-AMS same-process RHS solve as main path
unconverged official R/T/A
production solver default changes
```

如果 p=2 h=5 strong gate 通过，最多只允许写下一步 productionization / p=2 h=2 preflight 计划，不在本任务内直接跳到 h=2 或 h=1.5。

---

## 5. 工程化风险必须记录

### 5.1 风险 B：SciPy selected FE RHS 不是并行 production 路径

当前最强 selected FE response 来自：

```text
SciPy GMRES + diagonal preconditioner, rtol=1e-2
```

它是：

```text
single-process / exported-matrix / research runner path
```

不是：

```text
MPI-distributed PETSc production path
```

Task019 可以继续用它做 p=2 h=5 qualification，但报告中必须明确：

```text
数学方向可能并行化；当前实现不能直接作为并行 production solver。
```

如果 p=2 也成功，后续工程化必须单独解决 selected FE RHS 的 production 形态：

```text
1. MPI-distributed PETSc selected RHS solve；
2. isolated-process selected FE response service；
3. offline/cache selected response construction；
4. 或其他不污染 ordinary Stage4 solve 的 safe service layer。
```

### 5.2 风险 C：PETSc selected FE-AMS 同进程生命周期风险

Task018 已重新尝试 PETSc selected FE-AMS opt-in path，结果：

```text
KSPSetUp/PCSetUp error 101
invalid communicator behavior risk
can poison later AMS communicator setup
```

Task019 默认不得把它作为主路径。若需要诊断，只能 opt-in、单独进程、单 profile 运行，并且必须记录失败不会污染主结果。

后续工程化必须注意：

```text
1. 避免 late/repeated setup/destroy 多个 hypre AMS helper；
2. 若使用 PETSc selected FE-AMS，需要 early setup and reuse；
3. 更稳妥方案是 isolated process / subprocess service；
4. MPI production 需要重新设计 communicator ownership、PC lifetime、destroy order。
```

---

## 6. Stage A：p=2 h=5 complex export and memory preflight

目标：先确认 p=2 h=5 reduced Stage4 matrix 可以导出，并且资源仍在 workstation-safe 范围。

运行：

```text
python -m src.studies.run_stage4_real_split_block_pc export-complex \
  --degree 2 \
  --h-nm 5 \
  --stage-case stage4_block_grating \
  --domain-preset default100 \
  --dtn-order-policy auto_propagating \
  --output-dir docs/task019_p2_h5_true_fe_sampled_schur_qualification/outcomes
```

输出：

```text
outcomes/p2_h5_export_preflight.csv
```

字段至少包括：

```text
case,p,h_nm,n_complex,n_real,fe_complex_dofs,aux_complex_dofs,nnz_complex,nnz_real,relative_matvec_error,relative_rhs_error,rss_upper_gb,export_status,notes
```

停止条件：

```text
export fails;
real split equivalence error > 1e-10;
RSS or matrix size clearly exceeds workstation-safe range;
raw .npz cannot be cleaned after extracting lightweight metadata.
```

---

## 7. Stage B：p=2 h=5 baseline FE-AMS + aux identity

目标：建立 p=2 h=5 的 baseline。必须使用完整真实残差：

```text
||A_real x - b_real|| / ||b_real||
```

推荐设置：

```text
baseline_max_it = 1000
restart = 200
FE block PC = same-H1 real hypre AMS/HX
aux block = identity
```

输出：

```text
outcomes/p2_h5_baseline_summary.csv
outcomes/p2_h5_baseline_history.csv
```

停止条件：

```text
baseline cannot run stably;
AMS setup triggers memory pressure or communicator lifecycle failure;
true residual cannot be computed reliably.
```

注意：baseline 如果不收敛并不表示失败；它只是后续 improvement 的 denominator。

---

## 8. Stage C：p=2 h=5 selected top_bottom_y one-shot

目标：测试 Task018 的 strongest basis 是否在 p=2 h=5 上仍有正信号。

使用：

```text
mode_set = top_bottom_y
selected FE RHS solver = SciPy GMRES + diagonal preconditioner
rtol = 1e-2
```

构造：

```text
A_FE q_j = -C_j
Z_j = [q_j; e_j]
alpha = argmin ||r - A Z alpha||
x_new = x + Z alpha
```

输出：

```text
outcomes/p2_h5_selected_fe_rhs_solve.csv
outcomes/p2_h5_one_shot_summary.csv
outcomes/p2_h5_true_fe_basis_quality.csv
```

最低正信号：

```text
residual_after < 1e-2 或 improvement >= 2x
```

如果 one-shot 没有正信号，不要继续 outer loop；先判断：

```text
mode mapping 是否变化；
selected top_bottom_y 是否仍是 residual-dominant；
FE RHS solve 是否太差；
是否需要 only one minimal alternative: rtol=1e-4 或 top_y-only diagnostic。
```

如果这些最小诊断仍无正信号，Task019 可停止并报告 p=2 不继承 p=1 信号。

---

## 9. Stage D：p=2 h=5 residual-corrected outer loop

只有 Stage C 有正信号才进入。

首轮设置：

```text
start = zero
segment_max_it = 120
cycles = 1
omega candidates = 1.0, 0.5, 0.3, 0.1
```

如果 cycle 1 正信号稳定：

```text
continue cycles 2/3/4
```

如果 cycle 2/3 停滞但不反弹，记录停滞点。如果反弹，停止该子方向并记录。

输出：

```text
outcomes/p2_h5_residual_outer_loop_summary.csv
outcomes/p2_h5_residual_outer_cycle_history.csv
outcomes/p2_h5_adaptive_experiment_log.csv
```

强信号 gate：

```text
final residual <= 2e-3 或 improvement >= 10x
```

production-like gate：

```text
final residual <= 1e-6
```

---

## 10. Stage E：long segment / continuation sanity

只有 Stage D 有正信号才进入。

目的：判断 p=2 h=5 是否受 FE-AMS segment length 限制。

最小测试：

```text
segment_max_it = 500, cycles <= 3
```

如果仍有明显下降，再试：

```text
segment_max_it = 1000, cycles <= 2
```

同时可以对 best solution 做：

```text
FE-AMS continuation max_it = 1000
```

输出：

```text
outcomes/p2_h5_long_segment_summary.csv
```

判断：

```text
如果 long segment 只小幅改善，不作为主路线；
如果 long segment 明显改善，则 Task020 可考虑 tuned segment length / restart strategy。
```

---

## 11. Stage F：minimal mode-set escalation

只有 `top_bottom_y` p=2 h=5 有正信号但停在明显 residual floor 时才进入。

候选只允许：

```text
top_y diagnostic
top_bottom_xy diagnostic
```

不允许：

```text
all propagating modes
full 708-mode Schur
near-cutoff expansion
```

输出：

```text
outcomes/p2_h5_mode_set_escalation.csv
```

如果 `top_bottom_xy` 仍不优于 `top_bottom_y`，停止 expansion。

---

## 12. Gate decision and next step

输出：

```text
outcomes/gate_decision.csv
outcomes/solver_profile_ranking.md
outcomes/merge_recommendation.md
outcomes/next_decision.md
```

必须回答：

```text
1. p=2 h=5 export and real split equivalence 是否通过？
2. p=2 h=5 baseline residual 是多少？
3. top_bottom_y one-shot 是否仍有 >=2x 或 <1e-2？
4. residual outer loop 是否稳定？
5. 是否达到 strong gate？
6. 是否达到 production-like 1e-6？
7. 是否允许下一步 p=2 h=2 preflight？
8. SciPy selected FE RHS 并行 production 风险如何处理？
9. PETSc selected FE-AMS lifecycle 风险是否仍阻塞工程化？
10. 如果 p=2 h=5 失败，下一条路线是什么？
```

---

## 13. 必须输出文件

```text
docs/task019_p2_h5_true_fe_sampled_schur_qualification/outcomes/
├── summary.md
├── p2_h5_export_preflight.csv
├── p2_h5_baseline_summary.csv
├── p2_h5_baseline_history.csv
├── p2_h5_selected_fe_rhs_solve.csv
├── p2_h5_one_shot_summary.csv
├── p2_h5_true_fe_basis_quality.csv
├── p2_h5_residual_outer_loop_summary.csv
├── p2_h5_residual_outer_cycle_history.csv
├── p2_h5_long_segment_summary.csv
├── p2_h5_mode_set_escalation.csv
├── p2_h5_adaptive_experiment_log.csv
├── gate_decision.csv
├── solver_profile_ranking.md
├── merge_recommendation.md
├── next_decision.md
├── parameters.json
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 只保留轻量 JSON/CSV/log excerpts。必须删除或不提交大型 `.npz` matrix dumps、mesh dumps、HDF5、XDMF、VTU/PVTU。

---

## 14. 合并策略

默认：

```text
merge_code: no
merge_docs: yes
```

如果 Task019 只新增或小幅扩展 research runner，可考虑：

```text
merge_code: yes, research runner only
production_default_change: no
```

任何情况下都不允许：

```text
把 p=2 h=5 未达到 1e-6 的流程接入 ordinary Stage4 production R/T/A；
默认启用 SciPy selected FE RHS；
默认启用 PETSc selected FE-AMS same-process selected RHS。
```

---

## 15. 最终目标句

任务结束时必须用一句话回答：

```text
Task018 的 AMS/HX + true-FE sampled Schur residual-correction process，能否从 p=1 h=5 扩展到 p=2 h=5？
```

如果答案是否定的，必须说明失败属于：

```text
resource limit;
selected FE response quality;
mode-set non-transferability;
outer-loop instability;
AMS/HX block weakness;
或工程生命周期风险。
```

如果答案是肯定的，必须说明是否允许下一步 p=2 h=2 preflight，以及 productionization 需要先解决哪些工程风险。

# CODEX TASK 20260708：Task014a reduced Stage 4 real-split FE/aux block PC integration

## 0. 任务定位

本任务继续在现有分支上执行，不新建分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task014a_real_split_stage4_reduced_block_pc/
├── task.md
├── outcomes/
└── review_report.md
```

本任务是 Stage 4 integration qualification，不是 production solver 任务。

目标不是直接完成 full Stage 4 p=2 h=2 / h=1.5，而是回答：

```text
Task013 中 FE-only real-split AMS/HX + same-H1 auxiliary 的正信号，
能否安全接入 reduced Stage 4 的 FE/aux block 系统？
```

核心问题：

```text
1. Stage 4 complex system 是否能正确转写为 real split system；
2. Floquet MPC 后的 FE unknown block 是否仍能构造 compatible AMS data；
3. DtN modal auxiliary unknowns 如何从 FE block 中分离；
4. same-H1 AMS 作用在 FE block 上是否能改善 true residual；
5. reduced Stage 4 p=1 h=5 是否明显优于 Jacobi。
```

---

## 1. 必须遵守的边界

本任务不允许一开始直接跑 full Stage 4 p=2 h=2，也不允许跑 p=2 h=1.5 breakthrough。

必须采用 gated execution：

```text
Stage A 通过后，才进入 Stage B；
Stage B 通过后，才进入 Stage C；
Stage C reduced p=1 h=5 有正结果后，才允许 optional reduced p=2 h=5；
只有 Task014a 审查通过后，后续任务才考虑 full p=2 h=2。
```

本任务不做：

```text
1. full Stage 4 p=2 h=2 production validation；
2. full Stage 4 p=2 h=1.5 breakthrough；
3. Rayleigh/Floquet modal deflation；
4. RCWA/layered-background approximate inverse；
5. matrix-free MatShell；
6. 新一轮黑盒 PETSc profile sweep；
7. 大规模参数扫描。
```

---

## 2. 必须阅读的输入

开始前阅读：

```text
docs/task013_real_split_ams_hx_qualification/review_report.md
docs/task013_real_split_ams_hx_qualification/outcomes/summary.md
docs/task013_real_split_ams_hx_qualification/outcomes/fe_only_real_split_ams_summary.csv
docs/task013_real_split_ams_hx_qualification/outcomes/ams_memory_breakdown.md
docs/task013_real_split_ams_hx_qualification/outcomes/solver_profile_ranking.md
docs/task013_real_split_ams_hx_qualification/outcomes/merge_recommendation.md
docs/task013_real_split_ams_hx_qualification/outcomes/next_decision.md
src/studies/run_real_split_ams_qualification.py
```

同时阅读当前 Stage 4 相关实现。不要只凭文件名猜测；先搜索并确认实际入口、矩阵装配、MPC、DtN auxiliary、R/T/A 后处理所在文件。

建议先搜索关键词：

```text
Stage 4
DtN
modal
auxiliary
Floquet
MPC
R_total
T_total
A_volume
```

---

## 3. 技术目标

### 3.1 real split system

对 Stage 4 complex system：

```text
A u = b
A = Ar + i Ai
u = ur + i ui
b = br + i bi
```

构造 real split system：

```text
[ Ar  -Ai ] [ur] = [br]
[ Ai   Ar ] [ui]   [bi]
```

必须验证 matvec/residual 等价性，而不是只看 KSP residual。

### 3.2 FE/aux block split

Stage 4 系统含两类 unknown：

```text
FE unknowns: H(curl) field dofs after Floquet/MPC treatment
aux unknowns: DtN modal auxiliary unknowns / port modal variables
```

本任务第一版 PC：

```text
P^{-1} ≈ blockdiag(P_FE^{-1}, P_aux^{-1})
```

其中：

```text
P_FE^{-1}: real-split blockdiag AMS/HX using same-H1 auxiliary
P_aux^{-1}: identity or exact small solve
```

如果 auxiliary block 结构复杂，第一版可用 identity，但必须记录原因和影响。

### 3.3 AMS 数据

沿用 Task013 的优先路线：

```text
same-H1 auxiliary: H1 degree = N1curl degree p
```

必须记录：

```text
B rows / nnz
G rows / cols / nnz
H1 dofs
AMS setup RSS before/after
FE block rows
aux block rows
real block total rows
```

---

## 4. Stage A：Stage 4 assemble-only real split residual diagnostic

### 4.1 目标

在不求解的情况下，先确认 Stage 4 complex system 的 real split 构造正确。

### 4.2 算例

使用 reduced Stage 4，优先：

```text
p=1 h=5
```

如果这个仍过大，可以临时增加更小 smoke case：

```text
p=1 h=10
```

但最终必须回到 `p=1 h=5`。

### 4.3 必须检查

对随机向量 `u = ur + i ui`，验证：

```text
A_complex u
```

与 real block：

```text
[ Ar -Ai ] [ur]
[ Ai  Ar ] [ui]
```

一致。

如果存在 MPC/constraint-transformed matrix，必须明确验证对象是：

```text
constraint 后的 reduced matrix
```

还是：

```text
constraint 前的 full matrix + explicit C transform
```

不要混用两个口径。

### 4.4 输出

```text
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/stage4_real_split_equivalence.csv
```

字段：

```text
case,p,h_nm,includes_floquet_mpc,includes_dtn_aux,n_complex,n_real,nnz_complex,nnz_real,fe_complex_dofs,aux_complex_dofs,relative_matvec_error,relative_rhs_error,rss_upper_gb,notes
```

通过标准：

```text
relative_matvec_error <= 1e-10
relative_rhs_error <= 1e-12 或给出可解释原因
```

若 Stage A 失败，停止任务，不进入求解。

---

## 5. Stage B：FE/aux block PC 最小接入

### 5.1 目标

在 Stage 4 real split system 上接入最小 block preconditioner：

```text
FE real block: same-H1 AMS/HX
aux real block: identity or exact small solve
```

### 5.2 要求

必须实现为隔离的 experimental path，不修改 direct/BLR official production path 的默认行为。

推荐 profile 名：

```text
stage4_real_split_fgmres_jacobi
stage4_real_split_fgmres_fe_ams_aux_identity
stage4_real_split_fgmres_fe_ams_aux_exact_if_available
```

如果 exact auxiliary solve 不方便，先只做 identity，但要在 outcomes 中记录。

### 5.3 true residual 守门

必须每次求解后计算：

```text
true_relative_residual_norm = ||A_real x - b_real|| / ||b_real||
```

不能只依赖 KSP reported residual。

未达到 true residual 守门时，不允许输出 official R/T/A，只能输出 diagnostic residual。

---

## 6. Stage C：reduced Stage 4 p=1 h=5 对比测试

### 6.1 算例

必须运行：

```text
reduced Stage 4 p=1 h=5
```

profile 至少包括：

```text
stage4_real_split_fgmres_jacobi
stage4_real_split_fgmres_fe_ams_aux_identity
```

可选：

```text
stage4_real_split_fgmres_fe_ams_aux_exact_if_available
```

### 6.2 输出

```text
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/reduced_stage4_block_pc_summary.csv
```

字段：

```text
case,p,h_nm,profile,status,reason,iterations,true_relative_residual_norm,ksp_final_residual,rss_upper_gb,setup_time_s,solve_time_s,includes_floquet_mpc,includes_dtn_aux,fe_real_dofs,aux_real_dofs,total_real_dofs,B_rows,B_nnz,G_rows,G_cols,G_nnz,H1_dofs,ams_setup_rss_before_gb,ams_setup_rss_after_gb,notes
```

成功标准：

```text
1. FE/aux block PC 不崩溃；
2. true residual 明显优于 Jacobi；
3. RSS 明显低于 direct/BLR full p2 h2 reference，不接近 17.85 GB；
4. residual 口径清楚，不出现 KSP residual 与 true residual 严重不一致且无法解释。
```

建议量化标准：

```text
same-H1 FE-AMS profile 的 true residual 至少比 Jacobi 改善 10 倍；
若达到 <= 1e-6，则视为强成功；
若只改善 2-10 倍，则视为弱正信号；
若不改善或更差，则停止，不进入 Stage D。
```

---

## 7. Stage D：optional reduced Stage 4 p=2 h=5

### 7.1 进入条件

只有 Stage C 通过，才允许运行：

```text
reduced Stage 4 p=2 h=5
```

### 7.2 目标

检查 Task013 中 `p=2 h=5 same-H1` 的正信号是否能在 Stage 4 结构中保留。

### 7.3 输出

继续写入：

```text
reduced_stage4_block_pc_summary.csv
reduced_stage4_block_pc_memory.csv
```

并单独总结：

```text
p2_h5_reduced_stage4_decision.md
```

### 7.4 成功标准

```text
true residual 明显优于 Jacobi；
RSS 不出现接近 standard-H1 爆炸式增长；
AMS setup 稳定；
FE/aux block split 没有 residual mismatch。
```

如果 p=2 h=5 失败，也不代表 Task013 路线完全失败，但说明下一步不应直接 full p=2 h=2，而应转向 Rayleigh/Floquet deflation 或 DtN-aware block correction。

---

## 8. R/T/A 输出规则

本任务默认不追求 official R/T/A。

只有当以下条件同时满足时，才允许输出 diagnostic R/T/A：

```text
KSP converged；
true_relative_residual_norm <= 1e-6；
real split solution 能正确还原 complex solution；
Stage 4 后处理路径未被实验 PC 破坏。
```

即使输出，也必须标记为：

```text
diagnostic R/T/A, not production official reference
```

未收敛时禁止输出 R/T/A，避免制造假物理结果。

---

## 9. 必须输出文件

```text
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/
├── summary.md
├── stage4_real_split_equivalence.csv
├── reduced_stage4_block_pc_summary.csv
├── reduced_stage4_block_pc_memory.csv
├── p2_h5_reduced_stage4_decision.md
├── solver_profile_ranking.md
├── merge_recommendation.md
├── next_decision.md
├── parameters.json
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 只保存轻量文本、JSON、CSV。不要提交大型 matrix dumps、Paraview 文件或大体积 results。

---

## 10. summary.md 必须回答

```text
1. Stage 4 real split 等价性是否通过？误差是多少？
2. 验证对象是 constraint 后 reduced matrix，还是 constraint 前 full matrix + C transform？
3. FE unknowns 和 DtN auxiliary unknowns 如何分块？
4. same-H1 AMS 数据是否能在 MPC 后稳定构造？
5. reduced p=1 h=5 中，FE-AMS+aux identity 是否优于 Jacobi？改善多少？
6. true residual 与 KSP residual 是否一致？
7. 内存主要来自 real block、AMS hierarchy，还是 aux block？
8. optional p=2 h=5 是否运行？结果如何？
9. 是否允许下一任务进入 full Stage 4 p=2 h=2？
10. 是否建议合并代码？如果不建议，哪些代码应留在研究分支？
```

---

## 11. merge_recommendation.md 必须给出明确判断

必须写清楚：

```text
merge_code: yes/no
merge_docs_only: yes/no
reason:
minimal_files_to_merge:
files_to_drop:
risks_if_merged:
recommended_next_branch_or_same_branch:
```

由于本轮仍是 integration qualification，默认预期是：

```text
merge_code: no, unless reduced Stage 4 p=1 h=5 and optional p=2 h=5 both show strong, clean improvement.
merge_docs_only: yes / optional
```

---

## 12. 下一步决策规则

### A 档：允许进入 full Stage 4 p=2 h=2

```text
Stage A real split equivalence 通过；
reduced p=1 h=5 FE-AMS+aux PC true residual <= 1e-6 或明显优于 Jacobi；
optional reduced p=2 h=5 有正结果；
内存远低于 BLR/direct；
FE/aux split 与 true residual 口径清楚。
```

### B 档：继续研究，但不进 full p=2 h=2

```text
reduced p=1 h=5 有改善但不强；
p=2 h=5 未跑或结果一般；
PC 接入可行但需要更强 aux correction / modal deflation。
```

下一步可转：

```text
Rayleigh/Floquet modal deflation；
DtN-aware block correction；
FE/aux Schur complement approximation。
```

### C 档：不建议继续 AMS 主路线

```text
Stage 4 real split residual 不一致；
MPC 后 AMS data 无法稳定构造；
FE-AMS+aux identity 不优于 Jacobi；
true residual 与 KSP residual 无法解释；
内存接近或超过 BLR/direct。
```

### D 档：立即停止

```text
minimal reduced p=1 case 崩溃；
real split solution 无法还原 complex solution；
实验代码必须大幅侵入 production direct/BLR path 才能运行。
```

---

## 13. 最终要求

本任务结束时必须能给出一句清楚判断：

```text
Task013 的 FE-only same-H1 real-split AMS 正信号，是否能进入 Stage 4 reduced system？
```

不要用模糊措辞替代结论。即使失败，也要明确失败在：

```text
real split；
MPC；
FE/aux split；
AMS data；
aux block；
residual；
memory；
或 implementation complexity。
```

# CODEX TASK 20260707：real-split AMS/HX qualification with full Stage 4 gated breakthrough test

## 0. 任务定位

本任务是 qualification / go-no-go 任务，不是 production solver 实现任务。

目标不是一次性做出最终低内存求解器，而是回答：

```text
real-split AMS/HX 这条路线是否值得继续投入？
它能否绕开 complex hypre AMS crash？
它是否明显优于 Jacobi-Krylov？
p=2 的 auxiliary-space 内存是否可控？
如果小算例顺利，它能否在 full Stage 4 p=2 h=2 上复现 direct/BLR R/T/A？
是否有机会突破 p=2 h=1.5？
```

本任务必须采用 gated execution。只有前面阶段通过，才允许进入后面更大算例。

推荐新分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

本任务目录：

```text
docs/task013_real_split_ams_hx_qualification/
├── task.md
├── outcomes/
└── review_report.md
```

---

## 1. 合并策略：gated merge policy

本任务允许失败。如果失败且没有得到有效收敛或内存改善，原则上不要把复杂 solver 代码合并进 `master`。

合并策略：

```text
1. 若 Task013 产生有效 solver candidate：可合并最小必要代码和 outcomes。
2. 若 Task013 只有负结果但代码复杂：不合并 solver 代码。
3. 若负结果有记录价值：只保留精简文档或 review report，复杂实验代码留在分支。
4. 合并前必须清理临时 debug scripts、未使用 profiles、空 raw files 和大体积输出。
```

判断是否有资格合并代码的最低标准：

```text
p=2 h=5 FE-only 或 reduced Stage 4 明显优于 Jacobi；
并且内存没有接近 direct/BLR；
或者 full Stage 4 p=2 h=2 收敛并复现 R/T/A。
```

---

## 2. 必须阅读的输入

开始前阅读：

```text
docs/task012_literature_review_maxwell_preconditioners/review_report.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/summary.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/recommended_routes.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/physics_custom_preconditioner_ideas.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/implementation_feasibility.md
docs/task012_literature_review_maxwell_preconditioners/outcomes/next_task_proposal.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/ams_hx_smoke_notes.md
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/ams_hx_smoke_summary.csv
docs/task011_low_memory_ams_hx_iterative_solver/outcomes/solver_memory_comparison.csv
docs/task010_shifted_maxwell_preconditioner/review_report.md
docs/task008_70nm_official_convergence_benchmark/review_report.md
```

核心本地参考：

```text
task011 real FE-only AMS p=2 h=5: 7 iterations, true residual ≈ 4.024e-7, RSS upper ≈ 6.93 GB
task011 real FE-only AMS p=2 h=4: stopped at Docker memory pressure ≈ 12.86 GiB
task011 complex AMS p=1 h=10: malloc invalid size + PETSc signal 11
task010 BLR p=2 h=2: true residual ≈ 2.085e-8, RSS upper ≈ 17.85 GB
task008/task010 direct p=2 h=2 R/T/A:
R = 0.0013429328462348958
T = 0.5992132294442478
A = 0.3994438377095067
```

---

## 3. 数学目标

原 complex system：

```text
A u = b
A = Ar + i Ai
u = ur + i ui
b = br + i bi
```

real split system：

```text
[ Ar  -Ai ] [ur] = [br]
[ Ai   Ar ] [ui]   [bi]
```

第一版 preconditioner：

```text
P0^{-1} = blockdiag(B_AMS^{-1}, B_AMS^{-1})
```

其中：

```text
B_AMS ≈ curl curl + beta mass
beta ≈ k0^2 * |epsilon_r|
```

外迭代优先使用：

```text
FGMRES
right preconditioning
unpreconditioned norm
true residual monitor
rtol = 1e-6
atol = 1e-12
max_it = 1000
restart = 40 or 80, record both if tested
```

注意：`B_AMS` 是 real positive / shifted H(curl) auxiliary-space preconditioner，不是 direct LU，不是 BLR。

---

## 4. Stage A：real split 等价性验证

### 4.1 目标

先证明 complex matrix 和 real block matrix 的数学作用一致。

对任意 complex vector `u = ur + i ui`，验证：

```text
A_complex u
```

与

```text
[ Ar -Ai ] [ur]
[ Ai  Ar ] [ui]
```

一致。

### 4.2 算例

```text
FE-only complex Maxwell block
p=1 h=10
p=1 h=5
```

不包含 full Stage 4 DtN auxiliary，不输出 R/T/A。

### 4.3 输出

```text
real_split_equivalence.csv
```

字段：

```text
case,p,h_nm,n_complex,n_real,nnz_complex,nnz_real,relative_matvec_error,relative_rhs_error,rss_upper_gb,notes
```

成功标准：

```text
relative_matvec_error <= 1e-12
```

如果 Stage A 失败，停止任务，不进入 Stage B。

---

## 5. Stage B：FE-only real-split AMS/HX qualification

### 5.1 目标

验证 real-split + real AMS/HX 是否在 FE-only complex Maxwell block 上明显优于 Jacobi。

### 5.2 Profiles

至少实现并测试：

```text
real_split_fgmres_jacobi
real_split_fgmres_blockdiag_ams_positive
```

其中：

```text
P0 = blockdiag(B_AMS, B_AMS)
B_AMS = curl curl + beta mass
beta = k0^2 * |epsilon_r| or equivalent positive coefficient
```

### 5.3 算例顺序

```text
p=1 h=10
p=1 h=5
p=2 h=5
```

如果 `p=2 h=5` 成功且内存可控，再试：

```text
p=2 h=4
```

但 `p=2 h=4` 先作为 memory audit，不强行跑到系统交换或 Docker kill。

### 5.4 输出

```text
fe_only_real_split_ams_summary.csv
fe_only_real_split_ams_memory.csv
```

字段至少包括：

```text
case,p,h_nm,profile,status,reason,iterations,true_relative_residual_norm,ksp_final_residual,rss_upper_gb,setup_time_s,solve_time_s,n_real,nnz_real,B_rows,B_nnz,G_rows,G_cols,G_nnz,H1_dofs,Pi_present,Pi_nnz,ams_setup_rss_before_gb,ams_setup_rss_after_gb,notes
```

成功标准：

```text
p=2 h=5 true_relative_residual_norm <= 1e-6；
或至少比 Jacobi-Krylov true residual 改善 100 倍以上；
RSS upper 明显低于 BLR p=2 h=2 的 17.85 GB；
无 PETSc/hypre signal 11。
```

停止标准：

```text
p=1 h=5 即崩溃；
p=2 h=5 true residual 仍在 1e-1 量级；
p=2 h=5 RSS 接近或超过 BLR/direct；
real split residual 与 complex reference 不一致。
```

---

## 6. Stage C：low-order / p-coarsened auxiliary memory qualification

### 6.1 目标

如果标准 p=2 AMS 内存偏高，测试低阶或 p-coarsened auxiliary 是否能降低内存。

### 6.2 需要比较

```text
standard_p2_auxiliary
lower_H1_degree_auxiliary_if_supported
p1_auxiliary_or_low_order_Hcurl_pc_if_supported
```

必须记录不能实现的原因，不要假装已实现。

### 6.3 算例

```text
FE-only complex p=2 h=5
optional p=2 h=4 memory audit
```

### 6.4 输出

```text
p_coarsened_auxiliary_summary.csv
ams_memory_breakdown.md
```

重点回答：

```text
内存主要来自 real block A，还是来自 G/Pi/H1 auxiliary/AMS hierarchy？
降低 H1 degree 或 p-coarsening 是否降低 RSS？
迭代数是否明显恶化？
```

成功标准：

```text
p=2 h=5 保持 true residual <= 1e-6 或明显优于 Jacobi；
RSS 明显低于 standard p=2 AMS；
p=2 h=4 不再快速触及 Docker memory ceiling。
```

---

## 7. Stage D：reduced Stage 4 diagnostic

### 7.1 目标

在不直接冲 full production 的情况下，初步检查 real-split AMS/HX 是否能进入 Stage 4 结构。

### 7.2 算例

```text
reduced Stage 4 p=1 h=5
optional reduced Stage 4 p=2 h=5 only if p=1 succeeds
```

`reduced Stage 4` 可以包含真实几何、材料、Floquet MPC；是否包含 DtN auxiliary 由实现复杂度决定，但必须在 outcomes 中明确说明。

### 7.3 输出

```text
reduced_stage4_real_split_summary.csv
```

字段：

```text
case,p,h_nm,includes_floquet,includes_dtn_aux,profile,status,iterations,true_relative_residual_norm,rss_upper_gb,notes
```

成功标准：

```text
true residual 明显优于对应 Jacobi；
不崩溃；
内存没有接近 direct/BLR；
若 KSP 收敛，才允许输出 diagnostic R/T/A。
```

---

## 8. Stage E：full Stage 4 p=2 h=2 gated validation

### 8.1 进入条件

只有满足以下条件，才允许进入 full Stage 4 `p=2 h=2`：

```text
Stage A 通过；
Stage B 中 p=2 h=5 收敛或明显优于 Jacobi；
Stage C 证明内存可控，或至少 p=2 h=5 RSS 明显低于 BLR/direct；
Stage D reduced Stage 4 至少 p=1 h=5 不崩溃且 residual 有改善。
```

### 8.2 算例

```text
full Stage 4 p=2 h=2
```

物理设置必须与 task008/task010 direct reference 一致：

```text
50 x 25 x 140 nm domain
17 x 25 x 120 nm grating
theta_from_z = 80 deg
phi = 0 deg
s polarization
lambda0 = 13.5 nm
x/y Floquet
z top/bottom DtN port auxiliary
```

### 8.3 成功标准

```text
KSP converged to rtol target or true_relative_residual_norm <= 1e-6；
R/T/A 与 direct/BLR reference 一致到可解释范围；
R+T+A energy closure 可接受；
RSS upper 明显低于 BLR 17.85 GB；
wall time 可接受。
```

参考值：

```text
R_direct = 0.0013429328462348958
T_direct = 0.5992132294442478
A_direct = 0.3994438377095067
BLR eps=1e-5 RSS upper ≈ 17.85 GB
direct LU RSS upper ≈ 20.53 GB
```

### 8.4 输出

```text
full_stage4_h2_real_split_validation.csv
full_stage4_h2_vs_direct_rta.csv
```

未收敛时禁止输出 official R/T/A，只能输出 residual-only diagnostic。

---

## 9. Stage F：full Stage 4 p=2 h=1.5 breakthrough test

### 9.1 进入条件

只有 full Stage 4 `p=2 h=2` 成功后，才允许测试：

```text
full Stage 4 p=2 h=1.5
```

进入条件：

```text
p=2 h=2 converged；
p=2 h=2 R/T/A 对上 direct/BLR reference；
p=2 h=2 RSS upper 明显低于 17.85 GB；
没有 unexplained residual mismatch；
估计 h=1.5 不会立即触发 host memory kill。
```

### 9.2 目标

尝试突破 task008/task010 中 direct/BLR 未能完成的 `p=2 h=1.5`。

### 9.3 输出

```text
full_stage4_h1p5_breakthrough.csv
```

字段：

```text
case,p,h_nm,status,reason,iterations,true_relative_residual_norm,rss_upper_gb,wall_time_s,R_total,T_total,A_volume,energy_closure_error,notes
```

成功标准：

```text
KSP 收敛；
RSS 不触发 memory kill；
若收敛，R/T/A 和 energy closure 可解释；
结果相对 h=2 有合理网格趋势。
```

失败也有价值，但若失败且代码复杂，不建议合并 solver 代码。

---

## 10. 明确不在本任务范围内

```text
1. Rayleigh/Floquet modal deflation full implementation；
2. DtN-aware Schur complement full implementation；
3. layered-background / RCWA-like approximate inverse；
4. matrix-free Stage 4 MatShell；
5. new black-box PETSc profile sweep；
6. p=2 h=1.0 或更细 full Stage 4；
7. 反演或参数扫描。
```

这些只在 outcomes 中作为后续任务建议保留。

---

## 11. 必须输出文件

```text
docs/task013_real_split_ams_hx_qualification/outcomes/
├── summary.md
├── real_split_equivalence.csv
├── fe_only_real_split_ams_summary.csv
├── fe_only_real_split_ams_memory.csv
├── p_coarsened_auxiliary_summary.csv
├── ams_memory_breakdown.md
├── reduced_stage4_real_split_summary.csv
├── full_stage4_h2_real_split_validation.csv
├── full_stage4_h2_vs_direct_rta.csv
├── full_stage4_h1p5_breakthrough.csv
├── solver_profile_ranking.md
├── merge_recommendation.md
├── next_decision.md
├── parameters.json
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 只保存轻量、有内容的文件。不要提交 0-line placeholder、大型 results 文件、Paraview 文件或完整 matrix dumps。

---

## 12. summary.md 必须回答

```text
1. real split 等价性是否通过？
2. real-split AMS/HX 是否比 Jacobi 明显改善 true residual？
3. p=2 h=5 是否收敛？内存如何？
4. p=2 h=4 是否仍触发内存压力？
5. low-order / p-coarsened auxiliary 是否降低内存？
6. reduced Stage 4 是否可运行？
7. full Stage 4 p=2 h=2 是否运行？是否收敛？R/T/A 是否对上 direct/BLR？
8. full Stage 4 p=2 h=1.5 是否突破？
9. 是否建议合并代码？若不建议，原因是什么？
10. 下一步是继续 AMS，转 Rayleigh/Floquet modal deflation，还是转 DtN-aware block PC？
```

---

## 13. merge_recommendation.md 必须给出明确判断

必须写清楚：

```text
merge_code: yes/no
merge_docs_only: yes/no
reason:
minimal_files_to_merge:
files_to_drop:
risks_if_merged:
recommended_next_branch:
```

如果没有得到有效结果，推荐写：

```text
merge_code: no
merge_docs_only: optional
```

---

## 14. 最终判断标准

### A 档：可合并候选

```text
full Stage 4 p=2 h=2 收敛；
R/T/A 与 direct/BLR reference 一致；
RSS upper 明显低于 17.85 GB；
代码改动局部、可维护。
```

### B 档：保留继续研究，但暂不 production

```text
FE-only / reduced Stage 4 明显优于 Jacobi；
full p=2 h=2 尚未成功；
内存有改善但仍需优化。
```

### C 档：负结果，建议不合并代码

```text
p=2 h=5 不收敛或内存不可接受；
full Stage 4 未取得有效结果；
代码复杂且维护成本高。
```

### D 档：立即停止

```text
real split 不等价；
minimal p=1 case 崩溃；
AMS auxiliary data 无法稳定构造；
true residual 与 KSP residual 严重不一致且无法解释。
```

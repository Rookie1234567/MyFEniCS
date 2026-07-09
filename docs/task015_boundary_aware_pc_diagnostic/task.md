# CODEX TASK 20260708：reduced Stage 4 DtN/Floquet boundary-aware PC diagnostic

## 0. 任务定位

本任务继续在现有研究分支上执行，不新建分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task015_boundary_aware_pc_diagnostic/
├── task.md
├── outcomes/
└── review_report.md
```

本任务是 diagnostic / go-no-go 任务，不是 production solver 实现任务。

Task014a 已证明：

```text
Stage 4 real split 可行；
MPC 后 same-H1 AMS data 可构造；
FE/aux block split 可建立；
但 FE-AMS + aux identity 在 default100 p=1 h=5 上只把 true residual 从 3.436e-2 降到 2.147e-2，未通过 Stage C。
```

因此 Task015 的目标不是继续调 FE-AMS，也不是直接 full p=2 h=2，而是诊断当前停滞到底主要来自：

```text
1. DtN aux block identity 太弱；
2. FE/aux Schur coupling 未处理；
3. Rayleigh/Floquet propagation modes 未处理；
4. positive proxy AMS 对不定 FE block 本身太弱；
5. 以上因素的组合。
```

---

## 1. 不 merge master 的工作方式

本任务依赖 Task014a 的研究脚本和 real-mode MPC 兼容层，但这些代码目前不应合并到 `master`。

正确做法：

```text
继续在当前研究分支上做 Task015；
复用 Task014a 的 runner / helper；
若 Task015 成功，再考虑抽取最小必要代码进入正式求解器；
若 Task015 失败，则只保留文档和负结果，不合并复杂实验代码。
```

可复用但不 production 化的文件：

```text
src/studies/run_stage4_real_split_block_pc.py
src/constraints/floquet_3d.py
src/studies/run_real_split_ams_qualification.py
```

---

## 2. 必须阅读的输入

开始前阅读：

```text
docs/task014a_real_split_stage4_reduced_block_pc/review_report.md
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/summary.md
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/stage4_real_split_equivalence.csv
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/reduced_stage4_block_pc_summary.csv
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/reduced_stage4_block_pc_memory.csv
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/solver_profile_ranking.md
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/merge_recommendation.md
docs/task014a_real_split_stage4_reduced_block_pc/outcomes/next_decision.md
docs/task013_real_split_ams_hx_qualification/review_report.md
```

当前关键 baseline：

```text
case: task014a_default100_stage4_block_grating_p1_h5
Jacobi true residual: 3.436220600931187e-2
FE-AMS + aux identity true residual: 2.1465559540488233e-2
FE-AMS + aux identity iterations: 1000 / max_it
FE-AMS + aux identity RSS: 0.786 GB
```

Task015 的所有改进都应与上述 baseline 比较。

---

## 3. 本任务的核心策略

Task015 不再把 DtN 和 Floquet 拆成两个独立任务。原因是 Task014a 的失败可能来自 DtN、Floquet、FE/aux coupling 或它们的组合。

本任务应在同一 reduced case 中做边界感知诊断：

```text
A. DtN-aware aux / Schur diagnostic；
B. Rayleigh/Floquet modal coarse diagnostic；
C. FE block proxy diagnostic；
D. 小规模 exact / reference 对照。
```

但本任务仍然必须小范围执行：

```text
只以 default100 p=1 h=5 为主 case；
不跑 full p=2 h=2；
不跑 p=2 h=1.5；
不输出未收敛 official R/T/A；
不做新的黑盒 PETSc profile sweep。
```

---

## 4. Stage A：确认并固化 Task014a baseline

### 4.1 目标

复现或读取 Task014a 的 default100 p=1 h=5 baseline，确保后续比较口径一致。

必须保留：

```text
stage4_real_split_fgmres_jacobi
stage4_real_split_fgmres_fe_ams_aux_identity
```

### 4.2 输出

```text
docs/task015_boundary_aware_pc_diagnostic/outcomes/baseline_reproduction.csv
```

字段：

```text
case,p,h_nm,profile,status,iterations,true_relative_residual_norm,ksp_final_residual,rss_upper_gb,notes
```

通过标准：

```text
baseline residual 与 Task014a 同量级；
若不一致，必须解释是代码变动、参数变动还是随机/求解口径变动。
```

---

## 5. Stage B：DtN-aware aux block diagnostic

### 5.1 目标

判断 `P_aux = identity` 是否是主要瓶颈。

### 5.2 Profiles

在 current FE same-H1 AMS 基础上测试：

```text
stage4_real_split_fgmres_fe_ams_aux_identity          # Task014a baseline
stage4_real_split_fgmres_fe_ams_aux_exact            # A_aux exact small solve
stage4_real_split_fgmres_fe_ams_aux_diag             # A_aux diagonal / block diagonal approximation
```

如果 exact aux solve 无法实现，必须记录原因，不要伪造结果。

### 5.3 解释

`aux exact` 只处理 `A_aux` 自身，不处理 `C,D` coupling。它回答的问题是：

```text
aux block 自身是不是问题？
```

如果 aux exact 改善很小，说明瓶颈更可能在 FE/aux coupling 或 Rayleigh/Floquet modal slow modes。

### 5.4 输出

```text
dtn_aux_block_diagnostic.csv
```

字段：

```text
case,profile,status,iterations,true_relative_residual_norm,improvement_vs_aux_identity,rss_upper_gb,aux_complex_dofs,aux_real_dofs,aux_solve_type,notes
```

---

## 6. Stage C：DtN-aware Schur diagnostic

### 6.1 目标

判断 FE/aux coupling 是否是主要瓶颈。

从系统：

```text
[ A_FE    C     ] [E] = [f]
[ D       A_aux ] [a]   [g]
```

构造或近似：

```text
S_aux = A_aux - D A_FE^{-1} C
```

真实 `A_FE^{-1}` 不可用，所以本任务只做 diagnostic approximation：

```text
S_aux_diag ≈ A_aux - D diag(A_FE)^{-1} C
S_aux_pfe  ≈ A_aux - D P_FE^{-1} C
```

其中 `P_FE^{-1}` 使用 Task014a 的 same-H1 AMS apply。

### 6.2 Profiles

至少尝试：

```text
stage4_real_split_fgmres_fe_ams_aux_schur_diag
```

可选尝试：

```text
stage4_real_split_fgmres_fe_ams_aux_schur_pfe
```

注意：`schur_pfe` 可能需要对 aux coupling columns 做若干次 PC apply，成本较高；但 default100 p=1 h=5 中 aux complex dofs 708，real aux dofs 1416，作为 diagnostic 可以接受。如果成本过高，先做 subset / low-rank sample，但必须明确说明。

### 6.3 输出

```text
dtn_schur_diagnostic.csv
```

字段：

```text
case,profile,status,iterations,true_relative_residual_norm,improvement_vs_aux_identity,rss_upper_gb,schur_type,schur_rank_or_size,schur_build_time_s,schur_apply_time_s,notes
```

成功信号：

```text
true residual 比 aux identity 至少降低 10 倍；
或进入 1e-3 以下；
若接近 1e-6，则为强正结果。
```

---

## 7. Stage D：Rayleigh/Floquet modal coarse diagnostic

### 7.1 目标

判断传播/近截止 Rayleigh/Floquet modes 是否是主要慢收敛方向。

构造低维 coarse space：

```text
Z = [lifted Rayleigh/Floquet modal vectors]
```

做 coarse correction / deflation diagnostic：

```text
M_modal(r) = Z (Z^* A Z)^(-1) Z^* r
```

### 7.2 最小范围

不要一开始构造所有 evanescent modes。

建议顺序：

```text
1. zero-order reflected/transmitted modes only；
2. propagating Rayleigh orders；
3. optional near-cutoff evanescent orders。
```

如果 lift 到 volume FE space 太复杂，允许先做 boundary trace / auxiliary-space modal correction diagnostic，但必须说明它不是完整 volume deflation。

### 7.3 Profiles

```text
stage4_real_split_fgmres_fe_ams_modal_zero_order
stage4_real_split_fgmres_fe_ams_modal_propagating
stage4_real_split_fgmres_fe_ams_modal_near_cutoff_optional
```

### 7.4 输出

```text
rayleigh_floquet_modal_diagnostic.csv
```

字段：

```text
case,profile,status,iterations,true_relative_residual_norm,improvement_vs_aux_identity,rss_upper_gb,modal_space,modal_dim,coarse_matrix_condition,notes
```

成功信号：

```text
true residual 比 aux identity 至少降低 10 倍；
或 GMRES residual history 明显消除 stagnation；
若 modal correction 明显优于 Schur，则下一任务专攻 Floquet/Rayleigh deflation。
```

---

## 8. Stage E：FE block proxy diagnostic

### 8.1 目标

如果 Stage B-D 都不能明显改善，需要确认问题是否其实来自 FE block preconditioner 本身，而不是边界。

测试：

```text
P_FE = same-H1 AMS positive proxy           # current
P_FE = shifted/absorbing H(curl) proxy      # optional
P_FE = small exact FE block on tiny10 only   # diagnostic lower bound
```

注意：full exact FE block 不允许用于 default100 或更大 case；只能在 tiny10 上判断 FE block PC 的理论上限。

### 8.2 输出

```text
fe_block_proxy_diagnostic.csv
```

重点回答：

```text
当前 positive AMS proxy 是否太偏离 indefinite Maxwell FE block？
如果 tiny exact FE block + aux exact 仍不改善，问题可能在 modal/global correction；
如果 exact FE block 显著改善，说明 FE proxy 也需要升级。
```

---

## 9. Stage F：组合测试

只有 Stage B、C 或 D 中至少一个方向出现明确正信号，才允许做组合测试。

候选组合：

```text
FE-AMS + Schur_diag + modal_zero_order
FE-AMS + Schur_pfe + modal_propagating
```

输出：

```text
combined_boundary_pc_diagnostic.csv
```

不要把组合测试扩大到 p=2 h=5，除非 single component 已经通过强正信号。

---

## 10. R/T/A 规则

本任务默认不输出 official R/T/A。

只有满足以下条件才允许输出 diagnostic R/T/A：

```text
KSP converged；
true_relative_residual_norm <= 1e-6；
solution can be reconstructed to complex Stage4 fields；
postprocessing path is unchanged and verified。
```

即使输出，也必须标记为：

```text
diagnostic only, not official reference
```

未收敛时禁止输出 R/T/A。

---

## 11. 必须输出文件

```text
docs/task015_boundary_aware_pc_diagnostic/outcomes/
├── summary.md
├── baseline_reproduction.csv
├── dtn_aux_block_diagnostic.csv
├── dtn_schur_diagnostic.csv
├── rayleigh_floquet_modal_diagnostic.csv
├── fe_block_proxy_diagnostic.csv
├── combined_boundary_pc_diagnostic.csv
├── residual_history_summary.csv
├── solver_profile_ranking.md
├── merge_recommendation.md
├── next_decision.md
├── parameters.json
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 只保留轻量 JSON/CSV/log excerpts，不提交大型矩阵、HDF5、XDMF、Paraview 或完整 binary dumps。

---

## 12. summary.md 必须回答

```text
1. Task014a baseline 是否复现？
2. aux exact 是否显著优于 aux identity？
3. Schur_diag / Schur_pfe 是否显著改善 residual？
4. Rayleigh/Floquet modal coarse correction 是否显著改善 residual？
5. 当前主要瓶颈更像 DtN aux block、FE/aux coupling、Floquet/Rayleigh propagation modes，还是 FE block proxy？
6. 是否有 profile 达到 10x 改善或 true residual <= 1e-6？
7. 是否允许进入 reduced p=2 h=5？
8. 是否允许进入 full p=2 h=2？
9. 是否建议合并代码？
10. Task16 应专攻 Schur、modal deflation、二者组合，还是停止 real-split AMS 主线？
```

---

## 13. 合并策略

默认：

```text
merge_code: no
merge_docs_only: yes / optional
```

只有满足以下条件，才考虑合并最小代码：

```text
default100 p=1 h=5 至少一个 boundary-aware profile 达到 10x 改善；
代码改动局部、可维护；
不破坏 direct/BLR production path；
不引入默认启用的实验 PC。
```

---

## 14. 下一步决策规则

### A 档：允许进入 reduced p=2 h=5

```text
某个 boundary-aware PC 在 default100 p=1 h=5 上 true residual <= 1e-6；
或相对 aux identity 改善 >= 10x；
内存仍远低于 BLR/direct；
residual history 无明显异常。
```

### B 档：继续诊断，不进入 p=2

```text
有改善但不足 10x；
能定位主要瓶颈但 PC 还弱；
下一步针对最有效分支继续强化。
```

### C 档：停止当前 real-split AMS 主线

```text
aux exact / Schur / modal correction 均不能显著改善；
true residual 仍停在 1e-2 量级；
FE block proxy 也没有改善空间；
代码复杂度快速上升。
```

### D 档：立即停止

```text
baseline 不能复现；
Schur / modal correction 导致 residual 变差且无法解释；
coarse matrix 严重病态且无法稳定正则化；
必须大幅侵入 production path 才能继续。
```

---

## 15. 最终目标句

任务结束时必须用一句话回答：

```text
Task014a 的停滞主要来自 DtN aux block、FE/aux Schur coupling、Rayleigh/Floquet modal slow modes、FE block proxy，还是目前无法区分？
```

不要只输出一堆 residual 表格而不给决策。

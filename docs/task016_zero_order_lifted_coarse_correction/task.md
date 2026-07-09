# CODEX TASK 20260708：dominant zero-order FE+aux lifted coarse correction / low-rank sampled Schur

## 0. 任务定位

本任务继续在现有研究分支上执行，不新建分支：

```text
codex/20260707-real-split-ams-hx-qualification
```

任务目录：

```text
docs/task016_zero_order_lifted_coarse_correction/
├── task.md
├── outcomes/
└── review_report.md
```

本任务仍是 research / diagnostic / prototype 任务，不是 production solver 任务。

Task015 已定位：

```text
FE-AMS + aux identity 后，default100 p=1 h=5 的 residual 几乎全部集中在 auxiliary block；
其中 dominant residual mode 是 top,(m,n)=(0,0),y；
aux exact / aux diag / aux-space-only modal correction 都无改善；
Schur_diag = A_aux - D diag(A_FE)^(-1) C 明显变差。
```

因此 Task016 的目标是：

```text
针对 dominant zero-order mode，构造同时包含 FE trace/volume response 与 aux coordinate 的 lifted coarse correction，
验证它是否能显著降低 default100 p=1 h=5 的 true residual。
```

一句话：

```text
不要只修 a 向量里的 modal coordinate；要同时修对应的 FE 场和 aux mode。
```

---

## 1. 基线和成功标准

当前主 baseline：

```text
case: task014a_default100_stage4_block_grating_p1_h5
FE-AMS + aux identity true residual = 2.1465559540488233e-2
Jacobi true residual = 3.436220600931187e-2
dominant mode = top,(0,0),y
```

Task016 成功分级：

```text
A: true residual <= 1e-6，或相对 FE-AMS+aux identity 改善 >= 100x；
B: true residual <= 2e-3，或相对 FE-AMS+aux identity 改善 >= 10x；
C: 改善 2x-10x；只算弱正信号，不允许进入 p=2；
D: 改善 <2x 或变差；停止该方向。
```

只有 A/B 档才允许建议后续进入 reduced p=2 h=5。任何情况下，本任务不进入 full p=2 h=2 或 p=2 h=1.5。

---

## 2. 必须阅读的输入

开始前阅读：

```text
docs/task015_boundary_aware_pc_diagnostic/review_report.md
docs/task015_boundary_aware_pc_diagnostic/outcomes/summary.md
docs/task015_boundary_aware_pc_diagnostic/outcomes/boundary_residual_decomposition.csv
docs/task015_boundary_aware_pc_diagnostic/outcomes/aux_modal_residual_decomposition.csv
docs/task015_boundary_aware_pc_diagnostic/outcomes/dtn_aux_block_diagnostic.csv
docs/task015_boundary_aware_pc_diagnostic/outcomes/dtn_schur_diagnostic.csv
docs/task015_boundary_aware_pc_diagnostic/outcomes/rayleigh_floquet_modal_diagnostic.csv
docs/task015_boundary_aware_pc_diagnostic/outcomes/fe_proxy_upper_bound_diagnostic.csv
docs/task015_boundary_aware_pc_diagnostic/outcomes/next_decision.md
docs/task014a_real_split_stage4_reduced_block_pc/review_report.md
src/studies/run_stage4_boundary_pc_diagnostic.py
src/studies/run_stage4_real_split_block_pc.py
```

---

## 3. 数学目标

Stage 4 complex block form：

```text
[ A_FE    C     ] [E] = [f]
[ D       A_aux ] [a]   [g]
```

Task15 已证明 aux-only correction 无效。因此 Task016 要构造 coarse basis：

```text
Z = [ z_1, z_2, ... ]
```

每个 `z_j` 必须同时包含：

```text
FE component: q_j
aux component: e_j
```

其中 `e_j` 是 selected DtN/Rayleigh modal unknown 的 coordinate vector，`q_j` 是对应 FE response / lift。

第一优先的 lifted vector：

```text
z_j = [ q_j ; e_j ]
q_j ≈ -P_FE^{-1} C_j
```

解释：

```text
C_j 表示该 aux mode 对 FE equation 的 forcing column；
-P_FE^{-1} C_j 是该 aux amplitude 在 FE field 中诱导的 approximate response；
把 q_j 和 e_j 一起放进 coarse space，才能修正 FE/aux coupled residual。
```

在 real split 系统中，一个 complex lifted vector 应对应 real/imag pair。必须明确记录采用的 real basis 构造方式。

---

## 4. 重要原则：遇到问题不要直接停止

本任务的目标是解决问题，不是遇到第一个障碍就停止。遇到问题时必须先尝试合理排错和替代实现。

必须遵守以下 troubleshooting ladder：

### 4.1 如果 mode mapping 可疑

必须核对：

```text
mode_id
port
m,n
polarization
real/imag index mapping
aux row/column mapping
```

并至少输出 `selected_mode_mapping.csv`。

### 4.2 如果 coarse matrix 病态

不要立刻停止。依次尝试：

```text
1. 归一化每个 Z vector；
2. 删除近线性相关 vector；
3. 从单 mode 改为 top/bottom zero-order pair；
4. 加小 regularization：delta = 1e-12 ~ 1e-8 * ||Z^T A Z||；
5. 检查 transpose / Hermitian transpose 口径；
6. 检查 real split pair 是否构造正确。
```

### 4.3 如果 correction 让 residual 变差

不要直接停止。依次尝试：

```text
1. sign flip: q_j = +P_FE^{-1} C_j vs -P_FE^{-1} C_j；
2. aux sign flip: e_j vs -e_j；
3. post-correction one-shot vs PC-in-KSP；
4. additive coarse correction vs residual-corrected coarse correction；
5. single mode vs top/bottom pair vs x/y zero-order set；
6. exact FE lift on tiny10 to check whether AMS lift is too inaccurate。
```

### 4.4 如果 FE lift 构造困难

不要直接跳到 full physical lift。按以下顺序尝试：

```text
1. algebraic lift: q_j = -P_FE^{-1} C_j；
2. diagonal lift: q_j = -diag(A_FE)^(-1) C_j，仅作 sanity，不作为最终；
3. exact FE lift on tiny10；
4. same-H1 AMS lift on default100；
5. physical trace/volume Rayleigh lift，仅在前面有正信号后做。
```

### 4.5 如果 default100 失败

必须回到 tiny10 或 smaller default case 做机制验证，而不是直接放弃：

```text
tiny10 auto p=1 h=5；
default100 p=1 h=10 if available；
then default100 p=1 h=5。
```

只有完成以上排错后仍没有改善，才允许给出停止结论。

---

## 5. Stage A：selected dominant mode verification

### 5.1 目标

确认 Task15 中的 dominant mode mapping，并锁定第一批 coarse modes。

默认第一 mode：

```text
top,(m,n)=(0,0),y
```

必须同时准备候选 set：

```text
S1: top,(0,0),y only
S2: top/bottom,(0,0),y
S3: top/bottom,(0,0),x/y 共 4 个 zero-order polarization channels
```

如果实际 mode list 中 polarization 命名不是 x/y，而是 s/p，需要建立映射并说明。

### 5.2 输出

```text
selected_mode_mapping.csv
```

字段：

```text
set_name,mode_id,port,m,n,polarization,real_aux_index,imag_aux_index,is_propagating,is_near_cutoff,source_residual_fraction,notes
```

通过标准：

```text
selected mode 与 Task15 aux modal residual decomposition 一致；
real/imag index mapping 清楚；
若不一致，必须先修正 mapping，不进入 Stage B。
```

---

## 6. Stage B：lifted vector construction and sanity checks

### 6.1 目标

构造 coarse vector `Z`，并验证其不是 aux-only vector。

至少实现并比较：

```text
Z_aux_only              # 已知无效，仅作 sanity
Z_diag_lift             # q=-diag(A_FE)^-1 C_j，仅作 sanity
Z_pfe_lift              # q=-P_FE^-1 C_j，主候选
Z_pfe_lift_sign_flip    # q=+P_FE^-1 C_j，排查 sign
Z_exact_lift_tiny10     # tiny10 only
```

### 6.2 必须检查

对每个 Z set 输出：

```text
Z dimension
||Z_FE||
||Z_aux||
FE/aux norm ratio
||A Z||
coarse matrix condition
Z^T r magnitude
```

如果 `||Z_FE||` 接近 0，则它退化为 aux-only correction，不算有效 lifted correction。

### 6.3 输出

```text
lifted_coarse_vector_diagnostic.csv
```

字段：

```text
case,set_name,lift_type,modal_dim,real_coarse_dim,fe_norm,aux_norm,fe_aux_norm_ratio,az_norm,zt_r_norm,coarse_condition,regularization,notes
```

---

## 7. Stage C：one-shot post-correction diagnostic

### 7.1 目标

在不先改 KSP PC 的情况下，对 Task014a/Task15 baseline solution 做 one-shot coarse correction，验证 correction 方向是否对。

对 baseline solution `x0`：

```text
r0 = b - A x0
alpha = (Z^T A Z)^(-1) Z^T r0
x1 = x0 + Z alpha
r1 = b - A x1
```

或使用 complex/Hermitian counterpart，必须记录实际口径。

### 7.2 输出

```text
one_shot_coarse_correction.csv
```

字段：

```text
case,set_name,lift_type,residual_before,residual_after,improvement,fe_fraction_after,aux_fraction_after,coarse_condition,regularization,notes
```

### 7.3 成功信号

```text
one-shot correction 将 residual 至少降低 2x：说明方向可能正确；
降低 10x：强正信号，进入 Stage D；
变差：执行 troubleshooting ladder 后再判断。
```

如果所有 lifted variants 的 one-shot correction 均无改善，并且排错后仍无改善，应停止，不进入 KSP PC 集成。

---

## 8. Stage D：KSP PC with lifted coarse correction

### 8.1 目标

将 lifted coarse correction 集成到 real-split FGMRES PC 中。

当前 baseline PC：

```text
M0^{-1} = FE same-H1 AMS + aux identity
```

新增 two-level additive PC：

```text
M^{-1} r = M0^{-1} r + Z (Z^T A Z)^(-1) Z^T r
```

也可以测试 residual-corrected form：

```text
M^{-1} r = M0^{-1} r + Z (Z^T A Z)^(-1) Z^T (r - A M0^{-1} r)
```

必须记录使用哪一种。

### 8.2 Profiles

至少测试：

```text
stage4_real_split_fgmres_fe_ams_aux_identity                         # baseline
stage4_real_split_fgmres_fe_ams_lifted_zero_order_top_y_additive
stage4_real_split_fgmres_fe_ams_lifted_zero_order_top_bottom_y_additive
stage4_real_split_fgmres_fe_ams_lifted_zero_order_xy_additive
```

可选：

```text
stage4_real_split_fgmres_fe_ams_lifted_zero_order_top_y_residual_corrected
```

### 8.3 输出

```text
lifted_coarse_ksp_summary.csv
residual_history_summary.csv
```

字段：

```text
case,profile,set_name,lift_type,pc_form,status,iterations,true_relative_residual_norm,improvement_vs_aux_identity,ksp_final_residual,rss_upper_gb,setup_time_s,solve_time_s,coarse_condition,regularization,notes
```

成功标准：

```text
B 档：true residual <= 2e-3 或 improvement >= 10x；
A 档：true residual <= 1e-6 或 improvement >= 100x。
```

---

## 9. Stage E：low-rank sampled Schur diagnostic

### 9.1 目标

如果 Stage D 中 lifted correction 有正信号，但不够强，尝试 residual-dominant sampled Schur。

不要构造 full 708 x 708 Schur。只对 selected dominant modes 构造 sampled approximation：

```text
S_selected ≈ A_selected - D_selected P_FE^{-1} C_selected
```

selected modes 按 Stage A 的 S1/S2/S3 逐步扩展。

### 9.2 输出

```text
sampled_schur_diagnostic.csv
```

字段：

```text
case,set_name,selected_dim,schur_type,build_time_s,condition,regularization,true_residual_after_pc,improvement_vs_aux_identity,notes
```

若 sampled Schur 需要大量 PC apply，必须记录 apply_count 和 apply_time。

---

## 10. Stage F：gate to reduced p=2 h=5

只有 Stage D 或 E 达到 B 档，才允许测试：

```text
reduced Stage 4 p=2 h=5
```

否则禁止进入 p=2。

p=2 h=5 输出：

```text
p2_h5_lifted_coarse_decision.csv
```

成功标准：

```text
true residual 明显优于 p2 baseline；
内存仍远低于 BLR/direct；
不出现 unexplained residual mismatch。
```

本任务仍然不进入 full p=2 h=2。

---

## 11. 不在本任务范围内

```text
1. full Stage 4 p=2 h=2；
2. full Stage 4 p=2 h=1.5；
3. full 708-mode Schur；
4. full volume physical Rayleigh basis for all modes；
5. matrix-free MatShell；
6. RCWA/layered inverse；
7. 新一轮黑盒 PETSc profile sweep；
8. 未收敛 R/T/A。
```

---

## 12. 必须输出文件

```text
docs/task016_zero_order_lifted_coarse_correction/outcomes/
├── summary.md
├── selected_mode_mapping.csv
├── lifted_coarse_vector_diagnostic.csv
├── one_shot_coarse_correction.csv
├── lifted_coarse_ksp_summary.csv
├── sampled_schur_diagnostic.csv
├── residual_history_summary.csv
├── p2_h5_lifted_coarse_decision.csv
├── solver_profile_ranking.md
├── merge_recommendation.md
├── next_decision.md
├── parameters.json
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 只保留轻量 JSON/CSV/log excerpts，不提交大型 matrix dumps、HDF5、XDMF、Paraview 或完整 binary dumps。

---

## 13. summary.md 必须回答

```text
1. selected mode mapping 是否与 Task15 一致？
2. lifted vector 是否真的包含非零 FE component？
3. one-shot correction 是否降低 residual？降低多少？
4. KSP PC 中 lifted correction 是否优于 FE-AMS + aux identity？
5. 单 mode、top/bottom pair、x/y zero-order set 哪个最好？
6. coarse matrix 是否病态？如何处理？
7. 若失败，失败原因是 lift 错、sign 错、P_FE lift 太弱、还是 dominant mode 解释不充分？
8. 是否允许进入 reduced p=2 h=5？
9. 是否建议合并代码？
10. Task17 应继续 lifted correction、改 FE block proxy，还是停止 real-split AMS 主线？
```

---

## 14. 合并策略

默认：

```text
merge_code: no
merge_docs_only: yes / optional
```

只有满足以下条件才考虑合并最小代码：

```text
default100 p=1 h=5 lifted correction 达到 B 档或 A 档；
代码局部、可维护；
不破坏 direct/BLR production path；
不引入默认启用的实验 PC。
```

---

## 15. 最终目标句

任务结束时必须用一句话回答：

```text
Dominant zero-order FE+aux lifted coarse correction 是否能把 Task015 的 2.1466e-2 residual 显著压低？
```

不要只输出一堆 residual 表格而不给判断。

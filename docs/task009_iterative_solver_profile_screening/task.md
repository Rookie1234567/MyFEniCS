# CODEX TASK 20260706：Stage 4 3D Maxwell 迭代求解器 profiles 快速筛选

## 0. 分支与执行流程

本任务书写在当前 task008 分支中，供下一轮本地执行。**不要由 ChatGPT 代为创建远程分支。**

当前已完成分支：

```text
codex/20260706-target-50x25x140-oblique80-official-benchmark
```

开始 task009 前，建议先在本地完成 task008 的轻量收尾并合并：

```bash
git checkout master
git pull
git merge codex/20260706-target-50x25x140-oblique80-official-benchmark
git push origin master
```

然后由本地 Codex/开发者从更新后的 `master` 新建 task009 分支，例如：

```bash
git checkout -b codex/20260706-iterative-solver-profile-screening
git push -u origin codex/20260706-iterative-solver-profile-screening
```

推荐本任务分支名：

```text
codex/20260706-iterative-solver-profile-screening
```

开始前必须阅读：

```text
docs/task008_70nm_official_convergence_benchmark/review_report.md
docs/task008_70nm_official_convergence_benchmark/outcomes/summary.md
docs/task008_70nm_official_convergence_benchmark/outcomes/official_convergence.csv
docs/task008_70nm_official_convergence_benchmark/outcomes/p2_convergence.csv
docs/task008_70nm_official_convergence_benchmark/outcomes/failure_boundary.md
docs/task008_70nm_official_convergence_benchmark/outcomes/parameters.json
docs/task007_dtn_port_modal_official_rta/review_report.md
notes/reference/current_version_boundaries.md
README.md
```

本任务的任务书、outcomes 和后续 review report 都应保存在：

```text
docs/task009_iterative_solver_profile_screening/
├── task.md
├── outcomes/
└── review_report.md
```

所有轻量结果写入：

```text
docs/task009_iterative_solver_profile_screening/outcomes/
```

不要改写 task000-task008 的 outcomes 或 review report。

---

## 1. 背景

task008 已在目标几何和 80° 斜入射条件下建立了本机 default MUMPS direct benchmark 与资源边界：

```text
Geometry: 50×25×140 nm domain, 17×25×120 nm grating
Incidence: theta_from_z=80°, phi=0°, s polarization
Official power source: dtn_port_modal_amplitudes + A_volume
Best completed direct benchmark: p=2 h=2 nm
R = 0.0013429328462348958
T = 0.5992132294442478
A_volume = 0.3994438377095067
R+T+A_volume = 0.9999999999999893
Direct boundary: p=2 h=1.5 stopped at stage4_dtn_augmented_ksp_setup
Assemble boundary: p=2 h=1 timeout at stage4_dtn_base_matrix_assembled with large swap
```

用户后续实际问题可能更苛刻：波长可能降至 `0.7~0.8 nm`，若仍按二阶单元且 `h < λ/5`，自由度会达到上亿甚至更高。1 TB 内存工作站也不适合继续依赖全局 sparse direct solver。因此，需要尽快筛选可用的 PETSc 迭代求解器与预条件器组合。

本任务不是最终大规模求解方案，也不是开发高级 H(curl) AMS / shifted Maxwell / two-level DDM。它的定位是：

```text
在 task008 direct-reference cases 上快速筛选 PETSc 现成 iterative profiles，找出 1–2 个有希望上 1 TB 工作站继续扩展的候选组合。
```

---

## 2. 任务目标

本任务只做三件事：

```text
1. 在代码中加入一组 PETSc iterative solver profiles；
2. 在 task008 已有 direct reference cases 上系统测试；
3. 根据 residual、R/T/A、内存、时间，选出最有希望的 profile。
```

核心判据：

```text
能否复现 task008 p=2 h=2 direct R/T/A；
能否突破 p=2 h=1.5 default direct failure boundary；
是否能显著低于 direct solve 内存；
迭代次数是否可控。
```

---

## 3. 固定物理与几何设置

所有 task009 测试均固定使用 task008 主设置：

```text
stage_case = stage4_block_grating
period_x = 50 nm
period_y = 25 nm
domain_x = 50 nm
domain_y = 25 nm
substrate_thickness = 10 nm
grating_height = 120 nm
top_air_above_grating = 10 nm
air_height = 130 nm
total_height = 140 nm
grating_width_x = 17 nm
grating_width_y = 25 nm
lambda0 = 13.5 nm
incident_theta_from_z_deg = 80
incident_azimuth_phi_deg = 0
polarization_kind = s
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
stage4_dtn_order_policy = auto_propagating
official_power_source = dtn_port_modal_amplitudes
A = A_volume_total from volume_integral_Im_epsilon_E2
MPI ranks = 8 unless otherwise specified
```

必须保留 task008 中验证过的：

```text
kx = 0.458350341046137
ky = 0
kz = -0.0808195317433606
Floquet phase x = -0.600741134898 - 0.799443612046j
Floquet phase y = 1
polarization = (0,1,0)
k dot E = 0
```

---

## 4. 必须实现的 PETSc iterative solver profiles

请在现有 solver profile 体系中新增或完善以下 profiles。命名可以按代码风格微调，但 summary 和 CSV 中必须能对应到这些逻辑。

### 4.1 Baseline 组

#### iter_gmres_none

```text
-ksp_type gmres
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_gmres_restart 80
-ksp_monitor_true_residual
-pc_type none
```

用途：判断原系统无预条件时有多难。预计多数较大 case 不收敛。

#### iter_gmres_jacobi

```text
-ksp_type gmres
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_gmres_restart 80
-ksp_monitor_true_residual
-pc_type jacobi
```

用途：最弱代数 baseline。

#### iter_gmres_bjacobi_ilu0

```text
-ksp_type gmres
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_gmres_restart 80
-ksp_monitor_true_residual
-pc_type bjacobi
-sub_ksp_type preonly
-sub_pc_type ilu
-sub_pc_factor_levels 0
```

用途：低成本代数/块 Jacobi baseline。

### 4.2 主力组

#### iter_fgmres_asm1_ilu0

```text
-ksp_type fgmres
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_gmres_restart 80
-ksp_monitor_true_residual
-pc_type asm
-pc_asm_overlap 1
-sub_ksp_type preonly
-sub_pc_type ilu
-sub_pc_factor_levels 0
```

这是本任务首选 profile。

#### iter_fgmres_asm2_ilu0

```text
-ksp_type fgmres
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_gmres_restart 80
-ksp_monitor_true_residual
-pc_type asm
-pc_asm_overlap 2
-sub_ksp_type preonly
-sub_pc_type ilu
-sub_pc_factor_levels 0
```

用途：判断 overlap=2 是否明显改善收敛。

#### iter_fgmres_asm1_ilu1

```text
-ksp_type fgmres
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_gmres_restart 80
-ksp_monitor_true_residual
-pc_type asm
-pc_asm_overlap 1
-sub_ksp_type preonly
-sub_pc_type ilu
-sub_pc_factor_levels 1
```

用途：判断 ILU fill level 提升是否值得。

### 4.3 强预条件器组

#### iter_fgmres_asm1_lu

```text
-ksp_type fgmres
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_gmres_restart 80
-ksp_monitor_true_residual
-pc_type asm
-pc_asm_overlap 1
-sub_ksp_type preonly
-sub_pc_type lu
-sub_pc_factor_mat_solver_type mumps
```

用途：判断局部直接解是否能明显改善收敛。该 profile 可能较耗内存，不要求所有大 case 都跑。

#### iter_fgmres_asm2_lu

可选：

```text
-ksp_type fgmres
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_gmres_restart 80
-ksp_monitor_true_residual
-pc_type asm
-pc_asm_overlap 2
-sub_ksp_type preonly
-sub_pc_type lu
-sub_pc_factor_mat_solver_type mumps
```

仅在 asm1_lu 表现有希望且内存允许时运行。

### 4.4 低内存备选组

#### iter_bicgstab_asm1_ilu0

```text
-ksp_type bicgstab
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_monitor_true_residual
-pc_type asm
-pc_asm_overlap 1
-sub_ksp_type preonly
-sub_pc_type ilu
-sub_pc_factor_levels 0
```

#### iter_bicgstab_bjacobi_ilu0

```text
-ksp_type bicgstab
-ksp_rtol 1e-6
-ksp_atol 1e-12
-ksp_max_it 1000
-ksp_monitor_true_residual
-pc_type bjacobi
-sub_ksp_type preonly
-sub_pc_type ilu
-sub_pc_factor_levels 0
```

用途：低内存备选。BiCGStab 可能不如 GMRES 稳定，但若内存优势明显，可作为大规模候选。

---

## 5. 测试矩阵与执行策略

### 5.1 Direct reference cases

使用 task008 已有 direct reference：

```text
p=2 h=5
p=2 h=4
p=2 h=3
p=2 h=2.5
p=2 h=2
```

其中 p=2 h=2 是当前本机 best-effort official benchmark 主结果：

```text
R_direct = 0.0013429328462348958
T_direct = 0.5992132294442478
A_direct = 0.3994438377095067
```

### 5.2 Boundary case

最后只用筛选出的 1–3 个最好 profiles 尝试：

```text
p=2 h=1.5
```

该点是 task008 default direct failure boundary，不要求所有 profiles 都跑。

### 5.3 执行策略

不要所有 profiles 直接跑到最大 case。必须分阶段筛选：

```text
Stage A：所有 profiles 先跑 p=2 h=5 和 p=2 h=4；
Stage B：保留 residual 明显下降或收敛的 profiles，跑 p=2 h=3 和 h=2.5；
Stage C：只保留最有希望的 profiles，跑 p=2 h=2；
Stage D：只用 1–3 个最好 profiles 尝试 p=2 h=1.5。
```

若某个 profile 在 `p=2 h=4` 已经明显不收敛或内存过高，可提前停止该 profile 后续测试，并在 `iterative_failure_cases.csv` 中记录原因。

---

## 6. 成功/失败判据

### 6.1 A 档：可作为工作站首选

满足：

```text
p=2 h=2 能收敛；
R/T/A 接近 direct；
p=2 h=1.5 能跑完或至少明显推进；
内存低于 default direct；
迭代次数没有爆炸。
```

### 6.2 B 档：有潜力但需要加强

满足：

```text
残差能稳定下降；
p=2 h=2 接近 direct，但迭代次数较多；
p=2 h=1.5 未完成，但不是立刻崩溃。
```

后续可考虑：

```text
OOC local LU
更强 ILU
shifted Maxwell
two-level DDM
H(curl) AMS
```

### 6.3 C 档：淘汰

满足任一：

```text
p=2 h=4 都不收敛；
残差停滞；
迭代 1000 步仍无明显下降；
R/T/A 与 direct 差异巨大；
内存不比 direct 低；
求解器频繁崩溃。
```

---

## 7. 必须记录的字段

每个 iterative run 至少记录：

```text
p
h_nm
profile_name
mpi_ranks
ksp_type
pc_type
pc_asm_overlap
sub_ksp_type
sub_pc_type
sub_pc_factor_levels
sub_pc_factor_mat_solver_type
ksp_converged_reason
ksp_converged_reason_text
ksp_iterations
ksp_initial_residual_norm
ksp_final_residual_norm
true_residual_norm
true_relative_residual_norm
setup_time_seconds
solve_time_seconds
elapsed_seconds
max_rss_mb
RSS_upper_GB
matrix_rows
nnz_used
estimated_AIJ_matrix_memory_GB
R_total_dtn_port_modal
T_total_dtn_port_modal
A_volume_total
R_plus_T_plus_A_volume
energy_closure_error_dtn_port_modal_volume
R_direct
T_direct
A_direct
abs_error_R
abs_error_T
abs_error_A
relative_error_R
relative_error_T
relative_error_A
status
failure_stage
returncode
stdout_tail
stderr_tail
```

必须注意：

```text
不能只看 residual；必须看 R/T/A 是否接近 direct。
```

---

## 8. 输出文件要求

本任务 outcomes 至少包含：

```text
docs/task009_iterative_solver_profile_screening/outcomes/
├── summary.md
├── iterative_profile_summary.csv
├── iterative_vs_direct_rta.csv
├── iterative_resource.csv
├── iterative_failure_cases.csv
├── profile_ranking.md
├── workstation_recommendation.md
├── parameters.json
├── run_log.txt
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 只保存轻量文件：

```text
run_summary.json
progress_3d.jsonl
solver_log.txt
stdout_tail.txt
stderr_tail.txt
iterative_profile_row.json
```

不要提交大型文件：

```text
results/*/*.vtu
results/*/*.bp
results/*/*.h5
完整 results/ 目录
大型临时矩阵文件
MUMPS OOC scratch 文件
```

---

## 9. summary.md 必须包含的表格

`summary.md` 必须用中文撰写，并至少包含：

### 表 1：测试设置

| item | value |
|---|---|
| geometry | 50×25×140 nm, grating 17×25×120 nm |
| incidence | theta_from_z=80°, phi=0°, s polarization |
| official reference | task008 p=2 h=2 direct |
| MPI | 8 |
| target | iterative profile screening |

### 表 2：profiles 列表

| profile | ksp | pc | overlap | sub_pc | purpose |
|---|---|---|---:|---|---|

### 表 3：p=2 h=5/h=4 初筛结果

| profile | h | converged | iterations | final residual | R error | T error | A error | RSS upper GB | status |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|

### 表 4：p=2 h=3/h=2.5 复筛结果

| profile | h | converged | iterations | final residual | R error | T error | A error | RSS upper GB | status |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|

### 表 5：p=2 h=2 direct-reference 复现结果

| profile | converged | iterations | R_iter | T_iter | A_iter | abs_error_R | abs_error_T | abs_error_A | RSS upper GB | status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|

### 表 6：p=2 h=1.5 boundary 尝试

| profile | status | iterations | final residual | R | T | A | RSS upper GB | failure stage | note |
|---|---|---:|---:|---:|---:|---:|---:|---|---|

### 表 7：profile ranking

| rank | profile | grade | reason | workstation use |
|---:|---|---|---|---|

summary 必须回答：

1. 哪些 profiles 已实现？
2. 哪些 profiles 在 p=2 h=4 就被淘汰？
3. 哪些 profiles 能复现 p=2 h=2 direct R/T/A？
4. 哪些 profiles 能尝试或突破 p=2 h=1.5 failure boundary？
5. 哪个 profile 最推荐上 1 TB 工作站？
6. 哪个 profile 作为备选？
7. 是否需要继续测试 OOC local LU、shifted Maxwell、H(curl) AMS 或 DDM？
8. 当前是否建议合并？

---

## 10. workstation_recommendation.md 要求

必须给出明确工作站建议：

```text
workstation_first_profile = ...
workstation_second_profile = ...
workstation_first_case = p=2 h=1.5
workstation_second_case = p=2 h=1
workstation_third_case = p=2 h=0.75
workstation_fourth_case = p=2 h=0.5
```

并说明：

```text
不要直接从 task009 跳到 h=0.14~0.16 nm；
先用 1 TB 工作站验证 iterative profile 是否能突破 p=2 h=1.5 / h=1；
若 p=2 h=1 都不稳定，不应继续硬推 h=0.5 或 h=0.14。
```

---

## 11. 验收标准

本任务通过标准：

1. 代码中实现上述 iterative profiles，至少包含：

```text
iter_gmres_none
iter_gmres_jacobi
iter_gmres_bjacobi_ilu0
iter_fgmres_asm1_ilu0
iter_fgmres_asm2_ilu0
iter_fgmres_asm1_ilu1
iter_fgmres_asm1_lu
iter_bicgstab_asm1_ilu0
```

2. 至少在 `p=2 h=5` 和 `p=2 h=4` 上完成所有 profiles 初筛，或明确记录失败原因。
3. 至少对最有希望的 profiles 继续跑 `p=2 h=3`、`p=2 h=2.5`、`p=2 h=2`。
4. 至少选择 1–3 个 profiles 尝试 `p=2 h=1.5` boundary。
5. 每个 completed iterative run 必须输出 residual、iterations、memory、R/T/A 与 direct 差异。
6. 必须生成 `profile_ranking.md` 和 `workstation_recommendation.md`。
7. 不得把 residual 收敛当作唯一成功标准，必须检查 R/T/A。
8. 不提交大型结果文件或空 placeholder raw files。

---

## 12. 不在本任务范围内的内容

本任务暂不做：

```text
1. 自研 H(curl) AMS；
2. shifted Maxwell preconditioner；
3. two-level Schwarz / BDDC / FETI-DP；
4. matrix-free operator；
5. p polarization；
6. 0.7 nm 波长完整真实网格；
7. 反演流程；
8. common-reference-plane T。
```

这些方向重要，但会让 task009 失焦。task009 只做 PETSc 现成 iterative profiles 的快速筛选。

---

## 13. 最终预期

本任务完成后，应能回答：

```text
在当前 Stage 4 3D Maxwell + DtN port 系统中，哪些 PETSc 迭代法/预条件器组合完全没希望？
哪些组合能复现 p=2 h=2 direct reference？
是否存在能突破 p=2 h=1.5 default direct failure boundary 的候选？
1 TB 工作站上第一优先级该用哪个 solver profile？
```

如果所有现成 profiles 均失败，则必须明确写出：

```text
普通 Jacobi/BJacobi/ASM/ILU/LU 组合不足以解决该问题；下一步应转向 shifted Maxwell、H(curl) AMS、two-level DDM 或 matrix-free + physics-based preconditioner。
```

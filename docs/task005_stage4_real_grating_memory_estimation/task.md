# CODEX TASK 20260703：真实 3D 光栅 p=2 内存、OOC 与迭代法资源估算

## 0. 分支要求

继续在当前分支工作：

```text
codex/20260702-rta-output-volume-absorption
```

本任务仍然写在该分支上，后续由人工统一在本地合并到 `master`。

开始前必须阅读：

```text
docs/task004_small_cell_p_convergence_mpi_regression/review_report.md
notes/reference/current_version_boundaries.md
README.md
notes/quick_start/stage4_3d_block_grating_usage_guide.md
```

本任务的任务书、outcomes 和后续 review report 都应保存在：

```text
docs/task005_stage4_real_grating_memory_estimation/
├── task.md
├── outcomes/
└── review_report.md
```

本任务完成后，所有轻量结果写入：

```text
docs/task005_stage4_real_grating_memory_estimation/outcomes/
```

不要改写 task000-task004 的 outcomes 或 review report。

---

## 1. 任务性质

本任务不是物理精度验证任务，而是计算资源评估任务。

目标是回到真实 3D 光栅路径：

```text
stage_case = stage4_block_grating
```

在真实 `100 nm × 100 nm × 150 nm` 计算模型上，使用：

```text
nedelec_degree = 2
MPI ranks = 8
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
stage4_dtn_order_policy = auto_propagating
use_pml = false
```

扫描多个网格尺寸，估算后续为了做真实 3D 光栅收敛计算需要多大内存的工作站。

本任务重点回答：

```text
1. 不同 h 下 cells / DoF / nnz / matrix memory 是多少？
2. 默认 MUMPS 直接法的 LU fill-in 峰值内存是多少？
3. 默认 direct 在本机能跑到哪个 h，在哪个 h 被 kill 或失败？
4. MUMPS OOC 能否让更细网格跑完？需要多少 SSD？慢多少倍？
5. 如果未来写迭代法，理论内存大概是多少？
6. 为了跑 h=5 / h=3 / h=2.5 / h=2 / h=1.5，大概需要多大 RAM 和 SSD？
```

---

## 2. 物理与几何设置

使用真实 3D 周期矩形柱/光栅模型：

```text
stage_case = stage4_block_grating
period_x = 100 nm
period_y = 100 nm
air_height = 100 nm
substrate_thickness = 50 nm
total_z = 150 nm
grating_width_x = 50 nm
grating_width_y = 50 nm
grating_height = 50 nm
lambda0 = 13.5 nm
normal incidence
polarization = s
```

材料沿用当前 Stage 4 默认真实材料设置。若需要显式设置，请记录：

```text
n_air
n_substrate
n_grating
```

注意：本任务只做资源估算，不把 R/T/A 当作物理收敛结论。

---

## 3. 数值设置

主线设置：

```text
nedelec_degree = 2
mesh_cell_type = auto / hexa
mesh_spacing_mode = auto
stage4_boundary_model = dtn_port
stage4_dtn_order_policy = auto_propagating
stage4_dtn_assembly = auxiliary
use_pml = false
MPI ranks = 8
```

`auto_propagating` 是主线，因为真实 `100 nm` 周期下确实可能存在多个传播衍射级。

可选对照：如果资源允许，可额外跑少数 `zero_order` case，用来区分：

```text
FEM 体矩阵成本
DtN 多模态端口成本
```

但主结论必须基于 `auto_propagating`。

---

## 4. 已有工具与允许的最小改动

当前已有工具：

```text
src/studies/run_3d_matrix_scale.py
```

它已经支持：

```text
--mesh-sizes
--mpi-procs-list
--solver-profiles default mumps_ooc
--stage-case stage4_block_grating
--nedelec-degree 2
--stage4-dtn-order-policy auto_propagating
--assemble-only
--matrix-diagnostics-assemble-unconstrained
```

当前它已经能抽取：

```text
dof_raw_nedelec
floquet_constraints
constrained_system_size
dtn_auxiliary_dofs
matrix_rows / matrix_cols
nnz_used / nnz_allocated
average_nnz_per_row
petsc_matrix_memory_mb
estimated_aij_matrix_memory_mb
solve_time_seconds
elapsed_wall_seconds
peak_rss_mb
swap_used_before/after/delta
mumps_ooc_removed/residual file bytes
actual_pc_factor_solver_type
dtn_augmented_to_base_nnz_ratio
constrained_to_unconstrained_nnz_ratio
```

本任务原则上不需要大改源码。

允许的最小补充：

```text
1. 如果现有 CSV 字段不足，可对 run_3d_matrix_scale.py 做小补充。
2. 推荐补充每个 rank 的 RSS 聚合统计：
   rss_rank_max_mb
   rss_rank_sum_mb
   rss_rank_mean_mb
   rss_rank_min_mb
   rss_rank_imbalance = max / mean
3. 成功 OOC case 必须把删除前的 OOC 文件大小换算为 GB 写入 CSV。
4. 失败或被 kill 的 case 必须尽量保留 stdout/stderr/progress_3d.jsonl 的最后状态。
5. 可增加轻量脚本生成 iterative_memory_estimates.csv 和 extrapolated_workstation_requirements.csv。
```

不要为了本任务重构求解器，不要实现正式迭代求解器。

---

## 5. Phase A：assemble-only 矩阵规模扫描

### 5.1 目的

只组装矩阵，不做 LU 分解。

目的：

```text
判断矩阵本体有多大；
统计 DoF、nnz、AIJ matrix memory；
判断还没 LU 之前内存是否已经不可承受；
为直接法和迭代法估算提供基础数据。
```

### 5.2 建议网格

建议扫描：

```text
h = 20, 15, 12, 10, 8, 6, 5, 4, 3, 2.5, 2 nm
```

如果本机还能承受 assemble-only，可以补充：

```text
h = 1.5 nm
```

如果某个 h assemble-only 已被 kill，则停止更细网格，并记录失败边界。

### 5.3 命令示例

可使用类似命令：

```bash
mpiexec -n 8 python3 -m src.studies.run_3d_matrix_scale \
  --stage-case stage4_block_grating \
  --case normal \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --stage4-boundary-model dtn_port \
  --stage4-dtn-order-policy auto_propagating \
  --solver-profiles default \
  --mpi-procs-list 8 \
  --mesh-sizes 20 15 12 10 8 6 5 4 3 2.5 2 \
  --assemble-only \
  --output-csv docs/task005_stage4_real_grating_memory_estimation/outcomes/assemble_matrix_scale.csv
```

如果 `mpiexec` 外层和 `run_3d_matrix_scale.py --mpi-procs-list` 冲突，请按当前脚本实际机制选择一种方式；最终必须保证每个 case 是 `MPI ranks = 8`。

### 5.4 必须记录字段

`assemble_matrix_scale.csv` 至少包含：

```text
h_nm
p
mpi_ranks
mesh_cells_resolved
cells
N1curl_raw_dofs
floquet_constraints
dtn_auxiliary_dofs
system_rows
system_cols
nnz_used
nnz_allocated
avg_nnz_per_row
estimated_AIJ_matrix_memory_GB
PETSc_matrix_memory_GB
peak_RSS_per_rank_max_GB
rss_rank_sum_GB            # 若能补充
estimated_total_RSS_upper_GB = peak_RSS_per_rank_max_GB * mpi_ranks
assemble_elapsed_s
status
failure_stage
last_progress_stage
```

---

## 6. Phase B：default MUMPS 直接法，跑到本机带不动

### 6.1 目的

使用普通 MUMPS direct LU：

```text
petsc_direct_solver_profile = default
```

目的：

```text
测真实 LU fill-in 峰值内存；
找到本机能跑到哪个 h；
记录程序在哪个 h 被 kill、OOM 或 PETSc/MUMPS 报错；
估算纯内存 direct solve 对工作站 RAM 的需求。
```

### 6.2 建议网格

从粗到细逐步运行：

```text
h = 20, 15, 12, 10, 8, 6, 5, 4, 3, 2.5, 2 nm
```

注意：不要要求所有网格都必须成功。目标就是找到失败边界。

建议每个 h 单独启动子进程，确保被 kill 后前面的结果仍保留。`run_3d_matrix_scale.py` 已经是 subprocess 逐 case 运行，适合这种用途。

### 6.3 记录字段

`direct_default_scale.csv` 至少包含：

```text
h_nm
p
mpi_ranks
returncode
case_status
status = completed / failed / killed / timeout
failure_stage
last_progress_stage
petsc_error_code
petsc_error_type
mumps_infog_1
mumps_infog_2
system_rows
nnz_used
matrix_memory_GB
estimated_AIJ_matrix_memory_GB
peak_RSS_per_rank_max_GB
rss_rank_sum_GB            # 若能补充
estimated_total_RSS_upper_GB = peak_RSS_per_rank_max_GB * mpi_ranks
swap_before_GB
swap_after_GB
swap_delta_GB
solve_time_s
elapsed_wall_s
stderr_tail
stdout_tail
result_dir
```

关键计算：

```text
effective_LU_memory_proxy_GB = estimated_total_RSS_upper_GB - estimated_AIJ_matrix_memory_GB
rss_to_matrix_ratio = estimated_total_RSS_upper_GB / estimated_AIJ_matrix_memory_GB
```

注意：这不是严格 MUMPS 内部 fill-in ratio，而是对实际工作站峰值内存的工程估算。

---

## 7. Phase C：MUMPS OOC 对照

### 7.1 目的

使用 MUMPS out-of-core：

```text
petsc_direct_solver_profile = mumps_ooc
```

目的：

```text
判断 OOC 能否让更细网格跑完；
统计 OOC 需要多少 SSD；
比较 OOC 与 default 的 RAM 峰值差异；
统计 OOC 速度慢多少倍。
```

### 7.2 建议网格

建议至少测试：

```text
h = 15, 12, 10, 8, 6, 5, 4, 3, 2.5
```

如果 default 在某个 h 被 kill，而 OOC 能完成，该点特别重要。

### 7.3 记录字段

`mumps_ooc_scale.csv` 至少包含：

```text
h_nm
p
mpi_ranks
status
case_status
failure_stage
last_progress_stage
system_rows
nnz_used
matrix_memory_GB
peak_RSS_per_rank_max_GB
rss_rank_sum_GB              # 若能补充
estimated_total_RSS_upper_GB
swap_delta_GB
solve_time_s
elapsed_wall_s
mumps_ooc_tmpdir
mumps_ooc_cleanup_removed_file_count
mumps_ooc_cleanup_removed_file_GB
mumps_ooc_residual_file_count
mumps_ooc_residual_file_GB
ooc_disk_GB = max(removed_file_GB, residual_file_GB)
result_dir
```

成功运行后 OOC 文件可能被删除，但必须把删除前大小写入表中。

### 7.4 default vs OOC 对照表

生成：

```text
direct_vs_ooc_comparison.csv
```

字段：

```text
h_nm
default_status
ooc_status
default_peak_RSS_per_rank_GB
ooc_peak_RSS_per_rank_GB
default_total_RSS_upper_GB
ooc_total_RSS_upper_GB
ooc_disk_GB
default_elapsed_s
ooc_elapsed_s
slowdown_ratio = ooc_elapsed_s / default_elapsed_s
ram_saving_ratio = 1 - ooc_total_RSS_upper_GB / default_total_RSS_upper_GB
note
```

如果 default 失败而 OOC 成功，则 `slowdown_ratio` 可以留空，但要写明：

```text
OOC extended solvable mesh beyond default direct.
```

---

## 8. Phase D：迭代法内存估算

当前代码没有正式迭代法主线，本阶段只做理论/工程估算，不要求实现迭代求解器。

### 8.1 估算基础

基于 assemble-only 得到的：

```text
system_rows
nnz_used
estimated_AIJ_matrix_memory_GB
```

估算复数向量内存：

```text
one_complex_vector_GB = system_rows * 16 / 1024^3
```

### 8.2 估算方案

生成：

```text
iterative_memory_estimates.csv
```

每个 h 至少估算：

```text
Jacobi / diagonal PC:
  A + 10 vectors

BiCGStab + simple PC:
  A + 10 vectors + PC_small

GMRES(30) no heavy PC:
  A + 35 vectors

GMRES(50) no heavy PC:
  A + 55 vectors

GMRES(50) + ILU(0) local estimate:
  A + 55 vectors + 1~3 × A

ASM + ILU estimate:
  A + 55 vectors + 2~8 × A
```

### 8.3 字段要求

```text
h_nm
system_rows
nnz_used
matrix_memory_GB
one_vector_GB
bicgstab_10vec_total_GB
gmres30_total_GB
gmres50_total_GB
gmres50_ilu0_low_GB
gmres50_ilu0_high_GB
asm_ilu_low_GB
asm_ilu_high_GB
direct_default_total_RSS_upper_GB
direct_ooc_total_RSS_upper_GB
memory_saving_vs_direct_low
memory_saving_vs_direct_high
convergence_risk_note
```

必须说明：

```text
迭代法内存估算只代表 memory_possible_if_converges；
不代表 Maxwell 问题一定收敛。
```

尤其对频域复数 Maxwell，不应承诺 Jacobi/BiCGStab/GMRES 一定能收敛。

---

## 9. Phase E：失败边界记录

本任务明确要求跑到本机带不动为止，但要安全记录失败边界。

生成：

```text
failure_boundary.md
```

至少回答：

```text
assemble-only:
  last completed h = ?
  first failed/killed h = ?
  failure stage = ?

default MUMPS:
  last completed h = ?
  first failed/killed h = ?
  failure stage = ?
  last progress = ?
  was swap used = ?

MUMPS OOC:
  last completed h = ?
  first failed/killed h = ?
  failure stage = ?
  OOC disk at failure = ?
```

如果程序被 OS kill，通常可能没有完整 `run_summary.json`。必须尽量从以下文件恢复信息：

```text
stdout_file
stderr_file
progress_3d.jsonl
solver_log.txt
```

在 `failure_boundary.md` 中保留最后 20 行 stderr/stdout 摘要。

---

## 10. Phase F：外推工作站需求

基于实测数据做外推。

目标网格：

```text
h = 8, 6, 5, 4, 3, 2.5, 2, 1.5, 1.0 nm
```

生成：

```text
extrapolated_workstation_requirements.csv
```

字段：

```text
target_h_nm
source = measured / interpolated / extrapolated
estimated_cells
estimated_dofs
estimated_nnz
estimated_matrix_memory_GB
estimated_direct_LU_peak_total_GB
estimated_OOC_peak_total_GB
estimated_OOC_disk_GB
estimated_iterative_gmres50_GB
estimated_iterative_asm_ilu_low_GB
estimated_iterative_asm_ilu_high_GB
recommended_RAM_GB
recommended_SSD_GB
confidence = high / medium / low
note
```

推荐 RAM 档位至少包含：

```text
64 GB
128 GB
256 GB
512 GB
1 TB
```

必须明确：

```text
direct LU 推荐值基于实测 RSS / 外推；
OOC 推荐值基于 MUMPS OOC 文件大小 / 外推；
迭代法推荐值仅为内存估算，不代表收敛保证。
```

---

## 11. 输出文件要求

本任务 outcomes 至少包含：

```text
docs/task005_stage4_real_grating_memory_estimation/outcomes/
├── summary.md
├── assemble_matrix_scale.csv
├── direct_default_scale.csv
├── mumps_ooc_scale.csv
├── direct_vs_ooc_comparison.csv
├── iterative_memory_estimates.csv
├── extrapolated_workstation_requirements.csv
├── failure_boundary.md
├── parameters.json
├── run_log.txt
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 中只归档轻量文件：

```text
run_summary.json
solver_log.txt
progress_3d.jsonl
stdout_tail.txt
stderr_tail.txt
matrix_scale_row.json
```

不要提交大型文件：

```text
results/*/*.vtu
results/*/*.bp
results/*/mesh_3d.h5
完整 results/ 目录
大体积 mumps_ooc_files/
```

完整 `results/` 和 OOC 临时文件仍应保留在本地磁盘，不提交 Git。

---

## 12. summary.md 必须回答的问题

`summary.md` 必须用中文简明回答：

1. p=2 真实 `100×100×150 nm` grating 在 MPI=8 下，不同 h 的 DoF / nnz / matrix memory 是多少？
2. 矩阵本体是否已经成为内存瓶颈？还是 LU fill-in 才是主要瓶颈？
3. 默认 MUMPS direct solve 能跑到哪个 h？
4. 第一个被 kill 或失败的 h 是多少？失败发生在 assembly、matrix finalize、LU factorization 还是 postprocess？
5. default direct 的峰值 RSS 是矩阵本体的多少倍？
6. MUMPS OOC 能否让更细网格跑完？
7. OOC 需要多少 SSD？速度慢多少倍？
8. 如果未来写迭代法，理论内存大概是多少？
9. 迭代法相比直接法可能节省多少内存？
10. 为了跑 h=5 / h=3 / h=2.5 / h=2 / h=1.5，大概需要多大 RAM 和 SSD？
11. 推荐购买 128 GB、256 GB、512 GB 还是 1 TB 工作站？

---

## 13. 表格模板

### 表 1：assemble-only matrix scale

| h_nm | cells | dofs | constraints | aux_dofs | rows | nnz | avg_nnz_row | matrix_GB | RSS_rank_max_GB | RSS_sum_GB | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 2：default direct MUMPS

| h_nm | rows | nnz | matrix_GB | RSS_rank_max_GB | RSS_total_upper_GB | solve_s | elapsed_s | swap_delta_GB | status | failure_stage |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|

### 表 3：MUMPS OOC

| h_nm | rows | nnz | matrix_GB | RSS_rank_max_GB | RSS_total_upper_GB | OOC_disk_GB | elapsed_s | status | failure_stage |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|

### 表 4：direct vs OOC

| h_nm | default_status | ooc_status | default_RSS_total_GB | ooc_RSS_total_GB | OOC_disk_GB | default_s | ooc_s | slowdown | note |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|

### 表 5：迭代法内存估算

| h_nm | rows | matrix_GB | one_vec_GB | GMRES30_GB | GMRES50_GB | ASM_ILU_low_GB | ASM_ILU_high_GB | direct_RSS_total_GB | note |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 6：工作站建议

| target_h_nm | direct_RAM_GB | OOC_RAM_GB | OOC_SSD_GB | iterative_RAM_GB | recommended_RAM_GB | recommended_SSD_GB | confidence | note |
|---:|---:|---:|---:|---:|---:|---:|---|---|

---

## 14. 验收标准

本任务完成标准：

1. 至少完成 assemble-only 的多网格扫描。
2. 至少完成 default MUMPS 的粗到细运行，并记录本机失败边界。
3. 至少完成若干 MUMPS OOC 对照点，并统计 OOC 硬盘占用与速度变化。
4. 给出迭代法内存估算表。
5. 给出 h=5 / h=3 / h=2.5 / h=2 / h=1.5 的工作站资源建议。
6. 明确区分：矩阵本体内存、LU fill-in 峰值内存、OOC 磁盘、系统 swap、迭代法估算内存。
7. 不把本任务结果写成物理 R/T benchmark。
8. 不提交大型 results、VTU/BP/H5 或 OOC 临时文件。

---

## 15. 重要注意事项

- 本任务可以把程序跑到被 kill，但必须尽量保留前面已完成 case 的结果。
- 如果本机资源不足，不要硬跑导致系统不可用；可以用 timeout 或从粗到细逐步停止。
- 如果 default direct 超内存但还能继续，必须记录 swap 使用，说明这是系统 swap，不是 MUMPS OOC。
- OOC 与系统 swap 必须分开统计。
- MPI 下 `max_rss_mb` 是最大单 rank RSS，不是总内存；推荐补充 `rss_sum_mb`。
- 若无法补充 per-rank RSS，则使用 `max_rss_mb × ranks` 作为保守总内存上界。
- 迭代法内存估算不代表迭代法一定收敛。
- 最终重点不是“算出了哪个 R/T”，而是“为了未来真实收敛计算，需要买多大内存和 SSD”。

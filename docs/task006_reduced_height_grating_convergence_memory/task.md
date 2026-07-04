# CODEX TASK 20260704：70 nm 缩短计算域真实 3D 光栅 p=1/p=2 收敛、资源与 R/T 分析

## 0. 分支与执行流程

本任务书写在当前 task005 分支中，供下一轮本地执行。**不要由 ChatGPT 代为创建远程分支。**

当前已完成分支：

```text
codex/20260703-stage4-real-grating-memory-estimation
```

开始 task006 前，建议先在本地合并 task005：

```bash
git checkout master
git pull
git merge codex/20260703-stage4-real-grating-memory-estimation
git push origin master
```

然后由本地 Codex/开发者从更新后的 `master` 新建 task006 分支，例如：

```bash
git checkout -b codex/20260704-reduced-height-grating-convergence-memory
git push -u origin codex/20260704-reduced-height-grating-convergence-memory
```

推荐本任务分支名：

```text
codex/20260704-reduced-height-grating-convergence-memory
```

开始前必须阅读：

```text
docs/task005_stage4_real_grating_memory_estimation/review_report.md
docs/task005_stage4_real_grating_memory_estimation/outcomes/summary.md
docs/task005_stage4_real_grating_memory_estimation/outcomes/extrapolated_workstation_requirements.csv
notes/reference/current_version_boundaries.md
README.md
notes/quick_start/stage4_3d_block_grating_usage_guide.md
```

本任务的任务书、outcomes 和后续 review report 都应保存在：

```text
docs/task006_reduced_height_grating_convergence_memory/
├── task.md
├── outcomes/
└── review_report.md
```

所有轻量结果写入：

```text
docs/task006_reduced_height_grating_convergence_memory/outcomes/
```

不要改写 task000-task005 的 outcomes 或 review report。

---

## 1. 任务目的

本任务的目标是测试：

```text
将真实 3D 光栅的 z 向计算域从 150 nm 缩短到 70 nm 后，
是否可以在不显著影响 R/T/A 结果的前提下显著降低内存，
并使 p=2、h=1 nm 的真实 3D 计算更接近可行。
```

本任务同时关注两类指标：

```text
1. 数值结果：R_total, T_total, A_volume, R+T+A_volume, 各衍射级 R_m/T_m；
2. 计算资源：cells, DoF, nnz, A 矩阵内存, RSS, OOC disk, elapsed time, failure boundary。
```

与 task005 相比，本任务新增：

```text
- 计算域高度从 150 nm 缩短为 70 nm；
- 同时扫描 p=1 和 p=2；
- 重点尝试 p=2, h=1 nm；
- 增加 MPI=1 与 MPI=8 的对照；
- summary 中必须展示每个完成 case 的 R/T/A，用来初步判断是否收敛；
- 增加一个专用 memory profiling 脚本，用于阶段性理解内存组成，但不作为以后常规运行路径。
```

注意：本任务仍然不是最终物理 benchmark。R/T/A 收敛判断是初步工程判断，用来指导后续网格和计算域选择。

---

## 2. 几何设置：70 nm reduced-height domain

原 task005 使用：

```text
period_x = 100 nm
period_y = 100 nm
air_height = 100 nm
substrate_thickness = 50 nm
total_z = 150 nm
grating_height = 50 nm
```

本任务改为：

```text
period_x = 100 nm
period_y = 100 nm
substrate_thickness = 10 nm
grating_height = 50 nm
top_air_thickness_above_grating = 10 nm
total_z = 70 nm
```

非常重要：请先确认代码中 `air_height` 的语义。

若当前 `stage4_block_grating` 中：

```text
air_height = substrate top 到 top boundary 的总高度
```

则本任务应设置：

```text
air_height = grating_height + top_air_thickness_above_grating = 50 + 10 = 60 nm
substrate_thickness = 10 nm
total_z = air_height + substrate_thickness = 70 nm
```

不要误设为：

```text
air_height = 10 nm
```

除非你已经确认代码的 `air_height` 表示的是 grating top 上方空气厚度。

本任务默认真实几何：

```text
stage_case = stage4_block_grating
period_x = 100 nm
period_y = 100 nm
grading/grating_width_x = 50 nm
grading/grating_width_y = 50 nm
grating_height = 50 nm
substrate_thickness = 10 nm
top_air_above_grating = 10 nm
air_height = 60 nm  # 若代码 air_height 表示 substrate top 到 top boundary
lambda0 = 13.5 nm
normal incidence
polarization = s
```

材料沿用 Stage 4 当前默认真实材料：

```text
n_air = 1
n_substrate = 0.999002304859 + 0.00182649365j
n_grating = 0.999002304859 + 0.00182649365j
```

---

## 3. 数值设置

主线设置：

```text
stage_case = stage4_block_grating
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
stage4_dtn_order_policy = auto_propagating
use_pml = false
mesh_cell_type = hexa / auto
mesh_spacing_mode = auto
visualization_degree = 1
```

需要同时测试：

```text
nedelec_degree = 1
nedelec_degree = 2
```

主线 MPI：

```text
MPI ranks = 8
```

对照 MPI：

```text
MPI ranks = 1
```

MPI=1 不要求跑所有网格，主要用于理解内存分布和并行开销：

```text
p=1: 选 h=5, 3, 2 nm 中可运行点
p=2: 选 h=5, 3, 2 或 h=1.5 nm 中可运行点
```

如果 MPI=1 在某些网格明显不可承受，可停止并记录 failure boundary。

---

## 4. 扫描计划

### 4.1 p=1 扫描

建议 h：

```text
h = 5, 4, 3, 2.5, 2, 1.5, 1 nm
```

p=1 目标：

```text
1. 给出低阶单元的 R/T/A 收敛趋势；
2. 作为 p=2 的对照；
3. 判断 reduced-height domain 下 h=1 nm 是否可作为直接法可跑的参考。
```

### 4.2 p=2 扫描

建议 h：

```text
h = 5, 4, 3, 2.5, 2, 1.5, 1 nm
```

p=2 目标：

```text
1. 主目标是尝试 h=1 nm；
2. 至少完成 assemble-only 到 h=1 nm；
3. direct solve 从粗到细逐步尝试；
4. 如果 default direct 失败，则对关键边界点尝试 mumps_ooc；
5. 记录 h=1 nm 是否可 assemble、是否可 direct solve、是否需要 OOC、失败在哪个阶段。
```

### 4.3 150 nm vs 70 nm 对照

为了验证缩短 z 向计算域是否影响结果，建议做少量 150 nm 原域对照，不需要重跑所有网格。

对照组合：

```text
150 nm original domain:
  p=1, h=5 nm, MPI=8
  p=2, h=5 nm, MPI=8

70 nm reduced domain:
  p=1, h=5 nm, MPI=8
  p=2, h=5 nm, MPI=8
```

若 task005 已经有 `150 nm, p=2, h=5, MPI=8` 的结果，可以直接引用，不必重复运行。p=1 若没有旧结果，可补跑或标记 unavailable。

对照指标：

```text
ΔR = R_70nm - R_150nm
ΔT = T_70nm - T_150nm
ΔA = A_70nm - A_150nm
relative difference if meaningful
```

如果 70 nm 和 150 nm 的 R/T/A 差异明显，必须在 summary 中说明：

```text
缩短空气/基座厚度可能影响 DtN port 与近场耦合，不能直接作为等价计算域。
```

---

## 5. 计算阶段设计

整体框架沿用 task005。

### Phase A：assemble-only scale

对 p=1 和 p=2 都跑 assemble-only：

```text
p=1, h = 5, 4, 3, 2.5, 2, 1.5, 1 nm, MPI=8
p=2, h = 5, 4, 3, 2.5, 2, 1.5, 1 nm, MPI=8
```

输出：

```text
assemble_matrix_scale.csv
```

字段至少包括：

```text
domain_height_nm
substrate_thickness_nm
top_air_above_grating_nm
air_height_parameter_nm
p
h_nm
mpi_ranks
mesh_cells_resolved
cells
N1curl_raw_dofs
floquet_constraints
dtn_auxiliary_dofs
system_rows
system_cols
nnz_used
avg_nnz_per_row
estimated_AIJ_matrix_memory_GB
peak_RSS_per_rank_max_GB
estimated_total_RSS_upper_GB
assemble_elapsed_s
status
failure_stage
```

### Phase B：default MUMPS direct solve

从粗到细运行，直到失败边界。

建议：

```text
p=1, MPI=8: h = 5, 4, 3, 2.5, 2, 1.5, 1 nm
p=2, MPI=8: h = 5, 4, 3, 2.5, 2, 1.5, 1 nm
```

但不要要求所有点必须完成。目标是记录边界。

输出：

```text
direct_default_scale.csv
```

字段至少包括：

```text
p
h_nm
mpi_ranks
status
returncode
failure_stage
last_progress_stage
system_rows
nnz_used
matrix_memory_GB
peak_RSS_per_rank_max_GB
estimated_total_RSS_upper_GB
swap_delta_GB
solve_time_s
elapsed_wall_s
R_total
T_total
A_volume_total
R_plus_T
R_plus_T_plus_A_volume
energy_closure_error_port_volume
num_reflection_orders
num_transmission_orders
result_dir
```

### Phase C：MUMPS OOC on boundary cases

不要求 OOC 跑所有网格，只跑 default direct 的关键失败边界和一两个完成点。

建议：

```text
p=1: 第一个 default direct 失败点，以及失败点前一个完成点
p=2: 第一个 default direct 失败点，以及失败点前一个完成点；若 h=1 nm default 未完成，可尝试 h=1 nm OOC
```

输出：

```text
mumps_ooc_scale.csv
direct_vs_ooc_comparison.csv
```

字段沿用 task005，并新增 R/T/A 字段。

### Phase D：MPI=1 对照

目的不是完整收敛，而是理解 MPI 对内存和时间的影响。

建议选择：

```text
p=1: h = 5, 3, 2 或可运行的代表点
p=2: h = 5, 3, 2 或可运行的代表点
```

如果 p=2 h=2 MPI=1 不可承受，停止并记录。

输出：

```text
mpi1_vs_mpi8_comparison.csv
```

字段：

```text
p
h_nm
mpi1_status
mpi8_status
mpi1_matrix_GB
mpi8_matrix_GB
mpi1_peak_RSS_GB
mpi8_peak_RSS_per_rank_GB
mpi8_RSS_upper_GB
mpi1_elapsed_s
mpi8_elapsed_s
mpi_speedup
R_total_mpi1
R_total_mpi8
T_total_mpi1
T_total_mpi8
A_volume_mpi1
A_volume_mpi8
note
```

### Phase E：R/T/A convergence table

这是本任务新增重点。

生成：

```text
rta_convergence.csv
```

字段：

```text
domain_height_nm
p
h_nm
mpi_ranks
solver_profile
status
R_total
T_total
A_volume_total
R_plus_T
R_plus_T_plus_A_volume
energy_closure_error_port_volume
R_change_vs_previous_h
T_change_vs_previous_h
A_change_vs_previous_h
R_change_vs_finest_available
T_change_vs_finest_available
A_change_vs_finest_available
matrix_memory_GB
RSS_upper_GB
elapsed_s
note
```

同时输出衍射级表：

```text
diffraction_orders_summary.csv
```

字段：

```text
p
h_nm
mpi_ranks
solver_profile
side = reflection/transmission
order_m
order_n
power
amplitude_real
amplitude_imag
is_propagating
```

如果当前 port_power.json 结构不同，请按现有结构提取尽可能多的信息。

summary.md 中必须有 R/T/A 表，至少分 p=1 和 p=2 两张表：

```text
p=1 R/T/A convergence
p=2 R/T/A convergence
```

并给出初步判断：

```text
R/T/A 是否随 h 收敛？
p=2 是否比 p=1 更快？
70 nm 与 150 nm 对照是否接近？
h=1 nm p=2 是否完成？若完成，R/T/A 与 h=1.5/2 nm 差异如何？
```

---

## 6. 专用 memory profiling 脚本

本任务还需要新增一个**阶段性诊断专用** Python 文件，用于现阶段理解内存组成。

要求：

```text
该脚本只用于当前资源需求理解；
后续实际批量跑程序时可以不用；
不要侵入主求解器逻辑；
不要把它变成正式运行路径的必需依赖。
```

建议文件名：

```text
src/studies/run_3d_memory_profile.py
```

功能建议：

```text
1. 包装一个 3D run command；
2. 每隔 1~5 秒读取子进程树 RSS；
3. 尝试读取 progress_3d.jsonl 的最后 stage；
4. 记录 OOC 文件夹当前大小；
5. 输出 memory_monitor_timeseries.csv；
6. 若进程被 kill，也保留 kill 前内存轨迹。
```

最低可接受字段：

```text
timestamp_s
elapsed_s
stage
status
num_processes
rss_sum_GB
rss_max_GB
rss_mean_GB
rss_min_GB
swap_used_GB
ooc_disk_GB
stdout_tail
stderr_tail
```

如果实现逐 rank 识别困难，可以先记录所有子进程总 RSS 和最大 RSS。

推荐只对少数代表 case 运行：

```text
p=2, h=5 nm, MPI=8, 70 nm domain, default direct completed case
p=2, h=1 or h=1.5 nm, MPI=8, 70 nm domain, assemble-only or failed boundary case
```

输出：

```text
memory_profile_timeseries.csv
memory_profile_summary.csv
```

注意：该脚本是 diagnostic only，不作为 task006 通过的硬性前置。如果时间不够，可实现脚本并跑一个代表 case。

---

## 7. 输出文件要求

本任务 outcomes 至少包含：

```text
docs/task006_reduced_height_grating_convergence_memory/outcomes/
├── summary.md
├── assemble_matrix_scale.csv
├── direct_default_scale.csv
├── mumps_ooc_scale.csv
├── direct_vs_ooc_comparison.csv
├── mpi1_vs_mpi8_comparison.csv
├── rta_convergence.csv
├── diffraction_orders_summary.csv
├── reduced_vs_original_domain_comparison.csv
├── memory_profile_summary.csv
├── memory_profile_timeseries.csv
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
power_summary.csv
port_power.json
volume_absorption.json
matrix_scale_row.json
```

不要提交大型文件：

```text
results/*/*.vtu
results/*/*.bp
results/*/mesh_3d.h5
完整 results/ 目录
mumps_ooc_files/
大体积 memory monitor raw dump
```

---

## 8. summary.md 必须回答的问题

`summary.md` 必须用中文回答：

1. 70 nm reduced-height domain 的几何参数到底如何传入代码？`air_height` 是否为 60 nm？
2. p=1 和 p=2 在不同 h 下的 DoF / nnz / matrix memory / RSS 是多少？
3. p=1 direct 能跑到哪个 h？p=2 direct 能跑到哪个 h？
4. p=2, h=1 nm 是否完成 assemble-only？是否完成 direct solve？是否需要 OOC？
5. 与 task005 的 150 nm domain 相比，70 nm domain 的矩阵和 RSS 降低了多少？
6. 70 nm 与 150 nm 的 R/T/A 是否接近？差异多大？
7. p=1 R/T/A 是否随 h 收敛？
8. p=2 R/T/A 是否随 h 收敛？p=2 是否明显优于 p=1？
9. MPI=1 与 MPI=8 对内存和时间有什么影响？
10. reduced-height domain 下，推荐后续主力网格是哪个 h/p 组合？
11. 如果目标是 p=2, h=1 nm，需要多少 RAM/SSD，当前机器是否可行？
12. memory profiling 脚本发现主要内存增长阶段在哪里？如果没有完整运行，也要说明原因。

---

## 9. 表格模板

### 表 1：资源规模

| p | h/nm | MPI | cells | rows | nnz | A matrix GB | RSS upper GB | elapsed s | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 2：R/T/A 收敛

| p | h/nm | MPI | R | T | A_volume | R+T+A | closure | ΔR prev | ΔT prev | ΔA prev | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 3：70 nm vs 150 nm 对照

| p | h/nm | R_70 | R_150 | ΔR | T_70 | T_150 | ΔT | A_70 | A_150 | ΔA |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|

### 表 4：MPI=1 vs MPI=8

| p | h/nm | RSS MPI1 GB | RSS MPI8 rank max GB | RSS MPI8 upper GB | time MPI1 s | time MPI8 s | R diff | T diff | note |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 5：h=1 nm feasibility

| p | h/nm | assemble status | direct status | OOC status | rows | nnz | A matrix GB | RSS/OOC estimate | conclusion |
|---:|---:|---|---|---|---:|---:|---:|---:|---|

---

## 10. 验收标准

本任务完成标准：

1. 正确设置 70 nm reduced-height domain，并在 parameters.json 中明确记录真实传入参数。
2. p=1 和 p=2 都完成多网格 assemble-only 扫描。
3. p=1 和 p=2 都完成 default direct 的粗到细运行，记录失败边界。
4. 对关键失败边界尝试 MUMPS OOC，记录 OOC disk 和状态。
5. 至少做若干 MPI=1 vs MPI=8 对照。
6. summary 中必须展示每个完成 case 的 R/T/A 值，并进行初步收敛判断。
7. 对 70 nm vs 150 nm 的结果差异做初步判断。
8. 尝试 p=2, h=1 nm；若无法 direct solve，至少完成 assemble-only 或记录失败阶段。
9. 新增一个 diagnostic-only memory profiling 脚本，并至少运行一个代表 case；若无法运行，说明原因。
10. 不提交大型 results、VTU/BP/H5 或 OOC 临时文件。

---

## 11. 注意事项

- 本任务重点是 reduced-height domain 是否降低资源需求，以及 R/T/A 是否仍可信。
- 不要把单个 h 的 R/T/A 当作最终物理 benchmark。
- 如果 70 nm 与 150 nm 差异明显，需要如实说明，不要强行认为缩短计算域无影响。
- `h=1 nm, p=2` 是目标尝试点，不是必须完成 direct solve 的验收前提。
- 若 direct/OOC 在 h=1 失败，必须记录失败阶段和资源边界。
- 若 memory profiling 脚本增加了依赖，优先使用标准库和 `/proc`；不要引入重依赖。
- 后续实际工程运行仍可只关注 A matrix memory、RSS、OOC disk、R/T/A，不必每次都运行详细 memory profiling。

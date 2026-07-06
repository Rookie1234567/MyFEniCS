# CODEX TASK 20260706：目标尺寸 50×25×140 nm、80° 斜入射 official DtN-port R/T/A 本机收敛 benchmark、内存边界与资源报告

## 0. 分支与执行流程

本任务书写在当前 task007 分支中，供下一轮本地执行。**不要由 ChatGPT 代为创建远程分支。**

当前已完成分支：

```text
codex/20260704-dtn-port-modal-official-rta
```

开始 task008 前，建议先在本地合并 task007：

```bash
git checkout master
git pull
git merge codex/20260704-dtn-port-modal-official-rta
git push origin master
```

然后由本地 Codex/开发者从更新后的 `master` 新建 task008 分支，例如：

```bash
git checkout -b codex/20260706-target-50x25x140-oblique80-official-benchmark
git push -u origin codex/20260706-target-50x25x140-oblique80-official-benchmark
```

推荐本任务分支名：

```text
codex/20260706-target-50x25x140-oblique80-official-benchmark
```

说明：当前目录名仍为：

```text
docs/task008_70nm_official_convergence_benchmark/
```

这是因为 task008 目录已经提前建立。**以本任务书中的新几何和 80° 斜入射参数为准，不再使用原 70 nm reduced-height 100×100 周期案例作为 task008 主目标。**

开始前必须阅读：

```text
docs/task007_dtn_port_modal_official_rta/review_report.md
docs/task007_dtn_port_modal_official_rta/outcomes/summary.md
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_modal_investigation.md
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_power_formula.md
docs/task006_reduced_height_grating_convergence_memory/review_report.md
docs/task005_stage4_real_grating_memory_estimation/review_report.md
notes/reference/current_version_boundaries.md
README.md
```

本任务的任务书、outcomes 和后续 review report 都应保存在：

```text
docs/task008_70nm_official_convergence_benchmark/
├── task.md
├── outcomes/
└── review_report.md
```

所有轻量结果写入：

```text
docs/task008_70nm_official_convergence_benchmark/outcomes/
```

不要改写 task000-task007 的 outcomes 或 review report。

---

## 1. 背景

task005 完成了真实 100×100×150 nm 3D block grating 的资源估算；task006 完成了 100×100×70 nm reduced-height domain 的资源扫描，但当时 R/T 后处理仍主要使用 probe-plane E/H Fourier fitting，不能作为 official R/T/A；task007 已将 Stage 4 dtn_port 主线 official R/T/A 恢复为：

```text
power_source = dtn_port_modal_amplitudes
```

并将 E/H Fourier probe、E-only Fourier probe 和 sampled net flux 全部降级为 diagnostic。

现在目标几何和入射角都发生变化。待仿真的结构为：

```text
period_x = 50 nm
period_y = 25 nm
grating_width_x = 17 nm
grating_width_y = 25 nm
grating_height = 120 nm
substrate_thickness = 10 nm  # 初始假定
top_air_above_grating = 10 nm  # 初始假定
total_domain = 50 × 25 × 140 nm
```

入射光不再采用垂直入射，而是采用更接近真实情况的 x-z 平面内斜入射：

```text
incident_theta_from_z_deg = 80 deg
incident_azimuth_phi_deg = 0 deg
incident_plane = x-z plane
ky = 0
```

其中 `theta_from_z = 80°` 表示入射传播方向与 z 轴法向之间的夹角为 80°，即接近掠入射；`phi = 0°` 表示横向波矢只在 x 方向，不在 y 方向。

由于新几何与 task005/task006 的几何尺度不同，且 80° 斜入射会改变 Floquet 相位、端口模态数量、传播/衍射级选择和线性系统条件数，**不能再直接沿用旧案例对 h、内存和可完成边界的经验判断**。因此，本任务必须先像 task005 一样进行 matrix-scale / assemble-only 资源评估，再决定哪些 direct solve 点值得运行，并最终跑到本机可承受边界。

---

## 2. 任务目的

本任务目标是为新目标尺寸和 80° 斜入射建立本机可复用 benchmark 和资源边界：

```text
50 × 25 × 140 nm computational domain
17 × 25 × 120 nm grating
80° oblique incidence in x-z plane
official R/T/A = dtn_port_modal_amplitudes + A_volume
先做 p=1/p=2 多个 h 的 matrix-scale 资源评估
再跑 completed direct convergence benchmark
最后跑到本机 direct/OOC failure boundary
```

本任务不是迭代法任务。它的定位是：

```text
1. 新目标结构 + 80° 斜入射在本机上的 rows/nnz/matrix GB/RSS/elapsed 边界；
2. p=1 与 p=2 每个 h 的内存需求和可运行性判断；
3. official dtn_port_modal R/T/A 的本机可完成收敛趋势；
4. 本机 direct solve 的最细 completed case 和下一失败点；
5. 后续工作站/服务器或迭代法路线的资源依据；
6. 检查斜入射下 R 是否不再像垂直入射那样接近零。
```

---

## 3. 固定几何、入射与物理设置

### 3.1 主几何

固定为新目标尺寸真实 3D block grating：

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
```

注意代码中的 `air_height` 语义：

```text
air_height = interface z=0 到 top boundary 的高度
           = grating_height + top_air_above_grating
           = 120 + 10 = 130 nm
```

总高度为：

```text
total_height = substrate_thickness + air_height = 10 + 130 = 140 nm
```

### 3.2 80° 斜入射定义

主任务采用斜入射，不采用垂直入射作为主结果：

```text
incident_theta_from_z_deg = 80
incident_azimuth_phi_deg = 0
incident_plane = x-z plane
```

推荐波矢约定为从上方空气入射、向下传播：

```text
kx =  k0 * n_air * sin(theta)
ky =  0
kz = -k0 * n_air * cos(theta)
```

也就是：

```text
theta = 80 deg from +z axis normal magnitude convention
propagation direction = +x transverse direction and -z downward direction
```

如果当前代码使用不同角度命名，例如 `incident_angle_deg`、`angle_from_normal_deg`、`theta_deg`、`azimuth_deg` 等，Codex 必须在 `parameters.json` 和 `summary.md` 中明确实际传参和转换关系。

必须记录：

```text
kx
ky
kz
kx/k0
ky/k0
kz/k0
Floquet phase x = exp(i*kx*Lx)
Floquet phase y = exp(i*ky*Ly) = 1
```

### 3.3 偏振

主任务先采用 s polarization，即电场垂直于入射平面 x-z：

```text
polarization_kind = s
incident plane = x-z
E_inc direction ≈ y direction
```

如果当前代码对 `polarization_kind=s` 的定义已经与 x-z 入射平面一致，应直接使用；如果代码只支持显式 polarization vector，则应设置：

```text
E_inc = (0, 1, 0)
```

并检查：

```text
k · E_inc = 0
```

p polarization 不作为本任务必跑项，可作为后续任务。

### 3.4 关于 grating_width_y = period_y

本任务中：

```text
grating_width_y = period_y = 25 nm
```

这意味着光栅在 y 方向跨满整个周期单元。Codex 必须先检查当前 `stage4_block_grating` / mesh builder 是否支持 `grating_width_y == period_y`。

如果当前代码要求 `grating_width_y < period_y` 或会因为材料面贴到周期边界而出错，应：

```text
1. 优先修正 geometry builder，使 full-span y block grating 成为合法输入；
2. 明确记录该结构相当于 y 方向全周期填充的 3D periodic block / extruded ridge；
3. 保证 x/y Floquet MPC 仍然正确；
4. 不要偷偷把 grating_width_y 改成 24.999 nm，除非仅作为临时 fallback，并必须在 summary 中明确说明。
```

### 3.5 材料

```text
n_air = 1
n_substrate = 0.999002304859 + 0.00182649365j
n_grating = 0.999002304859 + 0.00182649365j
```

### 3.6 边界与后处理

```text
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
stage4_dtn_order_policy = auto_propagating
use_pml = false
use_floquet_xy = true
official_power_source = dtn_port_modal_amplitudes
A = A_volume_total from volume_integral_Im_epsilon_E2
```

主运行默认：

```text
MPI ranks = 8
solver = default MUMPS direct
```

暂不做迭代法。迭代法留到后续任务。

---

## 4. 执行顺序：必须先资源评估，再 direct solve

本任务必须按以下顺序执行。

### 4.1 Step A：geometry + oblique-incidence smoke

先运行一个最小 smoke：

```text
p = 1
h = 5 nm
incident_theta_from_z_deg = 80
incident_azimuth_phi_deg = 0
polarization_kind = s
MPI = 8
default MUMPS direct 或 assemble+solve smoke
```

用途：

```text
1. 检查 grating_width_y = period_y 是否被 geometry builder 正确支持；
2. 检查 80° 斜入射的 kx/ky/kz 是否正确；
3. 检查 Floquet phase x/y 是否正确；
4. 检查 s polarization 是否满足 k·E=0；
5. 检查 mesh material tags 是否正确；
6. 检查 dtn_port_modal official R/T/A 是否输出；
7. 检查 propagating diffraction orders / port modes 数量是否合理；
8. 检查 energy closure；
9. 检查结果文件字段。
```

如果该 smoke 失败，先修正几何、入射角或端口模态支持，不要直接进入大规模扫描。

### 4.2 Step B：matrix-scale / assemble-only 资源评估

由于几何和入射角已经变化，必须先对 p=1 和 p=2 的每个 h 做 matrix-scale / assemble-only 评估，类似 task005/task006 的资源表。

所有 assemble-only 评估都必须采用 task008 主设置：

```text
50 × 25 × 140 nm domain
17 × 25 × 120 nm grating
incident_theta_from_z_deg = 80
incident_azimuth_phi_deg = 0
polarization_kind = s
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
stage4_dtn_order_policy = auto_propagating
```

#### p=1 assemble-only 必评估

```text
p = 1
h = 5, 4, 3, 2.5, 2, 1.5, 1 nm
MPI = 8
matrix_diagnostics_assemble_only = true
```

若 `p=1 h=1` 已经失败或极慢，可停止在失败边界，并记录原因。

#### p=2 assemble-only 必评估

```text
p = 2
h = 5, 4, 3, 2.5, 2, 1.5, 1 nm
MPI = 8
matrix_diagnostics_assemble_only = true
```

如果 p=2 某个 h 在 assemble-only 阶段超时、内存不足或被 OS kill，停止更细 h 的 assemble-only 评估，并记录最后完成点和第一个失败点。

#### assemble-only 资源表字段

必须输出：

```text
assemble_matrix_scale.csv
```

字段至少包括：

```text
p
h_nm
incident_theta_from_z_deg
incident_azimuth_phi_deg
kx
ky
kz
status
failure_stage
returncode
mesh_cells_resolved
cells
N1curl_raw_dofs
floquet_constraints
dtn_auxiliary_dofs
dtn_top_mode_count
dtn_bottom_mode_count
dtn_propagating_mode_count
matrix_rows
nnz_used
avg_nnz_per_row
estimated_AIJ_matrix_memory_GB
max_rss_mb
RSS_upper_GB
swap_used_GB if available
elapsed_seconds
last_progress_stage
comment
```

### 4.3 Step C：根据 assemble-only 结果制定 direct solve 计划

完成 Step B 后，Codex 必须先生成：

```text
direct_solve_plan.md
```

其中需要根据 rows/nnz/matrix GB/RSS 估计：

```text
1. p=1 哪些 h 值值得跑 default direct；
2. p=2 哪些 h 值值得跑 default direct；
3. 哪些 h 只适合 assemble-only，不建议 direct；
4. 80° 斜入射下 DtN port mode count 是否明显增加；
5. 斜入射是否导致线性系统条件数或求解时间明显变差；
6. 如果要尝试 OOC，应该尝试哪些边界点；
7. 预计本机最细 completed direct 点在哪里。
```

经验系数可参考 task005/task006，但不能直接套用旧结论。必须基于本任务新几何和 80° 斜入射的 assemble-only 数据重新判断。

### 4.4 Step D：default direct solve 收敛 benchmark

根据 Step C 的计划，运行 default MUMPS direct，并尽量跑到本机可完成边界。

初始建议 direct 点如下，但以 Step B 资源评估结果为准：

```text
p=1: h = 5, 4, 3, 2.5, 2 nm
p=2: h = 5, 4, 3 nm
```

如果 Step B 显示资源非常轻，可继续尝试：

```text
p=1: h = 1.5 nm
p=2: h = 2.5 nm
```

如果 `p=2 h=2.5` 完成且本机资源仍可承受，可选尝试：

```text
p=2: h = 2 nm
```

但不要无计划地长时间硬跑极细网格。

### 4.5 Step E：跑到极限并记录 failure boundary

本任务必须记录本机极限，而不仅是 completed benchmark。

对 p=1 和 p=2，分别记录：

```text
last_completed_default_direct_h
first_failed_default_direct_h
failure_stage
returncode / PETSc error / signal 9 / timeout
last_progress_stage
matrix_rows
nnz_used
estimated_AIJ_matrix_memory_GB
recorded max_rss_mb / RSS_upper_GB
stdout_tail / stderr_tail summary
```

如果 default direct 在某个边界失败，可选择对该边界点尝试 tuned MUMPS OOC，但不是必须。若尝试 OOC，必须记录：

```text
petsc_direct_solver_profile = mumps_ooc
petsc_extra_options, especially mat_mumps_icntl_14 if used
OOC scratch size
status
failure_stage
```

---

## 5. 输出指标

每个 completed direct case 必须记录：

```text
p
h_nm
mpi_ranks
incident_theta_from_z_deg
incident_azimuth_phi_deg
polarization_kind
kx
ky
kz
status
case_status
solver_profile
period_x_nm
period_y_nm
grating_width_x_nm
grating_width_y_nm
grating_height_nm
substrate_thickness_nm
top_air_above_grating_nm
air_height_nm
total_height_nm
cells
mesh_cells_resolved
N1curl_raw_dofs
floquet_constraints
dtn_auxiliary_dofs
dtn_top_mode_count
dtn_bottom_mode_count
dtn_propagating_mode_count
matrix_rows
nnz_used
avg_nnz_per_row
estimated_AIJ_matrix_memory_GB
max_rss_mb
RSS_upper_GB = max_rss_mb * mpi_ranks / 1024
elapsed_seconds
solve_time_seconds if available
R_total
T_total
A_balance
R_total_dtn_port_modal
T_total_dtn_port_modal
A_volume_total
R_plus_T_dtn_port_modal
R_plus_T_plus_A_volume_dtn_port_modal
energy_closure_error_dtn_port_modal_volume
A_port_balance_minus_A_volume_total
power_source
reference_planes
```

Diagnostic 值也可以保留，但必须加 diagnostic 前缀：

```text
R_total_diagnostic_eh_fourier
T_total_diagnostic_eh_fourier
A_balance_diagnostic_eh_fourier
R_total_diagnostic_sampled_net_flux
T_total_diagnostic_sampled_net_flux
A_balance_diagnostic_sampled_net_flux
```

不要让 diagnostic 值覆盖 official `R_total/T_total`。

---

## 6. 收敛分析要求

本任务重点分析 80° 斜入射下 official R/T/A 收敛趋势。

### 6.1 p=1 收敛

对 p=1 的 completed direct h 点生成表格：

```text
R_total_dtn_port_modal
T_total_dtn_port_modal
A_volume_total
R+T+A_volume
closure
ΔR vs previous
ΔT vs previous
ΔA vs previous
ΔR vs finest completed p=1
ΔT vs finest completed p=1
ΔA vs finest completed p=1
```

### 6.2 p=2 收敛

对 p=2 的 completed direct h 点生成表格：

```text
R_total_dtn_port_modal
T_total_dtn_port_modal
A_volume_total
R+T+A_volume
closure
ΔR vs previous
ΔT vs previous
ΔA vs previous
ΔR vs finest completed p=2
ΔT vs finest completed p=2
ΔA vs finest completed p=2
```

### 6.3 p=1 vs p=2 对照

至少比较：

```text
p=1 finest completed vs p=2 finest completed
p=1 h=3 vs p=2 h=3   # 如果二者都完成
p=1 h=5 vs p=2 h=5
```

80° 斜入射下 R 预计会比垂直入射更明显，但仍应同时报告绝对差和相对差；如果 R 仍很小，则继续以绝对差为主。

### 6.4 T/A 的解释

本任务固定总高度 140 nm、基座厚度 10 nm，因此 T/A 可以用于同一 domain 内的网格收敛比较。

不要把本任务的 T/A 与此前 70 nm 或 150 nm 不同结构、不同入射角案例的 T/A 直接比较为同一物理界面透射率。

---

## 7. 资源报告要求

本任务同时生成资源报告。必须输出：

```text
assemble_matrix_scale.csv
resource_convergence.csv
failure_boundary.csv
failure_boundary.md
direct_solve_plan.md
```

`resource_convergence.csv` 字段至少包括：

```text
p
h_nm
incident_theta_from_z_deg
incident_azimuth_phi_deg
cells
dofs
matrix_rows
nnz_used
estimated_AIJ_matrix_memory_GB
max_rss_mb
RSS_upper_GB
elapsed_seconds
status
case_status
```

summary 中必须给出资源表，并说明：

```text
1. p=1 从 h=5 到最细 assemble-only completed h 的 rows/nnz/RSS 增长；
2. p=2 从 h=5 到最细 assemble-only completed h 的 rows/nnz/RSS 增长；
3. p=1 从 h=5 到最细 direct completed h 的 R/T/A 与资源增长；
4. p=2 从 h=5 到最细 direct completed h 的 R/T/A 与资源增长；
5. 当前本机 completed direct benchmark 的最细点；
6. 当前本机 first failed direct boundary；
7. 如果想继续到 p=2 更细 h，需要工作站、OOC 还是迭代法；
8. 与此前 normal incidence / 100×100×70 / 100×100×150 nm 案例相比，新结构和 80° 斜入射导致规模变化的原因。
```

---

## 8. 输出文件要求

本任务 outcomes 至少包含：

```text
docs/task008_70nm_official_convergence_benchmark/outcomes/
├── summary.md
├── geometry_validation.md
├── oblique_incidence_validation.md
├── assemble_matrix_scale.csv
├── direct_solve_plan.md
├── official_convergence.csv
├── resource_convergence.csv
├── p1_convergence.csv
├── p2_convergence.csv
├── p1_vs_p2_comparison.csv
├── diagnostic_comparison.csv
├── failure_boundary.csv
├── failure_boundary.md
├── mumps_ooc_boundary.csv                 # 若尝试 OOC
├── parameters.json
├── run_log.txt
├── changed_files.md
└── raw_runs/
```

`geometry_validation.md` 必须说明：

```text
1. grating_width_y = period_y 是否被原代码支持；
2. 如果做了 geometry builder 修正，修正了什么；
3. material tags 是否正确；
4. 周期边界与 full-span y grating 是否存在冲突；
5. 实际传入的 period_x/period_y/grating_width/grating_height/air_height/substrate_thickness。
```

`oblique_incidence_validation.md` 必须说明：

```text
1. theta_from_z = 80 deg 和 phi = 0 deg 的实际传参；
2. kx/ky/kz 的数值；
3. Floquet x/y phase；
4. polarization vector；
5. k·E 是否接近 0；
6. propagating diffraction orders / port modes 数量；
7. 是否出现 Rayleigh warning 或近掠入射数值警告；
8. 入射功率归一化是否正常。
```

`raw_runs/` 中只归档轻量文件：

```text
run_summary.json
port_power.json
port_power.csv
power_summary.csv
volume_absorption.json
dtn_port_power_metrics_3d.json
dtn_port_diffraction_orders_3d.csv
progress_3d.jsonl
solver_log.txt
stdout_tail.txt
stderr_tail.txt
matrix_scale_row.json 或 matrix_scale.csv
```

不要提交大型文件：

```text
results/*/*.vtu
results/*/*.bp
results/*/*.h5
mumps_ooc_files/
完整 results/ 目录
```

---

## 9. summary.md 必须包含的表格

`summary.md` 必须用中文撰写，并给出清晰表格。至少包含：

### 表 1：运行设置

| item | value |
|---|---|
| domain size | 50 × 25 × 140 nm |
| period | 50 × 25 nm |
| grating size | 17 × 25 × 120 nm |
| substrate thickness | 10 nm |
| top air above grating | 10 nm |
| air_height parameter | 130 nm |
| incident angle | theta_from_z = 80°, phi = 0° |
| incident plane | x-z |
| polarization | s, E along y |
| power source | dtn_port_modal_amplitudes |
| solver | default MUMPS direct |

### 表 2：geometry validation

| check | result | note |
|---|---|---|

### 表 3：oblique incidence validation

| item | value | note |
|---|---|---|
| theta_from_z | 80 deg | |
| phi | 0 deg | |
| kx | | |
| ky | 0 | |
| kz | | downward |
| Floquet phase x | | |
| Floquet phase y | 1 | |
| polarization | | |
| k·E | | should be near 0 |

### 表 4：assemble-only matrix-scale 资源评估

| p | h/nm | status | cells | dofs | aux modes | rows | nnz | A matrix GB | RSS upper GB | elapsed s | last stage |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 5：direct solve boundary

| p | last completed h | first failed h | failure stage | matrix GB | RSS upper GB | note |
|---:|---:|---:|---|---:|---:|---|

### 表 6：p=1 official R/T/A 收敛

| p | h/nm | R | T | A_volume | R+T+A | closure | ΔR prev | ΔT prev | ΔA prev | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 7：p=2 official R/T/A 收敛

| p | h/nm | R | T | A_volume | R+T+A | closure | ΔR prev | ΔT prev | ΔA prev | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 8：p=1 vs p=2 对照

| comparison | R diff | T diff | A diff | note |
|---|---:|---:|---:|---|

### 表 9：direct solve 资源规模

| p | h/nm | cells | dofs | rows | nnz | A matrix GB | RSS upper GB | elapsed s | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 10：diagnostic vs official 差异

| p | h/nm | R official | R diagnostic EH | T official | T diagnostic EH | note |
|---:|---:|---:|---:|---:|---:|---|

### 表 11：当前固定 benchmark 建议

| benchmark | recommended use | reason |
|---|---|---|

summary 必须回答：

1. 新目标尺寸是否按 50×25×140 nm 正确建模？
2. `grating_width_y = period_y = 25 nm` 是否被正确支持？
3. 80° 斜入射是否按 x-z 平面、phi=0 正确设置？
4. kx/ky/kz、Floquet phase、polarization 是否正确？
5. 每个 p/h 的 assemble-only 资源需求是多少？
6. 根据 assemble-only 数据，direct solve 计划是否合理？
7. official R/T/A 是否全部来自 DtN port modal amplitudes？
8. p=1 的 R/T/A 是否随 h 收敛？
9. p=2 的 R/T/A 是否随 h 收敛？
10. 当前 p=1 和 p=2 最细 completed direct case 分别是什么？
11. 当前 p=1 和 p=2 first failed direct boundary 分别是什么？
12. p=1 finest 与 p=2 finest 是否接近？
13. 80° 斜入射下 R 是否比垂直入射更明显？
14. 当前可以固定哪些 case 作为本机 benchmark？
15. 资源增长趋势如何？
16. probe diagnostic 与 official 差异是否仍然大？
17. 后续若要更细网格，建议工作站、OOC 还是迭代法？
18. 是否建议合并？

---

## 10. 验收标准

本任务通过标准：

1. smoke case `p=1 h=5, theta=80°, phi=0°` 完成，并验证新几何、斜入射和 material tags。
2. 完成 p=1 与 p=2 的 assemble-only / matrix-scale 资源评估，至少覆盖 h=5/4/3/2.5/2，并尽量向 h=1.5/1 推进到失败边界。
3. 生成 `direct_solve_plan.md`，并明确由 assemble-only 数据推导 direct solve 计划。
4. p=1 h=5/4/3/2.5/2 的 official DtN port modal direct runs 完成，或明确记录不可完成原因。
5. p=2 h=5/4/3 的 official DtN port modal direct runs 完成，或明确记录不可完成原因。
6. 若 p=2 h=3 完成且资源允许，应尝试 p=2 h=2.5；若未尝试，必须说明原因。
7. 必须分别记录 p=1 和 p=2 的 last completed direct h 与 first failed direct h。
8. 所有 completed case 的 `power_source` 必须是 `dtn_port_modal_amplitudes`。
9. 所有 completed case 必须给出 `R_total/T_total/A_volume_total/R+T+A/closure`。
10. summary 中必须给出 geometry validation、oblique incidence validation、assemble-only 资源表、direct boundary 表、p=1 收敛表、p=2 收敛表、p1 vs p2 对照表、direct 资源表。
11. 资源表必须包含 rows、nnz、A matrix GB、RSS、elapsed。
12. 不得使用 task006 probe-plane R/T 作为 official 结果。
13. 不引入迭代法；迭代法留到后续任务。
14. 不提交大型结果文件。

---

## 11. 注意事项

- 本任务目标是“新目标尺寸 + 80° 斜入射的本机可完成 benchmark + 本机资源边界”，不是强行冲击极细网格。
- 由于尺寸和入射角都已变，不能沿用旧几何/垂直入射对 h=3/h=2.5 是否可完成的经验判断；必须先看 assemble-only 资源评估。
- `grating_width_y = period_y` 是本任务最容易出现几何边界问题的地方，必须优先验证。
- 80° 接近掠入射，可能导致端口模态数量增加、Rayleigh 附近问题、线性系统条件变差或 R/T/A 对网格更敏感，必须在 summary 中说明。
- 若代码内部需要 `grating_width_y < period_y`，应优先修正代码，而不是悄悄改用户尺寸。
- R 可能比垂直入射明显增大，但仍应同时报告绝对差和相对差。
- T/A 在本任务固定 50×25×140 nm domain 和固定 80° 入射下可用于网格收敛比较。
- 不要把本任务 T/A 与不同高度/不同周期/不同入射角案例的 T/A 直接作为同一参考面透射进行比较。
- 可复用 task007 的 official/diagnostic 字段设计，但所有 task008 主表必须基于新目标尺寸和 80° 斜入射重跑或明确复用来源。当前新几何与旧几何不同，且入射角不同，通常应重跑。

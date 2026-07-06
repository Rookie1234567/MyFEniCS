# CODEX TASK 20260706：目标尺寸 50×25×140 nm official DtN-port R/T/A 本机收敛 benchmark 与资源报告

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
git checkout -b codex/20260706-target-50x25x140-official-benchmark
git push -u origin codex/20260706-target-50x25x140-official-benchmark
```

推荐本任务分支名：

```text
codex/20260706-target-50x25x140-official-benchmark
```

说明：当前目录名仍为：

```text
docs/task008_70nm_official_convergence_benchmark/
```

这是因为 task008 目录已经提前建立。**以本任务书中的新几何参数为准，不再使用原 70 nm reduced-height 100×100 周期案例作为 task008 主目标。**

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

task005 完成了真实 100×100×150 nm 3D block grating 的资源估算；task006 完成了 70 nm reduced-height domain 的资源扫描，但当时 R/T 后处理仍主要使用 probe-plane E/H Fourier fitting，不能作为 official R/T/A；task007 已将 Stage 4 dtn_port 主线 official R/T/A 恢复为：

```text
power_source = dtn_port_modal_amplitudes
```

并将 E/H Fourier probe、E-only Fourier probe 和 sampled net flux 全部降级为 diagnostic。

现在目标几何发生变化。待仿真的结构为：

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

因此，本任务要在 task007 修正后的可信后处理口径下，完成这个新目标尺寸的本机可承受收敛 benchmark 与资源报告。

---

## 2. 任务目的

本任务目标是固定一个新目标尺寸的本机可长期复用 benchmark：

```text
50 × 25 × 140 nm computational domain
17 × 25 × 120 nm grating
official R/T/A = dtn_port_modal_amplitudes + A_volume
p=1 与 p=2 本机可承受网格收敛表
同步资源报告
```

本任务不是最终高精度物理 benchmark，也不是迭代法任务。它的定位是：

```text
1. 代码可信后处理口径下的新目标结构本机可完成收敛趋势；
2. 后续工作站/服务器计算前的固定回归 benchmark；
3. R/T/A、energy closure 与资源规模的统一表格；
4. 后续开发改动后的 regression reference；
5. 估算该新结构在个人电脑上可达到的最细 direct-solve 网格。
```

---

## 3. 固定几何与物理设置

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
normal incidence
polarization_kind = s
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

### 3.2 关于 grating_width_y = period_y

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

### 3.3 材料

```text
n_air = 1
n_substrate = 0.999002304859 + 0.00182649365j
n_grating = 0.999002304859 + 0.00182649365j
```

### 3.4 边界与后处理

```text
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
stage4_dtn_order_policy = auto_propagating
use_pml = false
use_floquet_xy = true
official_power_source = dtn_port_modal_amplitudes
A = A_volume_total from volume_integral_Im_epsilon_E2
```

主运行：

```text
MPI ranks = 8
solver = default MUMPS direct
```

暂不做迭代法。迭代法留到后续任务。

---

## 4. 必须扫描的网格

本任务目标是“本机可完成 benchmark”。由于新结构横向周期从 100×100 nm 缩小到 50×25 nm，虽然 z 向高度增加到 140 nm，但总体体积相较此前 100×100×70 nm 案例明显更小。因此本任务允许比之前 70 nm 案例尝试更细的网格。

### 4.1 先验 smoke / geometry check

必须先运行：

```text
p = 1
h = 5 nm
MPI = 8
```

用途：

```text
1. 检查 grating_width_y = period_y 是否被 geometry builder 正确支持；
2. 检查 mesh material tags 是否正确；
3. 检查 dtn_port_modal official R/T/A 是否输出；
4. 检查 energy closure；
5. 检查结果文件字段。
```

如果该 smoke 失败，先修正几何支持，不要直接进入大规模扫描。

### 4.2 p=1 必跑扫描

```text
p = 1
h = 5, 4, 3, 2.5, 2 nm
MPI = 8
default MUMPS direct
```

如果这些点全部顺利完成，并且本机资源允许，继续尝试：

```text
p = 1
h = 1.5 nm
```

`p=1 h=1.5` 可作为 optional completed point 或 failure boundary，不作为必须通过项。

### 4.3 p=2 必跑扫描

```text
p = 2
h = 5, 4, 3 nm
MPI = 8
default MUMPS direct
```

由于新结构体积更小，`p=2 h=3` 很可能成为本机可尝试的重要高阶点。若 `p=2 h=3` 完成并且资源仍可承受，继续尝试：

```text
p = 2
h = 2.5 nm
```

如果 `p=2 h=2.5` 也完成且本机仍可承受，可选尝试：

```text
p = 2
h = 2 nm
```

但 `p=2 h=2` 不作为验收前提。不要为了该可选点长时间消耗个人电脑。

### 4.4 可选失败边界 / assemble-only

可选，不作为验收前提：

```text
p=1, h=1.5 nm: direct solve or assemble-only / failure boundary
p=2, h=2.5 nm: direct solve if p=2 h=3 completed comfortably
p=2, h=2 nm: assemble-only 或 direct/OOC failure boundary
```

如果运行这些可选点，必须明确标记：

```text
not part of mandatory completed convergence benchmark
failure_boundary / assemble_only / optional_direct only
```

---

## 5. 输出指标

每个 completed case 必须记录：

```text
p
h_nm
mpi_ranks
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

本任务重点分析 official R/T/A 收敛趋势。

### 6.1 p=1 收敛

对 p=1 的 completed h 点生成表格：

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

对 p=2 的 completed h 点生成表格：

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

注意：R 可能很小，比较 R 时应优先使用绝对差，不要只看相对差。

### 6.4 T/A 的解释

本任务固定总高度 140 nm、基座厚度 10 nm，因此 T/A 可以用于同一 domain 内的网格收敛比较。

不要把本任务的 T/A 与此前 70 nm 或 150 nm 不同结构的 T/A 直接比较为同一物理界面透射率。

---

## 7. 资源报告要求

本任务同时生成资源报告。必须输出：

```text
resource_convergence.csv
```

字段至少包括：

```text
p
h_nm
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
1. p=1 从 h=5 到最细 completed h 的 rows/nnz/RSS 增长；
2. p=2 从 h=5 到最细 completed h 的 rows/nnz/RSS 增长；
3. 当前本机 completed direct benchmark 的最细点；
4. 如果想继续到 p=2 h=2 或更细，需要什么级别资源或是否只建议 assemble-only；
5. 与此前 100×100×70 / 100×100×150 nm 案例相比，新结构规模变化的原因。
```

---

## 8. 输出文件要求

本任务 outcomes 至少包含：

```text
docs/task008_70nm_official_convergence_benchmark/outcomes/
├── summary.md
├── official_convergence.csv
├── resource_convergence.csv
├── p1_convergence.csv
├── p2_convergence.csv
├── p1_vs_p2_comparison.csv
├── diagnostic_comparison.csv
├── optional_failure_boundary.csv          # 若运行可选失败边界
├── failure_boundary.md
├── geometry_validation.md
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
| power source | dtn_port_modal_amplitudes |
| solver | default MUMPS direct |

### 表 2：geometry validation

| check | result | note |
|---|---|---|

### 表 3：p=1 official R/T/A 收敛

| p | h/nm | R | T | A_volume | R+T+A | closure | ΔR prev | ΔT prev | ΔA prev | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 4：p=2 official R/T/A 收敛

| p | h/nm | R | T | A_volume | R+T+A | closure | ΔR prev | ΔT prev | ΔA prev | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 5：p=1 vs p=2 对照

| comparison | R diff | T diff | A diff | note |
|---|---:|---:|---:|---|

### 表 6：资源规模

| p | h/nm | cells | dofs | rows | nnz | A matrix GB | RSS upper GB | elapsed s | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 7：diagnostic vs official 差异

| p | h/nm | R official | R diagnostic EH | T official | T diagnostic EH | note |
|---:|---:|---:|---:|---:|---:|---|

### 表 8：当前固定 benchmark 建议

| benchmark | recommended use | reason |
|---|---|---|

summary 必须回答：

1. 新目标尺寸是否按 50×25×140 nm 正确建模？
2. `grating_width_y = period_y = 25 nm` 是否被正确支持？
3. official R/T/A 是否全部来自 DtN port modal amplitudes？
4. p=1 的 R/T/A 是否随 h 收敛？
5. p=2 的 R/T/A 是否随 h 收敛？
6. 当前 p=2 最细 completed direct case 是什么？
7. p=1 finest 与 p=2 finest 是否接近？
8. 当前可以固定哪些 case 作为本机 benchmark？
9. 资源增长趋势如何？
10. probe diagnostic 与 official 差异是否仍然大？
11. 后续若要更细网格，建议用工作站还是迭代法？
12. 是否建议合并？

---

## 10. 验收标准

本任务通过标准：

1. smoke case `p=1 h=5` 完成，并验证新几何和 material tags。
2. p=1 h=5/4/3/2.5/2 的 official DtN port modal direct runs 完成，或明确记录不可完成原因。
3. p=2 h=5/4/3 的 official DtN port modal direct runs 完成，或明确记录不可完成原因。
4. 若 p=2 h=3 完成且资源允许，应尝试 p=2 h=2.5；若未尝试，必须说明原因。
5. 所有 completed case 的 `power_source` 必须是 `dtn_port_modal_amplitudes`。
6. 所有 completed case 必须给出 `R_total/T_total/A_volume_total/R+T+A/closure`。
7. summary 中必须给出 p=1 收敛表、p=2 收敛表、p1 vs p2 对照表、资源表、geometry validation 表。
8. 资源表必须包含 rows、nnz、A matrix GB、RSS、elapsed。
9. 不得使用 task006 probe-plane R/T 作为 official 结果。
10. 不引入迭代法；迭代法留到后续任务。
11. 不提交大型结果文件。

---

## 11. 注意事项

- 本任务目标是“新目标尺寸的本机可完成 benchmark”，不是强行冲击极细网格。
- `grating_width_y = period_y` 是本任务最容易出现几何边界问题的地方，必须优先验证。
- 若代码内部需要 `grating_width_y < period_y`，应优先修正代码，而不是悄悄改用户尺寸。
- R 很小，比较 R 时使用绝对差；不要只看相对差。
- T/A 在本任务固定 50×25×140 nm domain 内可用于网格收敛比较。
- 不要把本任务 T/A 与不同高度/不同周期案例的 T/A 直接作为同一参考面透射进行比较。
- 可复用 task007 的 official/diagnostic 字段设计，但所有 task008 主表必须基于新目标尺寸重跑或明确复用来源。当前新几何与旧几何不同，通常应重跑。

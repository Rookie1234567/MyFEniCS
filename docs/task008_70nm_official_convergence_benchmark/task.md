# CODEX TASK 20260706：70 nm official DtN-port R/T/A 本机可承受收敛 benchmark 与资源报告

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
git checkout -b codex/20260706-70nm-official-convergence-benchmark
git push -u origin codex/20260706-70nm-official-convergence-benchmark
```

推荐本任务分支名：

```text
codex/20260706-70nm-official-convergence-benchmark
```

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

task005 完成了真实 100x100x150 nm 3D block grating 的资源估算；task006 完成了 70 nm reduced-height domain 的资源扫描，但当时 R/T 后处理仍主要使用 probe-plane E/H Fourier fitting，不能作为 official R/T/A；task007 已将 Stage 4 dtn_port 主线 official R/T/A 恢复为：

```text
power_source = dtn_port_modal_amplitudes
```

并将 E/H Fourier probe、E-only Fourier probe 和 sampled net flux 全部降级为 diagnostic。

因此，本任务要在 task007 修正后的可信后处理口径下，重新完成个人电脑可承受范围内的 70 nm reduced-height 真实 3D grating 收敛 benchmark。

---

## 2. 任务目的

本任务目标是固定一个本机可长期复用的 70 nm 真实 3D grating benchmark：

```text
70 nm reduced-height stage4_block_grating
official R/T/A = dtn_port_modal_amplitudes + A_volume
p=1 与 p=2 本机可承受网格收敛表
同步资源报告
```

本任务不是最终高精度物理 benchmark，也不是迭代法任务。它的定位是：

```text
1. 代码可信后处理口径下的本机可完成收敛趋势；
2. 后续工作站/服务器计算前的固定回归 benchmark；
3. R/T/A、energy closure 与资源规模的统一表格；
4. 后续开发改动后的 regression reference。
```

---

## 3. 固定几何与物理设置

固定为 70 nm reduced-height 真实 3D block grating：

```text
stage_case = stage4_block_grating
period_x = 100 nm
period_y = 100 nm
substrate_thickness = 10 nm
grating_height = 50 nm
top_air_above_grating = 10 nm
air_height = 60 nm
total_height = 70 nm
grating_width_x = 50 nm
grating_width_y = 50 nm
lambda0 = 13.5 nm
normal incidence
polarization_kind = s
```

材料：

```text
n_air = 1
n_substrate = 0.999002304859 + 0.00182649365j
n_grating = 0.999002304859 + 0.00182649365j
```

边界与后处理：

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

根据 task006/task007 已知本机边界，本任务只要求运行当前个人电脑可承受的 completed direct cases。

### 4.1 p=1 必跑

```text
p = 1
h = 5, 4, 3, 2.5, 2 nm
MPI = 8
default MUMPS direct
```

这些点 task006 曾经完成过，但 task006 的 R/T/A 口径不是最终 official。必须用 task007 后的 official `dtn_port_modal_amplitudes` 重新生成一套自洽 benchmark。

### 4.2 p=2 必跑

```text
p = 2
h = 5, 4 nm
MPI = 8
default MUMPS direct
```

这些是当前 reduced-height domain 下本机已知可完成的 p=2 点。`p=2 h=4` 是目前本机上更细、更重要的真实 3D grating 结果。

### 4.3 可选失败边界 / assemble-only

可选，不作为验收前提：

```text
p=1, h=1.5 nm: assemble-only 或 default/OOC failure boundary
p=2, h=3 nm: assemble-only 或 default/OOC failure boundary
```

如果运行这些可选点，必须明确标记：

```text
not part of completed convergence benchmark
failure_boundary / assemble_only only
```

不要为了可选失败点耗费过多本机时间。

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

对 p=1 的 h=5,4,3,2.5,2 生成表格：

```text
R_total_dtn_port_modal
T_total_dtn_port_modal
A_volume_total
R+T+A_volume
closure
ΔR vs previous
ΔT vs previous
ΔA vs previous
ΔR vs finest p=1 h=2
ΔT vs finest p=1 h=2
ΔA vs finest p=1 h=2
```

### 6.2 p=2 收敛

对 p=2 的 h=5,4 生成表格：

```text
R_total_dtn_port_modal
T_total_dtn_port_modal
A_volume_total
R+T+A_volume
closure
ΔR p2 h4-h5
ΔT p2 h4-h5
ΔA p2 h4-h5
```

### 6.3 p=1 vs p=2 对照

需要比较：

```text
p=1 h=2 vs p=2 h=4
p=1 h=3 vs p=2 h=5
p=1 h=5 vs p=2 h=5
```

注意：R 很小，比较 R 时应优先使用绝对差，不要只看相对差。

### 6.4 R 的特殊说明

由于有损基座导致 T/A 随基座厚度和 reference plane 变化，而本任务固定 70 nm domain，因此 T/A 可以用于同一 domain 内的网格收敛比较。

但如果未来再比较不同 total height，应优先关注 R 的绝对变化，或者实现 common-reference-plane T。当前任务只固定 70 nm，不做 interface-referenced T。

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
1. p=1 从 h=5 到 h=2 的 rows/nnz/RSS 增长；
2. p=2 h=5 到 h=4 的 rows/nnz/RSS 增长；
3. 当前本机 completed direct benchmark 的最细点；
4. 如果想继续到 p=2 h=3 或 p=1 h=1.5，需要什么级别资源或是否只建议 assemble-only。
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
├── parameters.json
├── run_log.txt
├── changed_files.md
└── raw_runs/
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
| domain height | 70 nm |
| substrate thickness | 10 nm |
| top air above grating | 10 nm |
| power source | dtn_port_modal_amplitudes |
| solver | default MUMPS direct |

### 表 2：p=1 official R/T/A 收敛

| p | h/nm | R | T | A_volume | R+T+A | closure | ΔR prev | ΔT prev | ΔA prev | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 3：p=2 official R/T/A 收敛

| p | h/nm | R | T | A_volume | R+T+A | closure | ΔR | ΔT | ΔA | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 4：p=1 vs p=2 对照

| comparison | R diff | T diff | A diff | note |
|---|---:|---:|---:|---|

### 表 5：资源规模

| p | h/nm | cells | dofs | rows | nnz | A matrix GB | RSS upper GB | elapsed s | status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

### 表 6：diagnostic vs official 差异

| p | h/nm | R official | R diagnostic EH | T official | T diagnostic EH | note |
|---:|---:|---:|---:|---:|---:|---|

### 表 7：当前固定 benchmark 建议

| benchmark | recommended use | reason |
|---|---|---|

summary 必须回答：

1. 70 nm benchmark 的 official R/T/A 是否全部来自 DtN port modal amplitudes？
2. p=1 的 R/T/A 是否随 h 收敛？
3. p=2 h=5 到 h=4 的变化是否明显？
4. p=1 h=2 与 p=2 h=4 是否接近？
5. 当前可以固定哪些 case 作为本机 benchmark？
6. 当前本机最细 completed official direct case 是什么？
7. 资源增长趋势如何？
8. probe diagnostic 与 official 差异是否仍然大？
9. 后续若要更细网格，建议用工作站还是迭代法？
10. 是否建议合并？

---

## 10. 验收标准

本任务通过标准：

1. p=1 h=5/4/3/2.5/2 的 70 nm official DtN port modal direct runs 完成，或明确记录不可完成原因。
2. p=2 h=5/4 的 70 nm official DtN port modal direct runs 完成。
3. 所有 completed case 的 `power_source` 必须是 `dtn_port_modal_amplitudes`。
4. 所有 completed case 必须给出 `R_total/T_total/A_volume_total/R+T+A/closure`。
5. summary 中必须给出 p=1 收敛表、p=2 收敛表、p1 vs p2 对照表、资源表。
6. 资源表必须包含 rows、nnz、A matrix GB、RSS、elapsed。
7. 不得使用 task006 probe-plane R/T 作为 official 结果。
8. 不引入迭代法；迭代法留到后续任务。
9. 不提交大型结果文件。

---

## 11. 注意事项

- 本任务目标是“本机可完成 benchmark”，不是强行冲击 p=2 h=3 或 h=1。
- p=2 h=4 可能用时较长，但已经在 task007 中完成过，是本任务最重要的高阶 benchmark 点之一。
- 允许复用 task007 中完全相同代码口径和参数的 70 nm p=2 h=5/h=4 raw results，但 summary 必须保证 task008 的表格自洽；如果复用，必须在 run_log 和 parameters 中写明复用来源。
- 最稳妥做法是重跑所有必跑点，保证同一 commit 下结果统一。
- R 很小，比较 R 时使用绝对差；不要只看相对差。
- T/A 在本任务固定 70 nm domain 内可用于网格收敛比较；不要把它外推到不同 total height 的界面透射结论。

# CODEX TASK 20260703：small-cell p 收敛、MPI 一致性与全阶段回归

## 0. 分支要求

继续在当前分支工作：

```text
codex/20260702-rta-output-volume-absorption
```

开始前先阅读上一轮审查报告：

```text
docs/task003_stage4_power_consistency/review_report.md
```

本任务的任务书、outcomes 和后续 review report 都应保存在本任务目录中：

```text
docs/task004_small_cell_p_convergence_mpi_regression/
├── task.md
├── outcomes/
└── review_report.md
```

本任务的所有输出记录必须写入：

```text
docs/task004_small_cell_p_convergence_mpi_regression/outcomes/
```

不要覆盖或改写之前任务目录，例如：

```text
docs/task003_stage4_power_consistency/
```

---

## 1. 背景与当前判断

task003 已经基本修复了 Stage 4 flat-layer 中的主功率闭合问题。当前判断是：

```text
port + A_volume 主线已经基本可信；
probe_eh_fourier 和 net_flux 仍为 diagnostic only；
真实 100 nm grating 不是当前小电脑阶段的必需验收项。
```

small-cell flat-layer 补充验证显示：

```text
period_x = period_y = 10 nm
air_height = substrate_thickness = 5 nm
```

在该设置下，auto_propagating 只保留零级 x/y 四个端口模态，`port` 不再全反射，且 `R_port + T_port + A_volume - 1` 达到机器精度。

本轮任务不再强制回到真实 100 nm grating。当前目标是把 small-cell flat-layer 固化为标准 benchmark，并研究：

1. p=1 和 p=2 的收敛性；
2. p=2 是否能让 `probe_eh_fourier` / `net_flux` 更接近 `port`；
3. MPI 并行 1/4/8 进程是否改变数值结果；
4. 当前分支改动是否破坏 Stage 1 / Stage 2 / Stage 4 的基本功能。

---

## 2. 本轮目标

本任务的核心目标是：

```text
建立一个小电脑可运行的 Stage 4 small-cell flat-layer 收敛与并行一致性验证链条。
```

具体包括：

1. 在 small-cell flat-layer 上比较 p=1 与 p=2；
2. 记录 `port`、`A_volume`、`probe_eh_fourier`、`net_flux` 随网格和阶次的变化；
3. 判断 p=2 是否改善 probe/net_flux 与 port 的一致性；
4. 使用 MPI 1/4/8 进程重复关键 case，检查并行结果是否与串行一致；
5. 在 small-cell 收敛与 MPI 检查通过后，运行 Stage 1 / Stage 2 / Stage 4 的轻量全阶段回归。

---

## 3. small-cell flat-layer 标准设置

默认物理参数：

```text
lambda0 = 13.5 nm
n_air = 1 + 0j
n_substrate = 0.999002304859 + 0.00182649365j
normal incidence
polarization = s
stage4_boundary_model = dtn_port
stage4_dtn_order_policy = auto_propagating
stage4_dtn_assembly = auxiliary
use_pml = false
```

默认 small-cell 几何：

```text
period_x = 10 nm
period_y = 10 nm
air_height = 5 nm
substrate_thickness = 5 nm
interface_z = 0 nm
z_min = -5 nm
z_max = 5 nm
```

该设置仍然是 flat air/Si interface，不是 grating。由于没有横向结构，理论上只应存在零级传播通道。高阶衍射级不应被激发。

---

## 4. p=1 / p=2 收敛性验证

### 4.1 p=1 建议网格

运行：

```text
nedelec_degree = 1
mesh_target_size = 2.7, 2.0, 1.5, 1.0 nm
```

这些点对应 task003 的 small-cell 序列，可作为延续和复核。

### 4.2 p=2 建议网格

运行：

```text
nedelec_degree = 2
mesh_target_size = 4.0, 3.0, 2.0, 1.5 nm
```

如果 p=2 的 1.5 nm 运行时间或内存过大，可以记录原因并跳过；但至少应完成：

```text
p=2, mesh_target_size = 4.0, 3.0, 2.0 nm
```

如果资源允许，可补充：

```text
p=2, mesh_target_size = 1.0 nm
```

但不要把 p=2 h=1 nm 作为必需项。

### 4.3 每个 case 必须记录的量

每个 p/h case 至少记录：

```text
p
mesh_target_size_nm
cells
N1curl DoF
DtN auxiliary modes
elapsed_s
max_rss_mb
R_port
T_port
A_port
A_volume
closure_port_volume = R_port + T_port + A_volume - 1
R_ref_port
T_ref_port
A_ref_port
dR_port
dT_port
dA_port
R_probe
T_probe
A_probe
R_flux
T_flux
A_flux
probe_minus_port
flux_minus_port
```

### 4.4 判断标准

重点判断：

1. `R_port` 是否随 h 减小而接近解析 `R_ref_port`；
2. `T_port` 是否接近解析 `T_ref_port`；
3. `A_volume` 是否接近解析 `A_ref_port`；
4. `R_port + T_port + A_volume - 1` 是否保持机器精度或接近机器精度；
5. p=2 是否比 p=1 在相近 DoF 或更粗网格下更接近解析参考；
6. p=2 是否明显改善 `probe_eh_fourier` 与 `port` 的差异；
7. p=2 是否明显改善 `net_flux` 与 `port` 的差异。

不要只用 `R+T≈1` 判断正确性。对于有损 Si，更重要的是：

```text
R_port + T_port + A_volume ≈ 1
```

---

## 5. MPI 并行一致性验证

上一轮主要是串行运行。本轮必须增加 MPI 并行检查。

### 5.1 必须测试的 MPI 进程数

至少测试：

```text
MPI ranks = 1, 4, 8
```

如果 8 ranks 在本机资源或 Docker 环境下不可用，应记录具体错误，并至少完成 1 和 4 ranks。

### 5.2 MPI 检查 case

建议选择一个 p=1 和一个 p=2 的中等规模 case 做 MPI 对比：

```text
p=1, mesh_target_size = 1.5 nm 或 2.0 nm
p=2, mesh_target_size = 2.0 nm 或 3.0 nm
```

选择原则：

```text
足够小，可以在 1/4/8 ranks 下跑完；
足够有代表性，可以检查 port、volume、probe、net_flux 的并行一致性。
```

### 5.3 MPI 结果比较指标

对每个 MPI rank 数，记录：

```text
R_port
T_port
A_port
A_volume
closure_port_volume
R_probe
T_probe
A_probe
R_flux
T_flux
A_flux
DoF
cells
DtN modes
elapsed_s
max_rss_mb
linear residual
```

比较：

```text
abs(value_mpi4 - value_mpi1)
abs(value_mpi8 - value_mpi1)
```

### 5.4 MPI 验收阈值

对于主线结果，建议阈值：

```text
|R_port_mpiN - R_port_mpi1| < 1e-8
|T_port_mpiN - T_port_mpi1| < 1e-8
|A_volume_mpiN - A_volume_mpi1| < 1e-8
|closure_mpiN - closure_mpi1| < 1e-10
```

如果由于并行装配顺序或直接求解器导致最后几位有差异，可以适当放宽到 `1e-7`，但必须在 summary 中说明。

probe/net_flux 可以使用较宽阈值，例如 `1e-6` 或 `1e-5`，因为它们仍是 diagnostic only。

如果 MPI 结果与串行明显不同，必须优先排查：

```text
MPC backsubstitution
auxiliary DtN rows ownership
parallel surface integration
ghost update
probe sampling/gather
volume absorption reduction
```

---

## 6. 全阶段轻量回归

当 small-cell p 收敛和 MPI 检查基本通过后，运行 3D 全阶段轻量回归，确认本分支的改动没有破坏其他功能。

至少覆盖：

```text
Stage 1
Stage 2A
Stage 2B
Stage 2C
Stage 4A small-cell flat-layer
Stage 4B zero-contrast smoke test
```

如果代码中已有统一 runner，可使用统一 runner；如果没有，就分别运行已有入口。

### 6.1 回归要求

每个 stage 至少记录：

```text
stage_name
command
status
elapsed_s
max_rss_mb
key_metric
result_directory
note
```

### 6.2 Stage 4B zero-contrast smoke test

Stage 4B zero-contrast 可以使用小尺寸或低成本配置，目标是验证：

```text
几何、材料 tag、输出结构、port/volume/probe/net_flux 路径没有崩溃。
```

不要把 zero-contrast smoke test 写成真实 grating 物理 benchmark。

### 6.3 real block 说明

本任务不要求真实 100 nm real Si block 通过。真实 grating 结构仍作为未来高资源条件下的应用验证目标。

---

## 7. 输出要求

本任务 outcomes 必须写入：

```text
docs/task004_small_cell_p_convergence_mpi_regression/outcomes/
```

至少包含：

```text
summary.md
metrics.csv
mpi_consistency.csv
parameters.json
run_log.txt
changed_files.md
```

可选但推荐包含：

```text
raw_runs/<case_name>/power_summary.csv
raw_runs/<case_name>/port_power.json
raw_runs/<case_name>/volume_absorption.json
raw_runs/<case_name>/flat_layer_reference.json
raw_runs/<case_name>/power_consistency.json
```

只归档轻量 JSON/TXT/CSV。完整 `results/` 目录继续由 `.gitignore` 排除，不提交 Git。

### 7.1 summary.md 必须包含的表格

#### 表 1：p=1 / p=2 收敛性总表

| p | mesh_nm | cells | dofs | aux_modes | R_port | T_port | A_volume | closure | R_ref | T_ref | A_ref | dR | dT | dA | elapsed_s | max_rss_mb | pass |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

#### 表 2：probe/net_flux 与 port 的差异

| p | mesh_nm | R_probe-R_port | T_probe-T_port | A_probe-A_volume | R_flux-R_port | T_flux-T_port | A_flux-A_volume | note |
|---:|---:|---:|---:|---:|---:|---:|---:|---|

#### 表 3：MPI 一致性

| p | mesh_nm | ranks | R_port | T_port | A_volume | closure | dR_vs_rank1 | dT_vs_rank1 | dA_vs_rank1 | elapsed_s | max_rss_mb | pass |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

#### 表 4：全阶段轻量回归

| stage | command_summary | status | elapsed_s | max_rss_mb | key_metric | note |
|---|---|---|---:|---:|---|---|

#### 表 5：最终判断

必须明确回答：

```text
p=2 是否比 p=1 更快收敛？
probe_eh_fourier 是否因 p=2 明显改善？
net_flux 是否因 p=2 明显改善？
MPI 4/8 与串行是否一致？
Stage 1/2/4 是否仍能通过轻量回归？
当前分支是否可以考虑合并，还是需要继续 task005？
```

---

## 8. 验收标准

本任务完成的标准：

1. small-cell flat-layer p=1 收敛表完成。
2. small-cell flat-layer p=2 收敛表完成。
3. p=1 与 p=2 的 `port / A_volume / analytic reference` 误差被清楚比较。
4. probe/net_flux 是否随 p=2 改善被清楚记录。
5. MPI 1/4/8 结果完成比较；若 8 ranks 不可用，必须记录原因。
6. `port + A_volume` 在关键 case 中保持稳定闭合。
7. Stage 1 / Stage 2 / Stage 4 的轻量回归完成。
8. outcomes 写入本任务目录，不污染旧任务目录。
9. 大型 `results/` 文件夹不提交。
10. summary 不夸大结论：真实 100 nm grating 仍不是本任务验收目标。

---

## 9. 重要注意事项

- 不要重新把真实 100 nm real block 作为本轮必需项。
- 不要用 `R+T≈1` 单独判断正确性。
- 对有损 Si，主检查是 `R_port + T_port + A_volume ≈ 1`。
- `port` 仍是 primary。
- `A_volume` 是 absorption_check。
- `probe_eh_fourier` 和 `net_flux` 仍是 diagnostic only，除非 p=2 结果证明它们已经和 port 稳定一致。
- MPI 检查的重点是“并行不改变结果”，不是追求并行加速。运行时间可以作为参考，但不是本轮主要目标。
- 运行时保留默认 timestamped unique output，除非明确需要覆盖旧结果。轻量归档复制到 `docs/task004.../outcomes/raw_runs/`。

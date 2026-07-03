# CODEX TASK 20260702：R/T/A 输出整理与体吸收积分

## 0. 分支流程

当前任务起点分支是：

```text
codex/20260703-stage4-validation-cleanup
```

先完成以下分支操作：

1. 确认当前分支 `codex/20260703-stage4-validation-cleanup` 已经通过基本检查，且没有需要保留但未提交的本地修改。
2. 将 `codex/20260703-stage4-validation-cleanup` 合并到 `master`。
3. 推送远程 `master`。
4. 从最新远程 `master` 创建新分支：

```text
codex/20260702-rta-output-volume-absorption
```

后续所有代码修改、文档修改、运行结果和 outcomes 都提交到这个新分支。不要继续在旧分支上直接开发。

本任务迁移后的任务闭环目录为：

```text
docs/task002_rta_output_volume_absorption/
├── task.md
├── outcomes/
└── review_report.md
```

理论笔记应放在 `notes/theory/`，不再放在旧的 `notes/docs/`。

---

## 1. 目标

本任务目标是重构 Stage 4 后处理中的 R/T/A 输出口径，新增体吸收积分 `A_volume`，并用一组轻量但有代表性的 13.5 nm EUV 算例验证四类功率/吸收指标的一致性。

需要统一四类结果：

| method | role | meaning |
|---|---|---|
| `port` | primary | DtN port / auxiliary modal amplitude 给出的主 R/T/A |
| `probe_eh_fourier` | cross_check | 上下 probe plane 的 E/H Fourier directional fitting 给出的 R/T/A |
| `net_flux` | diagnostic | 上下 probe plane 的 sampled Poynting flux 给出的总 R/T/A |
| `volume_absorption` | absorption_check | 材料内部体吸收积分给出的 A |

注意：`port` 是当前主结果；`probe_eh_fourier`、`net_flux`、`volume_absorption` 是交叉检查和能量闭合诊断。不要把四类指标混成一个没有来源说明的 `R_total/T_total/A_balance`。

---

## 2. 新增 A_volume 体吸收积分

新增体吸收积分后处理，计算材料内部真实吸收：

```text
A_volume = P_abs / P_inc
```

其中 `P_abs` 应来自有损材料区域内的体积分，形式上与下式一致：

```text
P_abs ∝ ∫ Im(epsilon_r) |E_total|^2 dV
```

实现要求：

1. 必须使用总场 `E_total`，不能只用 scattered field。
2. 如果 Stage 4 内部求的是 scattered field，应先构造或使用已有的 total field：

```text
E_total = E_background + E_scattered
```

3. 使用 `epsilon_r = n^2`，吸收项用 `Im(epsilon_r)`，不要直接用 `Im(n)`。
4. 分区域输出：

```text
A_volume_grating
A_volume_substrate
A_volume_total
```

5. 只积分真实物理材料区域：substrate、grating；不要把 PML 损耗计入 material volume absorption；空气通常不计吸收，除非明确设置为空气有损。
6. 若某个区域不存在，例如 flat-layer 没有 grating，则该区域输出 `null` 或 `0.0`，但必须在 json 中写清楚 status/reason。
7. 输出对比指标：

```text
A_port_balance_minus_A_volume_total
A_probe_balance_minus_A_volume_total
A_flux_minus_A_volume_total
energy_closure_error_port_volume = R_port + T_port + A_volume_total - 1
```

如果当前归一化常数存在不确定性，必须在代码注释和结果 json 中明确说明采用的是 code units，并通过 flat-layer / zero-contrast 对照验证一致性。

---

## 3. 新增理论说明

新增一个理论说明 markdown，迁移后的建议路径为：

```text
notes/theory/THEORY_RTA_AND_VOLUME_ABSORPTION.md
```

内容要求：

1. 解释四类 R/T/A 口径：`port`、`probe_eh_fourier`、`net_flux`、`volume_absorption`。
2. 说明 `A_balance = 1 - R - T` 的含义：它是能量余额，不是直接材料体吸收。
3. 说明 `net_flux` 的含义：它是边界总能流检查，可以给出 `R_flux/T_flux/A_flux`，但不分衍射级。
4. 说明 `volume_absorption` 的含义：它直接积分材料内部耗散，可分为 grating/substrate/total。
5. 说明理想一致性关系：

```text
R_port ≈ R_probe ≈ R_flux
T_port ≈ T_probe ≈ T_flux
A_port_balance ≈ A_probe_balance ≈ A_flux ≈ A_volume_total
R + T + A_volume_total ≈ 1
```

6. 明确有吸收材料时不能要求 `R + T ≈ 1`；更合理的是检查 `R + T + A_volume ≈ 1`。
7. 说明 zero-contrast 的作用：保留 block 几何但取消折射率对比，用来检查 geometry/tag/mesh/postprocess 是否引入虚假散射。

---

## 4. 重构 R/T/A 输出文件

对每个 case 的 results 文件夹，统一输出以下简洁结构。已有 `run_summary.json` 保留，不需要新增 `run_info.json`。

```text
results/<case_name>/
├── run_summary.json
├── power_summary.csv
├── port_power.json
├── probe_power.json
├── flux_power.json
└── volume_absorption.json
```

### 4.1 `power_summary.csv`

这是最重要的总览表，一行一个 method。建议字段：

```csv
method,R,T,A,role,status,source
```

建议内容形如：

```csv
port,<R_port>,<T_port>,<A_port_balance>,primary,ok,dtn_auxiliary_port_amplitudes
probe_eh_fourier,<R_probe>,<T_probe>,<A_probe_balance>,cross_check,ok,eh_fourier_orders
net_flux,<R_flux>,<T_flux>,<A_flux>,diagnostic,ok,sampled_poynting_flux
volume_absorption,,,<A_volume_total>,absorption_check,ok,volume_integral_Im_eps_E2
```

如某项未实现或未计算，必须写 `status = not_implemented / skipped / failed`，不要只留空值而不说明原因。

### 4.2 `port_power.json`

保存 DtN port 主结果和每个端口模态的功率明细。至少包含：

```text
method = port
role = primary
power_source = dtn_auxiliary_port_amplitudes
R_total
T_total
A_balance
orders / modes per-order details
incident_power_code_units
```

### 4.3 `probe_power.json`

保存 E/H Fourier probe 后处理结果。至少包含：

```text
method = probe_eh_fourier
role = cross_check
power_source = eh_fourier_orders
R_total
T_total
A_balance
top_probe_z
bottom_probe_z
sample_count_x
sample_count_y
fit_residuals
per-order R/T details
```

E-only Fourier 可以保留为 diagnostic 字段，但不能作为 official probe R/T。

### 4.4 `flux_power.json`

保存 sampled net Poynting flux 结果。至少包含：

```text
method = net_flux
role = diagnostic
power_source = sampled_poynting_flux
top_flux_outward
bottom_flux_outward
incident_power_code_units
R_total_from_net_flux
T_total_from_net_flux
A_flux
note = does_not_resolve_diffraction_orders
```

### 4.5 `volume_absorption.json`

保存材料体吸收积分结果。至少包含：

```text
method = volume_absorption
role = absorption_check
power_source = volume_integral_Im_epsilon_E2
A_grating
A_substrate
A_volume_total
regions
normalization_note
```

### 4.6 Legacy outputs

原来已有的零散 power json/csv 不再作为默认正式输出。可以删除，或移动/归类到 debug/legacy 输出；但正式 summary 和 outcomes 必须只引用新的五个文件：

```text
power_summary.csv
port_power.json
probe_power.json
flux_power.json
volume_absorption.json
```

---

## 5. 验证案例

本任务不要求达到最终物理收敛，但要验证四套 R/T/A 计算代码的正确性和一致性。

固定物理参数：

```text
lambda0 = 13.5 nm
substrate material = Si / silicon
n_substrate = 0.999002304859 + 0.00182649365j
```

真实 Si grating 时：

```text
grating material = Si / silicon
n_grating = 0.999002304859 + 0.00182649365j
```

zero-contrast 时：

```text
保留 block geometry
n_grating = n_air = 1 + 0j
```

建议运行以下案例，网格尺寸均为：

```text
mesh_target_size = 10 nm, 5 nm, 3 nm
```

必须运行：

```text
Stage 4A flat-layer: 10 nm, 5 nm, 3 nm
Stage 4B zero-contrast: 10 nm, 5 nm, 3 nm
Stage 4B real Si block: 10 nm, 5 nm, 3 nm
```

用户确认 4B 的 3 nm 可以跑通，因此不要默认跳过。除非遇到内存不足、额度不足、PETSc/Docker 错误或运行时间明显异常，否则耐心等待，不要提前中断。

优先使用当前 Stage 4 `dtn_port` 路径。若使用 `zero_order` 或 `auto_propagating`，必须在 `run_summary.json` 和 outcomes 中明确写出。如果为了资源控制需要限制衍射级，也必须写明：

```text
stage4_dtn_order_policy
diffraction_zero_order_only
diffraction_order_max_m/n
```

---

## 6. Outcomes 输出要求

本任务的 outcomes 应写入本任务目录：

```text
docs/task002_rta_output_volume_absorption/outcomes/
```

至少包含：

```text
summary.md
metrics.csv
parameters.json
run_log.txt
changed_files.md
```

### 6.1 `summary.md` required tables

`summary.md` 必须能一览无余。至少包含以下表格。

#### Table 1: run overview

| case | mesh_nm | stage | dofs | status | elapsed_s | max_rss_mb |
|---|---:|---|---:|---|---:|---:|

#### Table 2: four-method R/T/A summary

| case | mesh_nm | method | R | T | A | role | status |
|---|---:|---|---:|---:|---:|---|---|

#### Table 3: consistency checks

| case | mesh_nm | dR_probe_port | dT_probe_port | dA_flux_port | dA_volume_port | closure_error_port_volume | pass |
|---|---:|---:|---:|---:|---:|---:|---|

Definitions:

```text
dR_probe_port = R_probe_eh_fourier - R_port
dT_probe_port = T_probe_eh_fourier - T_port
dA_flux_port = A_flux - A_port_balance
dA_volume_port = A_volume_total - A_port_balance
closure_error_port_volume = R_port + T_port + A_volume_total - 1
```

#### Table 4: volume absorption by region

| case | mesh_nm | A_grating | A_substrate | A_volume_total | A_port_balance |
|---|---:|---:|---:|---:|---:|

#### Table 5: conclusions

| case | mesh_nm | conclusion |
|---|---:|---|

Conclusions should distinguish:

```text
code path passes
energy consistency passes
physical benchmark candidate
numerical sanity only
```

Do not overclaim physical correctness just because `R+T` is close to 1.

### 6.2 `metrics.csv`

`metrics.csv` should contain one row per case/method combination, or one row per case with method-specific columns. It must include enough fields to reconstruct Table 2 and Table 3.

Required fields include:

```text
case
stage_case
mesh_nm
method
R
T
A
role
status
source
dofs
cells
elapsed_s
max_rss_mb
```

### 6.3 `parameters.json`

Must record:

```text
branch_name
lambda0_nm
n_substrate_complex
n_grating_complex per case
mesh sizes
stage4 boundary model
stage4_dtn_order_policy
diffraction settings
material labels
validation_role
```

### 6.4 `run_log.txt`

Must record:

```text
commands executed
start/end status
failures or skips
reason for any skipped case
memory/time issues
```

---

## 7. Verification commands

Before running cases, run at least:

```bash
python -m compileall -q src
```

Inside the Docker/FEniCS environment, run:

```bash
python3 -m unittest discover -s src/test -p "test_*.py"
```

After implementing the new output structure and volume absorption calculation, run the validation cases listed above. If any case fails, record the error and continue with the remaining cases when safe.

---

## 8. 验收标准

This task is complete only if:

1. `codex/20260703-stage4-validation-cleanup` has been merged into remote `master`.
2. New branch `codex/20260702-rta-output-volume-absorption` exists and contains all new work.
3. Every completed result folder contains:

```text
run_summary.json
power_summary.csv
port_power.json
probe_power.json
flux_power.json
volume_absorption.json
```

4. `power_summary.csv` clearly separates `port`, `probe_eh_fourier`, `net_flux`, and `volume_absorption`.
5. `A_volume` is computed from total field and material-region volume integrals.
6. `summary.md` in outcomes contains the required tables.
7. The flat-layer and zero-contrast cases at 10/5/3 nm show reasonable agreement between port/probe/net_flux/volume metrics, or any disagreement is clearly diagnosed.
8. Stage 4B real Si block is run at 10/5/3 nm unless a concrete resource or runtime error prevents it.
9. No large unnecessary result files are committed.
10. The final response/commit notes do not claim final physical benchmark validity unless the evidence supports it.

---

## 9. Important cautions

- Do not judge correctness only by `R + T ≈ 1`.
- For lossy Si, the meaningful check is closer to:

```text
R + T + A_volume_total ≈ 1
```

- Keep `port` as primary, but use `probe_eh_fourier`, `net_flux`, and `volume_absorption` to validate it.
- Do not mix PML absorption with material volume absorption.
- Do not use scattered field alone for volume absorption.
- Do not silently skip 3 nm cases; record exact reasons if skipped.
- Do not keep ambiguous top-level `R_total/T_total/A_balance` in new summary outputs unless the containing json has a clear `method` field.

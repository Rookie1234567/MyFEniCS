# CODEX TASK 20260704：恢复 DtN port modal amplitudes 作为 Stage 4 官方 R/T/A

## 0. 分支与执行流程

本任务书写在当前 task006 分支中，供下一轮本地执行。**不要由 ChatGPT 代为创建远程分支。**

当前已完成分支：

```text
codex/20260704-reduced-height-grating-convergence-memory
```

开始 task007 前，建议先在本地合并 task006：

```bash
git checkout master
git pull
git merge codex/20260704-reduced-height-grating-convergence-memory
git push origin master
```

然后由本地 Codex/开发者从更新后的 `master` 新建 task007 分支，例如：

```bash
git checkout -b codex/20260704-dtn-port-modal-official-rta
git push -u origin codex/20260704-dtn-port-modal-official-rta
```

推荐本任务分支名：

```text
codex/20260704-dtn-port-modal-official-rta
```

开始前必须阅读：

```text
docs/task006_reduced_height_grating_convergence_memory/review_report.md
docs/task006_reduced_height_grating_convergence_memory/outcomes/summary.md
docs/task006_reduced_height_grating_convergence_memory/outcomes/reduced_vs_original_domain_comparison.csv
docs/task005_stage4_real_grating_memory_estimation/review_report.md
notes/reference/current_version_boundaries.md
notes/theory/stage4_3d_dtn_port.md
README.md
```

本任务的任务书、outcomes 和后续 review report 都应保存在：

```text
docs/task007_dtn_port_modal_official_rta/
├── task.md
├── outcomes/
└── review_report.md
```

所有轻量结果写入：

```text
docs/task007_dtn_port_modal_official_rta/outcomes/
```

不要改写 task000-task006 的 outcomes 或 review report。

---

## 1. 背景问题

目前 Stage 4 真实 3D block grating 的求解边界已经使用：

```text
stage4_boundary_model = dtn_port
stage4_dtn_assembly = auxiliary
```

但是 task006 暴露出一个后处理口径问题：

```text
当前 3D diffraction 的 official R/T 仍来自 E/H Fourier probe-plane modal fitting，
而不是直接来自 DtN port auxiliary modal amplitudes。
```

当前代码中存在：

```text
OFFICIAL_STAGE4_DIFFRACTION_POWER_SOURCE = "eh_fourier_orders"
```

这一路径比 E-only Fourier 和 sampled net flux 更可靠，因为它利用切向 E/H 分离上下行波；但它仍然依赖 probe plane 的位置。对于有损 substrate，T 在不同 bottom probe 深度评价会变化，A_volume 也会随 substrate 积分厚度变化。

这导致 task006 中 70 nm 和 150 nm 的 R/T/A 对照受到 reference plane / probe plane 影响，不能公平判断 reduced-height domain 是否物理等价。

因此，本任务目标是恢复正确层级：

```text
official R/T/A = DtN port modal amplitudes
probe-plane E/H Fourier fitting = diagnostic only
E-only Fourier = diagnostic only
sampled net flux = diagnostic only
```

---

## 2. 核心目标

本任务核心目标：

```text
将 Stage 4 dtn_port 主线的官方 R/T/A 改为直接来自 DtN port modal amplitudes，
并把所有 probe-plane fitting / sampled field 方法降级为 diagnostic。
```

具体要回答：

```text
1. 当前 dtn_port auxiliary unknowns 中是否已经包含 top/bottom modal coefficients？
2. 如果包含，如何直接用它们计算 R/T？
3. 如果没有被暴露，如何把 modal coefficients 写入 run_summary / port_power.json？
4. official R/T/A 如何统一定义 reference plane？
5. 70 nm 与 150 nm 在 DtN port modal official R/T/A 下是否接近？
6. E/H Fourier probe fitting 与 DtN port modal R/T 差异有多大？
```

---

## 3. 必须保持的术语边界

### 3.1 official

本任务完成后，正式输出必须使用：

```text
power_source = dtn_port_modal_amplitudes
```

official 字段包括：

```text
R_total
T_total
A_volume_total
R_plus_T
R_plus_T_plus_A_volume
energy_closure_error_port_volume
per_order R_mn / T_mn
```

其中 R/T 应来自 DtN port modal amplitudes，而不是 probe plane fitting。

### 3.2 diagnostic

以下全部必须标记为 diagnostic：

```text
diagnostic_eh_fourier_probe
diagnostic_e_only_fourier_probe
diagnostic_sampled_net_flux
```

不要再把 `eh_fourier_orders` 写成 official power source。

---

## 4. 代码调查要求

开始实现前，先调查并在 outcomes 中记录：

```text
1. src/solvers/dtn_port_3d.py 中 auxiliary unknown 的定义、索引、物理含义；
2. Stage 4 flat-layer sanity 中 port R/T 是如何计算的；
3. stage4_block_grating 当前 run_summary / port_power.json 中是否已有 dtn port modal amplitude；
4. top port 和 bottom port 的 modal reference plane 分别在哪里；
5. lossy substrate 中 bottom port amplitude 的功率归一化是否已经处理传播衰减；
6. 当前 diffraction_3d.py 的 E/H Fourier fitting 与 dtn_port auxiliary modal unknown 的关系。
```

将调查结果写入：

```text
docs/task007_dtn_port_modal_official_rta/outcomes/dtn_port_modal_investigation.md
```

---

## 5. 实现要求

### 5.1 暴露 DtN port modal amplitudes

如果当前 auxiliary unknown 已经等价于 port modal coefficient，则应：

```text
1. 给每个 top/bottom order 建立明确 metadata；
2. 记录 order_m, order_n, polarization, direction, medium, beta/kz, propagating/evanescent；
3. 记录 modal amplitude complex value；
4. 记录 modal power contribution。
```

如果当前 auxiliary unknown 不是直接 modal amplitude，而是某种辅助投影未知量，则应：

```text
1. 推导它与物理 outgoing modal amplitude 的关系；
2. 在代码中显式转换；
3. 在文档中写清楚转换公式；
4. 不允许模糊地把 auxiliary unknown 直接当 power amplitude。
```

### 5.2 official power path

新增或修改后处理，使官方功率路径为：

```text
R/T from dtn_port_modal_amplitudes
A_volume from material volume absorption
closure = R_total + T_total + A_volume_total - 1
```

输出文件建议：

```text
port_power.json
port_power.csv
```

其中必须包含：

```text
power_source = dtn_port_modal_amplitudes
reference = dtn_port_boundary_or_documented_modal_reference
R_total_dtn_port_modal
T_total_dtn_port_modal
A_volume_total
R_plus_T_dtn_port_modal
R_plus_T_plus_A_volume_dtn_port_modal
energy_closure_error_dtn_port_modal_volume
```

### 5.3 diagnostic power path

保留现有 E/H Fourier modal fitting，但改名或明确输出为：

```text
diagnostic_eh_fourier_probe
```

输出字段建议：

```text
R_total_diagnostic_eh_fourier
T_total_diagnostic_eh_fourier
A_balance_diagnostic_eh_fourier
probe_top_z
probe_bottom_z
diff_vs_dtn_R
diff_vs_dtn_T
```

E-only Fourier 和 sampled net flux 也保持 diagnostic，不参与 official R/T/A。

### 5.4 backward compatibility

如果已有 summary 依赖字段名 `R_total` / `T_total`，那么本任务完成后：

```text
R_total = R_total_dtn_port_modal
T_total = T_total_dtn_port_modal
```

旧的 E/H Fourier 值必须改成 diagnostic 前缀，不能继续覆盖 official 字段。

---

## 6. 公式与归一化要求

必须在 outcomes 中写清楚功率公式，至少包括：

```text
P_incident
P_reflected_order
P_transmitted_order
R_mn = P_reflected_order / P_incident
T_mn = P_transmitted_order / P_incident
```

对于有损 substrate，必须说明：

```text
1. bottom port modal power 的 reference plane 是哪里；
2. T 是否包含从 interface 到 bottom port reference 的吸收；
3. 如果要比较不同 substrate_thickness，如何统一 T 的参考面；
4. A_volume 的积分区域是否包括整个 substrate physical domain。
```

如果当前 DtN port amplitude 自然定义在 top/bottom truncation boundary，那么 70 nm 和 150 nm 的 T 仍可能因为 reference plane 不同而不同。此时必须明确写出：

```text
DtN port modal official R/T 是 boundary-referenced；
若要比较 interface-referenced T，需要额外实现 propagation correction。
```

如果可以实现 interface-referenced correction，则优先同时输出：

```text
T_total_dtn_port_modal_boundary_reference
T_total_dtn_port_modal_interface_reference
```

但不要在没有推导清楚时强行修正。

---

## 7. 回归算例要求

### 7.1 Flat-layer sanity

必须先跑 flat-layer sanity，确认 DtN port modal official R/T 与解析解一致：

```text
stage4_flat_layer_sanity
small-cell 或 task004 中已用配置
p=1 / p=2 至少各一个代表点
```

要求：

```text
R/T/A 与解析或既有 task004 port+A_volume 结果一致；
能量闭合正常。
```

### 7.2 真实 block grating smoke

运行：

```text
stage4_block_grating
70 nm reduced-height
p=2, h=5 nm, MPI=8
```

输出并比较：

```text
official dtn_port_modal R/T/A
diagnostic_eh_fourier_probe R/T/A
两者差异
```

### 7.3 70 nm vs 150 nm 对照

运行或复用：

```text
70 nm:  p=2, h=5 nm, MPI=8
150 nm: p=2, h=5 nm, MPI=8
```

比较：

```text
R_dtn_port_modal_70 vs R_dtn_port_modal_150
T_dtn_port_modal_70 vs T_dtn_port_modal_150
A_volume_70 vs A_volume_150
R/T diagnostic_eh_fourier_70 vs 150
```

必须特别讨论：

```text
如果 dtn_port_modal 仍随 height 变化，是因为 port reference boundary 不同，还是因为 physical truncation changed field solution？
如果 diagnostic_eh_fourier 随 bottom probe 深度变化，而 dtn_port_modal 更稳定，则说明 task006 差异主要来自 probe-plane postprocess。
```

### 7.4 Zero-contrast grating smoke

建议增加一个 zero-contrast block grating smoke：

```text
stage4_block_grating
n_grating = n_air or n_grating = background according to existing zero-contrast path
p=1, h=5 nm
```

要求：

```text
R ≈ 0
T ≈ expected background transmission
A consistent with material setup
```

---

## 8. 输出文件要求

本任务 outcomes 至少包含：

```text
docs/task007_dtn_port_modal_official_rta/outcomes/
├── summary.md
├── dtn_port_modal_investigation.md
├── dtn_port_power_formula.md
├── flat_layer_port_modal_validation.csv
├── block_grating_port_modal_vs_eh_probe.csv
├── reduced_vs_original_port_modal_comparison.csv
├── diagnostic_probe_comparison.csv
├── port_power_schema_example.json
├── parameters.json
├── run_log.txt
├── changed_files.md
└── raw_runs/
```

`raw_runs/` 中只归档轻量文件：

```text
run_summary.json
port_power.json
power_summary.csv
volume_absorption.json
progress_3d.jsonl
solver_log.txt
stdout_tail.txt
stderr_tail.txt
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

## 9. summary.md 必须回答的问题

`summary.md` 必须用中文回答：

1. 当前 DtN port auxiliary unknown 是否可以直接解释为 modal amplitude？如果不能，转换关系是什么？
2. 本任务后 official power source 是什么？
3. `R_total` / `T_total` 是否已经来自 dtn_port_modal_amplitudes？
4. E/H Fourier fitting 是否已经降级为 diagnostic？
5. flat-layer sanity 中 dtn_port_modal R/T/A 是否与解析或 task004 port 结果一致？
6. 真实 70 nm block grating 中 dtn_port_modal 与 diagnostic_eh_fourier 差异多大？
7. 70 nm vs 150 nm 在 dtn_port_modal 下是否仍有明显差异？
8. 若仍有差异，是 reference plane、volume absorption 厚度，还是物理解本身变化？
9. 当前是否还需要 height scan？如果需要，应该在什么 R/T/A 口径下做？
10. 是否建议合并？是否还存在 official/diagnostic 命名不清的问题？

---

## 10. 验收标准

本任务通过标准：

1. 不再把 `eh_fourier_orders` 作为 official power source。
2. `R_total` / `T_total` 的 official 来源改为 `dtn_port_modal_amplitudes`，或明确说明为什么当前 auxiliary formulation 尚不能暴露该值，并给出下一步阻塞点。
3. E/H Fourier、E-only Fourier、sampled net flux 全部明确标记为 diagnostic。
4. `port_power.json` 和 `run_summary.json` 中清楚写出 official 与 diagnostic 的来源。
5. flat-layer sanity 通过。
6. 真实 block grating p=2 h=5 至少跑通一个 70 nm case，并输出 official vs diagnostic 对照。
7. 70 nm vs 150 nm p=2 h=5 至少完成 official dtn_port_modal 对照，或明确说明无法比较的原因。
8. 所有改动有单元测试或 smoke test 覆盖。
9. 不提交大型结果文件。

---

## 11. 注意事项

- 不要为了追求结果一致而隐藏 reference plane 差异。
- 如果 DtN port amplitude 是 boundary-referenced，就如实写 boundary-referenced。
- 如果要做 interface-referenced T correction，必须写清楚传播因子和有损介质中的功率修正公式。
- 不要把 diagnostic probe 结果删除；它仍然有调试价值。
- 但 official R/T/A 只能有一个主来源，并且必须清楚。
- 在 task007 完成前，不建议继续基于 task006 的 probe-plane R/T/A 做 height 物理判断。

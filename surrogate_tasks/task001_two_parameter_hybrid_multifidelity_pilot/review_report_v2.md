# Task001 Review Report V2

## 1. 审阅结论

```text
review_status = changes_required_numerical_robustness
observable_schema_v2 = approved
existing_HF10_LF4_evidence = retain
five_failed_configurations = must_be_root_caused_and_corrected
Task002_bulk_generation = not_authorized
surrogate_training = not_authorized
production_inversion = not_authorized
required_next_action = Task001_M9_failure_forensics_and_robustness_correction
```

Review V1 要求的 fixed-order 母响应 schema 已经完成并通过静态审阅：每个固定 `(side,m,n)` 现在保存复数 `kx/ky/kz`、S/P 边界复振幅实部/虚部、S/P 功率、order total、分离的色散传播/实功率携带语义，以及分侧 `n!=0` 泄漏。已有 37 个通过的 raw PDE 记录在不重跑 FEM 的情况下被重新提取为 v2 mother responses，checker 和 targeted tests 通过。

这一部分批准，不需要再次修改或重跑。

但是，Task001 仍有五个正式照明配置没有通过。用户明确要求当前物理程序在 `grazing=0.5--10°`、`azimuth=0--90°`、S/P 条件内具备可计算性和鲁棒性。除精确零掠射、精确 Rayleigh/Wood 奇点或明确的数学退化点外，线性 Maxwell 边值问题不应因为入射偏振或方位角不同而无解释失败。当前五个点均不能简单作为“不可计算配置”跳过。

因此 Task001 暂不结束，也不批准 Task002。下一轮必须对五个失败配置逐项定位根因、修改代码并完成修复后的正式回归。不得仅放宽 Gate、增加容差、改写失败标签或将失败配置从参数域中删除。

---

## 2. 本轮已批准的修正

### 2.1 Observable schema v2

批准：

```text
schema = task001.fixed-n0-orders.v2
```

每个 sample 保存：

- `incident_polarization`；
- reflection/transmission 两侧固定 9 个 `n=0` order；
- `m,n` 与 `kx,ky,kz={re,im}`；
- `dispersion_propagating`；
- `power_carrying`；
- grouped `components.s/p.amplitude_re/im`；
- grouped `components.s/p.power`；
- `order_total_power`；
- 分侧 `n_nonzero` 功率泄漏和最大复振幅；
- raw execution/solver SHA、parameter hash、numerical source 与 v1/v2 schema identity。

`dispersion_propagating=false` 但在有损基底有限端口上有正向实 Poynting 功率的模式继续计入 T；真正不携带功率的 component/order 使用 `power=null`，传播但数值功率恰为零时保留 `0.0`。

### 2.2 既有数值证据

以下结果继续有效，不得无理由重跑：

```text
selected HF = HF10 p6/h10/M120/MPI2
selected LF = LF4 p4/h10/M120/MPI2
HF7P5 = controlled_stop_resource_projection; PDE not launched
selected provisional bundle = 10°/0°/S + 10°/90°/S
numerical source = 68f4f9bc92de6cd7ec2896755ef210fb182280a1
```

已有 S 配置和几何敏感度 pilot 可复用，但在五个失败配置修复之前，只能称为当前通过配置的局部证据，不能称为整个用户照明域已资格化。

---

## 3. 五个失败项的正确身份

这不是“五个不同代理模型失败”，而是同一 LF4 Hybrid 数值路径下五个照明配置失败：

| ID | grazing | azimuth | incident pol | 失败阶段 | 已知现象 |
|---|---:|---:|---|---|---|
| F1 | 0.5° | 0° | S | trace reduction before solver record | eliminated trace/interior consistency about `6.99e-8 / 6.31e-8` |
| F2 | 0.5° | 0° | P | trace reduction before solver record | eliminated trace/interior consistency about `1.38e-7 / 1.38e-7` |
| F3 | 0.5° | 90° | P | post-solve physical Gate | interface E about `0.8993`, H about `0.02020`, energy about `8.729e-4` |
| F4 | 10° | 0° | P | post-solve physical Gate | interface E about `0.6008`, H about `0.02167`, energy about `2.203e-5` |
| F5 | 10° | 90° | P | post-solve physical Gate | interface E about `0.6005`, H about `0.01924`, energy about `2.566e-5` |

F1/F2 没有进入 PDE 求解；F3--F5 的线性系统残差可以很小，但物理接口/能量检查失败。两类失败必须分开分析。

---

## 4. 审阅发现的高优先级根因假设

以下是代码审阅得到的候选根因，不得直接写成最终结论。Codex 必须用 A/B 数值证据逐项证实或排除。

### R2-A：interface surface-load quadrature 的 coefficient degree 可能错误

`src/coupling/hybrid_internal_modes.py::_ReusableInterfaceSurfaceLoad` 将二维 modal field lift 到三维接口上的 DG 高阶 coefficient，然后组装：

```text
inner(lifted_modal_field, Hcurl_test) * ds(interface)
```

但当前 `high_order_quadrature_policy(...)` 传入：

```text
coefficient_degree = 0
```

实际 lifted target 是与 local FE degree 相当的 DG 高阶函数，不是常数。这个设置可能低估接口积分所需 quadrature，导致本应只有 trace 支撑的 surface vector 在 cell-interior dof 上留下非舍入级残量。F1/F2 的 `1e-7` 量级远高于已批准的 p6 roundoff envelope `~1e-12`，不能再通过调大 `project_mpc_vector_to_active_trace` 容差处理。

必须检查：

1. 使用实际 lifted coefficient degree 重新计算 quadrature policy；
2. 对 F1/F2 做 quadrature degree sweep；
3. 记录每个 mode/side/role 的 `max_active/max_slave/max_interior/cutoff/roundoff_units`；
4. 找到第一个 offending mode，记录其 beta、kind、normalization、basis condition 和 amplitude scale；
5. 证明修正后 interior/slave 残量随 quadrature 收敛到舍入级，而不是被容差掩盖。

### R2-B：近掠射/Rayleigh 邻域的模式归一化可能放大无害误差

在 `grazing=0.5°` 时，入射零级纵向波数接近零。接近 Rayleigh 截止时，unit-amplitude、unit-power、biorthogonal 或 traction normalization 之间可能出现很大的尺度差异。即使绝对 surface integral 误差很小，也可能因 modal normalization 被放大。

必须为 F1/F2 输出：

- 所有外部 DtN order 与内部 QEP mode 的 `|beta|/k0`；
- 最近 Rayleigh order；
- mode power、trace norm、biorthogonal norm、traction norm；
- normalization scaling 前后的 trace-only residual；
- 同一物理解在等价 mode rescaling 下是否不变。

若确认是 normalization 问题，修复应采用稳定的模式缩放并将缩放显式传递到 projection/traction/modal unknown，而不是放宽 eliminated-entry Gate。

### R2-C：sampled physical interface Gate 不是 exact trace norm

`interface_field_continuity` 目前在有限的 `(x,y)` 采样网格上比较 local FEM 与 modal reconstruction。该检查不是 H(curl) trace mass/Riesz norm。P 入射在小掠射角下切向 E 可能比法向 E 小，基于采样值的相对误差可能被小分母放大；同时在单元边界上的 one-sided point evaluation 也可能比 S 更敏感。

必须新增一个与离散耦合空间一致的 exact/assembled interface diagnostic：

- tangential E 的 trace mass/Riesz residual；
- tangential H/traction 的 dual residual；
- 分量绝对 L2、参考尺度和相对误差；
- sampled diagnostic 与 assembled diagnostic 的对照。

只有 assembled diagnostic 也失败，才能证明是物理解耦/截断失败；若 assembled pass 而 sampled fail，应修正采样诊断，不能错误拒绝正确解。

### R2-D：physical magnetic reconstruction 使用的 beta 与实际 coupling 模型不一致

Task001 固定：

```text
internal propagation = full3d_uniform_cg
internal traction = scalar_cg_discrete_derivative
```

但 `ModalFieldReconstructor._sample_mode_bases` 当前构造磁场时直接使用：

```text
mode.beta
```

即 continuous QEP beta。实际 coupling/traction 则可能使用 discrete effective propagation beta 和 discrete traction beta。这会使求解阶段与 physical H reconstruction 使用不同符号，P 模式含较强纵向场时尤其容易放大差异。

必须：

1. 将 reconstructor 明确接收 `positive/negative propagation beta` 与 `positive/negative traction beta`；
2. E 的轴向相位使用 selected propagation beta；
3. H/traction reconstruction 使用与 coupling 相同的 selected traction symbol；
4. 报告 continuous 与 discrete 两套 reconstruction 的差异；
5. 加入能在 P 模式上发现 beta 混用的测试。

这项是当前 P 失败最明确的代码一致性风险之一。

### R2-E：M120 对 P 模式是否收敛尚未验证

P 偏振具有更强的纵向电场和界面电荷效应，可能需要更多高阶/倏逝内部模式才能恢复接口连续性。当前 M160 未运行，因此不能区分：

```text
implementation bug
vs
M120 modal truncation insufficient for P
```

必须在 LF4 G00 上做受控 M sweep，例如：

```text
M = 40, 80, 120, 160
```

只有资源允许且仍无趋势时才增加 M。报告 residual、assembled/sample interface E/H、R/T/A、order vector 和成本随 M 的趋势。

若 P 需要大于 M120，最终应：

- 选择覆盖全部正式配置的统一 M；或
- 建立可验证的 configuration-dependent modal convergence policy；
- 不得把不同 M 的结果静默混入同一 fidelity identity。

### R2-F：必须用独立前向路径区分 Hybrid bug 与物理/后处理问题

至少建立以下低成本独立参考：

- 对 `phi=0°`：利用 y-invariant decoupling，与 2D TE/TM 或等价 direct 3D low-order reference 比较；
- 对 `phi=90°`：运行可承受的 direct Full3D p2/p4 coarse reference；
- 同一配置比较 standard Hybrid 与 static-condensed Hybrid；
- 同一配置比较 continuous-beta/traction 与 discrete closure，仅作为诊断，不改变正式 identity。

如果 direct reference 正常而 Hybrid 失败，则定位 Hybrid coupling/reconstruction；如果 standard Hybrid 正常而 static 失败，则定位 trace/static-condensation；如果两者都正常而 sampled Gate 失败，则定位 diagnostic。

---

## 5. Task001 M9：五失败配置鲁棒性修正任务

### M9.0 硬边界

- 不开始 Task002；
- 不生成 49 点数据；
- 不训练 surrogate；
- 不修改用户角度域；
- 不删除 P 偏振；
- 不将 grazing 下限从 0.5°提高；
- 不通过放宽 residual/interface/energy Gate 宣称成功；
- 每次只运行一个 forward job，zero swap，watchdog 保留；
- 先使用 LF4 G00 做定位，避免盲目高保真重跑。

### M9.1 建立 failure-forensics record

新增结构化记录，逐个失败配置保存：

```text
configuration identity
nearest Rayleigh order and beta/k0
QEP/basis/normalization diagnostics
first offending surface mode and role
active/slave/interior maxima and cutoffs
quadrature policy and degree
standard/static path comparison
continuous/discrete propagation and traction comparison
M convergence
assembled interface E/H residual
sampled interface E/H residual
R/T/A/Avolume/energy closure
raw diffraction mother response
resource and source identity
```

建议交付：

```text
benchmarks/cases/111_task001_illumination_robustness/
  config.json
  expected.json
  records/
```

### M9.2 修复 F1/F2

执行顺序：

1. 在不改容差的情况下复现并定位 first offending mode；
2. 修正 interface coefficient degree/quadrature；
3. 做 mode-rescaling invariance；
4. 比较 standard 与 static-condensed path；
5. 如仍失败，改为实体/trace-aware surface assembly，使理论零 trace 的 cell-interior entries 不通过数值抵消产生；
6. 重新运行 `0.5°/0°/S` 和 `0.5°/0°/P` G00。

验收要求：

- 能产生完整 solver record；
- trace-only residual 有解释且通过原 Gate；
- true residual、interface、energy、order 和 zero-swap Gate 全部通过；
- 真实泄漏负测试仍失败，证明没有掩盖错误。

### M9.3 修复 F3--F5

执行顺序：

1. 新增 assembled interface trace diagnostics；
2. 修正 reconstruction beta/traction consistency；
3. 做 M sweep 判断是否存在 truncation；
4. 用 independent direct/2D reference 对照；
5. 检查 P 入射下共偏振和交叉偏振定义、符号、功率归一化；
6. 在 G00 重新运行三个 P 配置。

验收要求：

```text
linear true residual <= 1e-9
algebraic interface projection <= 1e-8
traction equilibrium <= 1e-8
assembled tangential E/H physical Gate pass
sampled diagnostic与assembled结论一致
|R+T+A_volume-1| <= 1e-5
raw order sum matches R/T
zero swap
```

若某配置处于非常接近但非精确的 Rayleigh anomaly，不允许直接排除。必须通过角度邻域双侧扫描证明响应的极限和数值收敛，并采用稳定的 limiting formulation。只有精确数学奇点可在 schema 中标为 `rayleigh_singular`, 且必须有解析判据，而不是以求解失败代替判定。

### M9.4 全域最小回归

五个 G00 全部修复后，再执行：

- 原 3 个通过 S 配置 G00 回归，确保修复无退化；
- F1--F5 的 G00 正式记录；
- 对最终可能进入 DOE 的新增通过配置，才运行必要的 9 点 LF pilot；
- 若 selected bundle 改变，才补做新增 HF10 五点；
- 既有 HF10/S 记录不得因无关后处理改动整批重跑。

### M9.5 测试要求

至少新增：

- high-order interface quadrature degree regression；
- trace-only support under arbitrary modal rescaling；
- near-Rayleigh nonzero-beta stability；
- P-mode propagation beta/traction beta consistency；
- assembled vs sampled interface diagnostic；
- S/P phi=0 decoupling：交叉偏振接近数值零；
- phi=90 conical S/P power closure；
- standard vs static-condensed observable equivalence；
- M-convergence checker；
- Case095/096 和现有 S configuration 不回归。

---

## 6. 必须提交的修正报告

Codex 完成修复后必须新增：

```text
surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/
  outcomes/five_configuration_failure_correction.md
  response_v3.md
```

`five_configuration_failure_correction.md` 对 F1--F5 每项必须包含：

1. 失败前的阶段和数值；
2. 经过哪些诊断；
3. 被排除的假设；
4. 最终根因；
5. 修改的代码和数学理由；
6. 修复前/修复后对比；
7. standard/static、continuous/discrete、M sweep、direct reference 证据；
8. residual、interface E/H、R/T/A、energy、order、内存和 swap；
9. 新增测试；
10. 剩余适用边界。

报告不得只写“提高鲁棒性”“调整容差”“现在通过”。根因必须落到具体数学离散、归一化、quadrature、trace map、mode truncation、reconstruction 或 diagnostic 机制。

---

## 7. Task002 放行条件

Review V3 只有在以下事项满足后才批准 Task002：

1. observable schema v2 保持通过；
2. F1--F5 均有明确 root cause；
3. 五个 G00 在修复代码上完成正式 pass，或精确数学奇点由解析判据正确分类；
4. 不是通过放宽 Gate 得到 pass；
5. P 偏振至少在 `0.5°/90°`、`10°/0°`、`10°/90°` 完成物理资格化；
6. `0.5°/0°` S/P trace path 可稳定组装并求解；
7. standard/static 和独立 reference 支持修复结论；
8. M120 是否足够已有证据，必要时 fidelity identity 已更新；
9. 原有 S/HF10/Case095/096 无回归；
10. 更新后的 DOE 和 Task002 dataset plan 使用真实通过的完整候选池。

在此之前，Task002 的 49 点 LF、HF anchors、surrogate training 和 inversion 均保持禁止。

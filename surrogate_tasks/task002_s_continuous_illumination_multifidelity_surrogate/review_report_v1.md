# Task002 Review Report V1

## 1. 审阅结论

```text
review_status = targeted_numerical_investigation_required
reviewed_branch = codex/only-one-13p5nm-surrogate-inversion
reviewed_head = 23ac700e2fb0691d9bb4f112d98ca2deca70f85a
M0 = approved
M1 = approved
M2_anchor_evidence = approved_and_retain
M2_controlled_stop = procedurally_correct
reported_root_cause = not_yet_established
bulk_generation = not_authorized
surrogate_training = not_authorized
angle_DOE = not_authorized
production_inversion = not_authorized
required_next_action = M2A_low_grazing_intermediate_azimuth_fidelity_investigation
```

本轮计算中止不是内存不足、swap、watchdog、MUMPS 不收敛或衍射级窗口遗漏。Task002 按任务书在首个未通过正式数值 Gate 的新角度点受控停止，程序行为正确，已有 8 个通过的 LF/HF anchor 和 1 个失败样本均应保留。

中止点是：

```text
height = 120 nm
width  = 17 nm
grazing = 0.5°
azimuth = 15°
polarization = S
fidelity = LF p4/h10/M120/MPI2 Hybrid
```

该点只有 `A_volume` 与 `A_balance=1-R-T` 的差值未通过：

```text
energy_closure_error = -2.6061279233e-5
formal limit         =  1.0e-5
```

而：

```text
true relative residual = 2.068e-11
assembled interface E  = 1.240e-3  < 5e-3
exact traction dual    = 3.051e-11
peak RSS               = 1.067 GB
swap                    = 0
cleanup                 = complete
```

因此这不是“求解失败”，而是**当前 LF Hybrid 在低掠射、一般中间方位角下的物理闭合精度尚未资格化**。

当前报告把它概括成 `near-cutoff` 失败还不充分。`cutoff_metric=0.0087265` 实际上由入射/镜面 `top m=0` 的

```text
|beta_00| / k0 = sin(0.5°)
```

给出；所有 `grazing=0.5°` 的方位角都具有相同数值，而 `0.5°/0°/S` 和 `0.5°/90°/S` 的 LF/HF 均通过。因此“接近截止”是该角度行的共同背景条件，**不是 15° 方位角单点失效的充分因果解释**。

在完成以下 M2A 定向诊断并得到明确 disposition 之前，不得继续 49 点 pilot、四维 bulk、代理拟合或角度 DOE。

---

## 2. 审阅范围与接受内容

审阅了：

- Task002 `README.md`、`task.md`、`response_v1.md`；
- 全部 Task002 outcomes；
- Case112 config、expected、M1/M2 tracked records 与 checker；
- `src/forward_data/task002_schema.py`、`task002_design.py`、`task002_dataset.py`、`task002_campaign.py`；
- Task002 独立 S-only runner Gate；
- exact assembled variational traction 与 sampled diagnostic 的路由；
- 9 个正式 M2 样本、资源数据和回归测试；
- Task000/001、Case095/096、Case110/111 的相关边界。

远程分支当前相对最新 `master` 为 ahead 46、behind 1。该状态不是本轮问题；按照支线规则不得自动 merge/rebase `master`。

### 2.1 M1 接受

接受并保留：

- S-only、13.5 nm、四维参数域 schema；
- exact 0° 与域外 fail-closed；
- degree 到 wavevector feature 的转换；
- 固定 order-window 解析审计；
- 49 LF、9 fixed HF 点表与 seed；
- campaign resume/dedup；
- canonical dataset、mask、split、hash 与混源拒绝；
- Case112 checker 与 91-test 回归。

当前解析审计已证明 49 点角度 grid 的传播 `n=0` order union 为 `m=-7..0`，现有固定窗口完整。此次中止不是 order-window 缺失。

### 2.2 Task002 独立 traction Gate 接受

接受 Task002 将：

```text
exact assembled variational conormal/traction dual
```

作为正式 H/traction Gate，并将旧 sampled point-interpolation H 指标保留为 diagnostic。该修改修正了 Task001 中已经发现的诊断语义问题，且没有修改 Task001/Task035c 历史 Gate。

### 2.3 四个角度 LF/HF anchors 接受

以下 8 个 center-geometry runs 全部通过、zero swap、clean source、watchdog cleanup 完整，应保留：

```text
LF/HF × (0.5°/0°, 0.5°/90°, 10°/0°, 10°/90°), S
```

它们证明：

- S-Hybrid 可以计算四个角域端点；
- 低掠射本身并不会必然失败；
- 中间方位角必须单独验证，不能由端点插值假定。

---

## 3. 为什么计算中止

Task002 M2 规定：连续角域 pilot 中一旦出现未解释的正式 numerical Gate failure，就保存证据并停止，不得直接进入 bulk。

执行结果为：

```text
M2 center anchors: 8/8 pass
LF angle pilot:     5/49 unique evaluated
HF fixed pilot:     4/9 completed by corner reuse
first new LF point: 0.5°/15°/S
classification:     failed_numerical_gate
failed formal Gate: volume_energy_closure_abs_le_1e-5
```

所以中止是**预期的 fail-closed 行为**，不是程序异常退出。

该点的能量账本为：

```text
R_total   = 0.8185631316479318
T_total   = 0.0014147769348765492
A_balance = 0.18002209141719164
A_volume  = 0.1799960301379584
A_volume - A_balance = -2.6061279233e-5
```

绝对闭合误差约为入射功率的 `2.6e-5`，相对于吸收约为 `1.45e-4`。它不是灾难性错误，但超过预先冻结 Gate，因此不能作为 `measured_pass` 静默进入正式 LF 数据集。

---

## 4. 主要审阅发现

### R1：`near-cutoff` 当前是背景标签，不是已证明根因

当前 `cutoff_metric` 对固定 order 集合取最小 `|beta|/k0`。在 `grazing=0.5°` 时，top `m=0` 本身满足：

```text
|beta_00|/k0 = sin(0.5°) = 0.0087265
```

因此 `0.5°/0°`、`0.5°/15°`、`0.5°/90°` 都会被标记为 near-cutoff。前两端点中 `0.5°/0°` 与 `0.5°/90°` 已通过，而 15°失败，说明需要解释的是：

```text
低掠射 + 中间方位角 + 一般 conical/full-vector coupling
```

而不是仅仅“低掠射”。

必须升级 cutoff 报告语义：

1. 保存达到最小值的 `side,m,n`；
2. 单独报告 `incident/specular grazing metric = |beta_top,m0|/k0`；
3. 单独报告排除 incident m0 后的 `nearest_nonincident_rayleigh_metric`；
4. 判断邻域内是否真的有非零衍射级 `beta` 穿越零；
5. 只有存在非入射 order opening/closing 时才称为 `Rayleigh-near`。

不得把所有 0.5° 点统一解释成同一个 Rayleigh anomaly。

### R2：LF p4 与 HF p6 在 0.5° 区域存在巨大的保真度差异

四角 anchors 已经暴露出一个比单点 energy Gate 更重要的问题。

在 `0.5°/0°/S`：

```text
LF R/T/A = 0.859005 / 0.000834 / 0.140161
HF R/T/A = 0.621706 / 0.006224 / 0.372070
LF-HF Δ  = +0.237299 / -0.005390 / -0.231909
```

在 `0.5°/90°/S`：

```text
LF R/T/A = 0.861286 / 0.000824 / 0.137889
HF R/T/A = 0.625420 / 0.006239 / 0.368341
LF-HF Δ  = +0.235867 / -0.005415 / -0.230452
```

而在 10° 两端，LF-HF 的 R/A 差约为 `1e-3--5e-3` 量级。

因此：

```text
LF4 p4/h10/M120 is not yet qualified as one uniform low fidelity over 0.5°--10°.
```

多保真模型允许 LF 有系统偏差，但前提是该偏差随四维输入平滑、可学习且 LF/HF 灵敏度保持相关。当前只有四个 anchor，不足以证明低掠射区的巨大 discrepancy 可由少量 HF 校正。

必须优先比较 p4/p5/p6 与 M 截断，决定：

- p4 是否只是低掠射离散不足；
- p5 是否能成为全角域经济 LF；
- M120 是否在中间方位角不足；
- 是否需要按角域建立显式 fidelity regime。

### R3：15°点的接口 E 误差虽通过 Gate，但相对端点显著放大

失败点：

```text
assembled interface E = 1.2399e-3
```

同一低掠射 LF 端点：

```text
0.5°/0°  : 1.2876e-6
0.5°/90° : 2.1795e-5
```

因此 15° 点的 assembled E 误差约为：

```text
~963 × the 0° value
~57  × the 90° value
```

虽然仍低于 `5e-3` Gate，但这种突增与能量误差同时出现，强烈提示：

- 中间方位角使 S 偏振同时含全局 x/y 分量；
- `kx`、`ky` 同时非零；
- 一维 y-invariant 几何进入一般 2.5D/conical 全矢量耦合；
- 当前 p4/M120 模态空间可能没有充分表示该接口场。

这是当前首要数值假设，但必须通过 HF、M/p 收敛和 direct reference 证实。

### R4：尚未区分“LF 离散误差”“Hybrid 模态误差”和“吸收后处理误差”

目前只记录了总 `A_volume` 与 `A_balance`，还缺少该点的完整能量分解：

```text
bottom local FEM absorption
top local FEM absorption
middle modal volume absorption
middle-entry Poynting flux
middle-exit Poynting flux
middle Poynting loss
volume-loss minus Poynting-loss
raw reflection order sum
raw transmission order sum
n!=0 leakage
```

Task001 M9 已具备 middle volume-loss / Poynting-flux 双重审计能力。必须在当前 S 失败点复用这一审计：

- 若 middle volume loss 与 Poynting loss 不一致，根因在 reconstruction/integration；
- 若二者一致而全局仍不闭合，根因更可能在 Hybrid modal closure、接口场截断或 external port coupling；
- 若 Full3D 与 HF 均通过而 LF 失败，根因属于 LF 资格而非整个 S-Hybrid 路线。

### R5：任意方位角的入射 S 定义从代码上看是自洽的，但仍需运行时审计

当前定义：

```text
direction = (sin theta cos phi, sin theta sin phi, -cos theta)
S = (-sin phi, cos phi, 0)
```

解析上 `S·k=0` 且 `|S|=1`，Floquet phases 来自同一 `kx,ky`。因此没有静态证据表明 15° 输入矢量公式错误。

但正式诊断仍应记录：

```text
|k|/(k0*n_air)
k·S
|S|
kx, ky, kz
Floquet phase x/y
incident normal power
```

并与独立 Full3D 同配置比较，以排除 runner/config mapping 的实现偏差。

---

## 5. Required M2A：定向诊断与恢复范围

下一轮只解决 M2，不开始 M3--M10。

建议建立：

```text
benchmarks/cases/113_task002_low_grazing_intermediate_azimuth/
```

及：

```text
surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
  outcomes/m2_low_grazing_failure_analysis.md
  response_v2.md
```

### M2A-0：证据与 source 纪律

1. 保留 `f6613e4...` 的 9 个 raw/compact 样本及 hashes，不改写；
2. 诊断若只新增 instrumentation，可建立新的 clean diagnostic SHA；
3. 任何影响 matrix、RHS、modal basis、propagation、traction、absorption 或 order extraction 的修复，都必须建立新 formal dataset SHA；
4. 不自动 merge/rebase master；
5. 一次只运行一个 FEM、MPI2、threads=1、zero swap、watchdog。

### M2A-1：在准确失败点建立三条参考

对中心几何 `0.5°/15°/S` 至少运行：

```text
A. current LF: Hybrid p4/h10/M120       # 已有，保留
B. current HF: Hybrid p6/h10/M120       # 必须新增
C. independent: Full3D static p4/h10    # 必须新增
```

Full3D 使用 assembly-time static condensation、同一网格拓扑、同一材料/角度/DtN 和 mother-response schema。

比较：

- R/T/A_balance/A_volume；
- 每个固定 order 的复振幅与功率；
- raw order sums；
- true residual；
- assembled interface E/traction；
- complete energy ledger。

判定：

```text
HF pass + Full3D pass + LF fail -> LF model problem
HF fail + Full3D pass           -> Hybrid M120 continuous-angle problem
Full3D also fails               -> common discretization/postprocessing/config problem
```

不要求本机尝试 Full3D p6；只有资源投影安全且前述三条证据仍不足时才考虑。

### M2A-2：p/M 收敛矩阵

在 `0.5°/15°/S` 先做小矩阵：

```text
p4/h10: M = 80, 120, 160, 240
p5/h10: M = 120
p6/h10: M = 120
```

若 p4/M240 尚未出现明确趋势且资源允许，可增加 M320；不得无边界扩展。

每个点报告：

- interface E exact assembled norm；
- exact traction dual；
- energy closure；
- R/T/A 和 selected orders；
- mode/basis conditioning；
- wall/RSS；
- 相对 Full3D p4 reference 的 observable error。

目标不是强迫所有组合通过，而是判断误差主要随：

```text
M 增加收敛 -> modal truncation
p 增加收敛 -> transverse/local FE discretization
两者均不收敛 -> propagation/closure or common formulation
```

若 p5 在低掠射区明显接近 p6、成本仍显著低于 HF，可提出：

```text
new LF candidate = Hybrid p5/h10/M120 or evidence-based M
```

但必须作为全角域统一 LF 重新资格化，不能只在失败区静默换模型。

### M2A-3：最小角度邻域，不运行完整 49 点

LF 先运行以下 center-geometry stencil：

```text
grazing = 0.5°:
  azimuth = 0, 5, 10, 15, 20, 30, 45, 60, 75, 90°

azimuth = 15°:
  grazing = 0.5, 0.75, 1.0, 2.0°
```

已存在点必须复用。若某些点仍失败，保留完整 failure map，不因首个失败再次终止整个**诊断 stencil**；但这些点仍不能进入 dataset。

HF 仅在下列位置运行：

- 0.5°/15°；
- LF error/curvature 最大的 2--4 个邻域点；
- 判断 LF/HF discrepancy 连续性所需的最少点。

该 diagnostic stencil 与正式 49 点 campaign 分开记录。

### M2A-4：升级 cutoff 诊断

输出至少包括：

```text
incident_specular_abs_beta_over_k0
nearest_nonincident_abs_beta_over_k0
nearest_order = {side,m,n}
rayleigh_crossing_in_local_angle_neighborhood
all order beta complex values
```

当前 `near_cutoff` 字段可保留兼容性，但不能再单独用于根因分类。

### M2A-5：完整能量账本

对 LF、HF、Full3D 的 0.5°/15°点记录：

```text
incident power
R raw and reported
T raw and reported
A_balance
bottom local grating/substrate loss
top local grating/substrate loss
middle modal volume loss
middle Poynting flux loss
A_volume total
volume-vs-flux discrepancy
global closure
n!=0 leakage
```

若生产 surrogate 只使用 R/T 与 `A_balance=1-R-T`，也不能据此忽略 `A_volume` Gate；先要确定闭合误差是否只是可量化的 LF 离散误差。

### M2A-6：LF/HF discrepancy 资格化

在低掠射 stencil 上，至少报告：

- LF/HF R/T/A 差；
- fixed-order amplitude/power 差；
- 对 angle 的一阶差分趋势；
- LF/HF 导数方向 cosine；
- discrepancy 是否平滑；
- 是否存在符号反转或 regime jump。

现有 0.5° anchors 的巨大 LF/HF 差异不能仅凭 GP 可以拟合而跳过。

---

## 6. 允许的最终 disposition

### D1：现有 LF4 通过修复/收敛

条件：

- 发现明确实现 bug；
- 修复后不放宽 Gate；
- LF4/HF10/Full3D 在 targeted stencil 闭合；
- 新 clean SHA 下重新运行所有受影响 anchors。

则恢复 M2，完成 49 LF + 9--13 HF pilot。

### D2：LF4 不够，但 LF5 或更大 M 是经济的统一 LF

条件：

- 新 LF 在 targeted stencil 和角域端点通过；
- 与 HF10 discrepancy 明显更平滑；
- 成本仍显著低于 HF；
- 固定一个统一 model identity。

则：

1. 更新 Task002 schema/expected/model IDs；
2. 建立新 dataset source SHA；
3. 重新运行四角 LF anchors；
4. 完成整个 49 点 LF pilot；
5. 不把旧 LF4 与新 LF 静默混入同一 fidelity 层。

### D3：Hybrid LF 在低掠射一般方位角没有经济稳定配置

可选：

1. 使用 static-condensed Full3D p2/p3/p4 中经资格化的较低成本模型作为**统一 LF**；或
2. 将角域显式分 regime，分别建立 surrogate/model package。

若分 regime：

- solver route 必须显式写入样本身份；
- regime 边界必须由物理/数值证据冻结；
- 不能把两种 solver 输出当成同一平滑 LF 静默拼接；
- 预测 API 必须报告 route/regime；
- 跨边界连续性必须独立验证。

### D4：只有 `A_volume` 存在有界 LF 离散偏差，而 R/T/order 已由 HF/Full3D 证实可靠

可以提出新的**fidelity-specific acceptance contract**，但本 Review 不预先批准放宽阈值。任何修改必须：

- 基于 p/M/Full3D 收敛证据；
- 在 `expected.json` 中预先冻结；
- 将 LF numerical discrepancy 纳入 dataset/model card；
- 建立新 source/version；
- 重新分类和重跑受影响样本；
- 保持 HF Gate 不变。

不能直接把 `1e-5` 改成 `3e-5` 来让当前样本通过。

---

## 7. 恢复 M2 与开启 bulk 的 Gate

只有以下条件满足，才允许继续：

1. `0.5°/15°/S` 有 HF 和 Full3D reference；
2. 根因被分类为 LF discretization、modal truncation、Hybrid closure 或 postprocessing 中的明确一类；
3. 采用的正式 LF identity 在 targeted stencil 通过冻结 Gate；
4. LF/HF discrepancy 在低掠射区被证明可学习；
5. cutoff diagnostic 能区分 specular grazing 与真正 Rayleigh order crossing；
6. 完成全部 49 LF center-angle pilot；
7. 完成 9--13 HF angle pilot；
8. order window、topology、zero swap、source/hash 全部通过；
9. 没有未解释的 angle-dependent failure。

随后才可进入 M3：冻结 4D Sobol design 和 validation split。

---

## 8. 必须交付

下一轮至少提交：

```text
benchmarks/cases/113_task002_low_grazing_intermediate_azimuth/
  README.md
  config.json
  expected.json
  test_command.txt
  records/
    direct_reference.json
    p_m_convergence.json
    angle_stencil.json
    energy_ledger.json
    cutoff_diagnostics_v2.json

surrogate_tasks/task002_s_continuous_illumination_multifidelity_surrogate/
  outcomes/m2_low_grazing_failure_analysis.md
  outcomes/continuous_angle_qualification.md
  outcomes/test_summary.md
  outcomes/sampling_design.md
  response_v2.md
```

报告必须清楚区分：

- measured result；
- derived diagnostic；
- hypothesis；
- confirmed root cause；
- rejected hypothesis；
- production decision。

不得将 `near-cutoff` 标签本身写成已确认根因。

---

## 9. 给 Codex 的执行摘要

```text
保留 Task002 M1 与现有9个 M2样本。
不要开始49点剩余 campaign、四维 bulk、surrogate或DOE。

首先对中心几何 0.5°/15°/S 运行：
- HF Hybrid p6/h10/M120
- independent Full3D static p4/h10
- LF p4 M sweep与p5 candidate
- complete volume/Poynting energy ledger

随后运行小型低掠射/中间方位角 stencil，升级 cutoff 语义，判断 LF4 是否可作为全域统一 low fidelity。

正式 Gate 不得直接放宽；若需要新 LF 或新 fidelity-specific contract，必须建立新 SHA、schema/model identity 和 dataset version。

完成 M2A evidence、response_v2.md 并推送后停止，等待 ChatGPT Review V2。
```

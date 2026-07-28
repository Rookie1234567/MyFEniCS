# Task001 Review Report V1

## 1. 审阅结论

```text
review_status = changes_required
valid_existing_numerical_evidence = retain
Task002_bulk_generation = not_authorized
surrogate_training = not_authorized
production_inversion = not_authorized
required_next_action = targeted_Task001_correction_and_response_v2
```

Task001 已经完成了大部分关键工程工作，尤其是本地 Hybrid 高/低保真资格化、资源保护、固定拓扑、无 swap 正式运行、同源 p6/h10 参考闭合以及高度/宽度的局部二维信息验证。这些结果应保留，不应无理由重跑。

但是，当前照明 campaign 与任务书的权威角度集合不一致，而且 compact order schema 尚未完整实现任务书规定的母响应字段。因此，当前结果可以证明所实际计算的两个 `80°/S` 配置在中心附近可辨识，却不能声称 Task001 规定的 `70°/80° × 0°/90° × S/P` 首轮候选筛选已经完成，也不能据此正式冻结 Task002 数据集。

本轮不创建或执行 Task002。Codex 应按第 6 节完成定向修正，提交 `response_v2.md` 后再由 ChatGPT Review V2 决定是否放行 Task002。

---

## 2. 审阅范围

本轮审阅了：

- `surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/README.md`；
- `task.md`；
- `response_v1.md`；
- 全部 Task001 outcomes；
- Case110 config、expected、compact records 与 checker；
- `src/forward_data/schema.py`、`task001_config.py`、`orders.py`、`identifiability.py`、resource/watchdog/campaign 模块；
- Task001 对 Hybrid runner 和 static-condensation roundoff Gate 的改动；
- Task000/001、Task035b/c、Case095/096 的 targeted tests 与 authority 对照。

远程分支当前相对最新 `master` 为 ahead 20、behind 1。该 behind 状态不是本轮 blocker；按照支线规则，不得因此自动 merge 或 rebase `master`。

---

## 3. 已接受并保留的结果

### 3.1 本地正式 high fidelity

接受：

```text
selected_high_fidelity = HF10
method = Hybrid static / modal-schur-memory-minimal
field contract = p5 trace / p6 interior exact sequence
mesh = h10, axis counts (6,3,14)
M = 120
MPI = 2
numerical source = 68f4f9bc92de6cd7ec2896755ef210fb182280a1
```

名义点 `height=120 nm, width=17 nm, solver theta=80°, phi=0°, S`：

- true residual `2.4838e-12`；
- interface E/H `1.6395e-7 / 3.8958e-5`；
- energy closure `1.5568e-10`；
- `R/T/A/Avolume = 0.0007628815 / 0.6027016340 / 0.3965354845 / 0.3965354847`；
- process-tree peak RSS `3,287,891,968 B`；
- swap `0 B`；
- Case095/096 12 个冻结通道最大功率/复振幅绝对差 `2.052e-12 / 2.183e-12`。

这些证据足以把当前本地 HF10 作为 Task001/Task002 的 high-fidelity 候选。它仍是 best-available discrete reference，不是 continuum truth。

### 3.2 p6/h7.5 受控停止

接受：

```text
HF7P5 = controlled_stop_resource_projection
PDE launched = false
```

central 预测 `11,588,731,106 B` 已超过 launch ceiling，conservative 预测 `15,878,719,347 B` 也超过 hard ceiling。未使用 swap、OOC 或 OOM 冒险。无需在本机再次尝试 p6/h7.5。

### 3.3 low fidelity

接受：

```text
selected_low_fidelity = LF4 global p4/h10/M120/MPI2
```

在权威 `80°/0°/S` 五点 stencil 上：

- `cosine(dy/dh)=0.999689`；
- `cosine(dy/dw)=0.999998`；
- top-80% Fisher 通道无符号反转；
- mean wall/HF `0.19155`；
- mean RSS/HF `0.31765`。

LF4 可以用于多保真低层，但不得冒充 HF；LF-HF bias 必须由 discrepancy model 显式学习。

### 3.4 当前已计算配置的局部可辨识性

接受为“当前实际配置下的局部 pilot 结论”，不是完整 Task001 候选集结论：

```text
C1 = solver theta 80°, phi 0°,  S
C2 = solver theta 80°, phi 90°, S
```

HF 结果：

| 观测 | rank | cond(Jw) | rho(h,w) |
|---|---:|---:|---:|
| reflection-only | 2 | 1.3217 | 0.000182 |
| reflection + transmission | 2 | 1.2208 | -0.14793 |

这足以说明在名义点附近，两个 S 配置的功率响应包含两个独立局部方向。2,000 次 1% provisional noise 抽样仍只能称为 DOE sanity，不能解释成真实实验精度或正式反演不确定度。

### 3.5 负结果与工程质量

接受：

- 37 个 measured pass 全部同一 numerical source、solver Gate 通过、zero swap、watchdog cleanup 完成；
- 5 个失败配置及日志 hash 被保留；
- HF7P5 未启动；
- targeted suite `68 passed, 4 skipped`；
- Case110 checker、compileall、`git diff --check` 通过；
- Ruff 在资格化 `.venv` 中不可用，未虚假宣称通过。

---

## 4. Blocking Finding R1：照明角度与任务书不一致

### 4.1 权威任务书

Task001 明确规定 solver 角度：

```text
theta = 70°, 80°       # 偏离向下法线
phi   = 0°, 90°
polarization = S, P
```

对应用户表面掠射角应为：

```text
grazing = 90° - theta
70° solver theta -> 20° grazing
80° solver theta -> 10° grazing
```

若首轮失败，补充 theta=75°，对应 15° grazing。

### 4.2 当前实现

当前 schema/config/expected 使用：

```text
grazing = 0.5°, 10°
solver theta = 89.5°, 80°
fallback grazing = 5.25°
solver theta = 84.75°
```

因此实际 campaign 不是任务书规定的 `70°/80°`，而是 `89.5°/80°`。Case110 checker 通过只能证明实现、config 和 expected 彼此一致；由于三者共同采用了错误候选集合，它不能证明与任务书一致。

### 4.3 影响

这是 blocking issue，因为：

1. solver theta=70° 的 4 个候选配置没有被筛选；
2. M2 规定的 `70°/90°/P` 轻量真实 smoke 没有执行；
3. theta=70° 下 `phi=90°` 会出现与近掠射条件不同的传播级集合，固定 `+1/-1` order 和交叉偏振输出尚未按任务书被真实验证；
4. 当前“最小 configuration bundle”没有与完整权威候选池比较；
5. Task002 的 2-configuration 冻结计划因此仍是 provisional。

### 4.4 必须修正

Codex 必须恢复权威角度合同。允许用户界面继续使用 `grazing_deg`，但候选必须精确映射为：

```text
primary grazing = [20.0, 10.0]
primary solver theta = [70.0, 80.0]
fallback grazing = [15.0]
fallback solver theta = [75.0]
```

schema 的允许范围至少必须覆盖 10--20° grazing；不得再把 0.5°当作 Task001 主候选。已有 0.5°记录可保留为 out-of-scope research/negative evidence，但必须从 Task001 completion count、DOE candidate pool 和 Task002 selection 中排除。

---

## 5. Blocking Finding R2：compact diffraction 母响应字段不完整

任务书要求每个固定 order 保存足以唯一重建实验 observation 的母响应。当前 `orders.py` 的 compact row 主要保存：

```text
side, m, n, polarization,
propagating/power_carrying,
dispersion_propagating,
power,
outgoing_amplitude_at_boundary
```

但没有完整保留：

- `kx, ky, kz` 的 complex identity；
- 明确的 incident polarization linkage；
- 复振幅 `re/im` 的稳定 JSON 结构；
- 同一 `(side,m,n)` 下 S/P component 和 `order_total_power` 的分组关系；
- `n!=0` reflection 与 transmission 分开的泄漏功率；
- `n!=0` 最大复振幅。

当前单一 `n_nonzero_leakage_power` 不满足任务书规定的三个 leakage diagnostics。

### 5.1 允许的规范化结构

不要求机械复制任务书的扁平字段。推荐升级为一个分组明确的 observable schema，例如：

```text
sample-level:
  incident_polarization

order-level:
  side, m, n
  kx, ky, kz = {re, im}
  dispersion_propagating
  power_carrying
  components:
    s: {amplitude_re, amplitude_im, power}
    p: {amplitude_re, amplitude_im, power}
  order_total_power

leakage:
  n_nonzero_reflection_power_sum
  n_nonzero_transmission_power_sum
  n_nonzero_max_abs_amplitude
```

必须继续保留：

- 非传播/不携带功率时 `power=null`，不能与传播但零功率混淆；
- lossy substrate 中 `dispersion_propagating` 与 positive-outward-power 语义分开；
- 固定 order identity，不采用动态 top-N。

因为 Task002 尚未生成正式 dataset，现在可以升级 observable schema，而不需要迁移任何生产数据。已有 raw PDE artifact 可重新提取，不需要因此重跑 PDE。

---

## 6. Required Task001 Correction Scope

Codex 下一轮只执行以下定向修正，不开始 Task002。

### M8.1 权威与 schema 修正

1. 将 Task001 illumination contract 恢复为 solver theta `70°/80°`，或等价 grazing `20°/10°`；
2. fallback 恢复 theta `75°` / grazing `15°`；
3. 同步修正：
   - `src/forward_data/schema.py`；
   - `src/forward_data/task001_config.py`；
   - Case110 `config.json`、`expected.json`；
   - campaign/checker/tests；
4. 升级 fixed-order observable schema，完成第 5 节字段；
5. 更新 README 状态为 `changes_required_after_review_v1` 或等价明确状态。

### M8.2 既有 PDE 复用规则

不得无理由重跑已经有效的 80°结果、HF10/LF4 fidelity qualification 或 HF7P5 projection。

由于修正后 full Git SHA 会改变，允许复用 `68f4f9b...` raw PDE 结果的前提是：

- 建立可审查的 numerical-core manifest；
- 证明影响矩阵、RHS、网格、Hybrid coupling、DtN、求解与 raw postprocessing 的文件在旧/新 baseline 间 byte-identical；
- 现有 raw artifact hash 不变；
- 只对 compact extraction/schema 重新生成并独立 checker 验证。

若无法证明 numerical-core identity，则只重跑最终 selected bundle 所需的最小 80°集合，不得整轮盲目重跑。

### M8.3 补齐 theta=70° 候选

使用 LF4 执行权威候选：

```text
70°/0°/S
70°/0°/P
70°/90°/S
70°/90°/P
```

执行规则：

1. 先在 G00 做完整 numerical Gate；
2. G00 失败时保留真实 negative evidence，不再运行该配置其余 8 个几何点；
3. G00 通过时运行完整 9 点；
4. 每次只运行一个 forward job、zero swap、同一 clean baseline；
5. 必须包含任务书指定的 `70°/90°/P` order-schema smoke。

### M8.4 重新 DOE

用精确权威候选池重新计算：

```text
70/0/S, 70/0/P, 70/90/S, 70/90/P,
80/0/S, 80/0/P, 80/90/S, 80/90/P
```

已有 80°失败/通过证据按 numerical-core identity 规则复用。重新报告：

- 每个候选的 pass/failed/not-run 状态；
- reflection-only 与 R+T；
- 0.5%、1%、2% provisional noise；
- rank、singular values、cond、rho、logdet、channel contribution；
- 最小 planar+conical bundle。

若最终 bundle 仍为 `80/0/S + 80/90/S`，无需重复现有 HF 五点，只需证明 theta=70°候选没有改变选择。

若新 bundle 包含任何 theta=70°配置，则仅对新增配置运行 HF10 五点，并重新完成 HF identifiability 与 synthetic local recovery。

### M8.5 P 偏振表述

当前 P 结果应称为：

```text
current Hybrid numerical qualification failure
```

而不是“P 偏振在物理上失败”或“不存在”。当前失败值主要是 interface/energy/trace Gate 未通过；它说明当前计算路径尚未对该配置资格化，不说明真实结构不能产生或测量 P 响应。

phi=0 的交叉偏振可作为对称性泄漏 Gate；phi=90 的交叉偏振应作为正式物理响应保存。若 theta=70° P 仍失败，Task002 首版可以继续只使用通过资格化的 S 配置，但必须保留 P 的 negative evidence。

### M8.6 测试与交付

至少生成或更新：

```text
surrogate_tasks/task001_two_parameter_hybrid_multifidelity_pilot/
  outcomes/summary.md
  outcomes/test_summary.md
  outcomes/fidelity_qualification.md
  outcomes/illumination_identifiability.md
  outcomes/task002_dataset_plan.md
  response_v2.md

benchmarks/cases/110_surrogate_two_parameter_pilot/records/
```

要求：

- Task000/001、condensation、Task035c、Case095/096 targeted tests；
- order schema synthetic tests和真实 theta=70° record checks；
- Case110 checker 从 raw artifact 重算；
- compileall、`git diff --check`；
- Ruff 仅在资格化环境可用时执行，不得临时破坏 ABI；
- 工作树 clean、唯一分支/upstream、完整 HEAD、ahead/behind；
- 不生成 Task002 49 点数据，不拟合 surrogate，不执行正式 inversion。

---

## 7. Task002 的暂定方法方向

Task001 Review V2 通过后，Task002 不应进行无边界的“模型大比武”。建议冻结：

```text
primary surrogate = multi-fidelity Matérn GP / autoregressive discrepancy
  y_H(h,w,c) = rho_c y_L(h,w,c) + delta_c(h,w)

low-order Chebyshev/PCE = smoothness and interpretability diagnostic baseline
not a model zoo
```

如果低阶 PCE 在冻结验证点上已经满足实验噪声归一化误差 Gate，可以采用它作为最终简单模型；否则使用 multi-fidelity GP。PCE 与 GP 同时失败时，应检查数据、网格连续性、传播级切换和参数域，而不是继续堆 SVR/NN 等模型。

Task002 数据预算仍可沿用 `49 LF geometry + 9 initial HF anchors + adaptive HF + frozen validation` 的框架，但 configuration bundle、observable schema 和精确 solve count 必须由修正后的 Task001 重新冻结。

---

## 8. Review V2 通过条件

只有以下事项全部满足，才批准 Task002：

1. theta=70°/80° 权威候选集与代码/schema/records 完全一致；
2. theta=70°候选按 fail-fast 规则完成；
3. DOE 使用完整权威候选池重算；
4. selected bundle 经必要 HF 五点确认，rank=2、`|rho|<=0.90`；
5. fixed-order 母响应 schema 完整，含 wavevector、复振幅分量、S/P功率、order total 和分侧 leakage；
6. P 失败被正确表述为 numerical qualification failure；
7. Task002 dataset plan 根据最终 bundle 更新；
8. 所有 evidence hash-bound、source/core identity 清楚、zero swap；
9. 没有提前开始 bulk generation、surrogate training 或 inversion。

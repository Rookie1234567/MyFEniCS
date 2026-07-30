# Task036 Review Report V2：全参数域 S/P 鲁棒性扫描与问题驱动修复

## 1. 覆盖关系与任务结论

```text
reviewed_branch = codex/20260730-task36-forward-solver-bugfix-hardening
reviewed_head_before_v2 = 32b417bad88abfe7b464b09bdae883a7eba10cad
base_master = 007298261681014efbe6508ac91c6c3ae9a6a44a
review_v1 = retained_as_historical_review
review_v2 = execution_authority_for_next_round
merge_to_master = not_authorized
ordinary_default = unchanged_until_qualified
```

本 V2 覆盖 V1 中“最多两个 P 点、最多八个 Hybrid PDE、建议新增数值代码不超过
250 行”等硬限制。用户现在要求的目标不是只证明两个代表点，而是提高前向求解器在
完整参数域内的鲁棒性：扫描光栅高度、宽度、入射角、方位角以及 S/P 入射；发现问题
后直接定位并修复实际数值缺陷。

本轮不限制必要的数值代码规模和 PDE 数量，但仍有一条核心原则：

> 先由可重复的失败证明问题，再修改产生问题的数值核心；不得在尚未知道根因时先搭建
> 新 package、状态机、证据框架或大量防御性 wrapper。

允许对 Hybrid 模态基、近简并子空间、模态截断、接口耦合、能量账本和 Full3D/Hybrid
共同代码做实质修复。若某项问题在多个参数点重复出现，应修复其通用数值算法，而不是
逐点增加例外判断。

---

## 2. 已知基础与本轮重点

Task036 已确认并修复：

- DtN direct projection 必须使用切向 `E_x/E_y`；
- exact variational traction dual 与 sampled proxy 必须分离；
- propagation、traction、H reconstruction 的 beta 身份必须显式一致；
- Ny=3 可产生真实离散 trace alias，Ny=4 能消除已知污染；
- Full3D-P 物理解存在，不能把 Hybrid-P 失败写成 P 物理失败；
- 现有 Hybrid-P 的 `modal_rank_sufficient=False` 仍是临时 quarantine，不是实际能力判断；
- 现有 one-shot near-degenerate repair 只能处理一组，修复后最坏误差会移动到另一组。

因此本轮重点不是继续增加 disposition 字段，而是回答并解决：

1. Full3D 在整个 `(h,w,grazing,azimuth,S/P)` 域内是否稳定；
2. Hybrid 在同阶、同几何、同照明下与 Full3D 的差异分布；
3. Hybrid-P 需要多少内部模态才能收敛；
4. 近简并 block、mode selection、interface closure 与 energy closure 在什么区域失效；
5. 失败是代码错误、离散欠分辨、模态截断，还是 Hybrid 本身失去降维优势；
6. 修复后是否在邻域和离网格点上仍成立，而不是只修好单个样本。

---

## 3. 固定物理域

沿用已经使用的 13.5 nm 规则矩形光栅参数域：

```text
height_nm  in [115.0, 125.0]
width_x_nm in [16.0, 18.0]
grazing_deg in [0.5, 10.0]
azimuth_deg in [0.0, 90.0]
incident_polarization in {S, P}
wavelength_nm = 13.5
period_x = 50 nm
period_y = 25 nm
vertical sidewalls
```

内部角度仍为：

```text
incident_theta_deg = 90 - grazing_deg
incident_phi_deg = azimuth_deg
```

不得 clip 越界输入，也不得用精确 0° 代替 0.5° 下限。

---

## 4. 模型与比较合同

### 4.1 主扫描离散模型

主扫描采用已经证明可运行且成本适中的同阶模型：

```text
Full3D authority:
    static condensation
    uniform N1curl p5
    h10
    Nx = 6, Ny = 4, Nz = 14

Hybrid candidate:
    static condensation
    same p5 / h10 / Ny4 cross-section identity
    initial M = 120 per direction
```

每个 Hybrid 点必须与同一输入下的 same-p Full3D 比较。不得拿不同 p、不同 Ny、不同
几何或不同角度的历史值代替当前 authority。

### 4.2 高阶压力测试

在第 8 节指定的少量关键点上增加：

```text
Full3D p6/h10
Hybrid p6/h10
```

该层用于检验高阶 reciprocal trace、近简并子空间和 p6 mode classification，不将 p6
全域扫描作为主循环。

### 4.3 每个点必须保留的已有量

不新增大型 schema，只将现有结果追加到一个 task-local JSONL/CSV：

- 输入：`h,w,grazing,azimuth,incident polarization,p,h,Ny,M`；
- Full3D/Hybrid true residual；
- interface-E algebraic residual；
- exact traction dual；
- full biorthogonality row norm 和 max cross-block overlap；
- direct tangential auxiliary-vs-field projection；
- 每个固定衍射级的 outgoing S/P amplitude 与 power；
- R/T/A balance、A_volume；
- bottom local、middle modal、top local、external port energy ledger；
- rows、matrix/factor NNZ、wall、同步内存（可用时）、swap；
- same-p Full3D 的 R/T/A 和主要通道差异；
- 最终状态及根因分类。

---

## 5. 扫描设计

扫描不是全因子暴力组合，而是“中心角域全覆盖 + 几何边界压力 + 离网格验证 +
失败邻域细化”。所有点同时运行 S 和 P，除非某个点在进入 PDE 前被同一个明确数值
根因阻断。

### 5.1 Round A：中心几何角域骨架

固定：

```text
height = 120 nm
width  = 17 nm
```

基础角网格：

```text
grazing = [0.5, 1, 2, 4, 6, 8, 10] deg
azimuth = [0, 15, 30, 45, 60, 75, 90] deg
```

额外加入已知敏感方位带：

```text
azimuth = [54.25, 54.50, 54.75] deg
for grazing = [0.5, 4.538499870338, 10] deg
```

每个点运行 S 和 P。Round A 的目的：获得完整角域失败类型图，而不是立即在每个失败点
单独调参。

### 5.2 Round B：高度/宽度边界压力

几何角点：

```text
(115,16), (115,18), (125,16), (125,18) nm
```

角度哨兵：

```text
(0.5,0)
(0.5,45)
(0.5,90)
(2,45)
(4.538499870338,54.420819282532)
(10,0)
(10,45)
(10,90)
```

每个组合运行 S 和 P。中心几何的相同点直接复用 Round A，不重复 PDE。

若失败对高度或宽度呈明显单调变化，再只在该失败角度加入边中点：

```text
(115,17), (125,17), (120,16), (120,18)
```

不得预先把全部 3×3 几何网格与全部角度做笛卡尔积。

### 5.3 Round C：离网格鲁棒性

在四维参数域中冻结 16 个确定性 Sobol/LHS 离网格点，每点运行 S 和 P。

要求：

- 不与 Round A/B 精确重复；
- 覆盖低/中/高 grazing；
- 覆盖接近 45°、54.5° 和一般方位；
- 覆盖高度、宽度的内部与边界邻域；
- 点表一经生成即提交，后续不得因结果调整。

这一步用于防止修复只适配规则扫描线。

### 5.4 Round D：高阶 p6 压力点

中心几何固定运行：

```text
(0.5,0), (0.5,45), (0.5,90)
(4.538499870338,54.420819282532)
(10,0), (10,45), (10,90)
```

S/P 都运行 Full3D p6 与 Hybrid p6。若某个 p6 问题被证明与几何强相关，再加入最坏几何
角点；不得一开始扩展为 p6 全域 campaign。

---

## 6. 每个扫描点的执行顺序

每个配置严格按以下顺序，一次只运行一个 heavy PDE：

1. **Full3D same-p**：建立当前源码下的物理/离散 authority；
2. Full3D 若失败，立即停止该队列，修复 Full3D/core bug；
3. **Hybrid M120**：使用同阶、同输入、同 Ny4；
4. 将 Hybrid 与 Full3D 逐项比较并分类；
5. 若通过，记录最小 M=120 并继续下一个配置；
6. 若失败，先根据第 7 节确定根因类型，再决定 M 扫描或代码修复；
7. 修复后先重跑原失败点、两个角度邻点、一个几何邻点以及相反入射偏振 control；
8. 局部回归通过后继续原扫描清单。

不得先把所有 PDE 跑完、最后再统一分析；也不得遇到失败后跳过并继续积累一批未知错误。

---

## 7. 失败分类与修复规则

### 7.1 Full3D 失败

包括 residual、energy、direct tangential projection、Ny alias 或固定衍射级 identity 失败。

处置：修复共享 Full3D/DtN/Floquet/mesh/postprocess 数值核心。不得用 Hybrid 结果解释或
覆盖 Full3D 失败。

### 7.2 Hybrid 在 solve 前 basis Gate 失败

典型为 near-degenerate block split、biorthogonality 或 mode identity 失败。

处置：修复 mode grouping / subspace normalization 本身。当前“只修最坏一对”的 one-shot
逻辑升级为对所有满足以下条件的 connected components 一次联合处理：

- beta 距离在冻结 near-degenerate 尺度内；
- 同一传播方向；
- cross-overlap 超过阈值；
- component 条件数可接受。

优先使用稳定的 SVD/QR 或一次 block inverse 形成联合 left subspace；right modes 与 beta
保持不变。修复后必须检查完整 `||B-I||_inf`，不能只检查最大单 entry。

若 component 很大或病态，不是增加防御字段，而是检查 clustering 和 mode selection 是否
把同一物理子空间错误切开；必要时直接修复 clustering 算法。

### 7.3 interface E / exact traction 失败，但 basis Gate 通过

先做 M 收敛，不立即改耦合公式：

```text
M = 120 -> 240 -> 480 -> maximum finite/full trace rank
```

若相邻层响应已收敛而 interface 仍不闭合，说明不是单纯截断，应审查 projection、reciprocal
pairing、propagation/traction map 和 local static recovery。

### 7.4 interface 与 traction 通过，但 R/T/A 不匹配 Full3D

这是最值得修复的耦合/后处理 bug。逐项检查：

- external auxiliary amplitude 与 recovered field direct projection；
- top incident subtraction；
- port boundary phase location；
- propagation beta 与 traction beta；
- mode power normalization；
- selected positive/negative mode ordering；
- static/standard equivalence。

不得用提高 M 掩盖一个与 M 无关的平台误差。

### 7.5 R/T 接近 Full3D，但 whole-domain energy 失败

只使用现有 ledger 定位：

```text
bottom local FEM flux/loss
+ middle modal Poynting loss / volume loss
+ top local FEM flux/loss
+ external R/T
```

若发现 sign、phase plane、double counting、omitted region 或 normalization bug，直接修复。
若各局部 identity 自洽且误差随 M 收敛，则归类为 modal truncation；不要增加经验能量修正项。

### 7.6 只有接近 full rank 才通过

记录为：

```text
HYBRID_FUNCTIONAL_NO_REDUCTION_ADVANTAGE
```

这不是代码失败。Hybrid 功能可以保留，但该参数区生产路由应使用 Full3D。不得把 Full3D
fallback 计为 Hybrid success。

---

## 8. M 收敛与实际 rank 判定

删除调用处硬编码的：

```text
modal_rank_sufficient = false
```

用同点相邻 M 的真实结果判定。最小判据：

```text
interface_E <= 1e-8
exact_traction_dual <= 1e-8
full_biorthogonality_row_norm <= 1e-6
direct_projection_difference <= 1e-10
max(|Delta R|,|Delta T|,|Delta A|)_M_to_next <= 1e-4
```

最后一个 M 没有 next 时，只有在达到 maximum finite/full trace rank，并与 same-p Full3D
满足全部比较 Gate 时，才允许 rank sufficient。

每个扫描点记录：

```text
minimum_passing_M
selected_modes / available_finite_trace_rank
M_fraction_of_full_rank
Hybrid/Full3D wall ratio
Hybrid/Full3D peak-memory ratio
```

这样最终能够回答 Hybrid-P 在何种角度、几何和资源范围内真正有优势。

---

## 9. S/P 与输出验收

每个通过点必须同时满足：

```text
true relative residual <= 1e-9
interface E residual <= 1e-8
exact traction dual <= 1e-8
full biorthogonality row norm <= 1e-6
direct tangential projection difference <= 1e-10
abs(R + T + A_volume - 1) <= 1e-5
same-p Full3D max(|Delta R|,|Delta T|,|Delta A|) <= 1e-4
zero swap
```

此外必须比较固定 order identity 下的 outgoing S/P amplitudes 和 powers。不能只看总 R/T/A，
因为 cross-polarization 或弱级次错误可能被总量掩盖。

最终输出两个 domain maps：

1. `Full3D robustness map`：S/P 全部点的 pass/fail 与修复历史；
2. `Hybrid validity map`：最小通过 M、精度、资源优势和失败根因。

---

## 10. 开发方式：允许解决问题，禁止搭空框架

本轮不设机械的代码行数或 PDE 数量上限，但执行以下约束：

- 允许修改真正产生错误的通用数值函数；
- 一个问题在多个点重复出现时，必须合并为一个根因修复；
- 每次修复必须有最小复现测试和邻域实际 PDE 回归；
- 不为每个扫描点增加独立 if/exception/status 类；
- 不新建 package、campaign engine、状态机、receipt/hash 层或新 watchdog；
- 扫描调度最多使用一个简单 task-local driver 和一个 analyzer；
- driver 只读取冻结 CSV/JSON 点表、顺序调用现有 runner、追加 JSONL、跳过已完成 tuple；
- analyzer 只汇总现有字段和生成 failure clusters；
- 不复制求解器逻辑到扫描脚本；
- 不为了“鲁棒”吞掉异常、自动放宽 Gate 或静默 fallback。

发现真正需要较大算法修复时可以做，但应直接修复算法本体。例如 connected-component
near-degenerate subspace normalization 是数值修复；再造一个新 Hybrid framework 不是。

---

## 11. 检查点与最终交付

无需等待每一小批次 review，但必须在以下节点提交并推送：

1. 扫描点表和简单 driver 完成；
2. Round A 完成或出现第一个重复根因并完成修复；
3. Round B/C 完成；
4. p6 stress 完成；
5. 最终全量回归完成。

每个 checkpoint 更新：

```text
docs/task036_forward_solver_bugfix_hardening/outcomes/
    robustness_scan_matrix.md
    hybrid_validity_map.md
    discovered_bugs_and_fixes.md
    test_summary.md
```

最终必须给出：

- 总配置数、Full3D/Hybrid PDE 数与失败/修复计数；
- S/P 各自的通过率和失败区域；
- 每类根因的 before/after；
- Hybrid 最小通过 M 的角度/几何分布；
- 哪些区域 Hybrid 有降维优势；
- 哪些区域功能正确但应使用 Full3D；
- 仍未解决的明确算法问题；
- full-repository pytest 最终结果；
- branch HEAD、upstream 和 clean status。

不得自行 merge master。

---

## 12. 给 Codex 的执行摘要

从当前 Task036 分支继续。先收口现有 full-suite traceback，再以本 V2 为权威执行完整
S/P 鲁棒性扫描。V1 的两个固定 P 点和八个 PDE 上限不再适用。

不要先开发新框架。先冻结 Round A/B/C/D 点表，用现有 Full3D 和 Hybrid runner 顺序运行。
每个配置先 Full3D、再 same-p Hybrid M120；失败后立即分类并修复数值根因，局部回归通过
后再恢复扫描。Hybrid rank 必须由实际 M 收敛判定，不得继续写死 false。

优先解决反复出现的通用问题：near-degenerate connected subspace、mode rank/selection、
interface coupling、energy ledger 和 P 偏振有效域。最终形成 Full3D robustness map 与 Hybrid
validity map，而不是只给两个样本的 pass/fail。

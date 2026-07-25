# Task035b 任务书：高阶 local-hp 压缩与 0.7 nm / 2 TiB 资源桥接

## 0. 任务身份

```text
task = Task035b
execution_branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
stacked_parent_branch = codex/20260721-task35-hcurl-goal-oriented-adaptivity
stacked_base_sha = 81c714b236e9c362df8783382f1d40a5cd888cd5
primary_wavelength = 13.5 nm
primary_geometry = Task034 fixed block grating
primary_incidence = 10 degree grazing
primary_polarization = S
primary_outputs = R00, R_total, T_total, A_closure, significant diffraction orders
ordinary_default_changed = false
master_merge = not_authorized
```

Task035b 是 Task035 的聚焦延续，不是独立于 Task035 的新实现。它直接依赖 Task035 分支中尚未合入 master 的：

- actual discrete DtN adjoint；
- R-total / multi-goal DWR；
- periodic tetra refinement；
- p5/p6 tetra Floquet 与高阶 orientation；
- adaptive/uniform records；
- watchdog、canonical mesh replay 和资源证据。

不得从 `master` 重新创建 Task035b，也不得把 Task035b 单独合并进 master。最终 selective merge 必须统一审查 Task035 与 Task035b 的依赖关系。

---

## 1. 背景与任务动机

### 1.1 Task035 已经回答的问题

Task035 已经证明：

```text
真实 Maxwell/DtN 正问题
→ 离散伴随
→ DWR 单元/面定位
→ 周期闭合局部 tetra refinement
→ 标签/Floquet/DtN 重建
→ 重新求解
```

可以在当前目标结构上工作；一轮高阶 DWR 相对同阶 uniform tetra 产生了明确正收益。

但 Task035 尚未证明：

- 当前 adaptive tetra 在 strict `R00/R_total` 同误差条件下优于所有规则高阶网格；
- 真正 cellwise local-p H(curl) 已实现；
- 高阶 DoF 减少能够同步降低 NNZ、factor fill 和峰值内存；
- 当前结果已经足以保证 0.7 nm / 2 TiB 可行。

### 1.2 新的 COMSOL p5/p6 证据

COMSOL p4/p5/p6、hexa/tetra 多条序列给出高阶收敛中心：

```text
R00 ≈ 0.000752895
R   ≈ 0.000762014
T   ≈ 0.6027075
A_closure ≈ 0.3965305
```

`p6/hexa/h10` 以 173,882 DoF 得到非常接近该中心的 R/T，说明当前规则结构的大部分场具有很强的高阶可逼近性。

同时 `p6/hexa/h10` MUMPS 物理内存仍约 22.75 GB，说明高阶 direct memory 受 row width、front size 和 fill 控制，不能只看 DoF。

### 1.3 0.7 nm / 2 TiB 反推

```text
s = 13.5 / 0.7 = 19.285714
s^3 = 7173.105
```

使用 Hybrid local-volume factor：

```text
0.30 nominal
0.35 conservative
0.40 irregular-geometry stress
```

若把 13.5 nm Full3D-equivalent DoF 压到：

```text
90000  -> about 194M / 226M / 258M local FE DoF at 0.7 nm
86941  -> about 187M / 218M / 249M
70000  -> about 151M / 176M / 201M
```

因此本任务冻结：

```text
minimum engineering target = <=90000 equivalent DoF
preferred robust target = 65000–75000 equivalent DoF
stretch target = <=60000 only with all independent accuracy gates
```

`p6/h10` 再压缩约 50% 到 86,941 DoF，与最低工程目标一致；它是现实但有挑战的 stretch target，不是保证值。

---

## 2. 核心研究问题

Task035b 必须回答：

1. COMSOL 的 global-p5/p6 粗网格高阶收敛趋势能否在 FEniCS Nédélec/Floquet 中复现？
2. `p6/h10` 内存较高，主要来自 active DoF、平均 row width、element block、factor fill，还是未凝聚 interior modes？
3. 能否从一个可信 global-p6 基线出发，删除低影响高阶模式而保持 `R00/R/T/Aclosure`？
4. 如何在 H(curl) 中实现真正可减少矩阵行列的 local-p，而不是在 max-p 矩阵中保留全部行列再把系数设零？
5. 哪些单元应降 p、保持 p、升 p，哪些单元应局部减小 h？
6. static condensation 能否显著降低高阶 global system rows、factor fill 和内存？
7. 当前规则几何能否在同误差下达到 `<=90k`，优选 `65k–75k` Full3D-equivalent DoF？
8. 在斜侧壁、圆角和局部缺陷等代表性不规则几何中，高阶 + local h/p 的优势还能保留多少？
9. selected hp 结果接入 Hybrid 后，实际 local-volume factor、interface overhead 和 0.7 nm DoF envelope 是多少？
10. 若 50% 压缩失败，瓶颈是 strict R00、variable-p conformity、geometry error、fill、还是局部奇异性？

---

## 3. 正式范围

### 3.1 主线

```text
13.5 nm
Task034 fixed geometry
10 degree grazing
S incidence
Full3D primary
p4/p5/p6 high-order study
hexa and tetra where qualified
R00 + R/T/Aclosure multi-goal audit
local h + local/global p
MPI8 formal heavy point
```

### 3.2 代表性不规则几何

只在规则几何主线出现可信正信号后，建立三个受控 geometry tiers：

```text
G0: current rectangular block grating
G1: sloped sidewall or smooth rounded corner
G2: one local notch/defect or sharp singular perturbation
```

要求几何参数和网格生成完全机器可读。G1 必须区分 geometry-approximation error 与 field-discretization error；G2 必须保留尖角奇异性，不得通过人为圆滑掩盖困难。

### 3.3 条件范围

- selected hp mesh 的一个 Full3D–Hybrid closure；
- selected p5/p6 high-order hexa capability；
- element-interior static condensation research path；
- regionwise-p 或 max-p hierarchical active-mode constraints；
- matrix-free operator memory proxy，但不实现最终生产预条件器。

### 3.4 非目标

本任务不做：

- 0.7 nm production PDE；
- scalable generic modal core 完整重写；
- 最终 matrix-free low-memory iterative solver；
- 神经网络预条件器；
- 完整反演系统；
- 完整 P 入射矩阵；
- 未经资格化的 arbitrary variable-p production default；
- 为达到 DoF 数字而放宽 R00/R/T、residual 或 geometry Gate。

---

## 4. 权威基线与误差口径

### 4.1 内部 FEniCS 基线

至少绑定：

```text
Task034 p4/h5 Full3D reference: about 339892 rows
Task034 p4/h7.5 resource control: 147844 DoF
Task035 h50 p4/p5 DWR theta0.7: 106355 p5 DoF
Task035 h37.5 p4/p5 one-cycle DWR: 129005 p5 DoF
Task035 uniform tetra p5: 116120 DoF
Task035 p5/p6 hp-budget records
```

### 4.2 外部 COMSOL convergence authority

COMSOL只作 cross-solver sanity/convergence authority，不替代 FEniCS true residual：

```text
R00 center ≈ 0.000752895
R center   ≈ 0.000762014
T center   ≈ 0.6027075
Aclosure   ≈ 0.3965305
```

正式容差不得由单个 p6/h10 点决定。先用 p4-p6、hexa/tetra 高阶结果的 spread 建立：

- cross-solver strict band；
- FEniCS same-code band；
- engineering inversion band。

### 4.3 目标量分层

每个正式候选同时报告：

```text
Level 1: R00 strict error
Level 2: R_total strict error
Level 3: normalized R/T/Aclosure vector error
Level 4: significant order powers and complex amplitudes
Level 5: selected field/interface errors
```

不得只以 `R+T+A≈1` 或 normalized vector 很小替代 strict R00。

### 4.4 reference 不是 continuum truth

COMSOL 和 FEniCS 的阶次、basis family、mesh h 定义不同。所有结果必须标记：

```text
measured
cross_solver_reference
discrete_reference
derived
predicted
controlled_negative
not_run
```

---

## 5. 执行模式与候选管理

Task035b 采用连续自主研究，不逐 Phase 等待审查。

同时最多维持：

```text
2 primary candidate lanes
+ 1 control/audit lane
```

建议初始候选：

```text
Lane A: global-p6 accurate baseline -> local p-coarsening
Lane B: p5 base + DWR local-h + selected local-p6
Control: global p5/p6 uniform or structured mesh
```

出现正信号时继续加深；连续两个成本/精度负信号后关闭该 lane，保存证据并切换。

提交和 push 不是等待点。只有需要人工凭据、环境/evidence身份异常、安全资源风险、所有合理路线耗尽、准备改变 ordinary default 或准备 merge 时停止。

---

## 6. Phase A：FEniCS global-p5/p6 资格化

### A1. capability inventory

检查：

- tetra p5/p6 Basix layout；
- hexa p5/p6 Nédélec layout；
- edge/face/interior mode counts；
- high-order orientation transforms；
- S3/D4 face permutations；
- Floquet trace constraints；
- DtN trace extraction；
- MPI ownership；
- direct solver compatibility。

现有 tetra p5/p6 capability 不自动证明 hexa p5/p6。hexa失败时保留明确 blocker，tetra继续主线。

### A2. actual topology rather than nominal h

对于每个 `h` 输入记录：

- actual axis plan；
- cells/edges/faces；
- cell diameter和quality分布；
- geometry hash；
- material/facet tag hash。

重复拓扑，例如不同名义 h 生成同一网格时，只运行一次。

### A3. global-p ladder

在相同实际网格上比较：

```text
p4
p5
p6
```

优先使用一个粗 structured hexa candidate 和一个 boundary-fitted tetra candidate。每个点输出：

- R00/R/T/Aclosure/orders；
- true residual；
- DoF/rows/NNZ；
- factor NNZ/fill；
- peak/time；
- p-to-p correction；
- COMSOL convergence-center error。

### A4. reference v2

冻结 `Task035b high-p reference v2`，禁止后续随意更换。若后续发现 reference污染，只能新增version并说明全部旧判定影响。

---

## 7. Phase B：高阶内存构成与静态凝聚

### B1. DoF inventory

对p4/p5/p6分列：

```text
vertex / edge / face / cell-interior DoF
periodic constrained DoF
external auxiliary DoF
total active rows
```

### B2. matrix/factor anatomy

记录：

- average/max NNZ per row；
- matrix bytes；
- symbolic/numeric factor NNZ；
- elimination/front proxy；
- factor peak；
- solve peak；
- memory per active DoF；
- memory per NNZ。

解释 p6 DoF下降但内存不同比例下降的根因。

### B3. static condensation lane

优先实现或原型验证 element-interior mode condensation：

```text
local interior elimination
→ global edge/face trace system
→ local back-substitution
```

最低Gate：

- condensed与uncondensed full true residual一致；
- R00/R/T/orders闭合；
- serial/MPI identity；
- active global rows、NNZ和factor fill实测下降；
- local factors可释放或分批处理；
- 不以dense all-element cache换取表面行数下降。

若production实现过大，可先做小型actual fixture和资源模型，但不得把预测写成正式内存收益。

---

## 8. Phase C：真实 local h/p 决策器

### C1. same-mesh correction data

在同一网格、同一geometry hash上获得：

```text
eta_p4p5(K)
eta_p5p6(K)
DWR_R00(K)
DWR_R(K)
DWR_T(K)
R5 correction energy(K)
material/interface/corner tags
```

不得用不同 h 网格的全局差值冒充局部 smoothness sensor。

### C2. classifier

至少比较：

1. correction decay：`eta_p5p6 / eta_p4p5`；
2. high-order hierarchical coefficient decay；
3. local projection defect；
4. DWR goal sensitivity；
5. interface/corner prior，只作辅助，不覆盖measured indicator。

输出：

```text
p_down_candidate
p_keep_candidate
p_up_candidate
h_refine_candidate
undetermined
```

### C3. candidate competition

对代表cell/patch实际比较：

```text
cost-normalized benefit of p-change
vs
cost-normalized benefit of h-refine
```

收益必须来自actual local/enriched solve或可审查projection，不得只凭阈值经验。

### C4. fault fixtures

必须覆盖：

- smooth analytic field -> p preference；
- material interface -> h or moderate-p preference；
- sharp corner -> h preference；
- under-resolved high-frequency smooth field -> resolution Gate，不得错误判为p-converged；
- periodic mate pair -> identical hp decision；
- MPI partition -> canonical decision identity。

---

## 9. Phase D：真正可减少矩阵的 local-p H(curl)

### D1. 首选实现：hierarchical max-p active-mode space

可使用max-p basis作为定义框架，但正式矩阵只包含active modes。不得保留全部p6 rows再通过大罚项或零系数伪装降p。

必须明确：

- shared edge trace order；
- shared face trace order；
- cell-interior order；
- adjacent unequal-p conformity；
- periodic mate order同步；
- orientation/permutation；
- MPI ownership和ghost；
- active global numbering；
- field transfer和postprocess。

### D2. conformity policy

优先采用可证明的entity-based policy，例如共享entity只保留两侧都支持的trace modes，高阶cell保留额外interior modes；具体实现必须由Basix/DOLFINx实际basis验证，不得仅按模式索引猜测。

### D3. fallback

若 arbitrary cellwise p 暂时受阻，按顺序尝试：

1. regionwise p blocks with conforming interfaces；
2. p仅改变cell interior modes + fixed trace order；
3. static-condensed high-order interior enrichment；
4. global-p + local-h，明确标记为quasi-hp。

不得用非共形拼接制造local-p成功。

### D4. minimum qualification

- two-cell unequal-p analytic fixture；
- periodic unequal-p mate；
- material interface；
- actual target small mesh；
- serial/MPI2，必要时MPI8；
- full true residual；
- exact active-row count；
- no inactive rows retained in matrix；
- source-clean tests。

---

## 10. Phase E：规则几何 50% 压缩主线

### E1. 起点

起点不是低阶超粗网格，而是A阶段冻结的可信global-p5/p6 baseline。

### E2. 路线

优先执行：

```text
accurate global p6 baseline
→ DWR/R5/local coefficient audit
→ low-impact regions p6->p5/p4
→ singular/interface regions local h
→ selected smooth high-impact regions keep p6
→ optional static condensation
→ re-solve and audit
```

并行对照：

```text
global p5
global p6
uniform h refinement
Task035 one-cycle DWR tetra
```

### E3. DoF目标

正式结果同时按两种分母报告：

```text
A. relative to qualified FEniCS global-p6 baseline
B. relative to Task034 p4/h5 339892 reference
```

目标：

```text
minimum:
    >=2x reduction vs global-p6 baseline, or <=90000 Full3D-equivalent DoF

preferred:
    65000–75000 DoF

stretch:
    <=60000 DoF
```

COMSOL p6/h10的173,882 DoF仅作规划参考；FEniCS basis不同，不能直接以绝对数替代FEniCS active rows。

### E4. 精度Gate

候选必须：

- full true residual `<=1e-9`；
- `R00` strict band pass；
- `R_total` strict band pass；
- `T_total` pass；
- `A_closure` pass；
- normalized multi-goal vector pass；
- significant orders和complex amplitudes不隐藏恶化；
- selected fields/interfaces pass；
- geometry、periodic、tag、orientation pass；
- no threshold relaxation。

### E5. 成本Gate

必须实测：

- active DoF/rows；
- NNZ和row width；
- factor NNZ/fill或iterative operator inventory；
- peak memory；
- assembly/factor/solve/adjoint/estimator time；
- load imbalance；
- transfer/condensation cost。

成功不能只依据DoF。

---

## 11. Phase F：不规则几何转移

### F1. G1 smooth irregular geometry

选择斜侧壁或圆角。比较：

- linear geometry approximation；
- high-order/curved geometry where supported；
- geometry error vs field error；
- global-p5/p6 convergence；
- selected local hp。

### F2. G2 singular irregular geometry

加入一个明确局部notch、sharp corner或缺陷，验证classifier是否：

- 在奇异区选择h；
- 在远场平滑区保留高p；
- 不把整个域退化成低阶细网格。

### F3. 压缩标准

不规则几何按自己的qualified global-p baseline比较：

```text
30% same-error DoF reduction = useful signal
50% = target
>=60% = strong result
```

绝对 `<=90k` 只作为当前几何和资源映射指标，不强迫不同几何共享相同DoF。

---

## 12. Phase G：Hybrid与0.7 nm资源桥接

### G1. selected mesh only

只把规则几何最好的1–2个hp候选接入Hybrid，不对所有失败候选运行M funnel。

### G2. interface policy

优先保持Hybrid matching interface trace topology和trace-p固定，将local hp放在接口外部。若必须改变接口p/h：

- 同步bottom/top；
- 重建2D cross-section/QEP；
- 重新做mode classification/tracking；
- 重新做M/DtN funnel；
- 不复用不兼容缓存。

### G3. closure

完成一个same-degree Full3D–Hybrid closure，记录：

- local FE active DoF；
- total rows；
- interface trace DoF；
- QEP DoF；
- M；
- R00/R/T/Aclosure/orders；
- field/interface error；
- memory/time。

### G4. 0.7 nm projection v3

使用实际测得：

```text
selected N_equiv,13.5
selected Hybrid local fraction
actual trace/interface ratio
2/3 kB per DoF design bands
M lower-bound and risk ranges
```

生成0.7 nm / 2 TiB envelope。必须分离：

- local FE；
- mesh/coefficients；
- Krylov；
- preconditioner；
- modal/QEP/interface；
- safety margin。

不得把cumulative envelope写成simultaneous peak，也不得宣称0.7 nm已可解。

---

## 13. 并行实验与资源调度

允许同时生成多个网格和运行多个低成本候选，但按吞吐量而不是单模型内存宣传收益。

### 13.1 可并行

- mesh generation/audit；
- topology/DoF/NNZ prediction；
- pure-Python classifier；
- small serial/MPI2 fixtures；
- 两个资源互不冲突的低成本候选。

### 13.2 重型任务

- direct p5/p6、formal MPI8、large adjoint：默认one-heavy-case-at-a-time；
- 只有实测CPU、带宽和内存余量证明吞吐量增加时，才允许两个formal jobs并发；
- 总预测峰值加安全余量不得超过可用内存60%；
- 不超额使用MPI ranks或BLAS/OpenMP线程；
- 每个job独立run directory、stdout、timeline、temporary/OOC目录和process group。

### 13.3 Git

一个智能体负责代码；并行计算进程只读clean committed SHA。不得让多个智能体在同一worktree同时修改数值核心。

---

## 14. 测试策略

```text
small edit -> targeted unit test
one hp component -> serial + MPI2
one actual lane -> focused Task035b suite + anchor
numerical core change -> affected Task034/035 regression
major milestone/final delivery -> full repository pytest once
```

必须覆盖：

1. p5/p6 basis/orientation；
2. unequal-p trace conformity；
3. periodic unequal-p mate；
4. active-mode numbering；
5. no inactive rows in matrix；
6. static condensation equivalence；
7. h/p classifier fixtures；
8. DWR R00/R/T gradients；
9. geometry error separation；
10. mesh/tag/Floquet/DtN rebuild；
11. full true residual；
12. MPI identity；
13. failure preservation；
14. resource ledger；
15. clean-checkout records；
16. ordinary default unchanged。

最终必须运行：

- Task035b focused suite；
- relevant Task034/035 regression；
- qualified complex ABI full pytest；
- Ruff；
- compileall；
- JSON/schema checks；
- `git diff --check`；
- complete `git status`。

---

## 15. 交付物

保持文件数量可控，集中在以下权威输出：

```text
docs/task035b_high_order_local_hp_resource_envelope/outcomes/reference_and_resource_target.md
docs/task035b_high_order_local_hp_resource_envelope/outcomes/high_p_memory_anatomy.md
docs/task035b_high_order_local_hp_resource_envelope/outcomes/local_hp_capability.md
docs/task035b_high_order_local_hp_resource_envelope/outcomes/regular_geometry_compression.md
docs/task035b_high_order_local_hp_resource_envelope/outcomes/irregular_geometry_transfer.md
docs/task035b_high_order_local_hp_resource_envelope/outcomes/resource_projection_0p7nm.md
docs/task035b_high_order_local_hp_resource_envelope/outcomes/all_candidates.csv
docs/task035b_high_order_local_hp_resource_envelope/outcomes/all_candidates.json
docs/task035b_high_order_local_hp_resource_envelope/outcomes/negative_results.md
docs/task035b_high_order_local_hp_resource_envelope/outcomes/test_summary.md
docs/task035b_high_order_local_hp_resource_envelope/outcomes/summary.md
docs/task035b_high_order_local_hp_resource_envelope/response_v1.md
```

Case benchmark建议：

```text
benchmarks/cases/095_high_order_local_hp_resource_envelope/
```

尚未完成或被Gate阻止的交付物必须明确写 `not_run`、`stopped_by_gate` 或 `controlled_negative`，不得空缺冒充完成。

---

## 16. 成功判定

### 16.1 科学成功

- FEniCS p5/p6高阶收敛趋势得到资格化；
- actual local h/p classifier在真实mesh上工作；
- 至少一个unequal-p或regionwise-p H(curl)实际PDE通过；
- strict R00/R/T/Aclosure和true residual通过；
- hp候选优于同成本global-p或uniform control。

### 16.2 工程成功

当前规则几何满足：

```text
N_equiv,13.5 <= 90000
```

并且：

- strict R00/R/T不劣于冻结控制；
- normalized vector pass；
- DoF、NNZ、factor fill、memory/time均有完整测量；
- 不靠放宽阈值；
- selected Hybrid closure pass；
- 0.7 nm projection进入约150M–250M local FE区间。

### 16.3 强成功

```text
65000–75000 equivalent DoF
```

且在G1或G2不规则几何上仍显示可迁移正收益。

### 16.4 允许的最终状态

```text
PASS
PASS_WITH_QUALIFICATIONS
PARTIAL_WITH_CONTROLLED_NEGATIVES
ARCHITECTURE_BLOCKER_WITH_EVIDENCE
FAIL
```

若variable-p受阻，但global-p6 + static condensation + one local-h形成更优工程路线，也可判`PASS_WITH_QUALIFICATIONS`，但不得称真正cellwise hp完成。

---

## 17. 真正停止条件

只有以下情况停止整个Task035b：

- 需要用户输入sudo/SSH/凭据；
- stacked base、source、ABI或evidence身份异常；
- accepted Task035 numerical core/evidence被污染；
- MPI、periodic topology、orientation、true residual或official physics系统性失败；
- 资源状态对工作站有安全风险；
- 所有合理global-p/local-p/local-h/condensation路线均形成可审计负结果；
- 准备改变ordinary default；
- 准备final selective merge。

单个候选、单个高阶cell type、一个heavy case、一个classifier阈值或一项局部测试失败，不得自动停止整个任务。

---

## 18. Codex启动指令摘要

Codex进入本分支后必须先：

```text
1. 确认 branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
2. 确认 stacked base 包含 Review V6 SHA 81c714b236e9c362df8783382f1d40a5cd888cd5
3. 阅读根 AGENTS、Task035 AGENTS、Task035 Review V6、本 README 和本 task.md
4. 只读绑定 Task034/035 records，不重复已接受heavy runs
5. 建立 high-p reference v2 和 resource target records
6. 先完成FEniCS p5/p6 capability与内存构成，再进入真实local-p
```

Task035b以解决“高阶基线再压缩约50%，并为0.7 nm / 2 TiB提供可信local-FE规模”为目标持续研究，但不得预设一定成功，也不得把预测资源写成solver pass。

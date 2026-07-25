# Task035b Review V1：失败衍射通道定向恢复与 Hybrid 续研授权

## 1. 审阅身份与结论

```text
review_status = TASK035B_CHANNEL_RECOVERY_CONTINUATION_AUTHORIZED
execution_branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
reviewed_branch_head = 704c1ba0f1659dde10c1014eab02be4540be6ca6
review_scope = Task035b Response V1 + Case095 records + fixed-geometry high-p/local-hp results
geometry_scope = Task034 fixed rectangular block grating only
engineering_high_order_reduction = accepted
assembly_time_static_condensation = accepted_research_path
fixed_p5trace_p6interior_h15 = selected_recovery_seed
complete_same_error_candidate = not_yet_available
scalar_R00_R_T_reference = high_confidence
significant_channel_reference = provisional_v0_not_yet_convergence_frozen
channel_recovery_batch = authorized
hybrid_after_channel_recovery = conditionally_automatic
additional_review_between_recovery_and_hybrid = not_required
ordinary_default_changed = false
master_merge = not_authorized
irregular_geometry = out_of_scope_by_user
```

Task035b 已经取得两个不同层面的结论：

1. **工程结论为明确正结果。**
   装配时 cell-interior static condensation、Floquet slave 物理消元、tensor 去重、exact sparse preallocation、factor 生命周期释放和 `malloc_trim` 均真实降低了 active rows、NNZ、factor NNZ、峰值内存与时间；这些结果应保留并进入最终选择性合并审查。

2. **完整 same-error 科学结论仍为受控负结果。**
   `global p6/h15` 和 `fixed p5-trace/p6-interior h15` 都通过了 full true residual、`R00/R/T/A_closure`、normalized vector、选定 volume/interface field 和资源 Gate，但都未通过全部显著衍射通道功率及复振幅 Gate。因此它们不能直接称为最终压缩成功，也不能立即接入 Hybrid。

本 Review 不关闭 Task035b。下一轮直接在同一分支增加一个聚焦的：

```text
失败衍射通道定向恢复
+
显著通道收敛参考冻结
+
通过后自动接入 Hybrid
```

连续研究批次。

---

## 2. 已接受的 Task035b 结果

### 2.1 高阶同网格基线

FEniCS h10 structured hexa 的实际网格为：

```text
axis plan = (6, 3, 14)
cells = 252
```

同一实际网格上的结果为：

| degree | FE DoF | active rows | matrix NNZ | factor NNZ | R00 | R | T | Aclosure |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| p4 | 53,084 | 21,824 | 8,184,464 | 40,151,936 | 0.001872161 | 0.001882317 | 0.596619520 | 0.401498163 |
| p5 | 101,815 | 35,000 | 20,140,928 | 101,062,900 | 0.000785714 | 0.000794886 | 0.602483954 | 0.396721160 |
| p6 | 173,802 | 51,272 | 41,989,040 | 202,441,352 | 0.000753761 | 0.000762881 | 0.602701634 | 0.396535485 |

p6/h10 是当前 FEniCS **best-available same-code high-p discrete reference**，不是 continuum truth。

COMSOL p4–p6、hexa/tetra 的独立高阶趋势中心为：

```text
R00 ≈ 0.000752895
R   ≈ 0.000762014
T   ≈ 0.6027075
Aclosure = 1 - R - T ≈ 0.3965305
```

FEniCS p6/h10 与该中心高度一致，因此 `R00/R/T` 的标量收敛趋势可信。

### 2.2 高阶内存优化

历史 full p6/h10 路径：

```text
augmented rows = 173,882
matrix NNZ = 210,353,120
factor NNZ = 386,625,292
peak = 35.024 GiB
```

最终 opt-in assembly-time condensation 路径：

```text
active rows = 51,272
matrix NNZ = 41,989,040
peak = 15.964 GiB
```

恢复后的 full explicit true residual 和 official observables 与 global p6 等价。

这证明：

> 高阶 DoF 降低后内存没有同比降低，主要不是“高阶天然无效”，而是旧路径仍分配完整矩阵、inactive rows、重复 tensor，并让 factor 与后处理生命周期重叠。真正消除这些对象后，内存与时间可以明显下降。

### 2.3 当前最强资源候选

| candidate | Full3D-equivalent DoF | active rows | matrix/factor NNZ | peak | scalar/vector/field | significant power/amplitude |
|---|---:|---:|---:|---:|---|---|
| global p6/h15 | 84,492 | 24,704 | 19,207,136 / 59,616,320 | 12.000 GiB pair | pass | 6/12；8/12 |
| fixed p5-trace/p6-interior h15 | 74,890 | 16,880 | 9,195,812 / 27,916,600 | 5.803 GiB | pass | 6/12；7/12 |

`fixed p5-trace/p6-interior h15` 已落入 65k–75k 优选 DoF 区间，并具有最好的 rows、NNZ、factor 和 peak 结果，因此本 Review 将其选为下一轮的**恢复起点**。

但 `global p6/h15` 也在相同六个功率通道上失败，这表明：

> 共同的主要误差来自 h15 网格对弱衍射通道/相位的解析能力，而不是仅仅来自 p5 trace。
> p5 trace 相对 global p6/h15 还额外造成了一个复振幅失败，说明 trace 阶次仍是次级问题。

---

## 3. `fixed p5-trace/p6-interior h15` 的正式标量结果

### 3.1 模型身份

```text
geometry = Task034 fixed rectangular block grating
wavelength = 13.5 nm
incidence = 10 degree grazing / theta=80 degree from +z convention
polarization = S
mesh = structured hexa h15
actual axis plan = (6, 2, 10)
cells = 120
trace degree = 5
cell-interior degree = 6
Full3D-equivalent DoF = 74,890
active matrix rows = 16,880
MPI = 8
peak = 5.80286 GiB
full relative residual = 8.83457e-12
```

### 3.2 标量输出

| observable | candidate | provisional FEniCS p6/h10 reference | absolute difference | current Gate |
|---|---:|---:|---:|---|
| R00 | 0.000755888313624 | 0.000753761220068 | 2.12709e-6 | pass |
| R total | 0.000765024318140 | 0.000762881475133 | 2.14284e-6 | pass |
| T total | 0.602685146795610 | 0.602701633986135 | 1.64872e-5 | pass |
| A closure | 0.396549828886249 | 0.396535484538732 | 1.43443e-5 | pass |

normalized `R/T/Aclosure` L2 为：

```text
0.1272313309619017
```

相对冻结半径：

```text
sqrt(3) = 1.7320508075688772
```

因此标量和整体向量 Gate 均通过。

---

## 4. 显著衍射通道的选择

当前记录共有 80 个：

```text
side × m × n × polarization
```

通道。Task035b 采用：

```text
significant power floor = 1e-8
```

在 FEniCS p6/h10 authority 上选择出 12 个显著通道。

当前物理结构在 y 方向不变、入射 `k_y=0`，因此这 12 个通道全部为：

```text
n = 0
S-polarized
```

并由六个反射通道与六个透射通道构成：

```text
m = 0, -1, -2, -4, -5, -7
```

这 12 个通道已覆盖：

```text
R total 中除约 4.8e-9 外的全部功率
T total 中除约 8.9e-9 外的全部功率
```

因此它们适合作为当前固定几何的数值审计集合。

---

## 5. 显著通道功率：candidate 与 provisional reference v0

### 5.1 反射通道

| channel | candidate power | p6/h10 provisional reference | candidate relative difference | power Gate |
|---|---:|---:|---:|---|
| R(0,0) | 7.558883136239e-4 | 7.537612200685e-4 | +0.2822% | pass |
| R(-1,0) | 6.683590260997e-6 | 6.669309654169e-6 | +0.2141% | pass |
| R(-2,0) | 1.482618015326e-6 | 1.477690851330e-6 | +0.3334% | **fail** |
| R(-4,0) | 2.601812494996e-7 | 2.675239609866e-7 | -2.7447% | **fail** |
| R(-5,0) | 7.781273638942e-8 | 7.457300538323e-8 | +4.3444% | **fail** |
| R(-7,0) | 6.270075820289e-7 | 6.263542420285e-7 | +0.1043% | pass |

### 5.2 透射通道

| channel | candidate power | p6/h10 provisional reference | candidate relative difference | power Gate |
|---|---:|---:|---:|---|
| T(0,0) | 0.602657398112396 | 0.602673872346986 | -0.00273% | pass |
| T(-1,0) | 2.180407898565e-5 | 2.178167398456e-5 | +0.1029% | pass |
| T(-2,0) | 2.944639118765e-6 | 2.959841395079e-6 | -0.5136% | **fail** |
| T(-4,0) | 4.126661590130e-7 | 4.372888971898e-7 | -5.6308% | **fail** |
| T(-5,0) | 2.158752935655e-7 | 2.119208257498e-7 | +1.8660% | **fail** |
| T(-7,0) | 2.362208942307e-6 | 2.362010449446e-6 | +0.00840% | pass |

失败功率通道恰好是：

```text
R(-2,0), R(-4,0), R(-5,0)
T(-2,0), T(-4,0), T(-5,0)
```

---

## 6. 显著通道复振幅：candidate 与 provisional reference v0

复数按：

```text
real + imag * i
```

表示。

### 6.1 反射复振幅

| channel | candidate amplitude | p6/h10 provisional reference | amplitude Gate |
|---|---|---|---|
| r(0,0) | -2.526794899732e-2 + 1.083600789465e-2 i | -2.525230435362e-2 + 1.077415170214e-2 i | pass |
| r(-1,0) | -1.032163293531e-3 + 7.708690591278e-4 i | -1.032707715912e-3 + 7.678339217512e-4 i | pass |
| r(-2,0) | 4.946453230575e-4 - 2.068403464968e-4 i | 4.942316170696e-4 - 2.055157697568e-4 i | pass |
| r(-4,0) | 2.060543617580e-4 - 5.410824648266e-5 i | 2.102233361316e-4 - 4.973043613499e-5 i | **fail** |
| r(-5,0) | -1.001389753437e-4 - 6.698293100304e-5 i | -9.817807919640e-5 - 6.535503246511e-5 i | **fail** |
| r(-7,0) | -5.054590084015e-4 - 2.636301006796e-5 i | -5.052091111720e-4 - 2.608886163645e-5 i | pass |

### 6.2 透射复振幅

| channel | candidate amplitude | p6/h10 provisional reference | amplitude Gate |
|---|---|---|---|
| t(0,0) | 6.316854641481e-1 + 4.725932466778e-1 i | 6.313787033482e-1 + 4.730209810384e-1 i | pass |
| t(-1,0) | 2.090511240453e-3 - 1.027122588581e-3 i | 2.091013385263e-3 - 1.023379862806e-3 i | pass |
| t(-2,0) | -6.919800213370e-4 + 3.046224738404e-4 i | -6.970027805563e-4 + 2.979420807086e-4 i | **fail** |
| t(-4,0) | -2.499013080659e-4 + 9.801788006753e-5 i | -2.621322075218e-4 + 8.743226904798e-5 i | **fail** |
| t(-5,0) | 1.395982419880e-4 + 1.443131251313e-4 i | 1.340326965913e-4 + 1.470057843186e-4 i | **fail** |
| t(-7,0) | 9.811761813939e-4 - 8.820420410006e-5 i | 9.812210508833e-4 - 8.723749953097e-5 i | pass |

失败复振幅通道为：

```text
r(-4,0), r(-5,0)
t(-2,0), t(-4,0), t(-5,0)
```

其中 `R(-2,0)` 只有功率 Gate 失败，复振幅仍在当前容差内。

---

## 7. 当前“收敛参考”的准确分层

### 7.1 已有高置信标量参考

基于：

- COMSOL p4/p5/p6；
- COMSOL hexa/tetra；
- FEniCS same-mesh p4/p5/p6；
- FEniCS global p6/h10；
- FEniCS global p6/h15；

当前可以采用以下标量工作参考：

| observable | high-order convergence center | authority |
|---|---:|---|
| R00 | 0.000752895 | COMSOL multi-p/multi-mesh center + FEniCS p6 audit |
| R total | 0.000762014 | COMSOL multi-p/multi-mesh center + FEniCS p6 audit |
| T total | 0.6027075 | COMSOL multi-p/multi-mesh center + FEniCS p6 audit |
| A closure | 0.3965305 | `1-R-T`；避免 COMSOL `A_total` 定义差异 |

### 7.2 显著通道尚不能称为“收敛值”

本 Review 将上表中的 p6/h10 通道值命名为：

```text
significant_channel_reference_v0
status = provisional_same_code_high_p_reference
```

而不是：

```text
converged_channel_truth
```

原因是：

1. 过去大量 Task034 记录主要冻结了 `R/T/A`、场和 Full3D–Hybrid closure，未形成所有12个通道逐项的独立 h/p 收敛表；
2. global p6/h15 的 `R00/R/T/Aclosure` 与 p6/h10 几乎完全一致，但弱衍射通道仍有 6/12 power 和 4/12 amplitude 失败；
3. 这证明总量收敛并不自动保证每一个弱通道已经收敛；
4. 弱通道的相对误差会被很小的分母放大，必须同时冻结绝对误差、复振幅误差和实验意义。

因此，下一轮必须先建立：

```text
significant_channel_reference_v1
```

然后才能最终判定恢复候选。

---

## 8. 对未来反演最有价值的观测量分层

在真实仪器、噪声和待反演参数尚未冻结前，不得删除当前12通道数值审计。但可以按工程价值分层。

### Tier A：核心观测量

```text
complex r(0,0) 或 R00
R total
complex t(0,0) 或 T00
T total
Aclosure
```

理由：

- `R00` 约占总反射的 98.8%，通常是镜面反射测量的核心；
- 复振幅比单纯功率多保留相位信息；
- `R/T/Aclosure` 用于全局能量和材料响应审计。

### Tier B：主要非零级信息

```text
R/T (-1,0)
R/T (-2,0)
R/T (-7,0)
```

这些是当前最大的非零级通道，可能帮助区分：

- 线宽；
- 高度；
- 周期；
- 侧壁或局部几何变化；
- 材料光学常数。

### Tier C：弱但可能高灵敏度的通道

```text
R/T (-4,0)
R/T (-5,0)
```

它们功率较小，但不能因此认定反演价值低。弱通道可能对某些几何参数具有更大的相对导数。只有未来获得：

```text
实验噪声
+
待反演参数
+
observable Jacobian / Fisher information
```

后，才能决定是否从生产观测集合中移除。

本 Task 当前不得用“未来可能测不到”作为放宽数值 Gate 的理由。

---

# 续研任务：失败衍射通道定向恢复

## 9. 任务目标

在当前同一 Task035b 分支上，以：

```text
fixed p5-trace/p6-interior h15
74,890 Full3D-equivalent DoF
16,880 active rows
5.803 GiB
```

为首选起点，在不超过：

```text
90,000 Full3D-equivalent DoF
```

的条件下，恢复全部正式显著通道，同时保持：

```text
R00
R total
T total
Aclosure
normalized vector
selected volume/interface fields
full true residual
```

全部通过。

若恢复成功，Codex无需等待新的中间 Review，直接继续：

```text
selected Full3D candidate
→ Hybrid same-degree closure
→ M/DtN funnel
→ 0.7 nm resource model v3
```

然后提交下一份 response 集中审阅。

---

## 10. CR0：冻结显著通道 reference v1

### 10.1 先聚合已有结果

不得无理由重跑已有 heavy PDE。先机械聚合：

```text
FEniCS p5/h10
FEniCS p6/h10
FEniCS global p6/h15
FEniCS fixed p5-trace/p6-interior h15
Task034/035 可恢复的高阶 order records
COMSOL R00/R/T convergence center
```

建立每个通道一行的：

```text
power
complex amplitude real/imag
magnitude
unwrapped phase
p-difference
h-difference
absolute spread
relative spread
source SHA
mesh hash
qualification
```

### 10.2 最少的新增判别点

只有已有证据不足时，才运行最少、最有区分度的点。

优先顺序：

1. **p-direction判别**
   在 h10 同一实际网格上，若 p7 Nédélec/Floquet/condensation capability 与资源 preflight 通过，运行一个 p7 点；否则记录 `p7_not_run_by_capability_or_resource_gate`。

2. **h-direction判别**
   在 p6 下运行一个与 h10 真正不同、且比 h10更细的实际 structured topology，或运行经过预检的方向性 topology。不得只换名义 h 却生成同一个网格。

3. **方向性判别优先于盲目 h 扫描**
   h15 实际 plan 为 `(6,2,10)`，h10为 `(6,3,14)`。由于全部显著通道为 `n=0`，优先比较：
   - 只增加 z 分段；
   - 只增加 y 分段的 control；
   - 必要时 x 分段。

   该顺序是待验证假设，不得预写“z一定是根因”。

### 10.3 reference v1 的通过条件

对每个12个通道分别要求：

- p方向和h方向都出现稳定趋势；
- power、complex amplitude real/imag、magnitude、phase均有明确 spread；
- full true residual和网格身份通过；
- 不因弱通道分母小而只使用相对误差；
- 给出 numerical band 和可选 engineering/inversion band；
- 不能收敛的通道明确标记：
  ```text
  reference_not_converged
  ```
  而不是伪造单值。

产出：

```text
benchmarks/cases/095.../records/significant_channel_reference_v1.json
docs/task035b.../outcomes/significant_channel_convergence.md
```

---

## 11. CR1：为失败通道建立独立 goal/adjoint

至少覆盖：

### 功率目标

```text
R(-2,0)
R(-4,0)
R(-5,0)
T(-2,0)
T(-4,0)
T(-5,0)
```

### 复振幅目标

```text
Re/Im r(-4,0)
Re/Im r(-5,0)
Re/Im t(-2,0)
Re/Im t(-4,0)
Re/Im t(-5,0)
```

要求：

- 每个目标使用实际离散 DtN/port functional；
- 独立 Hermitian adjoint；
- direct-adjoint directional derivative 检查；
- complex amplitude不能只通过功率导数替代；
- 每个目标输出 cell、face、edge/trace entity indicator；
- MPI canonical ID 与周期 transitive aggregation；
- 归一化使用 reference v1 band，而不是临时调阈值。

允许将多个失败通道组合成 normalized multi-goal，但必须保留每个通道的独立审计。

---

## 12. CR2：根因分离

下一轮必须明确区分：

### 12.1 共同 h15 误差

`global p6/h15` 与 `fixed p5-trace/p6-interior h15` 共同失败的六个 power通道：

```text
R/T (-2,0), (-4,0), (-5,0)
```

优先视为：

```text
mesh/phase/port-resolution candidate cause
```

而不是直接归因于 p5 trace。

### 12.2 trace-specific误差

fixed trace相对global p6/h15额外失败的复振幅，重点检查：

```text
t(-2,0)
```

以及其他通道的trace-mode敏感度。

### 12.3 DtN/port误差

在改变大量体网格前，必须检查：

- auto-propagating order set；
- evanescent buffer；
- top/bottom port plane；
- DtN trace quadrature；
- port amplitude normalization；
- channel phase convention。

若增加DtN order或evanescent buffer即可恢复通道，不应错误地用体网格自由度解决边界截断误差。

---

## 13. 恢复候选路线

同时最多维持：

```text
2 primary lanes
+
1 control lane
```

### Lane A：方向性 structured-h 恢复

从 h15 高阶基线出发，只加入最少的方向性分段。

优先：

```text
z-direction phase recovery
```

同时运行一个：

```text
y-only control
```

以验证方向判断。

要求：

- 保持全共形 structured hexa；
- 周期面拓扑精确；
- 材料面精确；
- 不引入 hanging nodes；
- 每次预先计算DoF/rows/NNZ；
- DoF不得超过90k，除非仅为一次reference判别且Review明示不作为候选。

### Lane B：失败通道敏感 trace mode 恢复

从：

```text
p5 trace + p6 cell interior
```

开始，只在DWR判定为高影响的：

```text
edges
faces
periodic mate entities
port-adjacent trace entities
```

恢复必要的p6 trace modes。

硬规则：

- 共享entity与周期mate同步；
- exact sequence；
- 不保留inactive rows；
- 物理减少/增加实际matrix rows；
- active global numbering可审计；
- 不允许完整p6 trace矩阵后把系数设零；
- 记录每个新增mode对失败通道的边际收益。

### Lane C：最小组合

只有Lane A或B各自出现正信号后，才尝试：

```text
minimal directional h
+
selective p6 trace restoration
```

不得进行大规模组合盲扫。

---

## 14. 候选成功Gate

恢复候选必须同时通过：

### 数值与物理

- full explicit true residual `<= 1e-9`；
- strict `R00`；
- strict `R_total`；
- `T_total`；
- `Aclosure`；
- normalized multi-goal vector；
- 12/12 significant powers；
- 12/12 significant complex amplitudes；
- selected volume field；
- selected interface field；
- energy closure；
- geometry/tag/orientation/Floquet identity；
- exact-sequence audit。

### 资源

- Full3D-equivalent DoF `<=90,000`；
- 优选继续保持 `65k–75k`；
- active rows；
- matrix NNZ；
- average/max row width；
- factor NNZ/fill；
- peak RSS；
- assembly/setup/solve/adjoint/estimator time；
- no swap；
- one-heavy-case-at-a-time。

### 证据

- clean SHA；
- MPI8；
- deterministic mesh/entity/mode hash；
- reference v1 binding；
- failed attempts保留；
- no threshold relaxation。

---

## 15. 通过后自动继续 Hybrid

当且仅当一个候选通过第14节全部Gate时，Codex无需等待新Review，直接执行：

### 15.1 Full3D–Hybrid same-degree closure

- 只使用最佳1个候选，最多2个；
- 保持bottom/top matching interface trace topology和trace-p；
- 若候选改变接口，必须同步重建2D cross-section/QEP；
- 不复用不兼容cache。

### 15.2 M funnel

```text
M80
M120
M160
M240 only if M120->M160 fails solely on modal convergence
```

### 15.3 external DtN funnel

- propagating set；
- evanescent buffer；
- order count；
- channel-wise power/amplitude convergence。

### 15.4 Hybrid Gate

同时比较：

```text
R00
R total
T total
Aclosure
12 significant powers
12 significant complex amplitudes
selected fields/interfaces
full residual
interface continuity
local FE rows
total rows
QEP DoF
M
memory/time
```

### 15.5 0.7 nm资源模型v3

只有Full3D–Hybrid closure和M/DtN funnel通过后，才允许更新：

```text
0.7 nm / 2 TiB resource model v3
```

必须区分：

```text
measured
derived
predicted
unknown
```

不得把component sum写成simultaneous peak，也不得宣称0.7 nm production feasible，除非后续真正的scalable modal core和low-storage iterative也有实测证据。

---

## 16. 还值得并行研究的方向

### 16.1 channel-aware trace basis压缩

对p6 trace modes建立：

- failure-channel sensitivity matrix；
- singular-value/QR ranking；
- DWR-weighted mode importance；
- periodic entity共同保留策略。

目标不是按mode index机械保留，而是保留对失败通道最重要的trace子空间。

### 16.2 port/DtN phase authority

当前弱通道对phase非常敏感。应单独验证：

- complex-amplitude convention；
- top/bottom outgoing sign；
- reference-plane shift；
- phase normalization；
- DtN order buffer。

### 16.3 condensed trace iterative path

当前 condensed h15 candidate只有16,880 active rows，适合作为后续低存储迭代法的早期实验对象：

- GMRES/FGMRES；
- trace-space Schwarz；
- auxiliary-space或p-multigrid；
- low restart；
- factor-free memory inventory。

该方向可以做轻量prototype，但不得干扰本轮channel recovery主线，也不替代Hybrid closure。

### 16.4 inversion-aware observable selection

未来真实反演参数、实验角度、噪声和可测通道冻结后，应计算：

```text
Jacobian
Fisher information
parameter correlation
noise-normalized sensitivity
```

届时可以把数值Gate分成：

- solver reference set；
- inversion production set；
- diagnostic set。

在此之前，当前12通道仍全部保留。

---

## 17. 执行节奏

Task035b继续采用连续自主研究模式。

```text
reference v1
→ channel adjoints
→ root-cause audit
→ targeted recovery
→ if pass: Hybrid + M/DtN
→ resource model v3
```

上述阶段之间不需要逐段等待Review。

以下问题不应停止整个Task：

- 单个channel goal失败；
- 某个方向性topology为负；
- 某个trace-mode subset为负；
- metadata、schema、lint或局部test问题；
- p7 capability不可用。

应保存证据后切换lane。

只有以下情况停止并请求用户：

- 需要密码/凭据；
- ABI、source、reference或evidence身份异常；
- 资源安全风险；
- 所有合理channel recovery路线均耗尽；
- 准备修改ordinary default；
- 准备merge master；
- Hybrid后发现需要独立重构modal core才能继续。

---

## 18. 下一份Response要求

新增：

```text
docs/task035b_high_order_local_hp_resource_envelope/response_v2.md
```

至少报告：

1. significant channel reference v1；
2. 12通道收敛/未收敛状态；
3. 失败通道DWR与根因；
4. 所有恢复候选；
5. DoF/rows/NNZ/factor/peak/time；
6. 12通道power和complex amplitude；
7. 是否得到Hybrid-eligible candidate；
8. 若得到，Full3D–Hybrid closure、M/DtN funnel和resource model v3；
9. 若未得到，所有lane的受控负结论；
10. full repository regression、Ruff、compileall、JSON、diff-check和工作树状态。

未经最终Review与用户明确授权，不得合并master。

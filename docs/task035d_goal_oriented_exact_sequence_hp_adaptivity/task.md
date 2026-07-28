# Task035d：目标量驱动、保持 exact sequence 的局部 h/p 自适应

## 0. 执行身份

```text
task = Task035d
status_at_creation = staged_on_Task035c_branch
execution_branch = codex/20260726-task35d-goal-oriented-exact-sequence-hp-adaptivity
branch_creation = by Codex only after Task035c selective merge
branch_base = exact post-Task035c master SHA
ordinary_default = unchanged
primary_solver = direct MUMPS through assembly-time static condensation
primary_reference = p6/h10 Full3D static + Case095/096 reference-v1
primary_hybrid_reference = p6/h10 static Hybrid M120
formal_MPI = 8 after serial/MPI2 qualification
heavy_PDE_concurrency = one at a time
```

本任务只有在 `docs/task035c_hybrid_channel_memory_closure/review_report_v2.md` 的M0–M4全部完成、Task035c整合master并确认工作树干净后才能启动。

---

# 1. 研究问题

Task035d必须回答：

> 能否在保持H(curl)切向连续、exact sequence、Floquet周期闭合和12个显著衍射通道精度的前提下，把准确的p6/h10高阶离散自动压缩成真正的局部h/p空间，并进一步传递到static Hybrid M120？

这里“真正”包含三个条件：

1. **local-p是真实减行。** 不活跃高阶edge/face/cell模式不生成global row，不进入matrix NNZ和MUMPS factor；不得在完整p6矩阵中把系数设为零后宣称降阶。
2. **local-h是真实局部细分。** 只细化被标记区域，并通过H(curl)兼容悬挂trace或共形过渡保持切向连续；不得把整个方向统一加层冒充局部h。
3. **h与p在同一离散架构中竞争。** tetra-h与hexa-p的两个独立实验不能合并成“hp成功”。

---

# 2. 固定物理范围

## 2.1 物理模型

```text
geometry = Task034 fixed rectangular block grating
wavelength = 13.5 nm
polarization = S
incidence = 10 degree grazing
periodic = x/y double Floquet
external boundary = sparse auxiliary DtN
materials = frozen Task034/Case095 identity
significant reference = Case095 significant_channel_reference_v1
```

## 2.2 网格与方法范围

主线只支持：

```text
axis-aligned first-order affine hexahedra
structured or 2:1-balanced axis-aligned hexa refinement
complex128
Nedelec first family
p in an explicitly qualified subset of p4/p5/p6
assembly-time static cell-interior condensation
Floquet slave elimination before insertion
MUMPS direct solve
```

当前不研究：

- 曲面、斜侧壁、圆角、粗糙度、缺陷或任意不规则几何；
- distorted/curved hexa和高阶几何映射；
- tetra static condensation与混合单元；
- 新迭代求解器；
- matrix-free/partial assembly生产路径；
- 0.7 nm资源外推；
- h13 Hybrid自适应的直接恢复，除非本任务Full3D Gate先通过。

## 2.3 中间模态区域约束

Task035c的`full3d_uniform_cg`传播和离散traction要求中间模态区域具有明确的均匀轴向有限元链。因此：

- 中间模态区域的z分段保持均匀；
- 中间区域若做h适应，只允许修改横截面网格，并沿整个中间长度一致挤出；
- 非均匀z局部细化只允许发生在未来Hybrid保留为local 3D FEM的上下端区；
- 任何破坏均匀轴向链的候选不得使用Task035c离散传播模型，必须fail closed。

---

# 3. 权威基线与对照

## 3.1 主要参考

```text
p6/h10 structured hexa
axis plan = (6,3,14)
cells = 252
Full3D standard rows = 173,882
Full3D static rows = 51,272
Full3D static peak = 14.721756 GiB at MPI8
Hybrid standard M120 peak = 11.076893 GiB at MPI8
Hybrid static M120 rows = 17,168
Hybrid static M120 peak = 7.544262 GiB at MPI8
```

物理参考使用p6/h10 Full3D standard/static的共同离散结果和Case095 reference-v1。p6/h10不是continuum truth，但它是本任务冻结的best available discrete authority。

## 3.2 必须保留的控制组

至少比较：

- global p6/h10 reference；
- global p5或same-mesh p5 control；
- Task035的DWR local-h代表点；
- Task035b fixed `p5-trace/p6-interior` h15/h14/h13代表点；
- 本任务p-only最佳候选；
- 本任务h-only最佳候选；
- 本任务combined hp最佳候选。

只有combined hp在同精度下相对p-only或h-only至少减少一项真实资源指标，才能声称“hp组合具有额外价值”。

---

# 4. 成功标准

## 4.1 结构正确性

每个正式候选必须通过：

- H(curl) shared-edge/shared-face切向连续；
- local-to-global entity orientation；
- x/y Floquet master/slave完整orbit同步；
- 角点双周期闭合；
- variable-p active-space维数、rank和无重复/孤立row；
- hanging-trace约束的rank、一致性和2:1闭合；
- discrete gradient image包含于variable-p H(curl)空间；
- `curl(grad)`在资格化容差内为零；
- serial/MPI2/MPI8 identity；
- inactive模式不分配global row；
- static condensation恢复后的interior方程残差。

不得以低linear residual替代exact-sequence和约束审计。

## 4.2 物理精度

对p6/h10 reference-v1，必须同时满足：

```text
12/12 significant powers pass
12/12 physical-boundary-plane complex amplitudes pass
R00 pass
Rtotal pass
Ttotal pass
Aclosure pass
Avolume / energy closure pass
full explicit true residual <= 1e-9
interface/selected field probes pass
```

不得放宽Case095/096冻结的通道集合、significance floor或容差。

## 4.3 离散规模

正式Full3D hp候选：

```text
actual conforming active FE DoF before condensation <= 90,000 mandatory
65,000–75,000 preferred
```

必须同时报告：

- active edge/face/cell DoF；
- static-condensed rows；
- DtN rows；
- matrix NNZ；
- factor NNZ与fill；
-单元、entity和periodic orbit数量。

`Full3D-equivalent DoF`、实际variable-p active DoF和condensed rows不得混写。

## 4.4 资源

相对p6/h10 Full3D static：

```text
mandatory final-solve peak reduction >= 20%
preferred final-solve peak reduction >= 40%
active rows / matrix NNZ / factor NNZ must all decrease
0 swap
```

相对p6/h10 static Hybrid M120，在Full3D hp Gate通过后：

```text
Hybrid hp peak must decrease
preferred Hybrid hp peak reduction >= 20%
12/12 + 12/12 remains pass
```

自适应全过程的总成本与最终单次solve成本分开报告。不能因为自适应探索花费较高，就掩盖最终候选的资源收益；也不能只报告最终小矩阵而隐藏生成它所需的高阶参考成本。

## 4.5 最终分类

```text
SUCCESS:
    true local-p + true local-h + combined hp
    exact sequence / periodic / MPI pass
    <=90k active FE DoF
    12/12 powers + 12/12 amplitudes
    measured resource reduction

LOCAL_P_SUCCESS_H_INCOMPLETE:
    variable-p和精度成功，但同架构local-h未闭合

LOCAL_H_SUCCESS_P_INCOMPLETE:
    local-h成功，但真实variable-p未闭合

PARTIAL_WITH_CONTROLLED_NEGATIVES:
    根因和负结果清楚，但完整hp Gate未通过
```

只有第一类允许称为“Task035d完整成功”。

---

# 5. Phase 0：合并后恢复与基线冻结

1. 从Task035c整合后的master创建Task035d分支；
2. 激活同一WSL complex128环境；
3. 校验Case095/096 compact authority；
4. 复核p6/h10 reference、12通道和Hybrid M120；
5. 检查旧Task035b selective-trace、regionwise-p、DWR和periodic-tetra原型，只作为研究输入，不得整体复制；
6. 创建Case097；
7. 建立从第一条重型运行开始就记录RSS、PSS、USS、cgroup、swap和对象生命周期的watchdog。

如果Task035c数值kernel在合并中保持blob identity，不重复运行完整p6六路径；只有后续Task035d修改影响reference kernel时才重建必要anchor。

---

# 6. Phase A：reference active-space authority

在启动真实variable-p PDE前，先建立reference-cell与小网格权威。

## A1. Entity DoF目录

对p4/p5/p6六面体Nédélec空间，记录：

- 每条edge的模式；
- 每个face的切向模式；
- cell-interior模式；
- Basix orientation/entity transforms；
- uniform-p低阶空间嵌入p6空间的矩阵；
- 各entity子空间的rank与条件数。

不得假定“p6数组前若干项就是p5”。必须通过插值、moment/Riesz或等价数学构造得到嵌入。

## A2. Exact-sequence authority

为每个允许的entity-degree组合构造配套标量H1空间或离散gradient authority，并验证：

```text
range(G) subset of Hcurl active space
curl(G phi) = 0
rank and nullity identities
orientation invariance
```

若某种edge/face/cell阶数组合破坏exact sequence，必须永久标记非法，不能进入PDE候选。

## A3. Generalized local expansion

主实现采用：

```text
active variable-p local coefficients
    --E_K-->
full p6 reference local coefficients
```

再形成：

```text
A_K,var = E_K^H A_K,p6 E_K
```

随后按active trace/interior分块并做静态凝聚。要求：

- inactive模式不进入global numbering；
- 不能创建完整p6 global matrix；
- orientation与Piola在`E_K`前后闭合；
- full-field recovery可重建p6容器中的物理场表示；
- uniform p4/p5/p6退化情况与现有标准路径一致。

## A4. 低成本fixture

至少通过：

- 单cell；
- 两cell共享face；
- 2×2×2小网格；
- x周期、y周期和双周期；
- serial/MPI2；
- uniform-p退化对照；
- 真实减行、NNZ和inactive-row审计。

A1–A4没有全部通过前，不得运行p6/h10 variable-p PDE。

---

# 7. Phase B：真实 local-p

## B1. 全局entity-degree map

建立全局：

```text
edge_degree[e]
face_degree[f]
cell_interior_degree[K]
```

约束：

- shared entity只有一个权威degree；
- cell不能请求高于共享entity可表达范围的非法trace；
- periodic mate使用相同degree并保留Floquet相位；
- 角点orbit闭合；
- 每次只允许相邻一级变化，除非有独立资格化证据。

## B2. 从p6向下压缩

初始所有entity为p6。第一轮仅允许：

```text
p6 -> p5
```

后续有证据时允许：

```text
p5 -> p4
```

cell-interior降阶与trace降阶分开计成本。由于interior最终被静态凝聚：

- 降低interior主要减少局部tensor、Schur和recovery成本；
- 降低edge/face才直接减少global rows、NNZ和factor front。

控制器必须认识这种差别，不能只按“删除DoF数量”排序。

## B3. 正式p-only候选

至少形成：

- conservative p-down；
- goal-weighted p-down；
- cost-aware p-down。

每个候选实际重算PDE并检查12通道，不允许只根据投影或先验估计宣布成功。

---

# 8. Phase C：真实 local-h

## C1. 主路线：2:1 balanced hexa refinement

优先实现axis-aligned hexa的：

- cell octree/block split；
- 2:1 balance；
- edge/face child catalog；
- H(curl) coarse-to-fine tangential trace约束；
- hanging edge/face orientation；
- material-interface保护；
- x/y Floquet周期镜像细化；
- MPI ownership和ghost identity；
- static condensation与hanging constraints组合。

所有子单元仍必须为axis-aligned affine hexa，不能在本任务中引入未资格化曲面或混合过渡单元。

## C2. Hybrid兼容性

- 中间modal region的z链保持均匀；
- 中间区域横截面细化必须沿z一致挤出，并能生成同一2D QEP横截面网格；
- 上下local FEM区域可独立局部细化；
- Hybrid接口两侧trace网格必须有明确匹配或资格化投影。

## C3. 备选路线

若2:1 hanging-hexa在两个独立能力尝试后仍没有正信号，可尝试完全共形的multi-block hexa refinement。但它仍必须是局部的，不能通过全域插入所有坐标平面冒充局部h。

已有periodic tetra DWR可以作为：

- h指标对照；
- 标记位置oracle；
- 受控替代实验。

但除非variable-p也在同一tetra离散中闭合，否则不能获得“combined hp success”。

## C4. h-only候选

至少形成一个真实局部h PDE候选，并与：

- uniform refinement；
- Task035 tetra-DWR趋势；
- p-only候选；

比较精度和资源。

---

# 9. Phase D：多目标误差与h/p决策

## D1. 目标集合

最低包含：

```text
R(0,0)
R_total
T_total
A_closure
12 significant powers
Re/Im of 12 physical-boundary-plane complex amplitudes
selected interface and field probes
```

复振幅不能由功率开方反推。功率的导数可由相应复振幅Re/Im目标组合获得，但最终必须直接审计功率。

## D2. Adjoint与目标压缩

允许用所有目标逐个伴随，也允许构建goal-gradient矩阵后用SVD/QR形成较少的独立adjoint方向。但必须：

- 保存压缩前后的目标span误差；
- 对全部正式目标进行最终直接复算；
- 不得因低秩压缩遗漏弱通道。

## D3. p-surplus、h-surplus与DWR

对每个候选区域保存：

- p6→p5与p5→p4的目标修正；
- enriched residual-weighted DWR；
- local h split的预测修正；
- phase/traction敏感度；
- 目标误差对edge、face、interior模式的贡献。

## D4. 成本模型

每个动作比较：

```text
goal error reduction / active FE DoF
goal error reduction / condensed rows
goal error reduction / matrix NNZ
goal error reduction / symbolic factor-cost proxy
```

真实候选产生后，用实测factor NNZ、peak和time校准成本模型。

## D5. 决策规则

```text
smooth + goal-sensitive + p-surplus快速衰减
    -> 保持/提高p

p-surplus衰减慢，h-split收益高
    -> local h

smooth + low goal impact
    -> p-down

uncertain / incompatible / estimator disagreement
    -> keep, fail closed
```

---

# 10. Phase E：自动h/p循环

实现：

```text
solve
→ estimate all goals
→ classify h/p actions
→ periodic and hanging closure
→ build true active space
→ static-condensed solve
→ direct 12-channel audit
→ accept/reject
```

最多先运行4个正式cycle。每一cycle记录：

- mesh/entity-degree map hash；
- h/p动作数量与位置；
- active FE DoF和condensed rows；
- NNZ/factor/peak/time；
- 所有目标估计误差和实际误差；
- estimator effectivity；
- rejected动作及原因。

一旦出现：

- exact-sequence失败；
- periodic/hanging rank失败；
- 12通道退化且无法被下一轮局部恢复；
- 资源硬上限；

立即停止该候选并保留证据，不得继续堆叠错误网格。

---

# 11. Phase F：接入 static Hybrid M120

只有Full3D hp候选通过第4章全部Gate后才执行。

## F1. 映射原则

- 上下local 3D FEM使用同一hp entity map和hanging constraints；
- 中间modal region使用与Full3D一致的横截面h/p离散；
- z向保持Task035c已资格化的均匀scalar-CG链；
- `full3d_uniform_cg`与`scalar_cg_discrete_derivative`保持同一物理身份；
- M固定先用120，只有真实M信号才运行160。

## F2. 对照

至少比较：

```text
p6/h10 Full3D static reference
hp Full3D static
p6/h10 Hybrid static M120
hp Hybrid static M120
```

## F3. Gate

- hp Full3D ↔ hp Hybrid：12/12 powers + 12/12 amplitudes；
- hp结果 ↔ p6/h10 reference-v1：全部物理Gate；
- interface E/H与selected fields；
- full residual和eliminated interior residual；
- Hybrid rows/NNZ/factor/peak低于p6/h10 Hybrid static M120；
- ordinary default不变。

Hybrid不能给未通过Full3D的hp候选“精度信用”。

---

# 12. 资源、并行与遥测

所有正式重型运行从启动时记录：

```text
process-tree RSS
per-rank RSS
per-rank PSS
per-rank USS
cgroup current/peak
swap
PETSc matrix/factor inventory
Python/NumPy/native retained bytes when available
stage/object lifecycle
```

正式顺序：

1. serial fixture；
2. MPI2 component identity；
3. MPI8正式PDE；
4. 只有明确的内存/速度问题才增加MPI1/4对照。

不得把不同时间点的各rank峰值简单相加冒充simultaneous peak。

---

# 13. 测试与benchmark

新建：

```text
benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/
```

至少包含：

- README/config/expected/test command；
- reference active-space authority；
- exact-sequence与entity-degree records；
- hanging-trace authority；
- p-only、h-only、combined hp正式候选；
- 12通道compact authority；
- resource ledger；
- controlled negatives；
- hash-bound generator和hermetic checker。

测试层：

- pure reference algebra；
- serial small mesh；
- MPI2 periodic/hanging identity；
- MPI8 representative PDE；
- Task035/035b/035c regression；
- Case095/096/097 checker；
- full repository pytest；
- Ruff、compileall、JSON、diff-check。

---

# 14. 代码与文档原则

- 通用能力写入 `src/`，Task runner只放benchmark入口；
- 不为每个候选复制一个Python文件；候选由配置和record驱动；
- 首次出现的新术语必须通俗解释；
- 失败不能只写`10/12`或`failed`，必须列具体通道和值；
- 每个正式PDE后更新 `docs/development_model_registry.md`；
- ordinary default始终不变；
- Task035d不得自行merge master，完成后等待集中Review。

---

# 15. 连续执行与停止规则

- commit/push不是等待点；
-一个Phase完成不是自动等待点；
- 有正信号继续加深；
- 同一lane连续两个结构或数值负信号后关闭并切换备选；
- 一次只运行一个heavy PDE；
- 不删除负结果；
- 不以投影估算替代真实PDE；
- 不以低残差替代物理和exact-sequence；
- 遇到源码身份、ABI、exact-sequence、MPI或资源硬blocker才停止报告。

最终交付：

```text
docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/summary.md
docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/test_summary.md
docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/response_v1.md
benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/
docs/development_model_registry.md updated
```

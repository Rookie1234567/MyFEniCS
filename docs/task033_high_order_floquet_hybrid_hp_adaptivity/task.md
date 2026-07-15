# Task033：高阶 H(curl) Floquet 资格化与 Hybrid 局部 h/p 自适应可行性

## 0. 任务身份

```text
Task ID = Task033
recommended execution branch = codex/20260715-task33-high-order-floquet-hybrid-hp
local repository = C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal
base = Task032 selective-merge 后的 clean origin/master
ordinary default = unchanged
primary wavelength = 13.5 nm
primary material = 当前已验证 Si 复折射率
host memory hard budget = 14 GiB
primary solver family = Hybrid FEM–Modal direct reference
```

Task033 只有在 Task032 按 `selective_merge_manifest.csv` 合入 `master`、master 轻量回归通过、且工作树干净后才能开始。Codex 不得直接在 Task032 research branch 上继续开发，也不得把 Task032 的未扩展 current-scale direct 实现称为 0.7 nm production solver。

开始前必须阅读：

```text
docs/task032_hybrid_fem_modal_direct_baseline/task.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md
docs/task032_hybrid_fem_modal_direct_baseline/review_report_v1.md
docs/task032_hybrid_fem_modal_direct_baseline/review_report_v1_addendum.md
docs/task032_hybrid_fem_modal_direct_baseline/response_v1_review_followup.md
docs/task032_hybrid_fem_modal_direct_baseline/review_report_v2.md
docs/task032_hybrid_fem_modal_direct_baseline/outcomes/task032_0p7nm_scalability_assessment.md
docs/repository_work_principles.md
docs/markdown_rendering_standard.md
```

Codex 必须在 Task033 `outcomes/environment_and_base.md` 中记录：

- Task032 selective-merge SHA；
- Task033 branch base SHA；
- `origin` 与当前分支；
- Docker image 与真实 digest；
- PETSc、DOLFINx、Basix、SLEPc 版本；
- complex128 状态；
- 工作树 clean attestation；
- 宿主可用内存和容器上限。

---

# 1. 背景与核心问题

Task032 已经证明，在当前规则结构和相同离散下，中间 `z=10–110 nm` 的三维体网格可以由二维截面模式替代。h3/M160 中，Hybrid 相对 full 3D：

| 指标 | full 3D | Hybrid | 缩减 |
|---|---:|---:|---:|
| total rows | 198,518 | 68,796 | 65.35% |
| assembled NNZ | 21,317,860 | 8,594,673 | 59.68% |

但未来 0.7 nm 仍要求同时解决：

```text
1. 上下复杂三维端部的局部 FE DoF 过大；
2. 当前只正式支持 p=2 的高阶拓展不足；
3. Floquet 高阶边、面自由度的 orientation 与相位约束尚未资格化；
4. 截面 QEP 的高阶精度和成本未知；
5. local h、p、接口缓冲厚度和所需模式数 M 之间的联合代价未知；
6. 14 GiB 个人电脑不能无条件运行所有 p/h 组合。
```

Task033 的定位是：

> 先以极小的纯 3D 解析问题把 p=3、p=4 Nédélec 与双 Floquet 高效实现资格化；随后在 Task032 Hybrid 结构上测量固定阶次、局部 h 细化、候选 p 提升和接口缓冲优化能减少多少 local DoF、NNZ、内存与时间。

Task033 是 **h/p feasibility and compression study**，不是最终自适应 production solver，也不新增最终迭代法。

---

# 2. 冻结物理范围

## 2.1 主 Hybrid 物理模型

```text
full domain = 50 x 25 x 140 nm
period x/y = 50 / 25 nm
Si grating = 17 x 25 x 120 nm
wavelength = 13.5 nm
Si refractive index = 0.999002304859 + 0.00182649365j
primary incidence = 10° grazing from surface
phi = 0°
primary polarization = S
secondary polarization = P
external ports = existing double-Floquet Fourier-DtN
middle region = generic epsilon(x,y), z-invariant
bottom/top ends = exact 3D Nédélec FEM
```

未来端部可能存在曲边、圆角和任意三维材料变化，因此 Task033 不得使用当前 Case080 的 y 不变性简化未来服务路线，也不得删除上下 local 3D FEM。

## 2.2 高阶资格化微型问题

高阶 p=3、p=4 的第一资格化必须使用纯 3D 小问题，避免 Hybrid、QEP、模式截断和复杂几何同时介入。

### Fixture A：10 nm 均匀空气盒

```text
x = 0–10 nm
y = 0–10 nm
z = -5–5 nm
material = air
boundary x/y = double Floquet
field = analytic oblique Bloch plane wave
```

目标：验证高阶 Nédélec 自由度配对、相位、edge/face orientation、MPI ownership 和稀疏约束变换。

### Fixture B：10 nm 平坦空气–Si 界面

```text
x = 0–10 nm
y = 0–10 nm
z = -5–5 nm
interface = z=0
upper = air
lower = current Si
boundary x/y = double Floquet
outer z treatment = existing analytic homogeneous port / reviewed Fresnel path
incidence = S/P, 1° / 5° / 10° grazing representative points
```

目标：与解析 Fresnel R/T、场相位和能量闭合比较。该 fixture 只用于高阶能力资格化，不替代 Hybrid 主模型。

---

# 3. 主要目标与成功等级

## 3.1 高阶 Floquet 目标

必须把现有 p=2 topological-trace Floquet 扩展到 p=1、2、3、4，并满足：

- edge、face 和必要 interior trace DoF 的 orientation 正确；
- 双周期角点/边交叠约束无 slave chain；
- Bloch 相位与矢量切向方向同时正确；
- MPI1、MPI2、MPI4 结果一致；
- 不使用全边界 dense matrix；
- 不把完整 boundary DoF 或 field allgather 到 rank 0；
- 不以逐点最近邻搜索作为正式高阶路径；
- 不为每个入射角重复进行完整拓扑匹配；
- ordinary p=1/p=2 结果不回归。

## 3.2 h/p 压缩等级

Task033 不把“固定 p=2 的 h 自适应必须达到 3 倍”写成非黑即白的最低通过线。

| 同误差 local DoF 压缩倍数 | 评价 |
|---:|---|
| `<1.3x` | weak signal |
| `1.3–2x` | useful engineering positive |
| `2–3x` | clear success |
| `>=3x` | Task033 联合工程目标 |
| `>=5x` | strong / preferred target |

其中：

```text
p2 h-adaptive alone: 3x 是 stretch；
h + p3 或 hp zoning + interface budget: 3x 是工程目标；
5x: 强目标，不是预设必然结果。
```

## 3.3 1 TiB 路线的解释

Task033 的压缩结果将更新 1 TiB 资源预算，但不得宣称本任务已经证明 0.7 nm 可解。未来目标仍是：

```text
preferred local FE rows <= 2e8
candidate zone = 2e8–3.5e8
high risk = 3.5e8–5e8
likely infeasible > 5e8
```

---

# 4. 非目标

Task033 暂不做：

- 0.7 nm PDE 正式求解；
- 波长、材料色散或实验噪声扫描；
- 最终 scalable generic modal core 重构；
- replicated `M^2` 和 all-mode RHS 的完整 Task034 替代实现；
- 最终 matrix-free Hybrid 迭代法；
- arbitrary curved production geometry；
- 非匹配 mortar 接口；
- 为了声称成功而放宽 Task032 true residual、R/T/A 或 field Gate；
- 在 DOLFINx/Basix 缺少可靠支持时自行发明不可维护的任意 cellwise variable-p H(curl) 约束系统。

Task033 可以审计 variable-p 可行性；若没有原生、稀疏、可验证的实现路径，必须 fail closed，并以“fixed-p high-order efficiency + h-adaptive feasibility”收口。

---

# 5. Phase 0：Task032 选择性合并与新分支

1. 按 Task032 `selective_merge_manifest.csv` 从 clean master 执行选择性合并；
2. 运行 master 轻量回归和 Case080 checker；
3. 记录 merge SHA；
4. 在 `fenics_v3_hybrid_FEM_modal` 中更新 `origin/master`；
5. 确认工作树 clean；
6. 由 Codex 创建 Task033 执行分支；
7. 不复制 `.git`、results、artifacts、PEP cache 或 MUMPS scratch；
8. Task032 branch 保留为只读研究历史。

建议分支：

```text
codex/20260715-task33-high-order-floquet-hybrid-hp
```

---

# 6. Phase 1：高阶 H(curl) 与 Floquet 实现审计

## 6.1 搜索硬编码

必须系统搜索并记录所有与以下假设有关的代码：

```text
degree == 2
p2-only entity layout
固定 edge/face DoF 数
固定 orientation table
固定 trace order
固定 quadrature degree
固定 visualization degree
固定 QEP N1curl/Lagrange degree
```

输出：

```text
outcomes/high_order_assumption_audit.md
```

每项标记：

```text
remove / generalize / retain-with-reason / out-of-scope
```

## 6.2 正式高阶 Floquet 路径

高阶 Floquet 必须采用稀疏、实体局部的拓扑映射。推荐代数形式：

$$
\mathbf u = C_p(\mathbf k_{\parallel})\mathbf q,
$$

$$
A_{\mathrm{red}} = C_p^{H} A C_p.
$$

实现约束：

1. 周期 face pairing、edge pairing 和角点身份只构建一次；
2. entity permutation / orientation transformation 使用 Basix/DOLFINx 可验证的局部变换；
3. 入射角变化只更新 Bloch phase 权重，不重做几何点搜索；
4. `C_p` 保持 sparse distributed；
5. 正式路径复杂度随 constrained DoF 和 entity-local block 增长，不形成 boundary-size square dense object；
6. topology cache key 至少包含 mesh identity、element family、degree、periodic axis 和 orientation schema；
7. phase cache 与 topology cache 分离；
8. 任何数值插值或点匹配 fallback 只能用于小 fixture diagnostic，不能成为 p=3/p=4 ordinary path。

必须记录：

- periodic boundary DoF；
- slave/master count；
- transform NNZ；
- 每个 constrained DoF 的 NNZ；
- topology build time；
- phase-only update time；
- peak RSS；
- cache hit/miss；
- MPI communication volume；
- 是否存在 full gather 或 dense boundary square。

性能警戒，而非单一机器硬失败线：

| 指标 | 预期处理 |
|---|---|
| p4 Floquet setup 超过总 case 时间 20% | 必须分析并优化 |
| p4 每 constrained DoF setup 成本超过 p2 的 5 倍 | 必须解释 entity block 或算法原因 |
| 相邻角度仍重建完整 topology | 不接受 |
| 发现 boundary-size dense object 或 global allgather | 不接受 |

## 6.3 高阶积分与几何

- 物理 assembly、DtN coupling、QEP 和后处理不能继续使用 p=2 固定 quadrature；
- quadrature 必须根据 field degree、geometry degree 和 coefficient degree选择并做一次加阶对照；
- 当前平面 fixture 可使用线性几何；
- 文档必须明确：未来曲边结构需要高阶几何映射，不能用 p4 场配低阶折线几何后声称高阶收敛。

---

# 7. Phase 2：纯 3D p=1–4 资格化

## 7.1 Fixture A 合同

对 10 nm 空气盒至少完成：

```text
p = 1, 2, 3, 4
MPI = 1, 2, 4
至少两个 mesh levels
S 和 P 中至少各一个解析 plane-wave case
```

必须验证：

- slave/master relation round-trip；
- Bloch phase mismatch；
- edge/face orientation；
- reduced/full action equivalence；
- full explicit true residual；
- analytic plane-wave field error；
- MPI rank-independent result；
- p1/p2 regression。

代数 Gate：

```text
constraint round-trip relative error <= 1e-12
Bloch trace mismatch <= 1e-11
reduced/full random-vector action error <= 1e-11
full true residual <= 1e-10
MPI result difference <= 1e-10
```

## 7.2 Fixture B 合同

平坦 air–Si 界面至少完成：

```text
p = 1, 2, 3, 4
S/P
primary 10° grazing
1° / 5° 作为轻量角度 smoke
```

记录：

- analytic Fresnel complex amplitude；
- official R/T；
- field phase；
- energy closure；
- DoF、rows、NNZ；
- Floquet setup、assembly、factor、solve、postprocess time；
- simultaneous RSS。

p=3、p=4 的接受条件不是“数值一定达到某个预设极小误差”，而是：

- 约束和 orientation 代数 Gate 通过；
- 随 h 或 p 提升，Fresnel/field error 呈合理下降；
- 相同或更低资源下不出现明显反常回归；
- 若 p4 比 p3 成本高而无精度收益，必须保留为负结果，不得强推 p4。

建议建立：

```text
benchmarks/cases/090_high_order_3d_floquet_hcurl/
```

---

# 8. Phase 3：高阶 Hybrid 组件资格化

纯 3D 高阶 Gate 通过后，才允许扩展 Hybrid。

## 8.1 截面 QEP

将以下组件扩展到 p=1、2、3、4：

- quadrilateral N1curl transverse space；
- longitudinal Lagrange space；
- cross-section double Floquet reduction；
- QEP assembly；
- right/left modes；
- Poynting classification；
- biorthogonality；
- near-degenerate block handling；
- tracking；
- trace extraction。

必须使用相同 degree 语义，不能让 3D Nédélec p 与 2D QEP p 名称相同但实际 Basix 阶次不同。

解析 QEP 对照至少包括：

```text
air
homogeneous lossy
current patterned cross-section
```

对每个 p 记录：

- QEP full/reduced DoF；
- matrix NNZ；
- converged eigenpairs；
- beta error；
- polynomial residual；
- left/right residual；
- biorthogonality error；
- setup/solve/classification time；
- retained eigenvector bytes；
- peak RSS。

## 8.2 匹配接口

第一版继续使用 matching interface：

```text
3D interface face mesh
=
2D cross-section mesh
=
same polynomial degree
```

必须验证 p=1–4：

- 3D tangential trace；
- right reconstruction；
- left Petrov projection；
- coefficient round-trip；
- normal signs；
- near-degenerate subspace；
- MPI1/2/4。

Task033 不实现 nonmatching mortar。

## 8.3 Hybrid direct anchor

每个新 degree 在 h5 先完成：

```text
augmented direct
vs
Modal-Schur memory-minimal
```

要求 modal coefficients、local fields、official R/T/A 和 full residual 在既定代数 tolerance 内一致。

p2/h3 继续作为 Task032 regression anchor。

---

# 9. Phase 4：统一 p/h 计算矩阵

## 9.1 主求解路径

Task033 主批次使用：

```text
primary = modal-schur-memory-minimal
reference anchors = augmented direct
not selected = Schur fast
```

理由：Task032 h3 中 memory-minimal 同时获得最低实测峰值和不差于 augmented 的总时间；Schur fast 在 h3 反而增内存。

Task033 仍是直接法研究。不得在本任务中混入新的最终迭代 PC。

## 9.2 候选矩阵

计划网格：

```text
h = 5, 3, 2.5, 2, 1.5 nm
p = 1, 2, 3, 4
```

所有组合都必须先生成 DoF/NNZ/内存预测；“尽量运行”不等于无条件触发 OOM。

| degree | h5 | h3 | h2.5 | h2 | h1.5 |
|---:|---|---|---|---|---|
| p1 | required | required | required | required if Gate | required if Gate |
| p2 | required | required | required | conditional | locked by default |
| p3 | required | conditional | conditional | locked by default | locked by default |
| p4 | required | conditional | locked by default | locked by default | locked by default |

解释：

- `required`：必须建立、预测，并在安全 Gate 通过时运行；
- `conditional`：只有前一网格 clean 记录和两种内存预测均通过才运行；
- `locked by default`：除非前序实测显示明显低于预算且获得独立预测支持，否则不得运行；
- 未运行必须记录为 `not_run_by_memory_gate`，不能留空。

## 9.3 14 GiB 安全 Gate

内存权威口径为：

```text
max(simultaneous live MPI worker RSS sum, container cgroup current)
```

运行前要求：

```text
two independent center predictions <= 11.5 GiB
conservative upper <= 12.8 GiB
no swap
clean source
watchdog enabled
one large case at a time
```

运行时：

```text
warning = 11.5 GiB
controlled termination = 13.0 GiB
hard container/host budget = 14.0 GiB
```

如果环境实际 cgroup 上限小于 14 GiB，必须按更小值重新留安全余量。不得依靠 swap 把不安全组合跑完。

## 9.4 M 截断

`M` 仍表示每个传播方向保留的内部截面模式数。每个 p/h 结果必须说明 M，而不能只写 p/h。

执行规则：

1. p2/h3 复用 Task032 M160 canonical anchor；
2. 每个新 degree 至少在一个 h5 anchor 做 M80/120/160 漏斗；
3. p3 或 p4 若 M120→M160 未通过，条件增加 M240；
4. 正式 p/h 比较使用各自通过截断 Gate 的 M；
5. M4 parameter smoke 不得用于物理收敛；
6. 截断误差必须与 FE 离散误差分开记录。

---

# 10. Phase 5：固定 p=2 的局部 h 自适应可行性

## 10.1 先采用可维护的 conforming 路线

Task033 第一版 h 自适应优先使用：

- 非均匀、分级的 conforming hexahedral mesh；
- 物理界面和强场区局部细化；
- 平滑区域较粗；
- 周期两侧完全同步的边界网格；
- 固定匹配的内部 modal trace 网格；
- 必要时通过多轮 `solve → indicator → rebuild` 更新 mesh；
- 不在第一步引入未经验证的 hanging-node H(curl) 自定义约束。

如果 DOLFINx 当前原生局部 refinement 能安全保持 H(curl)、Floquet 和匹配 trace，可以建立受控原型；否则以 conforming graded mesh 作为 Task033 正式路线。

## 10.2 误差指标阶梯

按以下顺序推进：

1. physics-informed 标记：材料界面、端部、接口、强场梯度；
2. element residual 与 tangential/curl jump；
3. 面向 R/T/A 和显著衍射级的 adjoint-weighted 指标原型；
4. 对比不同指标的 DoF–error 曲线。

不得一开始就把复杂 DWR 作为所有功能的阻塞项。先证明分级网格能重现 reference，再升级 goal-oriented 指标。

## 10.3 三层 reference

### Level A：uniform p2/h5

用途：只验证 h-adaptive 机制。

### Level B：uniform p2/h3

用途：Task033 主要压缩率 reference。

### Level C：已有 p2/h2 official R/T/A

用途：向更细结果靠近的桥接诊断。若没有同口径完整 h2 field，则不得声称 h2 field-equivalent。

同网格/同 reference 基本 Gate：

```text
full true residual <= 1e-9
max absolute R/T/A delta <= 1e-5 mandatory
max absolute R/T/A delta <= 1e-6 strong
significant diffraction complex-amplitude relative delta <= 1e-3 mandatory
significant diffraction complex-amplitude relative delta <= 1e-4 strong
sampled interface E relative error <= 5e-3
sampled interface H relative error <= 1e-2
```

h2 bridge 应单独标记 `RTA/order bridge only`，不能伪装成完整 field qualification。

---

# 11. Phase 6：p=3、p=4 等精度效率与 h/p 原型

## 11.1 先做全局固定阶次效率

比较至少包括：

```text
uniform/adaptive p2
p3 on coarser graded meshes
p4 on selected safe coarse meshes
```

核心问题不是“p4 是否比 p2 更准确”，而是：

> 达到相同 R/T/A、显著衍射级、接口场和 QEP beta 误差时，哪种 p/h 组合的 local DoF、rows、NNZ、内存和总时间最低？

p3 是第一高阶候选。只有 p3 显示明确资源收益且 p4 预测安全时，才扩大 p4 研究。

## 11.2 variable-p 能力审计

必须审计 DOLFINx/Basix 对以下内容的原生支持：

- cellwise variable-order Nédélec；
- p 不同邻接单元的切向连续；
- periodic paired faces 的同步 p；
- high-order interface trace；
- MPI partition 后的 ownership；
- multimesh/submesh coupling 的维护成本。

若不存在可靠、稀疏、可测试的原生路线：

```text
do not implement bespoke arbitrary variable-p constraints in Task033
```

此时 Task033 仍可通过：

```text
p2 h-adaptive feasibility
+ global p3/p4 equal-accuracy efficiency
+ hp zoning design report
```

## 11.3 受控 hp zoning

只有 capability audit 通过后，才允许尝试最小两区原型：

```text
material interface / singular zone = p2 + fine h
smooth bulk zone = p3 + coarse h
```

p4 zoning 不是必须项。不得为了完成任务而引入复杂且不可维护的 mortar/constraint 系统。

---

# 12. Phase 7：接口位置与规则缓冲厚度

当前接口为：

```text
bottom z = 10 nm
top z = 110 nm
patterned-region buffer = 10 nm per side
```

Task033 至少比较对称 buffer：

```text
10.0 nm
7.5 nm
5.0 nm
2.5 nm
```

对应接口为：

```text
z_bottom = buffer
z_top = 120 - buffer
```

接口必须始终位于截面 z 不变的规则区域中。

每个 buffer 记录：

- bottom/top local thickness；
- local cells、FE DoF、rows、NNZ；
- interface trace DoF；
- 通过截断 Gate 所需 M；
- QEP 和 mode storage；
- direct peak RSS；
- setup/solve/total time；
- Hybrid/full3D 或当前 canonical reference 误差；
- interface E/H residual。

接口越靠近端部，local FE DoF 下降，但衰减模需求可能增加。最终选择必须基于联合代价，不能只按 local DoF 最小：

$$
\mathrm{Cost}_{\mathrm{total}}
=
\mathrm{Cost}_{\mathrm{local\ FEM}}
+
\mathrm{Cost}_{\mathrm{QEP/modes}}
+
\mathrm{Cost}_{\mathrm{interface/Schur}}.
$$

---

# 13. Phase 8：数据记录和比较表

每次正式运行必须记录：

## 13.1 物理与数值

- wavelength、material、angle、polarization；
- p、mesh policy、resolved cells；
- M / direction；
- true residual；
- R/T/A；
- 每个传播衍射级的 complex amplitude 与效率；
- energy closure；
- interface E/H residual；
- selected-plane field error；
- QEP beta/residual/biorthogonality；
- modal truncation delta。

## 13.2 规模

- full/local FE DoF；
- external auxiliary unknowns；
- internal `2M` modal unknowns；
- total rows；
- assembled NNZ；
- QEP full/reduced DoF 与 NNZ；
- interface trace DoF；
- projection/traction NNZ；
- LU factor NNZ；
- modal Schur bytes；
- dense RHS columns/bytes；
- retained eigenvector bytes。

## 13.3 资源

- mesh/space build time；
- Floquet topology build time；
- phase update time；
- assembly time；
- QEP solve/classification time；
- factor time；
- multi-RHS time；
- modal solve；
- field recovery；
- R/T/A；
- total time；
- simultaneous worker RSS；
- cgroup current；
- swap；
- stage peak。

所有表必须标注：

```text
measured / derived / predicted / not_run
unit
baseline and denominator
evidence record
```

---

# 14. Benchmark 与目录

建议建立两个独立 Case：

```text
benchmarks/cases/090_high_order_3d_floquet_hcurl/
benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/
```

Task 文档目录：

```text
docs/task033_high_order_floquet_hybrid_hp_adaptivity/
├── README.md
├── task.md
└── outcomes/
    ├── summary.md
    ├── environment_and_base.md
    ├── high_order_assumption_audit.md
    ├── high_order_floquet_results.md
    ├── qep_order_study.md
    ├── uniform_p_h_matrix.csv
    ├── adaptive_compression.csv
    ├── interface_buffer_tradeoff.csv
    ├── memory_prediction_and_launch_decisions.md
    ├── negative_results.md
    ├── test_summary.md
    ├── changed_files.md
    └── selective_merge_manifest.csv
```

重型 field、mesh、eigenvector、matrix、factor、memory timeline 和 raw log 继续保存在：

```text
benchmarks/artifacts/cases/090/
benchmarks/artifacts/cases/091/
```

并保持 Git ignored。

---

# 15. Markdown 公式与表格 Gate

所有 Task033 Markdown 必须遵守：

```text
docs/markdown_rendering_standard.md
```

特别要求：

- 独立公式使用空行隔开的 `$$` block；
- 不把需要渲染的公式放进代码围栏；
- 多行公式不放入 Markdown 表格单元格；
- 表格每行列数一致；
- 单元格内的竖线必须转义或改写；
- 提交前实际检查 GitHub rendered view；
- 若用户看到原始 LaTeX、破损表格或错位列，文档 Gate 视为失败。

Codex 应增加 Task033 文档合同，至少检查 task、summary 和关键 outcomes 的公式 delimiter 配对、必需表格和本地链接。

---

# 16. 分阶段执行顺序与停止条件

| 顺序 | 阶段 | 进入条件 | 失败时动作 |
|---:|---|---|---|
| 1 | Task032 selective merge | Review V2 accepted | 不创建 Task033 分支 |
| 2 | p3/p4 Floquet microfixtures | p1/p2 regression pass | 修复高阶约束，不进入 Hybrid p3/p4 |
| 3 | high-order QEP/trace | pure 3D high-order pass | 保留 p2 h-adaptive，暂停该高阶 degree |
| 4 | p/h safe matrix | 14 GiB prediction Gate | not_run，禁止 OOM/swap 硬跑 |
| 5 | p2 h-adaptive h5 | mechanism pass | 修复 mesh/indicator |
| 6 | p2 h-adaptive h3 | h5 pass | 保存压缩率，决定是否继续 |
| 7 | p3/p4 equal-accuracy | high-order components pass | 无收益则停止提升该 p |
| 8 | hp zoning audit/prototype | native safe capability | 无原生路径则文档化，不自造复杂系统 |
| 9 | buffer trade-off | p2/h3 canonical available | 选择 local/modal 联合最优点 |
| 10 | 1 TiB projection update | measured compression available | 不宣称 0.7 nm 已证明 |

---

# 17. 成功分类

Task033 最终必须选择一个准确身份。

## 17.1 高阶资格化

```text
high_order_floquet_pass
high_order_floquet_partial_p3_only
high_order_floquet_failed
```

## 17.2 h/p 可行性

```text
hp_compression_strong          >=5x combined
hp_compression_engineering     >=3x combined
hp_compression_clear           2–3x
hp_compression_positive        1.3–2x
hp_compression_weak            <1.3x
```

## 17.3 任务总分类示例

```text
high_order_floquet_pass_with_hp_engineering_positive
high_order_p3_pass_p4_negative_with_h_adaptive_positive
hp_feasibility_diagnostic_only
```

不得因为未达到 3x 就删除 1.3–2x 的工程正结果，也不得把 1.5x 写成 3x success。

---

# 18. 测试与回归

至少包括：

- p1/p2 existing Floquet regression；
- p3/p4 entity orientation unit tests；
- double-periodic corner/edge ownership；
- MPI1/2/4 constraint/action equivalence；
- 10 nm air plane-wave analytic test；
- 10 nm air–Si Fresnel S/P test；
- p1–4 QEP analytic beta tests；
- p1–4 left/right and trace round-trip；
- augmented/Schur equivalence anchors；
- adaptive mesh periodic synchronization；
- interface matching and normal signs；
- memory watchdog and `not_run` decision tests；
- JSON/CSV parser；
- Markdown rendering/documentation contract；
- Case080 regression；
- Case090/091 checker；
- Ruff、compileall、`git diff --check`。

正式 large records 必须来自 tracked-source-clean commit。Dirty screening 只能进入 ignored artifacts 或明确标记的 research record。

---

# 19. 文档与代码交付

Codex 必须同步：

- `docs/development_progress.md`；
- `docs/capability_matrix.md`；
- `docs/project_service_requirements_and_forward_model_roadmap.md`；
- Quick Start：如何选择 p、h、Hybrid path 和内存 Gate；
- Theory：高阶 H(curl) Floquet、orientation、h/p 误差与接口预算；
- Code Walkthrough：高阶约束、QEP、adaptive mesh 和运行矩阵；
- Benchmark Case090/091；
- `outcomes/summary.md`，表格优先；
- `selective_merge_manifest.csv`。

建议理论文件：

```text
notes/theory/high_order_hcurl_floquet_and_hp_adaptivity.md
```

---

# 20. 最终必须回答的问题

Task033 完成时必须用表格回答：

1. p=3、p=4 双 Floquet 是否在纯 3D 解析问题上正确？
2. 高阶 Floquet setup 是否保持 sparse、distributed、可缓存，而不是随边界 DoF 平方增长？
3. p=3、p=4 的 QEP beta 精度相对 p=2 提升多少，付出多少 DoF、NNZ、内存和时间？
4. p1–4、h5/h3/h2.5/h2/h1.5 中哪些实际运行，哪些被 14 GiB Gate 阻止？
5. 在达到 uniform h5 精度时，p2 h-adaptive 可压缩多少？
6. 在达到 uniform h3 精度时，p2 h-adaptive 可压缩多少？
7. p3 粗网格是否比 p2 细网格更省总资源？
8. p4 是否提供额外工程收益，还是只增加成本？
9. variable-p H(curl) 是否有原生可维护路径？
10. 当前 10/110、7.5/112.5、5/115、2.5/117.5 nm 接口中，哪个 local-FE/M 联合代价最低？
11. 最佳候选的 local DoF、total rows、NNZ、RSS 和时间相对 Task032 h3 基线下降多少？
12. measured compression 更新后，1 TiB 下 0.7 nm 路线处于 preferred、candidate、high-risk 还是 infeasible 区？
13. 哪些高阶/自适应组件可以合入 master，哪些只能留作 research？
14. Task034 scalable generic modal core 应以哪一个最终 local discretization 和 interface policy 为输入？

---

# 21. 最终原则

Task033 应优先得到可信的比较矩阵，而不是追求一次性实现最复杂的 hp 系统。

正确顺序是：

```text
高阶 Floquet 小问题资格化
→ 高阶 QEP/trace/Hybrid anchor
→ 安全 p/h 运行矩阵
→ p2 h-adaptive h5/h3
→ p3/p4 等精度效率
→ 可行时最小 hp zoning
→ interface buffer 联合优化
→ 更新 1 TiB 预算
```

无论结果是 1.5x、3x 还是 5x，都必须保留真实数据、负结果和 `not_run` 决策。Task033 不得通过降低物理精度、缩小模式数 M 而不做截断验证，或依赖 swap 来制造压缩成功。
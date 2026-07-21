# Task035 任务书：H(curl) 场/目标量驱动自适应与 hp 策略

## 0. 任务身份与启动锁

```text
task = Task035
status_at_creation = planning_only
execution_locked_until = Task034 final selective merge completed
execution_branch = codex/20260721-task35-hcurl-goal-oriented-adaptivity
primary_environment = qualified WSL native complex PETSc stack after fresh requalification
primary_physics = 13.5 nm, fixed geometry, S incidence
ordinary_default_changed = false
```

本任务由 Task034 的正式负结果触发：

- conforming graded-h mesh mechanism 可以构造；
- conservative/balanced/aggressive 三档 raw DoF 分别减少，但全部未通过 same-error physical Gate；
- 因此“按几何距离手工变粗/变细”不能替代真正的 field-driven adaptivity；
- p3/h3、p4/h5 Full3D–Hybrid closure、Case093、M funnel 和 MPI identity 已提供可审查基线；
- 当前主要未解决科学问题是：**哪些局部空间真正控制 R/T/A、R00、衍射级和场误差，以及应当做 h、方向性 h、p 还是 M refinement。**

Task035 不得在 Task034 尚未完成最终 review 和 selective merge 时启动代码实现或正式 PDE。Task034 合并完成、master 测试通过后，Codex才执行第 1 节分支流程。

---

## 1. 分支、同步与协作规则

### 1.1 创建执行分支

Task034 最终 selective merge 后，Codex 在 WSL 中执行：

```bash
git fetch origin --prune
git switch master
git pull --ff-only origin master
git status --short --untracked-files=all
git rev-parse HEAD
git rev-parse origin/master
```

确认：

- `HEAD == origin/master`；
- 工作树无 tracked 修改和 nonignored untracked 文件；
- Task034 最终 merge SHA、Task035 任务书和理论文档均已存在。

然后由 Codex 创建并推送：

```bash
git switch -c codex/20260721-task35-hcurl-goal-oriented-adaptivity
git push -u origin codex/20260721-task35-hcurl-goal-oriented-adaptivity
```

### 1.2 同一分支闭环

Task035 启动后：

- ChatGPT 的 task、addendum、review；
- Codex 的代码、测试、outcomes、response；
- 理论和项目文档更新；

全部只提交到 Task035 执行分支。最终 review approval 和用户授权前，不得把任何 Task035 过程材料写入或合并 `master`。

### 1.3 必读材料

开始前完整阅读：

```text
AGENTS.md
docs/repository_work_principles.md
docs/task035_hcurl_goal_oriented_adaptivity/README.md
docs/task035_hcurl_goal_oriented_adaptivity/task.md
notes/theory/hcurl_adaptive_error_estimators_and_hp_strategy.md
notes/theory/high_order_hcurl_floquet_and_hp_adaptivity.md
notes/theory/hybrid_fem_modal_domain_decomposition.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/summary.md
docs/task034_workstation_wsl_adaptive_scalability/outcomes/all_model_results.json
benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/convergence_summary.json
benchmarks/cases/093_fixed_geometry_ph_convergence_mpi/records/mpi_identity_summary.json
Task034 final review and response
```

不得只根据本任务标题或聊天摘要执行。

---

## 2. 核心研究问题

Task035 必须回答以下问题：

1. 对当前 complex lossy time-harmonic Maxwell 问题，哪一种 cell/face estimator 与真实物理误差最相关？
2. estimator 在高频 pre-asymptotic 区是否失效，如何使用 $kh/p$ 或其他 resolution Gate？
3. R/T/A、R00、显著衍射级和接口场应采用 energy residual、DWR，还是二者组合？
4. 当前 tensor-product strip refinement 为什么在 Task034 中产生大物理误差？
5. 是否能建立真正局部、周期同步、材料贴合、无未资格化 hanging-node 的 conforming mesh？
6. isotropic h、anisotropic directional h、mesh regeneration、global-p 和条件 local-hp 中哪条最有效？
7. Hybrid 中如何分离 local-3D mesh error、QEP discretization、external DtN truncation 和 internal M truncation？
8. 能否在 p4/h5 约 340k Full3D rows 的基础上，以更少 rows 保持或改善全部物理 observable？
9. 一个为 10° S 构造的网格能否扩展为 1°/5°/10° S common mesh？
10. 若所有方法均失败，瓶颈是 estimator、mesh backend、H(curl) conformity、reference accuracy 还是 cost？

---

## 3. 任务范围与明确非目标

### 3.1 正式主线

```text
wavelength = 13.5 nm
geometry = Task034 fixed block grating
incidence = 10° grazing first
polarization = S
Full3D + Hybrid
p = 2, 3, 4
MPI8 primary production point
MPI1/4 low-cost fixtures where appropriate
```

### 3.2 条件扩展

只有单点 10° S adaptive 主线通过后，才允许：

```text
1° / 5° / 10° S robust common mesh
conditional P capability smoke
conditional local variable-p audit
conditional p4 Hybrid adaptive campaign
```

### 3.3 非目标

本任务不得：

- 运行 0.7 nm production PDE；
- 重写 scalable generic modal core；
- 把最终 low-memory iterative solver 作为 Task035 主工作；
- 为表格完整性重复完整 P 入射矩阵；
- 在 estimator fixture 未通过前启动重型 p4 adaptive；
- 直接把 Task034 的手工 graded profiles 改名为 adaptive；
- 未经能力证明实现 arbitrary cellwise variable-p production；
- 以 R+T+A 接近 1 替代空间误差验证；
- 以 raw element/DoF reduction 冒充 same-error compression。

---

## 4. 冻结基线与数据身份

### 4.1 主要参考

Task035 使用 Task034 已接受证据：

| 角色 | 案例 | 边界 |
|---|---|---|
| fixed-p main adaptive baseline | p4/h5 Full3D S MPI8 | 约 339,972 rows；best available Case093 discrete reference，不是 continuum |
| same-degree Hybrid anchor | p4/h5 Hybrid selected M | closure pass；空间与 M 误差均已审查 |
| independent finer-degree reference | p3/h3 Full3D S MPI8 | finer discrete reference；与 p4/h5 不同 p/h |
| p3 adaptive candidate | p3/h5 或 p3/h7.5 | 由 Task034 accuracy/cost 决定 |
| low-cost estimator fixture baseline | p2/h5、p2/h3 | 资源低，适合多方法筛选 |
| fine diagnostic only | p4/h3 Hybrid M160 | 无 M funnel、无同点 Full3D closure，不是 official reference |
| external qualitative check | 用户 COMSOL 结果 | 软件/网格/solver 不同，不作为 FEniCS formal Gate |

### 4.2 双层精度判定

Adaptive candidate 必须同时通过：

#### Replacement Gate

相对 p4/h5 Full3D 的全部 observable 不超过冻结容差，证明可以替代 uniform p4/h5。

#### Direction/independence Gate

相对 p3/h3 Full3D 和 p4/h3 Hybrid diagnostic 的误差趋势不得明显恶化。该 Gate 只用于防止 candidate 复制 p4/h5 离散偏差，不升级为 continuum truth。

### 4.3 数据身份

每个结果明确标记：

```text
measured
derived
predicted
diagnostic
not_run
controlled_negative
failed
```

---

## 5. 总体执行顺序

```text
Phase A  environment/base/evidence qualification
Phase B  estimator mathematical definitions and fixtures
Phase C  estimator bake-off
Phase D  mesh-backend bake-off
Phase E  low-cost p2/p3 adaptive loops
Phase F  p4/h5 S Full3D adaptive mainline
Phase G  selected Hybrid adaptive + M/DtN error split
Phase H  recovery/equilibrated independent verification
Phase I  global-p and conditional hp strategy
Phase J  1°/5°/10° S robust common mesh
Phase K  benchmark freeze, project docs and next architecture decision
```

每阶段有 stop Gate；不允许因任务范围大而跳过 fixture 直接跑重型模型。

---

# Phase A：环境、基线与 clean evidence

## A1. WSL 重新资格化

复用 Task034 工具，但必须在 Task035 branch SHA 下重新记录：

- Ubuntu/WSL/kernel；
- CPU、NUMA、内存、swap；
- Python、MPI、PETSc/SLEPc、DOLFINx/Basix/UFL；
- complex128；
- MPI1/2/4/8；
- MUMPS、SLEPc PEP；
- source clean/stable；
- `benchmarks/artifacts` 是否可用及其 hash inventory。

环境失败时停止所有 formal PDE。

## A2. Task034 baseline binding

建立机器可读 base manifest，绑定：

- Task034 final master SHA；
- Case093 compact records；
- p4/h5 Full3D/Hybrid records；
- p3/h3 reference；
- M funnel；
- current material/geometry/config identity；
- Task035 theory document SHA。

## A3. artifact 规则

Task035 的普通测试和 checker 必须 clean-checkout hermetic。重型 field/mesh 只可作为正式运行输入，并由 tracked descriptor/hash 绑定；缺失时明确 `artifact_not_materialized`，不得静默使用其他文件。

输出：

```text
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/environment_and_base.md
benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/base_manifest.json
```

---

# Phase B：Estimator 定义与解析 fixture

## B0. 方法清单和状态机

为每种候选建立状态：

```text
not_started
formula_defined
fixture_pass
fixture_negative
real_case_screen_pass
real_case_negative
heavy_candidate
stopped
```

候选至少包括：

```text
R1 standard residual/jump
R2 frequency-scaled residual
R3 recovery H(curl)
R4 equilibrated patch estimator
R5 hierarchical/two-level estimator
G1 DWR total R/T/A
G2 DWR R00/order amplitudes
B1 DtN truncation split
M1 internal mode truncation split
```

## B1. 强制 fixture

至少建立四类：

### Fixture 1：homogeneous periodic analytic field

验证：

- volume residual；
- face jump；
- periodic phase residual；
- 高阶 orientation；
- MPI identity。

### Fixture 2：flat lossy layer / known modal solution

验证：

- complex material weighting；
- R/T/A goal derivatives；
- DtN boundary residual；
- uniform refinement error trend。

### Fixture 3：material interface / corner singularity

验证：

- interface term；
- anisotropic marking；
- recovery/equilibrated estimator 对 coefficient jumps 的表现。

可使用 manufactured solution 或可审查的 simplified geometry，但必须明确不等于目标光栅。

### Fixture 4：Hybrid analytic mode/interface

验证：

- interface Et/Ht residual；
- spatial error与 M truncation 分离；
- QEP/eigen residual 不被误计为空间 residual。

## B2. 每个 estimator 的最低 Gate

- finite、nonnegative；
- serial/MPI global sum identity；
- cell global ID canonical；
- 网格均匀加密后 estimator 总量呈合理下降；
- 精确/制造解误差为零时 estimator 接近数值舍入；
- 故意破坏 face orientation、material tag、periodic phase 或 DtN truncation 时能检测；
- 不使用 full-vector gather 或 dense global cell square；
- 复数共轭和伴随定义通过独立有限差分/complex-step directional derivative 检查。

输出：

```text
outcomes/estimator_definitions.md
outcomes/fixture_matrix.csv/json
benchmarks/cases/094.../records/fixture_summary.json
```

---

# Phase C：Estimator bake-off

## C1. 第一优先低成本候选

先比较：

```text
R1 standard residual
R2 frequency-scaled residual
R5 hierarchical/two-level
G1 DWR R/T/A/R00
B1 DtN split
```

R3 recovery 与 R4 equilibrated 在 C1 后作为独立校验，不先阻塞主线。

## C2. 比较指标

在 p2/h5、p2/h3 和一个 p3 coarse point 上：

- effectivity index；
- cell indicator 与 reference local-error proxy 的 Spearman/Pearson correlation；
- top marked cells overlap；
- refinement 后 observable error reduction；
- estimator assembly memory/time；
- MPI partition stability；
- 对 R/T/A、R00、主要衍射级是否给出不同标记。

数值相关系数只作 screen，不单独决定通过。Mandatory Gate 是：标记并 refinement 后，预定目标误差必须下降，且其他关键 observable 不出现隐藏失效。

## C3. 选择规则

进入真实 adaptive 的主 estimator 最多两个：

```text
one energy/residual-oriented
one goal-oriented or two-level
```

若所有 estimator 都无法在 fixture 和低成本 point 上预测 error reduction，停止 heavy adaptive，保留负结果并定位理论/实现问题。

---

# Phase D：Mesh backend bake-off

## D1. 现有 strip/tensor 路径作为 negative control

保留 Task034 mechanism，但只用于说明：

- topology/periodic matching 可行；
- 局部标记被轴向扩展的代价；
- 不称 genuine local adaptive。

## D2. multi-block conforming hexa regeneration

实现或扩展通用 `src/geometry/` 模块，不得继续放在 task-numbered benchmark 脚本。

要求：

- 真正局部 block；
- x/y periodic mates 同步；
- 双周期角/边/面 signature 一致；
- material planes exact；
- bottom/top Hybrid interface exact；
- no hanging nodes，除非另有完整 H(curl) 约束资格化；
- positive Jacobian；
- 2:1 或经审查的尺寸过渡；
- deterministic plan hash；
- MPI repartition 和 ghost layer 正确。

## D3. anisotropic directional candidates

每个 marked block 至少支持候选：

```text
x
y
z
xy
xz
yz
xyz
```

方向选择来自 directional defect、reference projection 或局部候选 solve，不得写死“所有角点只细 x/z”。

## D4. metric/size-field regeneration

调查 Gmsh/自定义 multi-block size field。若无法保证周期两侧同拓扑，保持 diagnostic，不进入正式主线。

## D5. tetrahedral control lane

使用 DOLFINx 已有 marked simplex refinement 建立低成本 control，只用于验证 estimator/marking。它不替代 hexa production，不与 hexa DoF 做不加说明的比较。

## D6. backend 选择

选择主 backend 时比较：

- locality；
- DoF overhead；
- mesh quality；
- periodic/matching complexity；
- H(curl) orientation；
- assembly/factor fill；
- field transfer；
- reproducibility。

若没有一个 backend 能产生真正局部且 conforming 的 hexa mesh，Task035 可得出 `hexa_backend_blocker`，但仍应完成 tetra control 以判断 estimator 是否正确。

---

# Phase E：p2/p3 低成本 adaptive cycles

## E1. 自适应循环

```text
SOLVE
→ ESTIMATE
→ MARK
→ PERIODIC/MATERIAL/INTERFACE CLOSURE
→ REBUILD MESH
→ REQUALIFY FLOQUET/DtN
→ SOLVE
→ COMPARE
```

至少 3 个 cycle，最多 6 个；满足停止条件可提前结束。

## E2. marking screen

主线 `Dörfler theta=0.5`，低成本比较 `0.3/0.7`。禁止在重型 p4 上遍历大量 theta。

## E3. p2/p3 决策

- p2 用于 estimator/mesh 快速迭代；
- p3 用于检验高阶稳定性；
- 只有 p2/p3 中至少一个 sequence 显示真实 observable error 下降，才进入 p4。

输出每 cycle：

```text
mesh hash
cells/DoF/rows/NNZ/factor
indicator totals/components
marked-set hash
R/T/A/A_volume/R00/orders
field/interface errors
residual
memory/time
```

---

# Phase F：p4/h5 S Full3D adaptive 主线

## F1. 起点

起始离散为 Task034 p4/h5 Full3D S MPI8。不得把 p4/h3 Hybrid diagnostic 当作 continuum truth。

## F2. 候选主线

至少运行：

1. selected residual/two-level estimator；
2. selected DWR/multi-goal estimator；
3. 若二者标记差异大，一个 combined robust candidate。

每条主线最多 4 个 heavy adaptive cycle，one-heavy-case-at-a-time。

## F3. 物理 Gate

每轮：

- full explicit true residual `<=1e-9`；
- official R/T/A 只从 pass field 产生；
- R/T/A/A_volume；
- R00_s/R00_p/R00_total；
- significant order powers and complex amplitudes；
- selected-plane E/H；
- interface Et/Ht；
- energy closure；
- source/env/memory/swap。

## F4. 压缩分类

uniform p4/h5 约 340k rows。只在全部 same-error Gate 通过后分类：

| adaptive total rows | 分类 |
|---:|---|
| `>300k` | mechanism only / no useful compression |
| `220k–300k` | useful signal |
| `150k–220k` | clear engineering success |
| `100k–150k` | strong result |
| `<100k` | exceptional；必须增加独立误差审计 |

这些是结果分类，不是允许放宽误差的目标函数。

## F5. 内存与时间

必须实测，不能按 DoF 线性推断。局部不规则网格可能减少 DoF但增加 MUMPS fill；同时记录：

- assembly peak/time；
- factor peak/NNZ/setup；
- solve；
- total；
- mesh/partition imbalance。

---

# Phase G：Hybrid adaptive 与 M/DtN 分离

## G1. 选点

只选 F 阶段最好的 1–2 个 mesh。不得对每个失败 cycle 运行完整 M funnel。

## G2. 接口策略

优先保持 bottom/top matching interface trace topology 固定，将 refinement 放在 interface 外部。若 estimator 明确要求接口细化：

- 同步重建 bottom/top interface；
- 重建 2D matching cross-section/QEP；
- 重新做 mode classification/tracking；
- 重新做 M funnel；
- 不复用不兼容缓存。

## G3. M funnel

```text
M80
M120
M160
M240 only if M120→M160 fails solely on modal convergence
```

同时记录 external DtN order funnel。空间、external DtN、internal M 三类 Gate 分开。

## G4. same-degree closure

若 adaptive Full3D reference 存在，必须做 same-degree Full3D–Hybrid closure；若 Full3D 因资源停止，则只能称 Hybrid measured result，不称 closure。

## G5. Hybrid 成功判定

除了物理误差，还比较：

- local 3D FE DoF；
- total rows；
- QEP DoF；
- M；
- interface projection；
- factor inventory；
- field recovery memory/time。

---

# Phase H：Recovery/Equilibrated 独立验证

## H1. recovery estimator

实现 global cheap recovery 或 local patch recovery 的最小可行版本，至少在 material-interface fixture 和一个 selected real mesh 上与主 estimator 对照。

## H2. equilibrated estimator

先在正定/mixed curl-curl fixture 实现 patch constrained minimization。只有 fixture 的 guaranteed/efficiency 行为可信，才尝试 time-harmonic real case；否则保留理论和 controlled negative。

## H3. 独立审计

若主 estimator 和 recovery/equilibrated 对高误差区域判断一致，增加可信度；若不一致，必须解释梯度核、材料权重、boundary/interface 或 goal localization 差异。

R3/R4 失败不自动否定已经通过真实 error reduction Gate 的主 adaptive sequence，但必须保留局限。

---

# Phase I：global-p 与条件 hp

## I1. global-p comparison

对 selected adaptive strategy 分别运行可承受的：

```text
p2 adaptive
p3 adaptive
p4 adaptive
```

比较同误差的 DoF、rows、NNZ、factor、memory、time。不得预设 p4 必然最优。

## I2. smoothness sensor

实现 projection defect 或 hierarchical coefficient decay，并在：

- analytic smooth field；
- material interface；
- corner singularity；
- high-frequency unresolved field；

上验证 h/p 判别方向。

## I3. local variable-p capability audit

按顺序：

1. 两个相邻 hexa unequal-p trace conformity；
2. edge/face orientation；
3. periodic mate unequal-p Floquet；
4. MPI ownership；
5. Hybrid interface trace；
6. source-clean tests。

任何 mandatory Gate 失败：

```text
local_variable_p = not_qualified
```

并停止真实 variable-p PDE。不得编写隐藏的非共形近似制造 hp 成功。

## I4. hp candidate competition

只有 I3 通过才实现 reference-solution candidate competition；否则 Task035 的正式 hp 结论局限为 global-p + h-adaptivity。

---

# Phase J：S 偏振 robust common mesh

## J1. 解锁条件

- 10° S 至少一个 field-driven adaptive sequence pass；
- selected estimator/mesh backend 冻结；
- p4 或 selected p 的 same-error compression 有 measured decision；
- MPI8 可重复。

## J2. 参数点

```text
1° / 5° / 10° grazing
S incidence
```

每点低成本估计后形成：

$$
\eta_K^{\mathrm{robust}}
=
\max_j \frac{\eta_K(\mu_j)}{\tau_j+s_j}.
$$

## J3. 验证

在同一个 common mesh 上重新求解三个角度并通过各自 physical Gate。不得用三个独立 adaptive mesh 冒充 common mesh。

## J4. P 边界

Task035 不要求完整 P 矩阵。S common mesh pass 后，可运行一个 p2/p4 coarse P capability 或直接移交后续任务。

---

# Phase K：Case094、项目文档与下一步

## K1. 新 benchmark

```text
benchmarks/cases/094_hcurl_goal_oriented_adaptivity/
```

至少包含：

```text
README.md
config.json
schema.json
expected.json
test_command.txt
records/estimator_fixture_summary.json
records/mesh_backend_summary.json
records/adaptive_cycle_summary.json
records/p4_same_error_summary.json
records/hybrid_modal_error_split.json
records/common_mesh_summary.json (if run)
records/canonical_manifest.json
```

## K2. 统一事实表

建立每 cycle 一行的 tracked CSV/JSON，字段至少：

```text
method/estimator/backend/cycle
p/h distribution/M/MPI
cells/DoF/aux/modal/rows/NNZ/factor
indicator components/effectivity/marked hash
R/T/A/A_volume/R00/orders/fields/interfaces
residual/memory/timings
reference/error/qualification/evidence
```

普通 tests 必须 clean-checkout hermetic，不依赖 gitignored artifact 实体。

## K3. 项目文档

必须更新：

```text
docs/development_progress.md
docs/capability_matrix.md
docs/project_service_requirements_and_forward_model_roadmap.md
docs/README.md
docs/benchmark.md
notes/theory/README.md
notes/reference/code_walkthrough.md
notes/reference/current_version_boundaries.md
```

能力声明必须区分：

```text
graded mesh mechanism
field-driven h-adaptivity
goal-oriented adaptivity
anisotropic mesh
local variable-p
hp-adaptivity
robust common mesh
```

## K4. 后续架构决定

Task035 最终必须决定：

1. 是否已获得可用于 0.7 nm 资源模型的 measured same-error compression；
2. hexa mesh backend 是否足够，还是需要新 mesh/constraint architecture；
3. local variable-p 是否值得继续；
4. 下一任务应优先 scalable modal core 还是 low-memory local iterative solver；
5. 是否有资格更新 5/2/1/0.7 nm 资源 envelope。

---

## 6. 统一停止条件

任一 lane 出现以下情况立即停止后续重型步骤：

- estimator fixture 不通过；
- estimator 在 refinement 后目标误差不降；
- periodic mate topology 不一致；
- material/matching planes 不精确；
- negative Jacobian 或 mesh quality 失败；
- 未资格化 hanging-node/unequal-p 约束；
- full true residual 失败；
- official R/T/A 无法生成；
- 关键 observable 恶化；
- MPI identity 失败；
- memory/swap/disk/time 达 termination；
- M/extern DtN convergence 未通过；
- clean source、environment 或 evidence Gate 失败。

失败结果必须保留，不得通过：

- 放宽容差；
- 删除难以收敛的 diffraction order；
- 只看总 R/T/A；
- 更换 reference 后不说明；
- 隐藏失败 cycle；
- 将 diagnostic p4/h3 Hybrid 变成 continuum truth；

制造通过。

---

## 7. 资源保护

- one-heavy-case-at-a-time；
- p4 每轮先 mesh/DoF/assembly prediction；
- direct 大点继续按 assembly → factorization-only → full solve Gate；
- no job/process-tree swap；
- WSL/host global swap 只作 diagnostic；
- 每个 estimator 记录自身额外内存和耗时；
- adjoint/DWR 不得与 forward 大对象无控制同时驻留；
- local patch solves 必须分批、可释放；
- 原场、mesh、matrix、factor、timeline 只存 ignored artifacts。

---

## 8. 测试要求

至少覆盖：

1. estimator exact-zero / manufactured fixture；
2. complex conjugation 与 adjoint directional derivative；
3. volume/jump/material/DtN/interface 分项；
4. frequency scaling；
5. MPI canonical cell ID 和 reduction；
6. Dörfler marking；
7. periodic mate marking closure；
8. directional split candidate；
9. material/matching-plane preservation；
10. mesh quality/Jacobian；
11. no hanging nodes；
12. tag transfer/rebuild；
13. Floquet requalification after rebuild；
14. field transfer only used as initial guess；
15. DtN/M error split；
16. clean-checkout evidence aggregation；
17. failure injection；
18. variable-p fail-closed audit；
19. documentation rendering；
20. ordinary uniform default unchanged。

最终至少运行：

```text
focused pure-Python tests
DOLFINx native complex tests
MPI2/MPI4 component tests
selected MPI8 adaptive tests
Task032/Task033/Task034 regression
Task035 tests
Ruff
compileall
git diff --check
git status --short --untracked-files=all
```

没有 GitHub Actions 时只能报告本地测试。

---

## 9. 必交付文件

```text
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/environment_and_base.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/estimator_definitions.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/fixture_matrix.csv
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/estimator_bakeoff.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/mesh_backend_bakeoff.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/p2_p3_adaptive.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/p4_adaptive_mainline.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/hybrid_modal_error_split.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/recovery_equilibrated_audit.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/hp_capability.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/robust_common_mesh.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/all_adaptive_cycles.csv/json
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/negative_results.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/test_summary.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/changed_files.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/selective_merge_manifest.csv
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md
docs/task035_hcurl_goal_oriented_adaptivity/response_v1.md
```

未运行文件必须写 `not_run`/`stopped_by_gate`，不能空白冒充完成。

---

## 10. 完成判定

Task035 的 workflow 可在正结果或受控负结果下完成，但最低要求：

```text
literature/method matrix complete
at least residual + goal/two-level estimators receive fixture decisions
at least two mesh backends receive measured decisions
p2/p3 low-cost adaptive receives measured decisions
p4/h5 S receives a controlled adaptive decision
spatial/DtN/M error budgets are separated
all official positives pass full true residual
all negatives and stopped lanes preserved
ordinary default unchanged
project docs synchronized
```

允许状态：

```text
PASS
PASS_WITH_QUALIFICATIONS
PARTIAL_WITH_CONTROLLED_NEGATIVES
FAIL
```

“代码存在”“网格更少”“indicator 有数值”或“R+T+A=1”均不构成 adaptive pass。

---

## 11. 审查与合并

Codex 完成后：

1. 推送 Task035 执行分支；
2. 提交 `response_v1.md`；
3. 给出精确 HEAD、base SHA、环境、测试、重型 evidence 与 clean-checkout checker；
4. 停止等待 ChatGPT review；
5. 不自行合并 `master`。

ChatGPT 的所有 review 直接提交同一个 Task035 分支。只有最终 review approval 且用户授权后，Codex 才按最终 manifest选择性合并到 `master`。

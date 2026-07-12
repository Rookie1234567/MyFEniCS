# REVIEW REPORT V3：Task028 最终文档深度、Benchmark 证据与 2D 有损端口修复审查

## 1. 审查对象

```text
repository = Rookie1234567/MyFEniCS
branch = codex/20260712-task28-stage-consolidation
base = master@0465b5f0e79046bcd82741d7396ba1c87f5a2606
review_chain = review_report_v1 -> response_v1 -> review_report_v2 -> response_v2 -> review_report_v3
review_scope = source code + main.py presets + Quick Start + Code Walkthrough + Theory + numbered Benchmark cases + records/checker
```

本轮重点审查 Response V2 新增和修改的内容：

```text
- src/main.py 命名 preset 与 PyCharm 工作流；
- 2D complex refractive-index CLI；
- 2D lossy DtN mode selection 与端口功率修复；
- 3D direct / MUMPS OOC / BLR profile；
- Quick Start 分层；
- Code Walkthrough 拆分；
- Theory 文档体系；
- benchmarks/cases 编号功能目录；
- benchmark metadata 与 automatic checker；
- Response V2 tests / run evidence。
```

Task026/Task027 已通过的核心凝聚算子、physical-slab PC 和 h=5/3/2 现有数值结果没有被本轮否定。

---

# 2. 审查结论

```text
review_status = changes_required

Task026_Task027_core_solver = pass
existing_3d_canonical_results = pass
selective_integration = pass
ordinary_default = pass
repository_work_principles = pass
main_preset_dispatch_framework = pass
complex_index_cli = pass
benchmark_checker_existing_records = pass
metadata_provenance = pass
Stage2B_Stage2C_honest_status = pass

two_d_lossy_port_fix = pass_with_canonical_evidence_required
main_preset_physical_identity = partial_fail
pycharm_mpi4_workflow = partial_fail
quick_start_depth = fail
code_walkthrough_accuracy = fail
code_walkthrough_depth = fail
benchmark_case_structure = partial_fail
benchmark_case_evidence = fail
benchmark_documentation_contract = fail

theory_docs = pass_with_minor_corrections
environment = pass_with_qualification
master_merge = not_yet
```

准确结论是：

> Response V2 已建立正确的五层文档目录、PyCharm preset 框架和编号 Benchmark 索引，并修复了一个真实的 2D 有损端口功率问题；但当前多数 Quick Start 和 Benchmark case 仍是速查卡或摘要表，Code Walkthrough 中还存在与源码不一致的技术描述，因此尚未达到“新用户可按文档理解代码、修改参数、运行功能并复核结果”的交付标准。

本轮不要求重新运行 h=2，不重新研究 Task27 求解器，也不启动 Task29。

---

# PART I：本轮已经接受的内容

## 3. `main.py` preset 框架方向正确

以下内容通过：

```text
- 无参数 PyCharm Run 默认进入轻量 3D Stage1；
- ACTIVE_PYCHARM_PRESET 是唯一默认选择器；
- --list-presets / --preset NAME 可用；
- preset 只翻译成真实 runner 参数，不复制 solver；
- 2D/3D preset 均被真实 parser contract test 覆盖；
- 普通 main 不静默启动 MPI4 iterative；
- ordinary solver default 仍是 direct。
```

当前 15 个命名 preset 的存在本身可以接受。

## 4. 2D 复折射率输入通过

`run_cases.py` 支持以下形式：

```text
1.45
0.999+0.002j
0.999+0.002i
```

这是必要的入口修复。Quick Start、参数地图和 capability matrix 应继续说明：

```text
- n 输入是折射率；
- epsilon_r = n^2；
- 当前 exp(-i omega t) 约定下，正 Im(epsilon_r) 表示吸收；
- 外部材料数据库的符号约定必须先核对。
```

## 5. Direct / OOC / BLR 分类通过

以下命名和分类正确：

```text
default
mumps_ooc
mumps_blr
```

BLR 必须继续描述为 compressed direct / inexact factorization fallback，而不是“迭代法 1”。

## 6. Benchmark checker 对现有 3D canonical records 的增强通过

以下 Gate 已正确补入：

```text
- benchmark_id matches manifest；
- metadata complete；
- commit relation；
- actual source command/root 与 canonical rerun command/root 分离；
- qualified_profile；
- ksp_reason > 0；
- coarse condition；
- physical_model；
- reported / condensed / full residual；
- R/T/A 与 energy closure；
- direct / iterative delta；
- h2 RSS；
- h5/h3/h2 iteration ratio。
```

现有 h=5/3/2 的 3D records 仍可信，87/87 只表示当前 checker 覆盖的 canonical suite 通过，不代表新增 13 个功能 case 全部已有运行记录。

## 7. Stage2B / Stage2C 状态已纠正

当前标记：

```text
Stage2B PML = experimental
Stage2C Fresnel = experimental
```

是正确的。代码路径和 smoke 已存在，但精度资格尚未关闭。

## 8. Theory 文档总体通过

以下理论主线已形成：

```text
- Maxwell 强式/弱式；
- 2D TM/TE；
- Nedelec H(curl)；
- Floquet；
- PML / Robin；
- DtN modal port；
- explicit / auxiliary；
- augmented system 与 exact condensation；
- official / diagnostic R/T/A；
- direct / OOC / BLR；
- FGMRES / physical slabs / coarse / sm2；
- 研究负结果边界。
```

Theory 可继续保留当前结构，只需完成 PART VIII 的小修。

---

# PART II：2D 有损端口修复

## 9. 修复方向通过

Response V2 修复了两个相互关联的问题：

### 9.1 有损传播模态误判

有损半空间的传播常数 `beta` 通常是复数，因此不能使用：

```text
Im(beta) == 0
```

作为传播判据。

新逻辑使用：

```text
Re(beta) > 0
Re(beta^2) / dispersion real part
Rayleigh tolerance
```

区分有损传播阶与截止倏逝阶，方向正确。

### 9.2 功率必须使用实际端口平面系数

对于有限有损层，功率应根据实际 port plane 的 coefficient 计算：

```math
P_m = L_x \frac{\operatorname{Re}Y_m}{2}|a_m(y_{port})|^2.
```

相位归一化回 reference plane 的 amplitude 可以用于报告相位和界面等效幅值，但不能替代实际平面功率，否则会消除真实传播衰减并与 `A_volume` 重复计数。

## 10. 当前证据不足以直接作为最终 production regression

目前已经有：

```text
- helper unit tests；
- TM complex smoke；
- TE complex smoke；
- run_log 中的 residual / R / T / A_volume / closure；
- gitignored 完整结果目录。
```

但是，这些真实 smoke 结果尚未形成 canonical lightweight records，Case 003 仍写“无 record”。因此必须完成以下闭环。

## 11. P0-1：冻结 2D lossy canonical records

建议新增：

```text
benchmarks/cases/003_2d_te_tm_complex_absorption/records/
├── tm_complex_absorption.json
└── te_complex_absorption.json
```

每份 record 至少包含：

```text
benchmark_id
case_id
polarization
physical_model
resolved_config
actual command
commit / branch / dirty
container image / digest
mesh / DoF
solver backend
linear true residual
R / T / A_balance / A_volume
R+T+A_volume
auxiliary / trace difference（若适用）
probe closure（明确 diagnostic）
elapsed time / RSS
artifact path / provenance
```

## 12. P0-2：将 lossy Gate 加入 automatic checker

至少检查：

```text
TM residual <= agreed tolerance
TE residual <= agreed tolerance
R >= 0, T >= 0, A_volume >= 0
abs(1 - R - T - A_volume) <= tolerance
abs(A_balance - A_volume) <= tolerance
TM auxiliary-vs-trace delta <= tolerance
probe result remains diagnostic and is not used to overwrite official
```

建议 tolerance 根据真实 smoke 数值设定，而不是随意使用机器零：

```text
linear residual <= 1e-10
energy closure <= 1e-8
auxiliary / trace <= 1e-8
```

若实际稳定性支持更严阈值，可以使用更小值。

## 13. P0-3：补 lossless regression

有损修复不能破坏既有无损逻辑。至少保留或新增：

```text
zero contrast: R≈0, T≈1
lossless flat interface: R+T≈1
below-cutoff order: no power
lossy propagating order: carries real power
```

## 14. 需要明确影响范围

`changed_files.md`、summary 和 version boundaries 应明确写：

> Response V2 改变了 2D lossy DtN / probe modal power 的数值口径；无损路径保持回归通过，3D Task27/28 official R/T/A 代码未因该 2D 修复重算。

避免用户误以为 h=5/3/2 的 3D records 已被本轮重新计算。

---

# PART III：PyCharm preset 与真实物理身份

## 15. 当前问题：Stage4 demo preset 被命名成 target-like preset

当前：

```text
3d_stage4b_grating_direct_h5
3d_stage4b_grating_direct_h3
```

实际使用的 `Stage4GratingInputs3D` 是一套 100 x 100 nm、50 nm block、normal-incidence demo；Task27/28 target 则是 50 x 25 x 140 nm、17 x 25 x 120 nm、80° s-polarized case。

因此现有名字容易让用户误以为：

> 在 PyCharm 运行 `direct_h5` 等价于重现 Benchmark 021 h=5。

实际上不是。

## 16. P0-4：拆分 demo preset 与 target preset

至少采用以下一种明确设计。

### 推荐方案

```text
3d_stage4b_demo_direct_h5
3d_stage4b_demo_direct_h3
3d_stage4b_demo_mumps_ooc
3d_stage4b_demo_mumps_blr

3d_target_grating_direct_h5
3d_target_grating_direct_h3
```

其中 target preset 必须直接复用或严格对齐：

```text
stage4_runtime.target_stage4_config
```

而不是复制另一套参数。

### 可接受替代方案

如果不希望将 target direct 放入普通 `main.py`，则必须：

```text
- 将现有名称全部改成 demo_*；
- 在 Quick Start 中明确 target 只能通过 Benchmark 021 的 CLI/config 运行；
- 文档禁止把 demo h5/h3 结果与 target h5/h3 records 对比。
```

## 17. P0-5：资源安全说明

每个 Stage4 preset 都应在 preset 描述或 `--list-presets --verbose` 输出中注明：

```text
physical geometry
mesh size
p order
expected resource class
whether canonical / demo / experimental
```

尤其 `p=2, h=3` 可能很重，不应只凭名字让初学者直接运行。

---

# PART IV：PyCharm MPI4 iterative 工作流

## 18. 当前问题

`40_3d_workstation_iterative.md` 只给出了 shell 命令，尚未说明如何在 PyCharm 中建立 MPI4 运行配置。

“不能由普通单进程 main 静默启动”是正确原则，但不能替代 PyCharm 使用说明。

## 19. P0-6：增加 PyCharm External Tool / Run Configuration 教程

至少提供一种真实可执行方案。

### 方案 A：PyCharm External Tool

说明：

```text
Program
Arguments
Working directory
Environment variables
Docker/WSL executable
MPI launcher
record path
artifact path
```

### 方案 B：PyCharm Python/Module + MPI wrapper

说明如何配置：

```text
module = benchmarks.run_workstation_iterative
parameters = --config ... --h-nm ... --record ...
interpreter = qualified container/WSL interpreter
before launch / wrapper = mpiexec -n 4
working directory = repository root
```

必须明确：

```text
- 普通 Python Run 是单进程，不具备 MPI4 qualification；
- 不在 Python 进程内部静默 spawn MPI；
- 不覆盖 canonical record 做参数扫描；
- 非 canonical 参数自动标记 experimental。
```

---

# PART V：Quick Start 深度

## 20. 当前问题

`notes/quick_start/` 的目录规划正确，但许多文件只有 11–45 行，属于速查卡，不是可跟随教程。

例如当前文档通常只包含：

```text
one command
few parameters
one success statement
links
```

仍无法让第一次接触项目的人完成：

```text
打开 main.py
找到对应 preset/dataclass
理解每个参数
修改自己的几何/材料/角度
运行
找到输出
读取 residual/RTA
打开 ParaView
判断是否越出 qualification
```

## 21. P0-7：核心 Quick Start 必须扩展成可跟随教程

以下文档为核心主线，必须优先扩展：

```text
00_environment_and_pycharm.md
01_main_py_parameter_map.md
02_results_and_paraview.md
10_2d_pml_floquet.md
11_2d_dtn_floquet.md
12_2d_te_tm_and_complex_material.md
13_2d_diffraction_and_rta_methods.md
20_3d_stage1_airbox.md
21_3d_stage2a_floquet.md
22_3d_stage2b_pml.md
23_3d_stage2c_fresnel.md
30_3d_stage4a_flat_layer.md
31_3d_stage4b_grating_direct.md
32_3d_direct_ooc_blr.md
40_3d_workstation_iterative.md
```

每篇至少包含：

```text
1. 功能与物理图景
2. 当前能力状态
3. 运行前提
4. PyCharm preset / Run Configuration
5. main.py 中实际修改位置
6. 完整参数块示例
7. 参数含义、单位、合法值、资格影响
8. CLI 等价命令
9. 真实调用链
10. 输出目录树
11. 关键 JSON 字段
12. ParaView 文件和显示步骤
13. 成功 Gate
14. 常见错误及原因
15. 如何从 smoke 改成自己的 case
16. Theory / Walkthrough / Benchmark 链接
```

## 22. Quick Start 不应复制完整理论或全部结果

可以写：

```text
关键公式
预期 residual 量级
预期能量关系
典型时间/RSS
```

完整推导链接 Theory，完整数值表链接 Benchmark records。

---

# PART VI：Code Walkthrough 技术准确性

## 23. 当前存在的明确错误

### 23.1 `SparseCoarseVector` 字段错误

文档当前写成类似：

```text
SparseCoarseVector(indices, values, global_size)
```

实际源码字段为：

```text
indices
values
slab
eigenvalue
eigenpair_residual
```

必须修正。

### 23.2 两级 PC apply 顺序写反

文档当前描述成：

```text
coarse correction -> residual -> smoother
```

实际源码是：

```text
smoother(source)
-> residual = source - A*approximation
-> coarse correction
-> optional post-smooth
```

必须按源码和公式重新解释。

### 23.3 `SmallDenseInverse` 描述不准确

当前实现不是 LU factorization，而是：

```python
H_inverse = np.linalg.inv(H_dense)
```

文档必须诚实写为“显式构造小型 dense inverse”，并标记这是非阻断技术债。

### 23.4 explicit PETSc condensation 限制缺失

`build_explicit_condensed_operator` 当前只支持已验证的：

```text
H = I
```

若 H 非单位块会抛出 `NotImplementedError`。Walkthrough 和 Solver Guide 必须说明该限制，不能写成任意 H 的通用显式分布式实现。

## 24. P0-8：修正全部已知技术错误

至少修正：

```text
notes/reference/code_walkthrough/31_exact_condensation.md
notes/reference/code_walkthrough/32_physical_slab_two_level_pc.md
notes/reference/code_walkthrough/33_workstation_fgmres_runtime.md
notes/theory/dtn_modal_ports_and_condensation.md
```

并在 `response_v3.md` 中列出逐项前后对照。

---

# PART VII：Code Walkthrough 深度

## 25. 当前问题

虽然已拆成 15 篇，但多数仍是 30–40 行函数职责摘要。用户目标是：

> 沿着文档打开源码，理解一个功能为什么存在、配置如何流入、数组/矩阵尺寸如何变化、公式如何对应到具体函数、最终结果字段如何形成。

当前深度仍不足。

## 26. P0-9：核心 Walkthrough 必须扩展

优先扩展以下主线：

```text
01_main_and_runner_dispatch.md
11_2d_floquet_pml_port_forms.md
12_2d_dtn_and_rta_postprocess.md
20_3d_staged_architecture.md
21_3d_floquet_and_pml.md
22_3d_dtn_augmented_system.md
23_3d_rta_and_field_reconstruction.md
30_direct_solver_profiles.md
31_exact_condensation.md
32_physical_slab_two_level_pc.md
33_workstation_fgmres_runtime.md
```

每篇必须包含：

```text
- 文件路径；
- 关键类/函数签名；
- 调用者与被调用者；
- 输入对象及 shape / global size；
- 输出对象；
- 主要 PETSc/DOLFINx 所有权；
- 关键公式；
- 公式到代码语句的映射；
- 一次真实调用顺序；
- 测试与 benchmark；
- official / diagnostic / research-only 身份；
- 当前限制。
```

## 27. 3D DtN Walkthrough 必须沿一个模式完整追踪

至少完整解释一次：

```text
(m,n,polarization)
-> alpha/gamma/beta
-> modal E/H and power normalization
-> surface vector
-> traction
-> C/D/H block
-> incident RHS
-> augmented solve
-> auxiliary amplitude
-> official R/T
```

## 28. 迭代 Walkthrough 必须说明对象尺寸

至少给出 target h=5 示例：

```text
n_fe
n_aux
F/C/D/H sizes
condensed operator size
coarse basis count
physical slab count
owner distribution
outer KSP / inner KSP roles
reported / condensed / full residual locations
```

无需逐行解释所有源码，但必须足以让用户跟踪。

---

# PART VIII：Theory 小修

## 29. P1-1：增加统一符号表

建议在 `notes/theory/README.md` 或单独文件中统一：

```text
2D coordinates x/y
3D coordinates x/y/z
normal direction
time convention
incident direction
top/bottom outgoing convention
alpha, gamma, beta
TE/TM/s/p
F/C/D/H
R/T/A
```

## 30. P1-2：修正公式排版与代码锚点

例如 2D TM 弱式中的逗号应修正；代码引用应优先精确到：

```text
module::function
```

避免只写文件名。

## 31. P1-3：明确 2D 与 3D 功率常数差异

Theory 应说明项目在不同模块中省略了哪些公共常数，为什么归一化后仍一致，以及哪些字段不能直接跨 2D/3D 比较绝对值。

---

# PART IX：Benchmark case 架构

## 32. 当前问题

`benchmarks/cases/` 已建立 13 个目录，但每个基本只有一张约 22 行的摘要表。

V2 要求的以下文件没有真正建立：

```text
config.json
expected.json
run.sh
records/
```

现有文档 contract test 只检查 README 是否出现 `1.` 到 `22.`，无法验证内容深度、命令可运行性和 record 完整性。

## 33. P0-10：为每个 case 建立真实 case-contained contract

### 对 recorded case

至少包含：

```text
README.md
config.json
expected.json
run.sh
records/
```

Recorded cases 至少包括：

```text
002
003
010
021
031
```

### 对 test-backed case

至少包含：

```text
README.md
expected.json
run.sh 或 test_command.txt
```

并明确：

```text
status = test_backed / experimental
no canonical physical record
```

### 对纯代数 case 022/040

可以没有几何 config，但必须有：

```text
test fixture 说明
expected tolerances
test command
Gate output
```

## 34. Case README 不应只是一张摘要表

保留 22 项契约表可以，但其后必须展开：

```text
physical problem
parameter explanation
PyCharm steps
CLI steps
code path
theory
results table
interpretation
limitations
```

---

# PART X：关键 Benchmark case 修正

## 35. P0-11：Case 002 必须真正比较 explicit 与 auxiliary solve

当前 Case 002 的 record 主要证明：

```text
auxiliary vs trace power
```

尚未证明完整的：

```text
explicit DtN solve vs auxiliary DtN solve
```

必须在相同物理问题、相同网格上运行两次，并记录：

```text
FE DoF / auxiliary DoF
matrix rows / nnz
linear residual
field relative difference
R_m / T_m
R_total / T_total
A_volume
energy closure
runtime
peak RSS
```

建议 Gate：

```text
field relative difference <= 1e-8
R/T/A absolute difference <= 1e-8
both residuals pass
```

若 explicit 路径没有 auxiliary DoF，应清楚说明矩阵尺寸变化。

## 36. P0-12：Case 003 接纳 Response V2 真实 TM/TE 运行

当前 Case 003 仍写“无 record”，与 Response V2 实际运行矛盾。

应：

```text
- 创建 TM record；
- 创建 TE record；
- 加入 checker；
- README 写入当前 canonical result；
- 链接 actual artifact provenance；
- 明确 probe closure 不是 official Gate。
```

## 37. P0-13：Case 021 的 PyCharm 与 canonical target 必须对齐

Case 021 不能继续写：

```text
PyCharm preset 是相近入口，canonical 用另一条 CLI
```

需要：

```text
- target preset；
或
- 明确无 PyCharm target preset，并给出 PyCharm runner configuration。
```

用户必须能按文档重现同一问题，而不是“相近 demo”。

## 38. P0-14：Case 031 增加 PyCharm MPI4 配置

Case 031 应链接 PART IV 的 PyCharm External Tool / Run Configuration，并说明 canonical record 不应被普通参数扫描覆盖。

## 39. Case 030 保持 experimental

OOC/BLR 没有新的 target run record，因此继续标记：

```text
test_backed / historical / experimental
```

不得因 preset 存在就升级为 recommended production。

---

# PART XI：文档合同测试增强

## 40. 当前测试过于表面

当前 `test_26_documentation_contract.py` 主要检查：

```text
file exists
link resolves
README contains 1..22 labels
Stage2 status wording
```

这无法发现本轮已识别的技术错误。

## 41. P0-15：增强文档 contract

至少增加：

```text
- recorded cases 必须有 config/expected/run/records；
- test-backed cases 必须有 test command 和 explicit status；
- Case 003 records 存在；
- Case 002 有 explicit and auxiliary records/results；
- demo/target preset 名称不能混淆；
- walkthrough 不再出现 SparseCoarseVector global_size；
- walkthrough 必须描述 smoother-before-coarse 的真实 apply 顺序；
- explicit condensation 文档必须出现 H=I limitation；
- SmallDenseInverse 文档必须出现 explicit inverse；
- all local links resolve。
```

测试不应尝试验证所有自然语言正确性，但应保护已知关键契约。

---

# PART XII：不需要做的工作

## 42. 本轮禁止扩张范围

不需要：

```text
- 重跑 h=2 direct；
- 重跑 h=2 iterative；
- 修改 Task27 PC 数值参数；
- 新增谱粗空间；
- 研究 h=1.5；
- 参数扫描；
- 启动 Task029；
- 修改 ordinary solver default。
```

## 43. 何时需要重跑重型 3D case

只有以下情况才需要：

```text
- 修改 condensed operator；
- 修改 physical-slab / coarse / FGMRES；
- 修改 3D official RTA；
- 修改 target geometry/config；
- 修改 canonical h5/h3/h2 records 对应的数值路径。
```

本报告要求的文档、2D record 和 preset 命名修正不要求重跑 h=2。

---

# PART XIII：Codex Response V3 要求

## 44. 回应文件

Codex 应在同一分支提交：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/response_v3.md
```

## 45. Response V3 必须逐项回应

```text
P0-1  freeze 2D TM/TE lossy records
P0-2  add lossy automatic gates
P0-3  lossless regression
P0-4  split demo and target presets
P0-5  preset resource identity
P0-6  PyCharm MPI4 workflow
P0-7  expand Quick Start tutorials
P0-8  fix walkthrough technical errors
P0-9  deepen core walkthroughs
P0-10 case-contained benchmark files
P0-11 Case002 explicit-vs-auxiliary
P0-12 Case003 records
P0-13 Case021 target reproducibility
P0-14 Case031 PyCharm MPI4
P0-15 strengthen documentation contract tests
```

每项必须包含：

```text
issue
root cause
files changed
implementation
commands/tests
records/evidence
remaining limitations
```

---

# PART XIV：最终验收 Gate

## 46. 代码 Gate

```text
full unit suite pass
MPI4 focused suite pass
ruff check pass
ruff format --check pass
ordinary default unchanged
repository principles test pass
```

## 47. 2D lossy Gate

```text
TM canonical record exists and passes
TE canonical record exists and passes
lossless regression passes
A_balance and A_volume agree
probe remains diagnostic
```

## 48. PyCharm Gate

```text
default Stage1 safe
all presets accepted by parser
demo vs target names unambiguous
target direct reproducible from PyCharm or documented Run Configuration
MPI4 iterative PyCharm External Tool / Run Configuration documented
```

## 49. Quick Start Gate

至少核心 15 篇具有完整教程结构，而不是只有命令卡。

## 50. Walkthrough Gate

```text
all identified technical errors fixed
core modules expanded with signatures, shapes, formulas, call chain and ownership
source and docs agree
```

## 51. Benchmark Gate

```text
recorded cases have config/expected/run/records
Case002 explicit-vs-auxiliary complete
Case003 TM/TE records complete
Case021 target reproducible
Case031 MPI4 PyCharm configuration linked
checker includes new records
```

## 52. Theory Gate

```text
symbol/convention index exists
formula typos fixed
module::function anchors improved
2D/3D power normalization boundaries stated
```

## 53. 最终状态判定

完成上述内容后，Task028 才可进入：

```text
pass_with_environment_qualification
```

环境仍可保留：

```text
qualified_local_image
```

不要求在 Task028 内解决公开 OCI 基础镜像。

---

# 54. 最终评语

Task028 的核心代码收口已经成功，Task026/Task027 的稳定求解路径和现有 3D records 可以保留。Response V2 也建立了正确的文档目录，并发现和修复了有价值的 2D 有损端口功率错误。

当前剩余工作不是继续增加目录或文件数量，而是：

```text
把速查卡写成真正可跟随的教程；
把函数清单写成准确的代码导览；
把 Benchmark 摘要写成可运行、可复现、可自动验收的案例；
把新增 2D 物理修复固化为 canonical records。
```

在 Response V3 关闭这些问题前，仍不建议合并到 `master`。

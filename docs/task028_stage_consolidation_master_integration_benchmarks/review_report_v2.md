# REVIEW REPORT V2：Task028 文档体系、PyCharm 使用入口与功能 Benchmark 重构

## 1. 审查对象

```text
repository = Rookie1234567/MyFEniCS
branch = codex/20260712-task28-stage-consolidation
base = master@0465b5f0e79046bcd82741d7396ba1c87f5a2606
review_baseline = response_v1.md + d708c63 + 3b3abf0
review_scope = source + main.py + user docs + theory docs + benchmark structure + canonical records
```

本轮审查承接：

```text
review_report_v1.md
-> response_v1.md
-> current V2 review
```

V1 的六个 P0 在实现层面已经基本关闭：

```text
- benchmark output root；
- scripts / manifest；
- automatic Gate checker；
- qualified Stage4 environment；
- sm2 production tests；
- 第一轮用户文档扩充。
```

但是，V2 审查确认：当前 Quick Start、Code Walkthrough、Theory 和 Benchmark 文档仍然更接近“阶段摘要”，尚未形成真正帮助用户理解、配置、运行和验证项目的完整知识体系。

用户明确要求：

> 文档不仅要告诉用户运行哪个命令，还要让用户知道在 PyCharm 的 `main.py` 中修改哪些参数、这些参数的物理和数值含义、代码如何实现对应边界条件和求解方法，以及某项功能由哪个 benchmark 证明可以运行。

---

# 2. V2 最终状态

```text
review_status = changes_required

core_solver_code = pass
numerical_results = pass
selective_integration = pass
ordinary_default = pass
sm2_tests = pass
benchmark_execution_scripts = pass
environment = pass_with_qualification
repository_work_principles = pass

benchmark_metadata_contract = partial_fail
benchmark_checker_completeness = partial_fail
main_py_pycharm_usability = fail
quick_start_information_architecture = fail
code_walkthrough_depth = fail
theory_cross_linking = partial_fail
feature_benchmark_catalog = fail
capability_to_usage_traceability = fail

master_merge = not_yet
```

这不是对 Task028 核心代码和数值成果的否定。

准确结论为：

> Task028 已完成稳定代码选择性整合和目标求解器复现，但要成为真正可维护、可学习、可交付的阶段版本，仍需完成一次以“用户如何理解和使用当前全部功能”为核心的文档与 Benchmark 信息架构重构。

本轮不启动新物理算法，不重新研究预条件器，也不要求仅因文档重构重复运行 h=2。

---

# PART I：文档体系应如何分工

## 3. 不应取消 Quick Start 或 Benchmark

用户提出 Quick Start 与 `benchmark_001_xxx.md` 可能重复。审查结论是：

```text
两者都保留，但必须明确职责，禁止重复维护同一份长内容。
```

推荐五层文档体系：

| 层 | 回答的问题 | 主要目录 |
|---|---|---|
| Capability / Progress | 项目现在具备什么、开发到哪里 | `docs/capability_matrix.md`、`docs/development_progress.md` |
| Quick Start | 我想运行某项功能，应修改什么、按什么步骤做 | `notes/quick_start/` |
| Code Walkthrough | 这项功能由哪些模块、类、函数和数据流实现 | `notes/reference/code_walkthrough/` |
| Theory | 为什么采用这种方程、边界、功率和求解方法 | `notes/theory/` |
| Benchmark | 哪个精确定义的问题证明这项能力可运行、结果是什么 | `benchmarks/cases/` |

### 3.1 避免重复的原则

#### Quick Start 负责

```text
- 用户目标；
- PyCharm main.py 如何选 preset；
- 需要修改哪些参数；
- 命令行等价命令；
- 输出在哪里；
- 最常见错误；
- 链接到 Theory、Code Walkthrough 和 Benchmark。
```

Quick Start 不应重复：

```text
- 完整理论推导；
- 大段代码逐函数解释；
- 多次 benchmark 数值表；
- 历史任务结论。
```

#### Code Walkthrough 负责

```text
- 模块结构；
- 配置如何流入网格、变分形式、约束、求解器和后处理；
- 关键类和函数的职责；
- PETSc/DOLFINx 对象所有权与生命周期；
- 代码表达式和理论公式的对应关系；
- 哪些路径是 official、diagnostic、research-only。
```

Code Walkthrough 不应重复完整运行结果。

#### Theory 负责

```text
- 强形式、弱形式；
- Floquet、PML、Robin、DtN；
- explicit/auxiliary DtN；
- R/T/A、Poynting、modal power；
- augmented system、static condensation；
- direct、BLR、FGMRES、Schwarz、coarse correction；
- 公式假设、符号、归一化和适用边界。
```

#### Benchmark 负责

```text
- 一个冻结的精确问题；
- 几何、材料、波长、角度、偏振、网格、求解方法；
- main.py preset / CLI / config；
- 期望输出和 Gate；
- canonical records；
- official 与 diagnostic 方法对照；
- 该 benchmark 证明了什么、没有证明什么。
```

Benchmark 不重复 Docker 安装和通用参数解释，而是链接 Quick Start。

---

# PART II：`main.py` 与 PyCharm 使用入口

## 4. 当前 `main.py` 的优点

当前 `src/main.py` 已经具备良好基础：

```text
- `SIMULATION_DIMENSION` 区分 2D / 3D；
- dataclass 保存 PyCharm 参数；
- 只把 active group 翻译为 CLI 参数；
- 最终复用 `run_cases` / `run_3d_cases`；
- 不复制求解器实现。
```

该方向应保留。

## 5. 当前 `main.py` 的问题

### 5.1 预设粒度不足

当前只有：

```text
2D:
- euv_grating

3D:
- stage1_airbox
- stage2_no_grating
- stage4_grating
```

这不能让新用户直接理解“选择哪个功能”。

### 5.2 注释与真实 CLI 不一致

当前注释列出：

```text
stage2_all
stage4_all
case = both
```

但 `run_3d_cases` 的实际 choices 只有：

```text
stage1_airbox
floquet_airbox
pml_airbox
fresnel_interface
stage4_flat_layer_sanity
stage4_block_grating

case = normal / oblique
```

必须删除无效选项或真正实现对应 preset 展开，不能继续保留误导注释。

### 5.3 默认直接运行不够安全

当前默认：

```text
SIMULATION_DIMENSION = 3d
ACTIVE_3D_INPUT_GROUP = stage4_grating
```

用户第一次在 PyCharm 点击 Run 就进入 Stage4 光栅，而不是轻量 smoke。

推荐默认改为：

```text
SIMULATION_DIMENSION = "3d"
ACTIVE_3D_INPUT_GROUP = "stage1_airbox_smoke"
```

这只是改变 PyCharm 示例入口的安全默认，不改变 ordinary solver default。

### 5.4 2D PyCharm 参数不完整

当前 `Inputs2D` 缺少或不能清晰配置：

```text
- scattered PML 的 top/bottom thickness 和 alpha；
- complex refractive index 的 PyCharm/CLI 输入；
- direct solver profile；
- official/diagnostic power method 开关的说明；
- 不同 DtN 对照 preset。
```

尤其当前 `run_cases` 的 `--n-substrate` / `--n-grating` 仍按 float 参数解析，而项目能力矩阵宣称支持 complex refractive index。Codex 必须：

```text
A. 让 main.py / CLI 支持 complex 字符串输入；
或
B. 在 Quick Start 中明确 complex material 只能通过哪个配置入口设置，并把 capability 的入口限制写清。
```

优先建议 A，前提是不破坏既有测试。

### 5.5 3D direct solver profile 未进入 PyCharm 参数层

要在 PyCharm 中演示：

```text
MUMPS direct
MUMPS OOC
MUMPS BLR
```

需要在对应 Stage4 input dataclass 中暴露并翻译：

```text
petsc_direct_solver_profile
petsc_extra_options / named BLR profile
petsc_ksp_view
petsc_log_view
```

不得要求用户为了 BLR 手工修改底层 solver 文件。

### 5.6 最新 MPI4 迭代法不能由普通单进程 `main.py` 静默启动

最新成功 profile 要求：

```text
mpiexec -n 4
```

因此不应让 `src/main.py` 在普通 PyCharm Run 时偷偷切到单进程 iterative，也不应在 Python 进程内部无提示 spawn MPI。

推荐设计：

```text
src/main.py
  = ordinary 2D/3D direct PyCharm facade

benchmarks/pycharm_workstation_iterative.py
  = 仅生成/检查参数并给出 mpiexec 命令，或作为 PyCharm External Tool / Run Configuration 的明确入口
```

可选方案：

```text
benchmarks/main.py
```

但必须保持：

```text
ordinary default = direct
iterative = explicit opt-in
MPI4 requirement = visible
```

## 6. `main.py` 应新增安全命名 preset

推荐至少建立以下 preset 名称：

### 2D

```text
2d_tm_pml_floquet_smoke
2d_tm_dtn_auxiliary_smoke
2d_tm_dtn_explicit_smoke
2d_te_port_smoke
2d_complex_absorption
2d_euv_grating_direct
```

### 3D ordinary direct

```text
3d_stage1_airbox_smoke
3d_stage2a_floquet_smoke
3d_stage2b_pml_smoke
3d_stage2c_fresnel_smoke
3d_stage4a_flat_layer_direct
3d_stage4b_grating_direct_h5
3d_stage4b_grating_direct_h3
3d_stage4b_grating_mumps_ooc
3d_stage4b_grating_mumps_blr
```

命名 preset 的目标不是让 `main.py` 变成 benchmark 数据库，而是让用户通过一个明确名字获得安全、经过验证的起始参数。

### 6.1 每个参数必须解释四件事

Quick Start 与 main.py 注释都应说明：

```text
1. 参数控制什么物理/数值对象；
2. 单位；
3. 合法值；
4. 改变后是否仍在已验证范围。
```

例如：

```text
stage4_boundary_model:
  dtn_port = 当前 recommended total-field periodic modal port
  pml      = diagnostic/experimental Stage4 truncation
  robin0   = local approximate diagnostic

stage4_dtn_order_policy:
  auto_propagating = 包含明确传播阶
  zero_order       = 仅 0 阶，适合小 sanity
  manual           = 需要额外 order 设置
```

---

# PART III：Quick Start 重构

## 7. 总体目录

当前 `docs/quick_start.md` 可以保留，但应改为全局入口和最短路径。

详细教程放入：

```text
notes/quick_start/
```

推荐结构：

```text
notes/quick_start/
├── README.md
├── 00_environment_and_pycharm.md
├── 01_main_py_parameter_map.md
├── 02_results_and_paraview.md
├── 10_2d_pml_floquet.md
├── 11_2d_dtn_floquet.md
├── 12_2d_te_tm_and_complex_material.md
├── 13_2d_diffraction_and_rta_methods.md
├── 20_3d_stage1_airbox.md
├── 21_3d_stage2a_floquet.md
├── 22_3d_stage2b_pml.md
├── 23_3d_stage2c_fresnel.md
├── 30_3d_stage4a_flat_layer.md
├── 31_3d_stage4b_grating_direct.md
├── 32_3d_direct_ooc_blr.md
├── 40_3d_workstation_iterative.md
└── 50_parameter_scans_and_new_cases.md
```

现有旧 quick-start 文档不得直接删除。Codex 应：

```text
- 判断是否仍有效；
- 将仍有效内容迁入新结构；
- 旧文件保留 redirect/archived 标记，或在 changed_files 中说明替代关系；
- 禁止无审计地覆盖用户长期使用说明。
```

## 8. 每个 Quick Start 子文档统一模板

```text
1. 这个功能解决什么问题
2. 运行前提
3. PyCharm：main.py 选择哪个 preset
4. 关键参数表及含义
5. 可以安全修改什么
6. 改哪些参数会超出 qualification
7. 命令行等价命令
8. 预期输出文件
9. 如何判断成功
10. 常见错误
11. 对应 Code Walkthrough
12. 对应 Theory
13. 对应 Benchmark
```

### 8.1 Quick Start 不写大段 benchmark 结果

只写：

```text
- 预期 residual 量级；
- 能量是否接近 1；
- 大致时间/内存级别；
- benchmark 链接。
```

详细数值只保存在 benchmark case 和 records 中。

---

# PART IV：Code Walkthrough 重构

## 9. 当前问题

当前 `notes/reference/code_walkthrough.md` 已从 V1 的极简列表扩展到调用链说明，但仍然不足以实现用户目标：

> 用户应能够沿着文档阅读代码，理解“某个模块为什么存在、对应哪个理论对象、输入输出是什么、最后如何形成结果”。

当前仍缺：

```text
- 文件级和符号级详细地图；
- config 字段到代码路径的映射；
- 2D PML、Robin、DtN 的分别实现；
- 2D TE/TM 分支；
- 3D Stage1/2A/2B/2C/4A/4B 的逐阶段代码差异；
- DtN explicit/auxiliary 的矩阵结构与代码对应；
- R/T/A 多种方法的具体函数与 official/diagnostic 身份；
- direct/OOC/BLR 选择如何传入 PETSc；
- 最新迭代 PC 每个组件的内部实现；
- 测试如何覆盖这些模块。
```

## 10. 建议拆分 Code Walkthrough

保留：

```text
notes/reference/code_walkthrough.md
```

作为总览和阅读顺序，并新增：

```text
notes/reference/code_walkthrough/
├── 00_repository_architecture.md
├── 01_main_and_runner_dispatch.md
├── 10_2d_config_mesh_material.md
├── 11_2d_floquet_pml_port_forms.md
├── 12_2d_dtn_and_rta_postprocess.md
├── 20_3d_staged_architecture.md
├── 21_3d_floquet_and_pml.md
├── 22_3d_dtn_augmented_system.md
├── 23_3d_rta_and_field_reconstruction.md
├── 30_direct_solver_profiles.md
├── 31_exact_condensation.md
├── 32_physical_slab_two_level_pc.md
├── 33_workstation_fgmres_runtime.md
├── 40_output_schema_and_visualization.md
└── 50_tests_and_benchmark_contract.md
```

## 11. Code Walkthrough 的写法

每个模块应按以下方式解释：

```text
文件：src/solvers/dtn_port_3d.py
职责：建立 periodic modal DtN 增广系统，并计算端口模态功率
理论对象：DtN map / modal admittance / tangential trace
输入：a, L, V, mesh_data, cfg, floquet_data, modes
输出：A, b, x, solver_info, modal amplitudes
关键函数：...
调用者：...
被谁测试：...
官方结果：modal amplitudes -> R/T
诊断结果：probe / sampled flux
限制：3D ordinary 目前 auxiliary assembly
```

### 11.1 代码与理论必须双向链接

例如：

```text
Code Walkthrough: 3D DtN augmented system
  -> Theory: notes/theory/3d_dtn_modal_port.md

Theory: static condensation
  -> Code: src/solvers/condensed_dtn.py
  -> Test: src/test/test_22_condensed_dtn.py
  -> Benchmark: benchmark_022_condensation_equivalence
```

不要在 Code Walkthrough 中重新推导十页公式；但必须写出关键公式并链接完整推导。

---

# PART V：Theory 文档更新

## 12. 理论文档需要形成索引

建议新增或重建：

```text
notes/theory/README.md
```

按以下结构组织：

```text
A. Maxwell 与有限元基础
B. Floquet 周期边界
C. PML 与 Robin
D. DtN / periodic modal port
E. R/T/A 与吸收
F. 3D staged verification
G. direct 与 iterative linear solvers
H. 当前研究失败路线和适用边界
```

## 13. 必须补齐或整合的理论主题

### 13.1 2D 理论

```text
- TM: Ex/Ey H(curl) 强形式与弱形式；
- TE: Ez scalar 强形式与弱形式；
- x-Floquet 条件和相位；
- scattered-field + PML；
- Robin total-field port；
- Fourier DtN port；
- explicit Q^H Y Q 装配；
- auxiliary modal unknown 增广装配；
- diffraction orders；
- modal R/T、probe Fourier、Poynting/net flux、A_volume；
- official 与 diagnostic 的判定。
```

### 13.2 3D staged 理论

```text
Stage1  = 3D plane-wave H(curl) propagation
Stage2A = double Floquet
Stage2B = PML
Stage2C = Fresnel interface scattered-field validation
Stage4A = flat-layer DtN + analytic/energy sanity
Stage4B = block grating + modal port + absorption
```

每个 Stage 应解释：

```text
新增了什么物理对象
新增了什么边界条件
验证什么
不能证明什么
```

### 13.3 3D DtN 与凝聚

必须有完整理论文档说明：

```math
\begin{bmatrix}F&C\\D&H\end{bmatrix}
\begin{bmatrix}u\\a\end{bmatrix}
=
\begin{bmatrix}b_F\\b_H\end{bmatrix}
```

及：

```math
A_c = F-CH^{-1}D,
\qquad
b_c=b_F-CH^{-1}b_H,
\qquad
a=H^{-1}(b_H-Du).
```

并解释：

```text
- 为什么凝聚保持原物理算子；
- matrix-free action 如何实现；
- transpose/Hermitian action 的用途；
- official modal amplitude 如何由 back-sub 得到。
```

### 13.4 求解器理论

分别解释：

```text
MUMPS direct
MUMPS OOC
MUMPS BLR
FGMRES
shifted-F local problem
complete physical slabs
owner-computes Schwarz
fixed 75D coarse
sm2 inner GMRES
right preconditioning
reported / condensed / full residual
```

特别需要纠正命名：

> MUMPS-BLR 不是一个独立的“3D 迭代法 1”。它是压缩低秩的 direct/inexact factorization 路线，可作为 Krylov 内部近似因子或 direct fallback。应与真正的 matrix-free physical-slab iterative solver 分开描述。

---

# PART VI：Benchmark 重构

## 14. Benchmark 的定位

Benchmark 不是普通教程，而是：

> 冻结问题定义、配置、结果、Gate 和代码能力之间的可追溯证据。

用户提出的设计是合理的：

```text
benchmark_001_xxx.md
+ 对应配置
+ 对应轻量结果
+ 对应重型 artifact 路径
```

审查建议采用“case-contained”结构。

## 15. 推荐目录

```text
benchmarks/
├── README.md
├── benchmark.md
├── benchmark_manifest.csv
├── benchmark_summary.csv
├── check_benchmarks.py
├── environment.json
├── cases/
│   ├── benchmark_001_2d_tm_pml_floquet/
│   │   ├── benchmark.md
│   │   ├── config.json
│   │   ├── expected.json
│   │   ├── run.sh
│   │   └── records/
│   ├── benchmark_002_2d_tm_dtn_floquet/
│   └── ...
├── records/
│   └── benchmark_gate_report.json
└── artifacts/
    └── <benchmark_id>/
```

说明：

```text
- case 内 records 是该案例的 canonical 轻量结果；
- 顶层 records 只保留全局 Gate report 等跨案例记录；
- artifacts 仍全部 gitignored；
- manifest 指向 case 内 record；
- checker 不应依赖固定 records 路径。
```

若 Codex 判断当前迁移成本过高，也可以先保留顶层 `benchmarks/records/`，但每个 `cases/benchmark_xxx/benchmark.md` 必须准确链接对应 record。长期推荐 case-contained。

## 16. 每个 Benchmark 文档模板

```text
1. Benchmark ID 与名称
2. 证明的功能
3. 不证明的内容
4. 物理问题图景
5. 几何尺寸
6. 材料参数
7. 波长、角度、偏振
8. 边界条件
9. 有限元空间和网格
10. PyCharm main.py preset
11. main.py 关键参数表
12. 命令行等价命令
13. 实际代码调用链
14. 理论链接
15. 求解器
16. R/T/A 方法与 official/diagnostic 身份
17. 预期输出文件
18. 数值 Gate
19. 当前 canonical 结果
20. records 链接
21. artifact 路径规则
22. 已知限制
```

## 17. 推荐 Benchmark 功能清单

### Benchmark 001：2D TM scattered PML + Floquet

```text
目的：证明 2D H(curl) TM、x-Floquet、scattered-field 和上下 PML 路径可以运行。
```

必须说明：

```text
- incident/scattered/total field；
- PML thickness/alpha；
- layered 或 air background；
- 当前 R/T 方法的身份；
- PML benchmark 是 path smoke 还是精度 benchmark。
```

建议至少一个 lossless sanity；若无解析/高可信参考，不得标记为 PML accuracy verified。

### Benchmark 002：2D TM DtN + Floquet，explicit vs auxiliary

这是用户提出的重点 benchmark。

必须在相同物理问题上比较：

```text
DtN explicit assembly
DtN auxiliary assembly
```

比较：

```text
field norm / selected field difference
R_m / T_m
R_total / T_total
A_volume
energy closure
matrix size / nnz
runtime / RSS
```

R/T 方法表必须列出：

| 方法 | 当前身份 | 作用 |
|---|---|---|
| DtN auxiliary modal amplitudes | official/recommended（以实际代码审计为准） | 主功率结果 |
| explicit DtN trace/modal projection | reference/cross-check | 检查 auxiliary 等价性 |
| E/H probe Fourier | diagnostic_only | 场与模态拟合诊断 |
| sampled net flux / Poynting | diagnostic_only 或 consistency | 能流检查 |
| A_volume | official absorption | 有损体积分 |

不得只写“方法一样”，必须给数值差和 Gate。

### Benchmark 003：2D TE/TM 与 complex material absorption

目的：证明：

```text
- TE scalar path 可运行；
- TM vector path 可运行；
- complex n -> complex epsilon；
- A_volume 与 R/T 闭合。
```

TE/TM 不应在不等价物理偏振下强行比较场值，只比较各自解析/能量 sanity。

### Benchmark 010：3D Stage1 airbox

证明：

```text
3D N1curl
plane wave
basic assembly
direct solve
field direction / magnitude / residual
```

该 benchmark 应是 PyCharm 默认安全入口。

### Benchmark 011：3D Stage2A double Floquet airbox

证明：

```text
x/y Floquet phase
p1/p2 pairing path
MPI consistency
plane-wave propagation
```

### Benchmark 012：3D Stage2B PML airbox

当前只能声明：

```text
PML path smoke / experimental
```

除非新增解析衰减、反射误差或网格/PML 参数收敛证据，否则不得写 `supported accuracy`。

### Benchmark 013：3D Stage2C Fresnel interface

必须与 Fresnel analytic reference 比较：

```text
field / R / T / angle / polarization
```

若当前只有粗网格 smoke，则状态保持 `experimental` 或 `not_verified accuracy`。

### Benchmark 020：3D Stage4A flat-layer DtN sanity

这是 3D 功率体系的核心 benchmark，应同时验证：

```text
- flat-layer reference；
- auxiliary DtN modal amplitudes；
- official R/T；
- A_volume；
- energy closure；
- probe/net-flux diagnostic；
- p1/p2；
- MPI consistency。
```

### Benchmark 021：3D Stage4B block grating direct

冻结目标几何：

```text
period = 50 x 25 nm
domain = 50 x 25 x 140 nm
grating = 17 x 25 x 120 nm
lambda = 13.5 nm
theta = 80 deg
phi = 0
polarization = s
material = complex Si
p = 2
```

记录：

```text
h5/h3 direct clean
h2 reviewed reference
R/T/A
energy closure
DoF/nnz/time/RSS
physical mesh-convergence limitation
```

### Benchmark 022：3D auxiliary / explicit condensed / matrix-free 等价性

使用可承受的小案例验证：

```text
augmented solve
explicit condensed solve
matrix-free condensed action
back-substitution
transpose/Hermitian action
R/T/A reconstruction
```

该 benchmark 连接 Task026 稳定代数与物理结果。

### Benchmark 030：3D MUMPS OOC / BLR 压缩求解路线

名称应避免写成“迭代法 1”。推荐：

```text
benchmark_030_3d_direct_ooc_blr_fallback
```

对比：

```text
ordinary MUMPS direct
MUMPS OOC
MUMPS BLR / inexact factorization profile
```

必须记录：

```text
true residual
R/T/A delta
RSS
factor/setup time
OOC scratch
BLR parameters
compression/iteration information
```

只有已验证配置可以标记 supported/experimental，不能把 Task10 的单点成功扩展为通用 production。

### Benchmark 031：3D matrix-free physical-slab workstation iterative

当前最新成功方案：

```text
exact matrix-free condensation
+ fixed 75D coarse
+ 16 complete physical slabs
+ owner-computes ILU1
+ sm2
+ right FGMRES
```

包含 h5/h3/h2，继续使用当前 1e-6、14 GB、iteration ratio Gate。

### Benchmark 040：MPI / p / algebraic regression collection

可将以下快速回归作为集合 benchmark：

```text
MPI1/2/4 consistency
p1/p2 small-cell
Floquet orientation/pairing
coarse cache certification
repository governance contract
```

它属于回归 Benchmark，不是新的物理案例。

## 18. Benchmark 与 Quick Start 的交叉链接

例如：

```text
notes/quick_start/11_2d_dtn_floquet.md
  -> 教用户怎么配置和运行
  -> 链接 benchmark_002

benchmarks/cases/benchmark_002_2d_tm_dtn_floquet/benchmark.md
  -> 冻结精确问题和结果
  -> 链接 Quick Start 获取环境与操作解释
  -> 链接 Theory 获取 DtN 推导
  -> 链接 Code Walkthrough 获取实现说明
```

这种交叉链接不是重复，而是四个不同视角。

---

# PART VII：Official / Diagnostic 功率方法总表

## 19. 必须建立统一文档

建议新增：

```text
notes/theory/official_and_diagnostic_rta_methods.md
```

并在 Quick Start、Code Walkthrough、Capability Matrix、每个相关 Benchmark 中链接。

文档至少包含：

| 维度/边界 | 方法 | 数据来源 | 当前身份 | 适用条件 |
|---|---|---|---|---|
| 2D DtN | auxiliary modal amplitudes | auxiliary unknowns | official/recommended，需按代码确认 | residual passed |
| 2D DtN | explicit trace projection | FE boundary trace | reference/cross-check | same modal basis |
| 2D/3D | E/H Fourier probe | sampled plane | diagnostic_only | homogeneous probe region |
| 2D/3D | sampled net flux | Poynting plane | diagnostic/consistency | adequate sampling |
| 3D DtN | modal amplitudes | auxiliary port modes | official | residual passed |
| 2D/3D lossy | volume absorption | Im(epsilon)|E|^2 integral | official absorption | material tags correct |

Codex 必须以实际代码和已审查结果填写，不得根据名称推断 official 身份。

---

# PART VIII：上一轮轻量修正仍需完成

## 20. Benchmark metadata truthfulness

h3/h2 历史 record 当前把 `metadata.command` 写成新的 canonical artifact 命令，但 artifact provenance 又说明原结果来自历史 `results/`。

必须拆分：

```text
actual_source_command
actual_source_artifact_root
canonical_rerun_command
canonical_artifact_root
provenance
```

`metadata.command` 必须代表实际产生该数值的命令，不能事后改写。

## 21. Checker 必须补齐

新增 Gate：

```text
record benchmark_id matches manifest
qualified_profile == true for required iterative records
ksp_reason > 0
coarse_condition <= configured maximum
git_dirty == false for clean_rerun
physical model matches canonical geometry/material/angle/wavelength/polarization/degree
artifact provenance consistent with command and root
```

历史 h3/h2 可以补明确的 `physical_model` / `resolved_config`，无需重新计算。

## 22. 其他一致性修正

```text
- gate_decision.csv 的 47/47 改为当前真实 58/58 或新 checker 数量；
- 最终 checker report 不应无解释地写 checkout_dirty=true；
- Stage2B/Stage2C capability 改为 experimental/not_verified accuracy；
- development_progress 当前待办更新为 Response V1 已完成、等待本轮文档重构；
- environment base image 字段使用 digest-pinned reference 命名。
```

---

# PART IX：实现顺序

## 23. 推荐 Stage

### Stage V2-A：功能审计

```text
- 从代码确认全部 2D/3D feature；
- 确认每项入口、边界、solver、RTA 方法；
- 输出 capability -> quick start -> walkthrough -> theory -> benchmark 映射表。
```

### Stage V2-B：main.py PyCharm facade

```text
- 修正无效 comments；
- 安全默认改为 Stage1 smoke；
- 新增 named presets；
- 补 PML、complex material、solver profile 参数；
- 保持 iterative 显式 MPI4 入口分离。
```

### Stage V2-C：Quick Start

```text
- 建 notes/quick_start/README.md；
- 按功能拆分子文档；
- 保留/迁移旧文档；
- PyCharm 与 CLI 双入口。
```

### Stage V2-D：Code Walkthrough

```text
- 总览 + 分模块文档；
- 代码符号、输入输出、生命周期；
- 理论和测试链接。
```

### Stage V2-E：Theory

```text
- 建 theory index；
- 整合已有理论；
- 补 official/diagnostic RTA；
- 补 exact condensation 和 workstation solver 理论。
```

### Stage V2-F：Feature Benchmarks

```text
- 建 cases/；
- 先建立文档和 manifest；
- 优先复用已有有效 records；
- 只运行缺少证据的轻量案例；
- 不因目录重构重跑 h2。
```

### Stage V2-G：Contracts 与最终一致性

```text
- checker 新 Gates；
- docs links；
- main preset/CLI contract test；
- benchmark record/config contract；
- update development progress and capability matrix。
```

---

# PART X：测试与 Gate

## 24. 新增文档/配置测试

建议新增：

```text
src/test/test_26_documentation_contract.py
src/test/test_27_main_preset_contract.py
```

检查：

```text
- notes/quick_start/README.md 中列出的文件存在；
- Code Walkthrough index 链接存在；
- Theory index 链接存在；
- capability matrix 每个 recommended/supported feature 至少有一个 Quick Start 或明确说明无用户入口；
- 每个 required benchmark case 有 benchmark.md/config/record；
- main.py preset 名称唯一；
- preset 产生的 CLI 参数可被 runner parser 接受；
- invalid stage2_all/stage4_all/both 不再出现；
- ordinary main default 是轻量 direct smoke；
- iterative 不会由单进程 main.py 静默标记 qualified。
```

## 25. 文档 Gate

```text
quick_start_overview = pass
pycharm_main_guide = pass
feature_guides_2d = pass
feature_guides_3d = pass
code_walkthrough_framework = pass
code_walkthrough_dtn = pass
code_walkthrough_rta = pass
code_walkthrough_iterative = pass
theory_index = pass
official_diagnostic_rta_theory = pass
feature_benchmark_catalog = pass
cross_links = pass
```

## 26. 不要求的重型工作

本轮默认不要求：

```text
- 重跑 h2 iterative；
- 重跑 h2 direct；
- 新角度/波长/材料扫描；
- 实现新求解器；
- 恢复 spectral/GenEO；
- 证明 Stage2B/2C 精度。
```

如果为 benchmark 目录需要新 record，优先运行轻量 smoke 或 h5；h2 继续引用已审查 record，并准确保留 provenance。

---

# PART XI：Codex 输出要求

## 27. Response V2

Codex 完成后提交：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/response_v2.md
```

逐项说明：

```text
1. documentation architecture；
2. main.py presets；
3. PyCharm workflow；
4. Quick Start migration；
5. Code Walkthrough split；
6. Theory updates；
7. Benchmark cases；
8. official/diagnostic RTA audit；
9. metadata/checker fixes；
10. tests and remaining limitations。
```

同时更新：

```text
docs/development_progress.md
docs/capability_matrix.md
notes/reference/current_version_boundaries.md
docs/task028.../outcomes/summary.md
docs/task028.../outcomes/documentation_audit.md
docs/task028.../outcomes/gate_decision.csv
```

---

# 28. 最终判断

```text
Task028 core solver integration = accepted
Task028 numerical results = accepted
Task028 Response V1 productization = substantially accepted
Task028 documentation/learning system = not yet accepted
Task028 feature benchmark catalog = not yet accepted
master merge = blocked until Response V2 documentation redesign and final review
```

本轮最核心的要求是：

> 把仓库从“有很多已经成功的代码和简短说明”，提升为“用户可以从功能总览进入 Quick Start，在 PyCharm 或 CLI 中配置案例，通过 Code Walkthrough 理解实现，通过 Theory 理解公式，并由独立 Benchmark 验证该功能确实可运行”的完整项目。

完成该文档与 Benchmark 信息架构后，Task028 才适合作为阶段版本合并到 `master`。

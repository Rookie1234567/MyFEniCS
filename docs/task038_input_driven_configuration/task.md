# Task038：单一 `.dat` 输入驱动、预制案例迁移与旧入口精简

## 0. 任务身份

```text
task                              = Task038
task_kind                         = USER_INTERFACE_AND_CONFIGURATION_REFACTOR
status                            = READY_FOR_CODEX_EXECUTION
base_master_sha                   = c2a6fc1ea2d91a42e8433ea94db8c832e1036a54
working_branch                    = codex/20260812-task38-input-driven-configuration
remote_upstream                   = origin/codex/20260812-task38-input-driven-configuration
ordinary_default_change           = authorized only through reviewed input migration
master_write                      = forbidden
merge_to_master                   = not_authorized_without_final_review
primary_user_entry                = python scripts/run_case.py <one-case.dat>
one_dat_one_run                    = required
normal_run_requires_run_selector   = false
normal_run_requires_mpi_cli        = false
input_directory                    = input/
input_syntax                       = TOML-compatible key/value text with .dat suffix
external_dependency               = forbidden; use Python stdlib tomllib
solver_algorithm_change            = forbidden
Task37b/37c numerical method change= forbidden
new_preconditioner_family          = forbidden
new_physics_model                  = forbidden
```

Task038 将项目从“在 Python preset、CLI、runner 和 benchmark profile 中分散修改参数”迁移为：

```text
一个 .dat 文件
    = 一个完整物理模型
    + 一种明确计算方法
    + 一组明确求解器参数
    + 一个明确 MPI 数量
    + 一套明确输出要求
```

用户的正常运行命令必须简化为：

```bash
python scripts/run_case.py input/path/to/case.dat
```

不得再要求用户额外输入：

```text
--run hybrid_iterative_mpi8
--method ...
--mpi-size ...
--requested-modes ...
```

这些信息必须全部写在同一个 `.dat` 文件中。`.dat` 文件就是本项目第一版“无图形界面的用户自定义界面”。

辅助命令只允许：

```bash
python scripts/run_case.py input/path/to/case.dat --validate-only
python scripts/run_case.py input/path/to/case.dat --dry-run
```

正常求解不得依赖命令行覆盖物理、方法、求解器或 MPI 参数。

---

# 1. 当前问题与重构目标

## 1.1 当前输入入口重复

开始编码前必须审计当前 `master` 的实际文件。已知至少存在：

- `SimulationConfig3D` 及其派生属性；
- `target_stage4_config()` 等代码内物理预制值；
- `src/main.py` 中的 `PRESETS_2D`、`PRESETS_3D`、`ACTIVE_PYCHARM_PRESET`；
- `_pycharm_args_2d()`、`_pycharm_args_3d()` 的逐字段 CLI 转发；
- `run_3d_cases.py` 的大型 argparse 与 `_config_updates()`；
- Full3D、Hybrid direct、Hybrid iterative 的专用 benchmark profile；
- 多个历史 research-only runner 与 compatibility flag。

当前流程常表现为：

```text
Python preset
→ CLI 字符串
→ argparse
→ Python config
→ solver
```

Task038 的目标流程为：

```text
.dat
→ 严格解析与验证
→ RunSpecification
→ SimulationConfig + MethodConfig + SolverConfig + ExecutionConfig
→ 现有 solver
```

## 1.2 最终用户体验

用户只需要：

1. 从模板复制一个 `.dat`；
2. 修改 `geometry`、`materials`、`incidence`、`discretization`、`boundary`、
   `method`、`solver`、`execution`、`output`；
3. 运行该文件。

不再要求用户进入 Python 源码修改尺寸、材料、角度、M、MPI 或 solver。

## 1.3 不重写物理与数值核心

Task038 是输入、配置、启动、结果溯源与旧入口精简任务，不是求解器开发任务。

必须复用：

- `SimulationConfig3D` 的波矢、偏振、Floquet 相位、材料与几何派生逻辑；
- 已合入 `master` 的 Full3D direct；
- 已合入 `master` 的 Hybrid direct；
- 已合入 `master` 的 Task37b/37c Hybrid iterative；
- 现有 DtN、静态凝聚、field recovery、R/T/A 与 canonical 逻辑。

禁止在本任务中改变：

```text
Maxwell 弱式
DtN 物理定义
Hybrid coupling
block-LDU/ILU/Woodbury 算法
traction model
迭代容差的物理资格含义
衍射级功率定义
```

---

# 2. Git、分支与继承 Gate

Codex 开始时必须确认：

```text
current branch = codex/20260812-task38-input-driven-configuration
upstream       = origin/codex/20260812-task38-input-driven-configuration
base ancestor  = c2a6fc1ea2d91a42e8433ea94db8c832e1036a54
worktree       = clean
```

必须读取：

```text
AGENTS.md
docs/repository_work_principles.md
docs/markdown_rendering_standard.md
docs/task_retrospective_standard.md

docs/task037b_hybrid_fem_modal_iterative/response_v8.md
docs/task037c_hybrid_iterative_robustness/task.md
docs/task037c_hybrid_iterative_robustness/response_v3.md
```

并完整审计当前 `master` 中实际存在的：

```text
src/main.py
src/common/config_3d.py
src/runners/run_3d_cases.py
src/runners/run_cases.py
benchmarks/run_task037b_hybrid_iterative.py
benchmarks/run_task037b_hybrid_iterative_watchdog.py
Task37c selected runner/profile/checker files
```

不得根据旧 Task37b/37c 研究分支假设某文件已经进入 `master`。

第一项提交必须是 docs-only inherited audit：

```text
docs(task038): audit public inputs, presets, and legacy interfaces
```

该提交创建：

```text
docs/task038_input_driven_configuration/outcomes/inherited_master_audit.md
docs/task038_input_driven_configuration/outcomes/parameter_and_legacy_inventory.md
```

不得夹带 Python 修改。

---

# 3. 固定目录结构

Task038 必须建立顶层目录：

```text
input/
├── README.md
├── templates/
├── examples/
├── official/
├── smoke/
└── local/
```

语义：

- `input/README.md`：用户输入参数完整说明书；
- `input/templates/`：各方法的完整注释模板；
- `input/examples/`：轻量、可直接运行的教学案例；
- `input/official/`：由正式 benchmark/preset 迁移的权威输入；
- `input/smoke/`：替代代码内 smoke preset 的小型输入；
- `input/local/`：用户本地临时输入，默认加入 `.gitignore`，仅保留 `.gitkeep` 或示例说明。

建议建立内部代码：

```text
src/io/
├── __init__.py
├── input_schema.py
├── input_loader.py
├── input_validation.py
├── run_specification.py
├── resolved_config.py
└── method_adapters.py

scripts/
├── run_case.py
└── create_case_template.py
```

可以根据当前项目模块边界微调文件拆分，但不得重新复制求解器核心。

---

# 4. 一个 `.dat` 文件只表示一次计算

## 4.1 强制原则

一个 `.dat` 文件不得包含多个 `[runs.xxx]` 或等待用户用 `--run` 选择的任务集合。

每个文件必须唯一确定：

- 物理模型；
- 方法；
- direct/iterative；
- MPI 数；
- Hybrid 模态数；
- solver 参数；
- 输出参数。

例如同一个物理模型的四种计算应使用四个文件：

```text
input/official/grazing1_phi0_full3d_direct_mpi8.dat
input/official/grazing1_phi0_hybrid_direct_m120_mpi8.dat
input/official/grazing1_phi0_hybrid_iterative_m120_mpi8.dat
input/official/grazing1_phi0_hybrid_iterative_m120_mpi1.dat
```

## 4.2 正常运行命令

唯一普通入口：

```bash
python scripts/run_case.py input/official/example.dat
```

程序必须从文件读取 `method.kind` 与 `execution.mpi_size`，自动启动正确 worker。

若用户直接在 MPI 环境中调用内部 worker，worker必须验证：

```text
MPI.COMM_WORLD.size == execution.mpi_size
```

不一致时 fail closed。

## 4.3 无参数隐式选择禁止

当用户未提供 `.dat` 路径时，`run_case.py` 必须显示简短用法并退出，不得静默运行某个硬编码 preset。

可以保留 PyCharm Run Configuration 指向：

```text
script     = scripts/run_case.py
parameters = input/local/active.dat
```

但 `active.dat` 不应由代码硬编码成正式模型。

---

# 5. `.dat` 语法合同

## 5.1 文件后缀与解析器

文件后缀固定为 `.dat`，内容采用 TOML-compatible 语法，由 Python 标准库 `tomllib` 解析。

禁止：

```text
eval
exec
ast.literal_eval 解析任意表达式
动态 import
任意 Python 代码
```

复数统一表示为：

```toml
n_grating = [0.999002304859, 0.00182649365]
```

即 `[real, imag]`。

## 5.2 顶层元数据

每个文件至少包含：

```toml
schema_version = 1
model_id = "euv_grazing1_phi0"
run_id = "euv_grazing1_phi0_hybrid_iterative_m120_mpi8"
comparison_group = "euv_grazing1_phi0"
dimension = 3
```

要求：

- `model_id` 标识物理模型；
- `run_id` 标识一次具体方法与执行；
- `comparison_group` 用于三路比较；
- `dimension` 决定 2D/3D 方法子 schema；
- ID 只允许安全文件名字符；
- 重复 `run_id` 不能覆盖旧结果。

## 5.3 九个固定 section

每个正式输入必须包含：

```text
[geometry]
[materials]
[incidence]
[discretization]
[boundary]
[method]
[solver]
[execution]
[output]
```

section 可以有 method-specific 必填/禁用字段，但不得改名或将重要参数藏在 CLI 中。

---

# 6. 完整 3D Hybrid iterative 示例

Task038 模板至少应生成如下结构；最终字段以实现后的 schema为准，但不得减少九个 section。

```toml
schema_version = 1
model_id = "euv_grazing1_phi0"
run_id = "euv_grazing1_phi0_hybrid_iterative_m120_mpi8"
comparison_group = "euv_grazing1_phi0"
dimension = 3

[geometry]
geometry_kind = "rectangular_block_grating"
period_x_nm = 50.0
period_y_nm = 25.0
z_min_nm = -10.0
z_max_nm = 130.0
interface_z_nm = 0.0
air_height_nm = 130.0
substrate_thickness_nm = 10.0
grating_width_x_nm = 17.0
grating_width_y_nm = 25.0
grating_height_nm = 120.0

[materials]
n_air = [1.0, 0.0]
mu_r = [1.0, 0.0]
substrate_name = "Si / silicon"
n_substrate = [0.999002304859, 0.00182649365]
grating_name = "Si / silicon"
n_grating = [0.999002304859, 0.00182649365]

[incidence]
wavelength_nm = 13.5
grazing_angle_deg = 1.0
azimuth_deg = 0.0
polarization = "s"
electric_amplitude = 1.0

[discretization]
nedelec_degree = 6
visualization_degree = 6
mesh_target_nm = 10.0
mesh_cell_type = "hexahedron"
mesh_spacing_mode = "boundary_fitted"
assembly_backend = "assembly_time_static_condensed"
floquet_constraint_mode = "auto"

[boundary]
use_floquet_x = true
use_floquet_y = true
vertical_boundary = "dtn_port"
dtn_order_policy = "auto_propagating"
dtn_assembly = "auxiliary"
use_pml = false

[method]
kind = "hybrid_iterative"
bottom_interface_nm = 10.0
top_interface_nm = 110.0
requested_modes_per_direction = 120
internal_propagation_model = "full3d_uniform_cg"
internal_traction_model = "full3d_one_cell_exact_schur"

[solver]
linear_solver = "fgmres"
preconditioner = "hybrid_block_ldu_ilu0_dtn_woodbury"
restart = 90
max_iterations = 4500
relative_tolerance = 5.0e-9
absolute_tolerance = 0.0
initial_guess = "zero"
ilu_level = 0
ilu_shift = 0.1
subdomain_count_per_endcap = 1
overlap_fraction = 0.0
side_residual_correction_steps = 2

[execution]
mpi_size = 8
warning_memory_gib = 10.0
terminate_memory_gib = 14.0
timeout_seconds = 7200
require_zero_swap = true

[output]
results_root = "results"
unique_output = true
export_fields = true
export_diffraction_orders = true
export_canonical_vectors = true
export_modal_amplitudes = true
export_reference_planes = true
reference_plane_z_nm = [10.0, 30.0, 60.0, 90.0, 110.0]
sample_count_x = 40
sample_count_y = 20
```

示例中的具体 Task37c 参数只是官方输入示例，不能被硬编码为所有用户案例的默认值。

---

# 7. 参数暴露原则

## 7.1 应暴露的独立用户输入

### Geometry

- 空间维度与 geometry kind；
- 周期；
- 物理域范围；
- air/substrate 尺寸；
- grating 尺寸与位置；
- Hybrid 接口位置仅在 Hybrid 方法中由 `[method]` 指定。

### Materials

- 材料名称；
- 复折射率；
- 相对磁导率；
- 必要时区域材料映射。

### Incidence

- 波长；
- 用户友好的掠射角；
- 方位角；
- S/P/custom 偏振；
- 入射幅值。

3D Stage4 普通用户优先输入：

```text
grazing_angle_deg
```

内部 `incident_theta_deg` 必须由：

```math
\theta=90^\circ-\gamma
```

自动计算。不得要求用户同时填写 grazing 与 theta。

若某类 2D/Stage1 案例必须使用另一角度约定，schema必须使用显式字段名并在文档中说明，不得复用含义模糊的 `angle_deg`。

### Discretization

- 元素类型与阶次；
- 网格尺寸；
- 网格 cell/spacing；
- assembly backend；
- public Floquet constraint mode。

### Boundary

- Floquet x/y；
- DtN/PML/Robin；
- DtN order policy；
- PML 参数；
- diffraction/output采样相关边界设置。

### Method

- `full3d_direct`；
- `hybrid_direct`；
- `hybrid_iterative`；
- 当前 ordinary 2D方法；
- Hybrid接口、M、propagation/traction model。

### Solver

- direct solver profile；
- iterative solver；
- preconditioner identity；
- restart、max iteration、tolerance；
- 当前已公开且通过审查的 ILU/side-correction 参数。

### Execution

- MPI数；
- 内存 warning/terminate；
- timeout；
- swap policy；
- 容器/环境选择若项目已有公共入口。

### Output

- 输出根目录；
- 是否唯一目录；
- field、orders、canonical、modal导出；
- 采样面与分辨率。

## 7.2 不应暴露的派生量

以下不得作为普通用户输入：

```text
k0 / omega
kx / ky / kz
propagation direction vector
S/P polarization vector
Floquet phases
epsilon values derived from n
grating bounds derived from center/width
mesh cell counts derived by policy
active/full DoF counts
external propagating order count
Woodbury K size
Schur size
matrix/factor NNZ
runtime lifecycle state
```

这些必须由代码计算并写入 `resolved_config.json` 或 `run_manifest.json`。

## 7.3 不应直接暴露的内部兼容状态

以下类别只能留在代码或显式 research-only schema，不得因为 dataclass字段存在就自动公开：

- legacy static-condensation booleans；
- deprecated aliases；
- temporary diagnostic switches；
- benchmark-only source/hash controls；
- raw PETSc internal options；
-未通过正式审查的新PC参数；
- lifecycle实验分支开关。

普通输入的 public schema必须是显式白名单，禁止自动暴露所有 dataclass字段。

---

# 8. `input/README.md` 参数说明书

Codex 必须在：

```text
input/README.md
```

写一份面向用户的完整参数手册，而不是简短目录说明。

## 8.1 文档必须包含

1. `.dat` 是什么；
2. 最简运行命令；
3. `--validate-only` 与 `--dry-run`；
4. 九个 section 的作用；
5. 每个公开参数的详细表格；
6. 2D/3D和method-specific适用范围；
7. 单位；
8. 类型；
9. 必填/可选；
10. 默认值来源；
11. 允许值；
12. 跨字段约束；
13. 派生量；
14. 常见错误；
15. 完整 Full3D direct、Hybrid direct、Hybrid iterative示例；
16. 结果目录与manifest说明；
17. preset迁移对应表；
18. legacy/deprecated入口说明。

## 8.2 每个参数表的最低列

```text
完整键名
类型
单位
是否必填
默认值/无默认
允许值
适用 dimension/method
物理或数值含义
映射到内部配置的位置
跨字段限制
示例
```

例如必须明确说明：

- `incidence.grazing_angle_deg=1` 对应内部 `incident_theta_deg=89`；
- `execution.mpi_size` 由外层 launcher使用，worker会做一致性检查；
- `method.requested_modes_per_direction` 只适用于 Hybrid；
- `solver.restart` 只适用于 GMRES/FGMRES；
- 复折射率数组的第二项是虚部；
- `boundary.dtn_order_policy=auto_propagating` 会在运行时生成实际mode keys。

## 8.3 文档与schema同步 Gate

必须增加自动测试：

```text
public schema keys == documented parameter keys
```

允许文档包含额外说明行，但不得存在：

- schema中有公开键而README未解释；
- README声称存在但schema不接受的键；
- 单位或method适用范围不一致。

建议从schema元数据生成参数清单或至少使用机器可读标记，避免后续漂移。

---

# 9. 严格解析与验证

## 9.1 未知键与拼写

未知section或未知键必须报错，并尽可能给出近似建议：

```text
Unknown key geometry.grating_hight_nm
Did you mean geometry.grating_height_nm?
```

不得静默忽略。

## 9.2 重复键、类型与有限值

必须拒绝：

- TOML重复键；
- bool冒充int；
- NaN/Inf；
- 非法复数数组；
- 负尺寸；
- 零或负波长；
- 非法角度；
- 不存在的method/solver；
- 非正MPI数；
- 无意义的输出采样。

## 9.3 Method-specific验证

### Full3D direct

必须拒绝 Hybrid-only字段，例如：

```text
requested_modes_per_direction
bottom_interface_nm
top_interface_nm
hybrid block preconditioner
```

### Hybrid direct

必须要求：

```text
bottom/top interface
requested modes
propagation/traction model
valid direct solver
```

### Hybrid iterative

必须要求：

```text
bottom/top interface
requested modes
accepted block-LDU preconditioner
FGMRES参数
multimetric tolerance
```

不得允许 `method.kind` 与 `solver.linear_solver` 相互矛盾。

## 9.4 Boundary/geometry兼容

例如：

- 双周期结构要求Floquet x/y；
- DtN与PML互斥时必须fail closed；
- Hybrid接口必须位于物理域内且bottom < top；
- grating必须位于定义的层范围；
- assembly-time static condensation必须继续执行现有qualified-scope检查。

## 9.5 解析结果不可变

解析后生成不可变 `RunSpecification`。求解开始后不得再从原始文件读取参数，也不得由runner静默覆盖。

---

# 10. 内部配置架构

建议建立：

```text
RunSpecification
├── identity
├── geometry
├── materials
├── incidence
├── discretization
├── boundary
├── method
├── solver
├── execution
└── output
```

并提供明确转换：

```text
RunSpecification
→ SimulationConfig2D/3D
→ Full3DDirectConfig | HybridDirectConfig | HybridIterativeConfig
→ ExecutionPlan
```

## 10.1 保留 `SimulationConfig3D`

不得删除 `SimulationConfig3D`。它继续作为内部物理配置模型，负责：

- direction；
- S/P polarization；
- wavevector；
- Floquet phases；
- dielectric constants；
- grating bounds；
- mesh/assembly qualified scope；
- JSON派生量导出。

`.dat` 是用户界面，`SimulationConfig3D` 是内部模型，两者不是替代关系。

## 10.2 配置来源优先级

新入口只有：

```text
schema固定默认/方法默认
+ .dat显式输入
→ 验证与派生
→ resolved config
```

正常运行禁止CLI物理覆盖。

若benchmark内部需要source/hash/path参数，它们应由专用内部execution contract传入，不得与用户输入混在一起。

## 10.3 Physical model hash

程序必须对以下标准化内容计算：

```text
geometry
materials
incidence
discretization
boundary
```

生成：

```text
physical_model_sha256
```

同一 `comparison_group` 的 Full3D、Hybrid direct、Hybrid iterative比较前必须检查hash一致。

method、solver、MPI和output不进入physical model hash，但进入完整 `input_sha256` 与 `run_manifest`。

---

# 11. Launcher 与 MPI

## 11.1 外层串行launcher

`python scripts/run_case.py case.dat`首先在普通Python进程中：

1. 读取与验证input；
2. 生成resolved spec；
3. 读取 `execution.mpi_size`；
4. 创建输出目录；
5. 复制原始input；
6. 启动对应MPI worker；
7. 监控资源、timeout和exit状态；
8. 写parent manifest。

## 11.2 内部worker

内部worker入口可以使用私有flag、临时resolved JSON或环境变量，但不得要求普通用户手工输入。

worker必须验证：

- resolved spec hash；
- source SHA；
- MPI size；
- method adapter；
- output collision；
- ordinary defaults未被隐式改变。

## 11.3 串行作业

`run_case.py`一次只运行一个case。Task038不实现并行队列或多case sweep。

以后批量扫描可另立任务，当前不允许一个`.dat`包含多run。

---

# 12. 三条主要方法接入

Task038必须首先完成三条正式3D路径：

```text
full3d_direct
hybrid_direct
hybrid_iterative
```

## 12.1 Full3D direct adapter

必须复用现有Stage4/Full3D runner与`SimulationConfig3D`，不重写求解器。

## 12.2 Hybrid direct adapter

必须复用已合入master的direct Hybrid配置、QEP、coupling、recovery与postprocess。

## 12.3 Hybrid iterative adapter

必须复用Task37b/37c已合入的accepted iterative路径，包括动态DtN mode count、exact one-cell traction、two-pass correction等当前master能力。

输入文件只能选择已经公开/审查的组合，不能通过字符串访问任意内部函数。

## 12.4 2D与早期3D smoke

Task038还必须迁移当前普通用户可见的2D与Stage1/2/4 smoke preset；但其adapter可以在三条主要3D路径通过后分阶段完成。

任务最终不能在删除`PRESETS_2D/PRESETS_3D`后留下不可运行的公开案例。

---

# 13. 结果目录与溯源

## 13.1 路径

建议自动生成：

```text
results/
└── <model_id>/
    └── <run_id>__<method>__mpi<N>__M<M-or-na>/
        └── <timestamp>/
```

即使用户的`run_id`没有写MPI，自动路径也必须显示method、MPI和M，避免结果混淆。

## 13.2 每次运行必须保存

```text
input_original.dat
resolved_config.json
run_manifest.json
input_sha256.txt
physical_model_sha256.txt
source_sha.txt
run_summary.json
```

按方法还可保存：

```text
diffraction_orders.json
resource_timeline.csv
canonical manifests
modal amplitudes
fields/
```

## 13.3 `run_manifest.json`

至少包含：

```text
model_id
run_id
comparison_group
method
solver
mpi_size
requested_modes
input path
input SHA
physical model SHA
source SHA
container/environment
resolved config SHA
start/end time
exit status
result classification
```

## 13.4 原始input不可被修改

运行开始后复制到结果目录的`input_original.dat`必须与启动文件byte-identical，并保存SHA256。

---

# 14. Preset迁移

## 14.1 完整inventory

Codex必须列出：

- `src/main.py`中的每个2D/3D preset；
- `target_stage4_config()`等物理factory；
- `_stage_defaults()`；
- PyCharm active preset；
- ordinary CLI default；
- official benchmark anchor；
- smoke preset；
- research-only frozen profile。

并为每项标记：

```text
migrate_to_dat
keep_as_internal_factory
keep_for_historical_replay
research_only_not_public
obsolete_delete_candidate
legacy_alias_deprecate
```

## 14.2 迁移位置

- official/canonical → `input/official/`；
- smoke → `input/smoke/`；
- tutorial → `input/examples/`；
- user local → `input/local/`。

## 14.3 等价性Gate

每个迁移preset必须比较：

```text
old preset resolved config
vs
new .dat resolved config
```

要求：

- 物理独立输入逐项相同；
- 派生波矢、偏振、Floquet phase相同；
- 方法/solver/MPI相同；
- physical_model_sha一致；
- representative smoke结果一致。

没有等价性证据前不得删除旧preset。

## 14.4 正式案例最低迁移集合

至少包括：

- Stage1 airbox smoke；
- Stage2 Floquet smoke；
- Stage4 flat-layer sanity；
- current target Full3D direct例；
-一个Hybrid direct official例；
- Task37b M10 iterative anchor；
- Task37c 1°/phi案例中至少一份MPI8与一份MPI1示例。

---

# 15. 旧preset、CLI与过时功能精简

## 15.1 可删除候选

在全部迁移与测试通过后，优先评估删除：

```text
ACTIVE_PYCHARM_PRESET
ACTIVE_2D_INPUT_GROUP
ACTIVE_3D_INPUT_GROUP
PRESETS_2D
PRESETS_3D
_pycharm_args_2d
_pycharm_args_3d
重复的preset metadata表
重复的逐字段CLI转发
```

不能预先假定全部可删；以call graph、测试和迁移结果为准。

## 15.2 `src/main.py`目标

最终`src/main.py`应成为轻量兼容入口或直接调用`run_case.py`，不再保存几十个具体物理preset。

旧用法可暂时输出明确deprecation错误，例如：

```text
Python presets were migrated to input/*.dat.
Run: python scripts/run_case.py <case.dat>
```

不得静默选择某个dat。

## 15.3 CLI精简

普通用户入口不再暴露几十个物理CLI参数。

底层runner为benchmark replay保留的CLI必须：

- 标记internal/research use；
- 不出现在普通用户README主流程；
- 不与dat发生双重优先级；
- 有明确retirement或保留原因。

## 15.4 过时功能删除条件

一个功能只有同时满足以下条件才允许删除：

```text
无普通用户入口需要
无current master代码调用
无正式benchmark replay需要
无tracked authority依赖
无测试保留价值
已有dat或新入口覆盖其必要能力
```

删除前后必须记录：

- 搜索/call graph证据；
- 受影响文件；
- 替代入口；
- 测试；
- 文档迁移。

## 15.5 Research-only历史路径

历史research runner不一定全部删除。可以：

- 保持在`benchmarks/`并从普通入口隐藏；
- 明确标记legacy/research-only；
- 仅删除已证明无回放价值的重复层。

禁止为了追求行数减少而破坏历史authority replay。

---

# 16. 执行阶段

## T0：继承审计与全参数inventory

输出：

```text
outcomes/inherited_master_audit.md
outcomes/parameter_and_legacy_inventory.md
```

必须覆盖2D、3D、Full3D、Hybrid direct、Hybrid iterative、runner/watchdog、preset与legacy flags。

## T1：schema与参数文档

建立：

```text
input/README.md
input/templates/*.dat
src/io/input_schema.py
```

先完成纯解析schema和文档coverage test，不接PDE。

## T2：loader、validator与resolved config

实现：

```text
load
strict type validation
cross-field validation
derived values
RunSpecification
physical_model_sha
resolved_config.json
```

## T3：launcher与MPI worker合同

实现：

```text
scripts/run_case.py
validate-only
dry-run
automatic mpiexec
worker MPI verification
output/provenance bootstrap
```

T3只用tiny fixture和smoke验证。

## T4：Full3D direct接入

先完成小型Full3D/Stage4 direct等价性，再迁移一个official direct输入。

## T5：Hybrid direct接入

迁移一个小型/official Hybrid direct输入，验证resolved config、R/T/A和orders。

## T6：Hybrid iterative接入

迁移accepted Task37b/37c输入。要求新dat入口与旧accepted runner在同一参数下数值/物理一致。

## T7：preset迁移

迁移公开2D/3D preset；建立旧preset与dat的等价性表。

## T8：删除重复preset与普通CLI层

只删除已通过T7 Gate的内容；分多个小提交执行。

## T9：legacy/obsolete cleanup

按严格删除条件处理。不得将该阶段变成无边界的全仓重写。

## T10：完整回归与结项

输出：

```text
docs/task038_input_driven_configuration/outcomes/summary.md
docs/task038_input_driven_configuration/outcomes/test_summary.md
docs/task038_input_driven_configuration/outcomes/input_schema_and_examples.md
docs/task038_input_driven_configuration/outcomes/preset_migration.md
docs/task038_input_driven_configuration/outcomes/legacy_cleanup.md
docs/task038_input_driven_configuration/outcomes/changed_files.md
docs/task038_input_driven_configuration/response_v1.md
```

然后停止等待审阅；未经审阅不得merge master。

---

# 17. 测试Gate

## 17.1 纯解析测试

必须覆盖：

- 九section完整输入；
- 未知键；
- 拼写建议；
- 重复键；
- 类型错误；
- NaN/Inf；
- 复数解析；
- method-specific必填/禁用；
- angle conversion；
- S/P偏振；
- boundary兼容；
- MPI验证；
- output路径；
- hash稳定性；
- README文档coverage。

## 17.2 Dry-run测试

`--dry-run`不得启动MPI/PDE，必须输出：

```text
method
MPI
M
physical model hash
theta/grazing
wavevector
polarization
Floquet phases
expected output directory
resolved method adapter
```

## 17.3 入口等价性测试

至少比较：

- 旧Stage1 preset vs新dat；
- 旧Stage4 direct preset vs新dat；
- 旧Hybrid direct profile vs新dat；
- 旧Task37b/37c iterative profile vs新dat。

## 17.4 MPI测试

轻量fixture运行：

```text
MPI1
MPI2
MPI4
```

正式accepted dat入口至少验证：

```text
Hybrid iterative MPI8
Hybrid iterative MPI1 or existing accepted MPI1 case
```

不得并行启动多个重型作业。

## 17.5 数值回归

至少要求：

- 一个2D smoke；
- 一个3D smoke；
- 一个Full3D direct；
- 一个Hybrid direct；
- 一个Hybrid iterative accepted anchor。

比较：

```text
residual
R/T/A/A_volume
orders/mode keys
canonical/selected fields when available
iterations
resource classification
```

输入重构不得改变算法结果。

## 17.6 静态与全仓测试

每阶段：

```text
ruff check
ruff format --check
python -m compileall
git diff --check
```

最终必须运行一次无deselect的：

```bash
python -m pytest -q
```

要求zero failures。若未完成或有failure，必须如实记录，不得请求master merge。

---

# 18. Commit计划

建议按职责拆分：

```text
docs(task038): audit public inputs, presets, and legacy interfaces
feat(task038): add strict dat schema and parameter documentation
feat(task038): add resolved run specification and provenance
feat(task038): add single-file launcher and MPI execution plan
feat(task038): connect Full3D direct dat input
feat(task038): connect Hybrid direct dat input
feat(task038): connect Hybrid iterative dat input
test(task038): add preset and numerical equivalence coverage
refactor(task038): migrate public presets to input files
refactor(task038): remove duplicated preset and CLI facade
docs(task038): close input migration and legacy cleanup
```

允许根据实际依赖调整，但禁止一个超大提交同时加入schema、删除旧入口和修改solver。

---

# 19. 停止边界

以下情况必须停止等待审阅：

- dat入口导致accepted numerical result变化；
- 无法证明旧preset与新dat等价；
- 删除项仍被正式authority/replay引用；
- parser需要引入新外部依赖；
- full pytest失败；
- 普通default或solver算法被意外修改；
- 为支持任意内部flag而不得不暴露research-only细节。

禁止自动扩展：

```text
GUI
Web界面
批量sweep
数据库
代理模型数据调度
0.7nm新PDE
新solver/PC
```

这些可在Task038完成后另立任务。

---

# 20. 最终验收

Task038只有在以下全部成立时才可申请最终审阅：

1. 用户可仅用一个dat路径启动一次明确计算；
2. method、solver、MPI、M全部来自dat；
3. normal run不需要`--run`或`--mpi-size`；
4. 九个section均进入public schema；
5. `input/README.md`详细解释全部公开参数；
6. README与schema key coverage自动通过；
7. 原始input、resolved config、input hash、physical model hash与manifest均保存；
8. Full3D direct、Hybrid direct、Hybrid iterative可由dat运行；
9. 公开preset已迁移或有明确保留理由；
10. 可删除的旧preset/CLI重复层已清理；
11. 历史research replay未被破坏；
12. 代表性数值结果与旧入口一致；
13. full repository pytest zero failures；
14. ordinary solver物理与算法未改变。

最终用户主流程必须在README中只呈现：

```bash
python scripts/run_case.py input/path/to/case.dat
```

而不是旧Python preset或几十个CLI参数。

# CODEX TASK 20260712：阶段成果收口、选择性主线整合与可复现 Benchmark 体系

## 0. 任务名称

```text
Task028: Stage consolidation, selective master integration,
documentation refresh, and reproducible benchmark suite
```

中文定位：

```text
Task028：Task000–Task027 阶段成果收口、选择性主线整合、
项目文档重建与可复现 Benchmark 体系。
```

本任务暂停新的求解器、预条件器和物理功能扩展。目标不是继续探索新算法，而是把 Task000–Task027 已经证明正确、可维护、值得长期保留的成果整理为一个清晰、可复现、可供新用户使用的阶段版本。

---

## 1. 执行分支和工作规则

ChatGPT 不创建分支。

Codex 应自行创建 Task028 执行分支，推荐从当前干净 `master` 创建，而不是直接把 Task027 分支整体并入：

```text
recommended base = master
```

当前已审查的 Task027 分支仅作为候选代码和证据来源：

```text
codex/20260711-task27-mesh-independent-spectral-schwarz
```

Task028 的核心原则：

```text
1. 不直接 merge Task027 整个分支；
2. 不直接 merge Task013–Task025 的研究分支；
3. 从 clean master 按功能抽取、重构和测试；
4. ordinary solver default 不得静默改变；
5. 新的 workstation iterative solver 必须保持显式 opt-in；
6. 未通过审查前不直接修改 master；
7. 大体积场、mesh、矩阵、因子和 OOC 文件不提交 Git；
8. 新算法扩展、角度大扫描、波长大扫描和新 PC 研究全部暂停。
```

---

## 2. 为什么现在需要 Task028

Task000–Task027 已经完成了从最小三维 Maxwell 框架到真实目标光栅、DtN modal port、official R/T/A、直接法、精确静态凝聚、matrix-free condensed operator 和 MPI4 物理 Schwarz 迭代求解器的长链条开发。

但当前仓库仍存在以下问题：

```text
- 成功代码分散在多个研究分支；
- 失败实验代码与长期可用组件混杂；
- README、Quick Start 和 Code Walkthrough 可能落后于实际源码；
- 2D/3D、direct/iterative、auxiliary/condensed 等能力缺少统一清单；
- 缺少从 clean checkout 可重复运行的正式 benchmark suite；
- 现有 results/ 既承担普通运行输出，也保存历史试验，边界不够清楚；
- 新用户难以判断推荐入口、实验入口和已废弃入口；
- 当前 master 还没有吸收 Task026/Task027 的最终成功路径。
```

Task028 应把项目从“连续研究分支”推进为“有明确阶段能力边界的可维护版本”。

---

## 3. Task028 最终目标

完成以下闭环：

```text
A. Task000–Task027 全任务阶段总结；
B. selective merge manifest；
C. 从 clean master 选择性整合成功代码；
D. 保留失败路线证据，但不污染普通生产接口；
E. 重建项目功能矩阵和架构文档；
F. 更新 README、Quick Start、Code Walkthrough、Solver Guide；
G. 建立独立 benchmarks/ 目录；
H. 建立 2D/3D smoke、sanity、direct、iterative benchmark；
I. 重新运行 benchmark 并保存完整轻量结果；
J. 确保普通用户运行代码仍默认输出到 results/；
K. 给出最终 master merge recommendation 和阶段版本边界。
```

---

# PART I：Task000–Task027 阶段总结与合并审计

## 4. Stage A：逐任务审计

必须阅读 Task000–Task027 的：

```text
task.md
review_report*.md
response*.md（若存在）
outcomes/summary.md
outcomes/gate_decision.csv
outcomes/merge_recommendation.md
outcomes/next_decision.md
```

不得只根据任务名称或旧 README 判断任务是否成功。

对每个任务至少记录：

```text
task_id
scope
physical_model
main_implementation
verified_successes
negative_results
known_limitations
superseded_by
merge_code_decision
merge_docs_decision
production_status
reason
source_branch_or_commit
```

输出：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/task000_task027_progress.csv
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/task000_task027_summary.md
```

### 4.1 成功类型必须分类

每个任务的成功必须标记为以下一种或多种：

```text
production_success
engineering_success
infrastructure_success
diagnostic_success
negative_result_success
documentation_success
research_only_positive
failed_or_superseded
```

不得把“成功定位失败原因”写成“生产求解器成功”。

### 4.2 后续任务优先于早期结论

若早期结论被后续任务修正，应在总结中标记：

```text
superseded
partially_superseded
still_valid
potentially_contaminated
```

特别检查：

```text
- Task009 的 KSP residual 与 true residual 口径；
- Task013–Task019 的 real-split / sampled-Schur 迁移失败；
- Task024 complex dot 修复对旧 coarse 负结果的影响；
- Task025 cached-Q 架构被 Task026 auxiliary-free condensation 替代；
- Task027 spectral/GenEO 失败与 physical-slab Schwarz 成功必须分开。
```

---

## 5. Stage B：selective merge manifest

建立文件级合并清单：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/selective_merge_manifest.csv
```

字段至少包括：

```text
source_task
source_branch
source_path
destination_path
action
category
ordinary_default_changed
required_refactor
required_tests
reason
status
```

`action` 只能使用：

```text
merge_as_is
extract_and_refactor
merge_docs_only
keep_research_only
exclude_superseded
exclude_failed
replace_with_newer_implementation
needs_review
```

### 5.1 第一优先级候选：Task026 exact condensation

重点审查并准备整合：

```text
src/solvers/condensed_dtn.py
```

目标功能：

```text
- auxiliary block extraction；
- exact static condensation；
- condensed RHS；
- matrix-free F-C H^-1 D action；
- transpose / Hermitian-transpose action；
- auxiliary back-substitution；
- explicit-vs-matrix-free equivalence；
- repeated-apply memory stability；
- complex-dot regression。
```

若通用代码与 Task027 实验代码混杂，必须先抽取为稳定 solver module，不得把整个研究 runner 当作库接口。

### 5.2 第二优先级候选：Task027 owner-computes physical-slab PC

重点审查并准备抽取：

```text
complete reduced-DoF physical slab gathering
balanced owner assignment
owner-only complete slab factorization
forward/reverse VecScatter
shifted local ILU1
two fixed shifted-F GMRES smoothing steps
sparse fixed coarse action
coarse cache rank/condition/action certification
MPI repeatability and empty-owner tests
```

建议从 `spectral_schwarz.py` 中抽取稳定模块，候选命名：

```text
src/solvers/physical_slab_two_level.py
```

实际名称可由 Codex 根据仓库结构决定。

必须继续保持：

```text
ordinary default = unchanged
profile = explicit opt-in workstation candidate
```

不得把以下失败路线放入普通 solver API：

```text
energy spectral coarse
interface harmonic coarse
shifted near-null coarse
PCHPDDM/GenEO
unsafe HPDDM cross-solve recycling
```

### 5.3 通用工程基础设施候选

审查以下长期价值组件：

```text
- explicit true residual computation；
- reported/true/full residual consistency checks；
- memory/RSS/swap telemetry；
- solver metadata and environment capture；
- unconverged solution blocks official R/T/A；
- field reconstruction and MPC back-substitution；
- Task024 vectorized CSR filter/exporter；
- CSR invariants and MPI packet audit；
- KSP A/P dual-operator support；
- benchmark result schema helpers。
```

如果相同功能在 Task026/Task027 已有更新实现，只合并最新版本。

### 5.4 历史 fallback

MUMPS-BLR 可作为显式 fallback 保留：

```text
profile = mumps_blr_fallback
ordinary default = no
```

必须清楚说明它属于 compressed factorization，不是低内存 mesh-independent iterative solver。

### 5.5 默认排除项

以下默认不进入 master 普通求解器路径：

```text
Task013–Task017 real-split/Petrov/lifted research runners
Task018 selected-response research workflow
Task019 failed p2 sampled-Schur path
Task024 manual FGMRES experimental implementation
Task025 cached 80-column Q solver as production path
Task026 serial-only early topology prototype
Task027 failed spectral/HPDDM profiles
unconverged R/T/A paths
large raw runs and local caches
mesh-specific undocumented tuning
```

若 Codex 判断其中某个工具仍有独立长期价值，必须在 manifest 中写明 isolation boundary 和 tests，不能静默带入。

---

# PART II：选择性整合与主线清理

## 6. Stage C：从 clean master 执行选择性整合

推荐提交顺序：

```text
Commit/PR group 1：Task028 文档、阶段总结和 merge manifest；
Commit/PR group 2：Task026 exact condensed operator + tests；
Commit/PR group 3：Task027 owner-computes physical-slab opt-in PC + MPI tests；
Commit/PR group 4：通用 telemetry / CSR / result-schema helpers；
Commit/PR group 5：用户文档和 benchmark suite。
```

不得用一个不可审查的大型 merge commit 把 48 个历史提交整体带入。

### 6.1 必须保持的旧路径

选择性整合后，以下 reference/fallback 路径不得被删除：

```text
existing auxiliary DtN reference
direct MUMPS reference
explicit auxiliary official R/T/A
existing Stage1–Stage4 smoke paths
```

新的 condensed/iterative 路径必须与 existing auxiliary path 共用 modal metadata 和 official postprocessing，避免形成两套互不一致的物理定义。

### 6.2 solver profile 命名统一

最终面向用户的名称建议收敛为：

```text
direct_auxiliary_reference
direct_condensed_reference
direct_mumps_ooc
mumps_blr_fallback
iterative_condensed_owner_slab_workstation
```

实际命名由 Codex 结合现有 config 决定，但必须提供兼容映射或迁移说明。

历史内部名称可以保留在 research 文档中，不应出现在 Quick Start 主路径。

### 6.3 配置入口简化

为用户提供少量高级 profile，同时允许高级用户覆盖底层参数：

```text
solver_profile = direct_reference
solver_profile = direct_low_memory_ooc
solver_profile = blr_fallback
solver_profile = iterative_workstation
```

不得为了 Task028 静默改变当前默认 profile。若建议未来更改默认值，只记录 recommendation，不在本任务直接实施。

---

## 7. Stage D：整合后回归测试

必须从 clean clone / clean container 运行：

```text
python -m py_compile ...
ruff check ...
unit tests
MPI1 tests
MPI2 tests
MPI4 targeted tests where applicable
git diff --check
```

重点回归：

```text
- auxiliary vs explicit condensed；
- explicit condensed vs matrix-free condensed；
- forward / transpose / Hermitian action；
- auxiliary back-substitution；
- official R/T/A；
- repeated MatMult RSS；
- distributed slab dense-reference action；
- empty owner rank；
- repeated PC apply；
- coarse cache true-action certification；
- MPI1/MPI4 physical output consistency。
```

任何回归失败都必须在进入文档和 benchmark 阶段前解决。

---

# PART III：项目功能清单与文档重建

## 8. Stage E：Capability Matrix

必须基于当前整合分支的真实源码和实际运行结果，建立：

```text
docs/capability_matrix.md
```

状态只能使用：

```text
recommended
supported
experimental
research_only
diagnostic_only
deprecated
not_implemented
not_verified
```

### 8.1 2D 能力核查

实际检查仓库是否支持：

```text
2D TE
2D TM
real/complex refractive index
Floquet periodicity
PML
DtN/port
Fresnel reference
multi-order diffraction R_m/T_m
total R/T/A
volume absorption
angle/wavelength scans
field output
mesh/order controls
direct solver
iterative solver
```

不得根据旧文档或聊天记忆假定支持。缺失功能必须如实标记。

### 8.2 3D 能力核查

至少检查：

```text
Stage1 airbox
Stage2A double Floquet airbox
Stage2B PML airbox
Stage2C Fresnel interface
flat-layer sanity
3D block grating
p=1/p=2 Nedelec
complex material
double Floquet MPC
auxiliary periodic modal DtN
explicit condensed DtN
matrix-free condensed DtN
direct MUMPS
MUMPS OOC
MUMPS-BLR
MPI4 owner-slab iterative solver
official modal R/T/A
volume absorption
field/mesh export
memory and residual diagnostics
```

每项说明：

```text
entry command
recommended profile
validated benchmark
known scale
known limitations
```

---

## 9. Stage F：文档更新范围

至少审查并更新：

```text
README.md
docs/README.md
notes/reference/code_walkthrough.md
notes/reference/current_version_boundaries.md
```

若现有 Quick Start 不完整，创建或统一：

```text
docs/quick_start.md
```

建议新增：

```text
docs/architecture_overview.md
docs/solver_guide.md
docs/result_schema.md
docs/capability_matrix.md
docs/benchmark.md
```

### 9.1 README.md

README 应只展示：

```text
- 项目定位；
- 当前推荐的 2D/3D 入口；
- 最小安装和运行命令；
- direct 与 iterative 的简要选择；
- 文档索引；
- 当前能力边界。
```

不得把完整研究历史塞进主 README。

### 9.2 Quick Start

Quick Start 必须从 clean environment 可执行，至少包含：

```text
1. build/start environment；
2. run a fast 2D case；
3. run a fast 3D sanity case；
4. run a 3D direct benchmark；
5. run the opt-in iterative workstation profile；
6. locate results；
7. read R/T/A and residual；
8. visualize field output。
```

重型 h=2 benchmark 不得作为第一条 Quick Start 命令。

### 9.3 Code Walkthrough

Code Walkthrough 应覆盖当前真实调用流：

```text
configuration
-> geometry/mesh
-> material assignment
-> function space
-> Floquet/MPC reduction
-> FE assembly
-> DtN modal metadata
-> auxiliary or static condensation
-> direct or iterative solver
-> field reconstruction
-> official R/T/A and A_volume
-> output/export
```

分别说明 2D 与 3D；分别说明 auxiliary、explicit condensed 和 matrix-free condensed。

### 9.4 Solver Guide

应解释：

```text
direct auxiliary MUMPS
direct condensed MUMPS
MUMPS OOC
MUMPS-BLR fallback
matrix-free condensed iterative solver
owner-computes physical-slab Schwarz
fixed coarse correction
true residual and stopping criteria
memory limits and recommended use cases
```

必须明确：

```text
Task027 iterative profile = explicit opt-in workstation candidate
not ordinary default
not a proven asymptotic multigrid method
not operator-adaptive spectral success
```

### 9.5 Result Schema

说明普通运行 `results/` 中常见文件：

```text
parameters.json
solver.json
residual_history.csv
memory_breakdown.csv
official_rta.json
port_metrics.json
volume_absorption.json
system_metadata.json
field/mesh outputs
```

标明哪些是 required、optional、diagnostic 和 large artifact。

---

# PART IV：独立 Benchmark 体系

## 10. Stage G：目录边界

Benchmark 不放入 `results/`。

在仓库根目录建立与 `results/` 并列的独立目录：

```text
benchmarks/
```

普通用户运行现有 solver 时，默认输出必须继续进入：

```text
results/
```

Task028 不得修改普通运行的默认 output root。

只有 benchmark runner 或 benchmark scripts 显式指定输出根目录时，结果才进入：

```text
benchmarks/records/
```

推荐目录：

```text
benchmarks/
├── README.md
├── benchmark.md
├── benchmark_manifest.csv
├── benchmark_summary.csv
├── environment.json
├── configs/
├── scripts/
├── expected/
├── records/
│   ├── 2d/
│   └── 3d/
└── artifacts/
```

说明：

```text
benchmarks/records/   = canonical benchmark JSON/CSV/MD and lightweight logs
benchmarks/artifacts/ = optional large fields/mesh/VTU/XDMF/HDF5, normally gitignored
results/              = ordinary user runs, unchanged
```

如仓库命名风格更适合 `runs/` 而不是 `records/`，可以调整，但必须保持 benchmark 与普通 results 严格分离。

---

## 11. Stage H：Benchmark 设计

Benchmark 分三层。

### 11.1 Level 1：fast smoke

目标：几分钟内验证入口和数据流未破坏。

候选：

```text
2D airbox / minimal propagation
2D flat interface
3D Stage1 airbox
3D double-Floquet airbox
3D flat-layer coarse sanity
3D zero-contrast block grating
```

检查：

```text
process exits successfully
no NaN/Inf
required output files exist
residual finite
MPI smoke consistent
```

### 11.2 Level 2：physics sanity / algebraic equivalence

候选：

```text
2D Fresnel interface
2D periodic grating diffraction
lossless R+T≈1
lossy R+T+A≈1
3D flat-layer Fresnel/energy sanity
auxiliary vs explicit condensed
explicit vs matrix-free action
auxiliary back-substitution
MPI1 vs MPI4 field/RTA consistency
```

阈值必须从已验证结果和离散误差出发，不得随意设置。

建议 algebraic gates：

```text
matrix action relative error <= 1e-11
coarse cache true-action error <= 1e-10
synthetic reconstruction error <= 1e-12
reported vs explicit true residual agreement <= 1e-10 relative
```

物理阈值应按 benchmark case 单独记录。

### 11.3 Level 3：workstation production benchmarks

至少包含目标 3D 模型：

```text
domain = 50 x 25 x 140 nm
period = 50 x 25 nm
grating = 17 x 25 x 120 nm
lambda = 13.5 nm
theta_from_z = 80 deg
phi = 0 deg
polarization = s
p = 2
```

Direct reference：

```text
h=5
h=3 if affordable
h=2
```

Iterative candidate：

```text
h=5
h=3
h=2
MPI4 owner-computes physical-slab + sm2
```

h=2 可继续使用已审查的 opt-in profile，但 Task028 应从整合后的 clean branch 重新运行，不得仅复制 Task027 outcome。

### 11.4 2D benchmark 边界

Codex 必须先确认 2D 当前入口和维护状态。

如果某个 2D 功能已不兼容当前环境：

```text
- 不得伪造 benchmark；
- capability matrix 标记 not_verified；
- 输出 blocking issue；
- 只修复小范围回归问题；
- 不在 Task028 扩展新的 2D 物理功能。
```

---

## 12. Stage I：统一 Benchmark 元数据

每个 benchmark case 至少保存：

```text
benchmark_id
category
case_description
command
config
commit_sha
branch
container_image
container_digest_if_available
Python version
PETSc version
SLEPc version if used
DOLFINx version
dolfinx_mpc version
mpi4py version
MPI size
CPU
RAM
OS/kernel
timestamp
status
```

数值结果至少保存：

```text
DoF
matrix rows/nnz
solver profile
iterations
reported residual
explicit true residual
setup time
solve time
total time
peak RSS
swap
R
T
A_volume
energy closure
field/action comparison where applicable
```

输出：

```text
benchmarks/benchmark_manifest.csv
benchmarks/benchmark_summary.csv
benchmarks/environment.json
```

---

## 13. Stage J：benchmark.md

建立：

```text
benchmarks/benchmark.md
```

内容至少包括：

```text
1. benchmark 目的；
2. 目录结构；
3. case 分级；
4. 运行命令；
5. 验收阈值；
6. direct/iterative reference；
7. 如何比较新旧 commit；
8. 如何更新 expected results；
9. 哪些结果提交 Git；
10. 哪些大文件只本地保留；
11. 当前 benchmark 数值表；
12. 已知限制和物理网格收敛边界。
```

同时更新：

```text
docs/benchmark.md
```

`docs/benchmark.md` 面向项目用户，解释 benchmark 的物理含义和选择；`benchmarks/benchmark.md` 面向实际运行和结果维护。

---

## 14. Benchmark 结果的 Git 策略

Task028 本地运行产生的所有 benchmark 输出都应位于 `benchmarks/` 下，而不是 `results/`。

允许提交：

```text
CSV
JSON
Markdown
small text logs
compact residual histories
configs
manifest
expected summaries
```

默认忽略：

```text
large mesh
XDMF/HDF5
VTU/VTX
full field arrays
large matrices
factor files
MUMPS OOC scratch
large caches
```

这些大文件即使保留，也必须位于：

```text
benchmarks/artifacts/
```

并由 `.gitignore` 控制。

---

# PART V：最终验收与审查循环

## 15. Task028 必须输出的文档

```text
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/task000_task027_summary.md
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/task000_task027_progress.csv
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/selective_merge_manifest.csv
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/merge_execution_log.md
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/changed_files.md
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/test_summary.md
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/documentation_audit.md
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/benchmark_gate.csv
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/gate_decision.csv
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/merge_recommendation.md
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/next_decision.md
docs/task028_stage_consolidation_master_integration_benchmarks/outcomes/summary.md
```

---

## 16. Task028 硬 Gate

### 16.1 Merge Gate

```text
- no whole research-branch merge；
- selective manifest complete；
- ordinary default unchanged；
- failed research profiles excluded from normal API；
- Task026 condensation tests pass；
- Task027 distributed-slab tests pass；
- auxiliary reference path preserved；
- Git contains no large benchmark artifacts。
```

### 16.2 Documentation Gate

```text
- README matches current source；
- Quick Start commands run from clean checkout；
- Code Walkthrough matches actual call graph；
- Capability Matrix complete；
- Solver Guide distinguishes recommended/experimental/research；
- Result Schema documented；
- current_version_boundaries updated；
- no claim of physical R/T/A mesh convergence unless demonstrated。
```

### 16.3 Benchmark Gate

```text
- benchmarks/ exists beside results/；
- normal solver output still defaults to results/；
- benchmark runner explicitly targets benchmarks/records/；
- Level1 smoke passes；
- Level2 algebraic/physics sanity passes or documented blocker exists；
- 3D direct reference rerun exists；
- 3D MPI4 iterative rerun exists；
- h=2 true residual <=1e-6 or clearly documented regression blocker；
- official R/T/A and energy closure present for converged production cases；
- environment and command metadata complete。
```

### 16.4 Repository Hygiene Gate

```text
py_compile pass
ruff pass
unit tests pass
MPI tests pass
git diff --check pass
no Results/ or results/ bulk ingestion
no papers/ modification
no generated cache accidentally committed
```

---

## 17. 审查—修正循环

Codex 完成首轮后，应提交：

```text
outcomes/summary.md
outcomes/gate_decision.csv
outcomes/merge_recommendation.md
```

随后由 ChatGPT 读取远程分支并编写：

```text
review_report_v1.md
```

若审查发现问题：

```text
1. Codex 在同一个 Task028 执行分支继续修改；
2. Codex 提交 response_v1.md，逐项回应 review；
3. 更新 outcomes、tests、benchmarks 和文档；
4. ChatGPT 再写 review_report_v2.md；
5. 可重复该过程，直到 pass / pass_with_qualifications / fail。
```

无需因为普通审查修正重新创建任务或分支。

只有以下情况应拆成新任务：

```text
- 需要新物理功能；
- 需要新求解算法；
- 需要大规模参数研究；
- 需要改变 ordinary default；
- 需要超出 Task028 阶段收口范围的架构重写。
```

在最终 review 通过前，不建议合并到 master。

---

## 18. Task028 成功定义

Task028 成功不等于“所有历史实验都进 master”。

成功定义为：

```text
1. master candidate 只包含已验证、可维护的长期组件；
2. Task026/Task027 成功路径被干净抽取；
3. 失败研究路线保留证据但不污染普通 API；
4. 新用户可以根据 Quick Start 跑通 2D/3D 示例；
5. 项目能力和限制有统一文档；
6. direct/iterative benchmark 可从 clean checkout 重复；
7. benchmark 与普通 results 输出目录分离；
8. ordinary solver defaults 保持稳定；
9. 阶段版本具备明确 review 和 merge recommendation。
```

最终状态建议使用：

```text
stage_consolidation = pass/fail
selective_master_candidate = pass/fail
documentation_refresh = pass/fail
benchmark_suite = pass/fail
ordinary_default_change = no
new_solver_research = paused
```

---

## 19. 最终一句话目标

> 暂停新的求解器扩展，从 clean master 选择性整合 Task000–Task027 已验证成果，形成清晰的 2D/3D、direct/iterative 项目能力说明和独立 `benchmarks/` 可复现测试体系，使仓库进入可维护、可审查、可交付的阶段版本。

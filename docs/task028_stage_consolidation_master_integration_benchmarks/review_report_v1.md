# REVIEW REPORT V1：Task028 阶段成果收口、主线整合与 Benchmark 体系

## 1. 审查对象

```text
repository = Rookie1234567/MyFEniCS
branch = codex/20260712-task28-stage-consolidation
base = master@0465b5f0e79046bcd82741d7396ba1c87f5a2606
review_scope = source + tests + docs + benchmark records + Task000-Task027 audit
```

本报告审查 Task028 是否已经完成以下目标：

```text
1. 从 clean master 选择性整合 Task000-Task027 的长期成果；
2. 不整分支合并失败研究代码；
3. 将 Task026 exact condensation 与 Task027 成功 physical-slab 路线抽成稳定模块；
4. 保持 ordinary direct 默认不变；
5. 重建 README、Quick Start、Code Walkthrough、Capability Matrix、Solver Guide；
6. 建立独立 benchmarks/ 目录和可复现的 2D/3D、direct/iterative benchmark；
7. 从当前整合分支重新运行 h=5/3/2 workstation profile；
8. 给出最终 master merge recommendation。
```

---

## 2. V1 最终审查状态

```text
review_status = changes_required

selective_integration = pass
core_solver_extraction = pass
numerical_reproduction = pass
ordinary_default_unchanged = pass
task000_task027_audit = pass

benchmark_directory_design = pass
benchmark_output_boundary = fail
benchmark_scripts = fail
benchmark_automatic_gates = fail
environment_reproducibility = fail
benchmark_metadata_completeness = partial_fail

documentation_refresh = partial_pass
quick_start = fail
capability_matrix = fail
code_walkthrough = partial_fail
solver_guide = partial_fail

condensation_tests = pass
physical_slab_basic_tests = pass
production_sm2_test_coverage = fail

master_merge = not_yet
```

Task028 不应被判为失败。核心代码抽取和数值复现完成度较高，当前阻塞点主要位于：

```text
- benchmark 与 ordinary results 的实际输出边界；
- benchmark scripts 与 manifest/records 不一致；
- 缺少自动 Gate checker；
- benchmark 环境无法由仓库独立重建；
- 用户文档过度压缩；
- production sm2 路径测试不足。
```

因此，当前准确结论是：

> Task028 的数值和代码主线基本成立，但尚未达到“可由其他用户从 clean checkout 和 clean environment 重复、可直接合并 master”的阶段版本标准。

---

# PART I：通过项

## 3. 选择性整合策略通过

Task028 从 `master@0465b5f` 建立整合分支，目前没有整体 merge Task027，也没有整体 cherry-pick Task013-Task025 的研究历史。

`selective_merge_manifest.csv` 正确区分：

```text
integrated:
- Task026 condensed_dtn.py 的通用凝聚逻辑；
- Task027 fixed sparse coarse 与 complete physical slab owner-computes 路线；
- 独立 stage4_runtime.py；
- 独立 benchmark runner；
- Task021-Task027 精简闭环文档。

excluded:
- Task026/027 综合研究 runner；
- cached-Q；
- sampled-Schur；
- spectral/GenEO/interface harmonic；
- HPDDM recycling；
- 大型 raw runs；
- 失败 profile；
- 任务编号研究依赖链。
```

审查判断：

```text
no_whole_research_branch_merge = pass
failed_solver_keepout = pass
ordinary_default_change = no
```

这是 Task028 最重要的治理成果。

---

## 4. 稳定求解组件抽取通过

### 4.1 `src/solvers/condensed_dtn.py`

该模块提供：

```math
A_c = F - C H^{-1}D,
\qquad
b_c = b_F - C H^{-1}b_H,
```

以及：

```text
- dense exact condensation；
- distributed FE/aux block extraction；
- matrix-free condensed MatPython action；
- transpose action；
- Hermitian-transpose action；
- condensed RHS；
- auxiliary recovery/back-substitution；
- explicit condensed reference for verified H=I；
- action error utility。
```

模块不依赖 Task026/Task027 runner、网格或具体物理参数，抽取边界合理。

### 4.2 `src/solvers/physical_slab_two_level.py`

保留的长期组件包括：

```text
- SparseCoarseVector；
- sparse Galerkin coarse basis；
- Z^H A Z 构造；
- coarse rank/condition certification；
- cached coarse true-action certification；
- complete global physical subdomain gathering；
- deterministic largest-first owner assignment；
- owner-only local submatrix extraction；
- sequential ILU factorization；
- distributed-to-sequential forward scatter；
- reverse ADD_VALUES overlap assembly；
- fixed-step inner smoothing。
```

Task027 中失败的 spectral eigensolver 和 HPDDM 代码没有进入该模块，抽取方向正确。

### 4.3 `src/solvers/stage4_runtime.py`

该模块只负责目标 Stage4 系统装配，不直接选择线性求解器。它为 benchmark 提供：

```text
RuntimeStage4System
+ target_stage4_config
+ assemble_target_stage4_system
```

这比继续依赖 Task021-Task027 综合 runner 更干净。

审查判断：

```text
stable_module_extraction = pass
research_runner_dependency = removed
```

---

## 5. 核心数值复现通过

Task028 当前分支重新得到：

| h (nm) | FE DoF | iterations | reported residual | condensed residual | full residual | peak total RSS including RTA |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1201 | `9.83949e-7` | `9.83949e-7` | `9.83949e-7` | 1.987 GB |
| 3 | 198,438 | 993 | `9.93265e-7` | `9.93265e-7` | `9.93265e-7` | 5.082 GB |
| 2 | 615,108 | 1804 | `9.99738e-7` | `9.99738e-7` | `9.99738e-7` | 13.080 GB |

h=2 三残差一致：

```text
reported_relative_residual      = 9.99737804496762e-7
condensed_true_residual         = 9.997378035033273e-7
full_augmented_true_residual    = 9.997378035033273e-7
```

h=2 official R/T/A：

```text
R = 0.001342936300877147
T = 0.5992132418465216
A_volume = 0.3994438284315462
R+T+A = 1.000000006578945
closure = 6.578944944e-9
```

该 run 不复用 Task027 的旧 basis/coarse cache，数值与 Task027 一致。

审查判断：

```text
h5_clean_rerun = pass
h3_clean_rerun = pass
h2_clean_rerun = pass
reported_condensed_full_consistency = pass
official_rta = pass
memory_under_14gb = pass
```

核心数值结果可信。当前问题不是结果造假或残差口径错误，而是复现和文档体系尚未闭环。

---

## 6. ordinary default 保持不变

当前普通入口仍为：

```text
python -m src.runners.run_cases
python -m src.runners.run_3d_cases ...
```

Task027 workstation solver 位于独立：

```text
python -m benchmarks.run_workstation_iterative
```

普通 direct runner 没有被静默切换到 iterative profile。

Task028 对普通路径的功能修改主要是增加所有 MPI ranks 的总峰值 RSS 字段，不改变求解器选择。

审查判断：

```text
ordinary_default_unchanged = pass
workstation_profile_opt_in = pass
```

---

## 7. Task000-Task027 审计通过

`task000_task027_progress.csv` 对每个 Task 记录了：

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
success_type
reason
source_branch_or_commit
```

关键纠偏正确：

```text
- KSP/preconditioned residual 不等于 true residual；
- FE-only AMS 正信号不能外推到 Stage4；
- p1 sampled-Schur 不迁移到 p2；
- cached-Q 不是必要的最终架构；
- Task027 成功来自 fixed coarse + physical slabs + sm2，不是 spectral/GenEO；
- 当前只能称 tested-range mesh-robust，而不是严格 mesh-independent。
```

审查判断：

```text
task_history_accuracy = pass
success_negative_separation = pass
supersession_logic = pass
```

---

# PART II：P0 必须修正项

以下问题在 V2 审查前必须关闭，否则不建议合并 master。

## 8. P0-1：Benchmark 与 `results/` 的实际输出边界失败

Task028 文档规定：

```text
ordinary runs -> results/
benchmark heavy artifacts -> benchmarks/artifacts/
benchmark lightweight records -> benchmarks/records/
```

但是当前 canonical iterative 参数文件记录：

```json
"results_dir": "results/task028_benchmarks"
```

当前 direct records 也引用：

```text
source_run_directory = results/3D_stage4_...
```

因此当前实际 benchmark 执行没有遵守用户明确要求的目录边界。

### 必须修改

```text
1. benchmark runner 默认和正式命令显式使用 benchmarks/artifacts/；
2. direct benchmark 脚本也必须支持或包装独立 benchmark output root；
3. canonical parameter files 不应再把 results/task028_benchmarks 作为 benchmark 输出根；
4. ordinary CLI 仍必须默认写 results/；
5. 清楚区分“历史 source run”与“Task028 canonical benchmark artifact”。
```

### 是否需要重跑

```text
- 若只是本地目录位置和 metadata 错误，可以移动/重命名本地 artifact，并修正 record；
- 若 canonical record 声称由新命令生成，则至少需要对一个轻量 case 和一个 workstation case重新验证输出根；
- h=2 不强制仅为目录重命名而完整重跑，但最终记录必须诚实说明数据来源和执行命令。
```

Gate：

```text
benchmark_output_boundary = fail -> must_pass
```

---

## 9. P0-2：Benchmark scripts 与 manifest/records 不一致

### 9.1 `run_level1.sh`

当前只执行：

```text
py_compile
focused unit tests
```

但文档将 L1 描述为：

```text
compile
full unit suite
2D DtN smoke
3D Stage1 smoke
```

脚本没有执行 2D/3D smoke，也没有执行 full unit discovery。

### 9.2 `run_level3_iterative.sh`

当前只执行：

```text
h=5
h=2
```

遗漏 h=3，因此无法由该脚本重现：

```math
\frac{\max N_{iter}}{\min N_{iter}} = \frac{1804}{993}=1.8167.
```

### 9.3 `run_level3_direct.sh`

当前无条件运行：

```text
h=5
h=3
h=2
```

但 Task028 明确没有在 14 GB 环境中复跑 h=2 direct，因为历史参考约需 20.53 GB。该脚本在当前环境可能直接触发 OOM。

### 必须修改

推荐行为：

```text
run_level1.sh
  - compileall / py_compile
  - full unit suite
  - explicit 2D smoke command
  - explicit 3D Stage1 smoke command

run_level2_mpi.sh
  - focused MPI condensation tests
  - physical-slab tests
  - benchmark record checker

run_level3_direct.sh
  - default only h=5/h=3
  - h=2 only with explicit --include-resource-heavy-h2 or environment flag
  - no unconditional 20 GB run

run_level3_iterative.sh
  - h=5/h=3/h=2
  - records written to benchmarks/records/
  - heavy output written to benchmarks/artifacts/
```

Gate：

```text
benchmark_scripts_match_manifest = fail -> must_pass
```

---

## 10. P0-3：缺少可执行的 Benchmark Gate checker

当前 `expected/gates.json` 只有：

```text
- residual <= 1e-6；
- coarse rank = 75；
- coarse condition；
- energy closure；
- h2 RSS；
- ordinary_default_changed=false。
```

缺少：

```text
1. reported / condensed / full residual 的一致性；
2. h=5/3/2 必须全部存在且使用同一 profile；
3. max(iter)/min(iter) <= 2；
4. direct-vs-iterative R/T/A 差异；
5. h2 official R/T/A 必须存在；
6. record 必须包含 commit/environment/command；
7. current checkout 与 record commit 的一致性；
8. reviewed_not_rerun 与 clean rerun 的状态区分。
```

目前 `benchmark_gate.csv` 和 `benchmark_summary.csv` 主要是人工整理，不是自动从 canonical records 计算。

### 必须新增

建议新增：

```text
benchmarks/check_benchmarks.py
```

职责：

```text
- 读取 benchmark_manifest.csv；
- 加载所有 required records；
- 校验 schema；
- 校验 residual/energy/RSS；
- 计算三网格 iteration ratio；
- 比较 h5/h3 direct 与 iterative R/T/A；
- 明确标记 h2 direct 为 reviewed reference；
- 输出或更新 benchmark_summary.csv；
- 输出 machine-readable gate report；
- Gate 失败时返回非零 exit code。
```

推荐新增 Gate：

```text
reported_condensed_relative_difference <= 1e-10
reported_full_relative_difference <= 1e-10
iteration_ratio_h5_h3_h2 <= 2.0
abs(delta_R_direct_iterative) <= case-specific tolerance
abs(delta_T_direct_iterative) <= case-specific tolerance
abs(delta_A_direct_iterative) <= case-specific tolerance
record_commit_matches_checkout = true for clean reruns
```

物理差异阈值应根据当前 h5/h3 实际结果写入 expected，不要随意使用统一机器精度阈值。

Gate：

```text
benchmark_automatic_gates = fail -> must_pass
```

---

## 11. P0-4：Benchmark 环境不能由仓库独立重建

当前环境记录：

```text
primary_container_image = code-dolfinx-task027-hpddm:latest
2d_smoke_image = code-dolfinx:latest
```

但：

```text
- Task28 排除了 Dockerfile.task027_hpddm；
- 仓库当前没有一个明确的稳定阶段镜像定义；
- 镜像标签使用 latest，没有 digest；
- 2D 和 3D 使用不同镜像；
- 依赖执行机器预先存在这些本地镜像。
```

因此当前证据只支持：

```text
clean source checkout reproducible
```

不支持：

```text
clean environment reproducible
```

### 必须修改

至少完成以下一种方案：

#### 方案 A：统一阶段 Dockerfile

```text
Dockerfile 或 docker/Dockerfile.stage4
```

包含：

```text
complex PETSc
DOLFINx
dolfinx_mpc
mpi4py
gmsh Python module
SciPy
项目运行所需的其他稳定依赖
```

不要求包含 HPDDM/SLEPc，因为最终成功 profile 不依赖它们。

#### 方案 B：可复现镜像说明

若暂不新增 Dockerfile，则必须提供：

```text
- 镜像来源；
- 构建命令；
- base image；
- package versions；
- image digest；
- 如何获得 gmsh；
- 如何从 clean machine 还原环境。
```

### `environment.json` 必须补充

```text
commit_sha
container_image_digest
CPU model / logical cores
RAM
kernel
Docker/WSL version if relevant
MPI implementation and version
dolfinx_mpc version
gmsh version
BLAS/LAPACK or SciPy build information when available
```

Gate：

```text
environment_reproducibility = fail -> must_pass_or_explicitly_qualified
```

若确实无法在 Task028 中统一环境，最终状态最多只能是：

```text
benchmark_suite = pass_with_environment_qualification
```

不能写完全 clean reproducible。

---

## 12. P0-5：用户文档过度压缩，不满足 Task028 文档 Gate

### 12.1 Quick Start

当前 `docs/quick_start.md` 只有基本命令，缺少：

```text
- Docker build/start；
- volume mount；
- 明确使用的镜像；
- Windows PowerShell 示例；
- 明确、快速、已验证的 2D 单案例命令；
- 3D sanity command；
- direct benchmark command；
- workstation command；
- 结果目录；
- 如何读取 residual 与 R/T/A；
- 如何打开 ParaView 输出；
- 预计时间与内存；
- 常见错误。
```

当前裸命令：

```bash
python -m src.runners.run_cases
```

使用默认：

```text
calculation_method = all
constraint_backend = both
port_boundary_model = all
```

它不是一个快速、单一、清晰的 Quick Start case。Task028 的 2D smoke 实际需要 `manual + DtN`，因为 nonlocal DtN 不支持 `mpc_official`。

Quick Start 必须给出已实际执行的完整显式命令，不应依赖复杂默认组合。

### 12.2 Capability Matrix

当前矩阵缺少任务书要求的大量能力项。

2D 至少应逐项列出：

```text
TE
TM
real/complex index
Floquet
PML
Robin port
DtN port
explicit/auxiliary DtN
Fresnel reference
multi-order R_m/T_m
total R/T/A
volume absorption
angle scan
wavelength scan
field output
mesh/order controls
serial/MPI restrictions
direct/iterative status
```

3D 至少应列出：

```text
Stage1 airbox
Stage2A Floquet
Stage2B PML
Stage2C Fresnel
flat-layer sanity
block grating
p1/p2 Nedelec
complex material
auxiliary DtN
explicit condensed DtN
matrix-free condensed DtN
MUMPS direct
MUMPS OOC
MUMPS-BLR
MPI4 workstation iterative
field/mesh output
residual/memory telemetry
probe/net-flux diagnostic status
```

状态必须统一为 Task028 任务书定义的枚举：

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

### 12.3 Code Walkthrough

原文档从近 3000 行压缩为约 42 行。删除过期叙述是正确的，但当前只剩文件列表，不足以帮助用户理解代码。

至少应覆盖：

```text
2D:
run_cases
-> SimulationConfig
-> mesh_builder
-> material assignment
-> Floquet constraints
-> TM/TE forms
-> PML/Robin/DtN
-> solve
-> diffraction/RTA
-> output

3D:
run_3d_cases
-> SimulationConfig3D
-> Stage1/2A/2B/2C/4 dispatch
-> mesh_builder_3d
-> Nedelec space
-> double Floquet MPC
-> forms
-> auxiliary DtN
-> direct or condensation
-> field reconstruction
-> RTA/A_volume
-> output

Task28 iterative:
stage4_runtime
-> PetscCondensedBlocks
-> CondensedDtnMatContext
-> fixed coarse basis
-> complete slabs
-> owner-computes smoother
-> sm2
-> FGMRES
-> back-substitution
-> official RTA
```

还应解释主要数据结构和生命周期。

### 12.4 Solver Guide

当前 Solver Guide 基本只描述 Task027 profile。还必须说明：

```text
- ordinary auxiliary direct MUMPS；
- explicit condensed direct；
- MUMPS OOC；
- MUMPS-BLR fallback；
- matrix-free condensed iterative；
- 各入口命令；
- 资源边界；
- 推荐使用场景；
- 不支持的规模和参数范围；
- 未收敛时禁止 R/T/A。
```

### 12.5 `current_version_boundaries.md`

当前内容准确但太短。至少应加入：

```text
- 2D 和 3D 各自可声明的能力；
- direct/iterative 边界；
- official/diagnostic power source；
- benchmark 状态；
- 物理网格收敛仍未完成；
- 参数域外使用要求；
- 资源边界。
```

Gate：

```text
documentation_refresh = partial_pass -> must_pass
```

---

## 13. P0-6：production `sm2` 路径测试覆盖不足

Task028 h=2 成功 profile 依赖：

```text
DistributedPhysicalSlabSmoother(... smoother_iterations=2 ...)
```

但当前 focused tests 主要覆盖：

```text
- subdomain gathering；
- owner balance；
- one-level action；
- empty owner；
- cached coarse certification。
```

没有直接测试：

```text
- sm2 fixed-step inner GMRES；
- sm1 与 sm2 行为区别；
- sm2 多次 repeated apply；
- sm2 MPI2/MPI4 一致性；
- sm2 destroy/lifecycle；
- action_operator requirement。
```

### 必须补充

建议增加：

```text
test_two_step_inner_gmres_matches_explicit_small_reference
test_two_step_smoother_repeated_apply_is_stable
test_two_step_smoother_mpi_action_consistency
test_two_step_smoother_destroy
```

不要求通过单元测试证明 h=2 收敛，但必须覆盖最终 production profile 的关键代码分支。

Gate：

```text
production_sm2_test_coverage = fail -> must_pass
```

---

# PART III：P1 工程改进项

以下问题可在 Task028 同一 response 中处理；若无法全部完成，应在最终文档明确留下技术债。

## 14. P1-1：稳定模块依赖私有内部函数

`stage4_runtime.py` 使用：

```text
_build_variational_forms
_create_nedelec_space
_prepare_direct_lu_options_for_comm
```

benchmark runner 使用：

```text
_assign_fe_solution_from_augmented
_incident_projection_onto_top_mode
_port_power_metrics
_json_default
```

这些下划线接口未来容易在普通代码重构时断裂。

建议：

```text
- 为 Task28 稳定模块提供少量公开 wrapper；
- 或在 docs/architecture_overview.md 明确这些暂时属于 internal dependency；
- 至少增加 import/smoke regression，防止静默重命名。
```

---

## 15. P1-2：`SmallDenseInverse` 使用显式逆

当前：

```python
self.H_inverse = np.linalg.inv(self.H_dense)
```

当前 H 为单位或小型良态块，数值上没有造成错误，但作为稳定通用组件更合适的是：

```text
LU factorization + solve
```

建议：

```text
- 使用 scipy.linalg.lu_factor/lu_solve 或 np.linalg.solve；
- 对 condition_number 增加合理 Gate 或 warning；
- 保留 H=I fast path 可选。
```

该项可以标记为非阻塞技术债，但应避免长期把显式 inverse 固化为通用接口。

---

## 16. P1-3：Benchmark 配置存在双重来源

当前 profile 参数同时存在于：

```text
benchmarks/configs/workstation_p2.json
benchmarks/run_workstation_iterative.py argparse defaults
```

runner 并不自动读取 JSON config，未来容易漂移。

建议：

```text
- runner 支持 --config benchmarks/configs/workstation_p2.json；
- CLI 参数只作为显式 override；
- record 中写入 resolved config；
- checker 比较 config 与 record。
```

---

## 17. P1-4：Runner 允许超出 qualification 范围却没有明显标记

runner 允许用户修改：

```text
--theta-deg
--lambda-nm
--h-nm
--num-slabs
--coarse-slabs
--absorption-shift
```

当前 production qualification 仅覆盖：

```text
theta = 80 deg
lambda = 13.5 nm
h = 5/3/2 nm
p = 2
MPI = 4
fixed profile parameters
```

建议：

```text
- record 增加 qualified_profile: true/false；
- 参数偏离已验证组合时打印强 warning；
- 非 qualified case 不自动标记 production pass；
- benchmark checker 只对 canonical config 开 production Gate。
```

---

## 18. P1-5：Benchmark metadata 不完整

当前 records 多数缺少：

```text
commit_sha
branch
exact command
timestamp
container image digest
CPU
RAM
kernel
versions
```

Direct record 只有 source directory 和数值；iterative record 也没有完整环境信息。

建议统一每个 record 至少包含：

```text
benchmark_id
commit_sha
branch
git_dirty
command
resolved_config
timestamp
container_image
container_digest
host/environment id
software versions
status
```

---

## 19. P1-6：`coarse_action_relative_error=0.0` 语义不清

当 coarse matrix 在当前 run 中由真实 action 直接构造时，代码直接设置：

```text
coarse_action_relative_error = 0.0
```

这不是独立随机认证得到的 0，而是“没有 cache mismatch”的默认值。

建议：

```text
- fresh_coarse_action_error 使用 null/not_applicable；
- cached coarse 才记录 random true-action certification error；
- 或对 fresh coarse 也执行一次独立随机组合认证。
```

避免用户把 `0.0` 理解为真正计算得到的机器零误差。

---

## 20. P1-7：异常路径资源清理

`benchmarks/run_workstation_iterative.py` 正常路径显式 destroy 较完整，但在 setup/solve/后处理异常时没有统一 `try/finally`。

建议：

```text
- 对一次性 benchmark 进程可保留当前结构；
- 若作为长期稳定入口，应逐步引入 context manager 或 try/finally；
- progress record 应在异常时写 failure stage 和 exception；
- 避免 setup 失败后用户只看到残留文件而不知道阶段。
```

---

# PART IV：文档与 Benchmark 的具体修改要求

## 21. `docs/development_progress.md`

本轮新增的全局开发进度文档必须长期保留，并在 Codex response 中核查：

```text
- Task000-Task028 阶段划分是否准确；
- 每阶段目标、实现、关键结果、失败路线和保留能力是否完整；
- 当前功能、当前限制和下一阶段状态是否与源码一致；
- 后续开发完成时同步更新，而不是只保留 Task28 时间截面。
```

该文档应成为：

```text
项目阶段进度总览
```

而 `task000_task027_progress.csv` 继续承担机器可读逐任务审计。

---

## 22. README / docs 索引

应增加：

```text
README.md -> docs/development_progress.md
docs/README.md -> docs/development_progress.md
```

并明确：

```text
- README 是用户入口；
- development_progress 是阶段历史和当前进展；
- docs/taskXXX 是任务证据；
- notes 是理论解释。
```

---

# PART V：更新后的 Gate

## 23. Gate V1

| Gate | 状态 | V1 判断 |
|---|---|---|
| clean master base | pass | 仅领先 3 commits，无整体研究分支 merge |
| Task000-Task027 audit | pass | 28 行结构化审计 |
| selective merge manifest | pass | 成功/失败路线分离正确 |
| exact condensation module | pass | 通用代码与测试存在 |
| physical slab module | pass | 失败 spectral 代码已排除 |
| ordinary default unchanged | pass | workstation 为显式 benchmark 入口 |
| h5 iterative rerun | pass | full residual <1e-6 |
| h3 iterative rerun | pass | full residual <1e-6 |
| h2 iterative rerun | pass | full residual <1e-6, 13.080 GB |
| official R/T/A | pass | 能量闭合通过 |
| benchmark/results actual boundary | fail | canonical 参数使用 results/task028_benchmarks |
| Level scripts consistency | fail | L1 不含 smoke，iterative 漏 h3，direct 无条件 h2 |
| automatic benchmark checker | fail | 当前 Gate 主要为人工整理 |
| clean environment reproduction | fail | 依赖本地 latest 镜像，无稳定 Dockerfile/digest |
| benchmark metadata | partial fail | 缺 commit/command/digest/CPU/kernel 等 |
| Quick Start | fail | 不足以从 clean environment 运行 |
| Capability Matrix | fail | 项目项和状态枚举不完整 |
| Code Walkthrough | partial fail | 过度压缩 |
| Solver Guide | partial fail | 未覆盖完整 direct/OOC/BLR/condensed 路线 |
| sm2 production tests | fail | 未覆盖最终关键分支 |
| master merge | blocked | 等待 response_v1 与 V2 审查 |

最终：

```text
core_integration_gate = pass
numerical_gate = pass
productization_gate = fail
master_merge_gate = blocked
```

---

# PART VI：Codex Response V1 必须完成的事项

## 24. P0 修改清单

Codex 应在同一 Task028 分支提交：

```text
response_v1.md
```

逐项回应以下 P0：

```text
P0-1 benchmark output root 修正；
P0-2 Level1/2/3 scripts 修正；
P0-3 automatic benchmark checker；
P0-4 reproducible environment / Dockerfile or qualified environment plan；
P0-5 Quick Start、Capability Matrix、Code Walkthrough、Solver Guide 扩充；
P0-6 sm2 production-path tests。
```

每项必须包含：

```text
issue
root_cause
files_changed
tests_or_commands
evidence
remaining_limitations
```

---

## 25. 建议新增或更新的文件

```text
benchmarks/check_benchmarks.py
benchmarks/scripts/run_level1.sh
benchmarks/scripts/run_level2_mpi.sh
benchmarks/scripts/run_level3_direct.sh
benchmarks/scripts/run_level3_iterative.sh
benchmarks/expected/gates.json
benchmarks/environment.json
benchmarks/benchmark_manifest.csv
benchmarks/benchmark_summary.csv

docs/quick_start.md
docs/capability_matrix.md
docs/architecture_overview.md
docs/solver_guide.md
docs/result_schema.md
docs/development_progress.md
notes/reference/code_walkthrough.md
notes/reference/current_version_boundaries.md

src/test/test_23_physical_slab_two_level.py
```

若新增阶段 Dockerfile，建议放在：

```text
docker/Dockerfile.stage4
```

或使用仓库现有命名习惯，但不要继续依赖一个未在仓库定义的 Task027 `latest` 镜像。

---

## 26. 重型计算复跑要求

不要求为了文档修改无条件重复所有 h=5/3/2 重型计算。

### 必须重新运行

```text
- Level1 脚本；
- Level2 MPI 脚本；
- automatic checker；
- 新增 sm2 small-matrix tests；
- 至少一个 benchmark 输出根验证；
- Quick Start 中的快速 2D/3D 命令。
```

### 条件性重新运行

```text
- 若修改 production solver 数值逻辑，必须重跑 h=5，必要时 h=2；
- 若只修改脚本、metadata、文档、output root，不强制重跑 h=2；
- 若移动 artifact 而非重新计算，record 必须明确 source commit/run 和 relocation；
- h=2 direct 仍不要求在 14 GB 环境中运行。
```

---

## 27. V2 审查预期

Codex 完成 response 后，V2 将重点检查：

```text
1. benchmark 脚本能否与 manifest 一致；
2. checker 能否自动判定三网格 Gate；
3. benchmark artifacts 是否不再写 results/；
4. 环境是否可构建或被诚实限定；
5. Quick Start 是否从零可执行；
6. Capability Matrix 是否完整且状态统一；
7. Code Walkthrough 是否足以理解 2D/3D 调用链；
8. sm2 是否有直接测试；
9. ordinary default 是否仍未改变；
10. 新增文档本地链接是否通过。
```

---

# PART VII：V1 最终结论

## 28. 最终决定

```text
Task028 core consolidation = ACCEPTED
Task028 numerical reproduction = ACCEPTED
Task028 documentation and benchmark productization = CHANGES REQUIRED
Task028 branch status = NOT READY FOR MASTER MERGE
```

理由：

```text
1. clean master 上的选择性抽取是成功的；
2. Task026/Task027 成功路径已经与失败研究代码分离；
3. h=5/3/2 数值复现可信；
4. h=2 三残差、R/T/A 和内存 Gate 通过；
5. ordinary direct 默认没有改变；
6. 但 benchmark 实际输出目录违反既定边界；
7. benchmark scripts 无法完整重现当前记录；
8. Gate 不是自动执行；
9. 环境仍依赖本地 latest 镜像；
10. Quick Start、Capability Matrix、Code Walkthrough 与 Solver Guide 不足；
11. sm2 关键 production 分支缺少聚焦测试。
```

Task028 应继续在同一分支修正，不需要新建 Task 或分支。完成 `response_v1.md` 后进入 `review_report_v2.md`。

# Task038 Review Report V1：双分支协调、选择性合入 master 与远程发布

## 0. 审阅身份与授权边界

```text
review                              = Task038 Review Report V1
repository                          = Rookie1234567/MyFEniCS
reviewed_master                     = c2a6fc1ea2d91a42e8433ea94db8c832e1036a54
primary_branch                      = codex/20260812-task38-input-driven-configuration
primary_reviewed_head               = 7a756f3a3e934c9bff7059fbad63110f9f5eacd0
secondary_branch                    = codex/20260812-repository-readability-cleanup
secondary_reviewed_head             = cc7ad352d1d6974c08c14984ede3397d66c08edd
primary_vs_master                   = ahead 28 / behind 0
secondary_vs_master                 = ahead 30 / behind 0
secondary_vs_primary                = ahead 2 / behind 0
canonical_Task38_source             = primary_branch
whole_branch_merge                  = forbidden
bulk_unreviewed_cherry_pick         = forbidden
selective_master_integration        = authorized subject to all Gates
optional_readability_child_layer    = authorized subject to M7 and final Gates
push_origin_master                  = authorized subject to all Gates
force_push_master                   = forbidden
new_branch_creation                 = not_requested / forbidden in this handoff
ordinary_numerical_defaults         = unchanged
public_user_entry_change            = authorized as reviewed Task38 migration
```

本报告以 `codex/20260812-task38-input-driven-configuration` 为唯一 Task38 功能与证据主线。
`codex/20260812-repository-readability-cleanup` 不是第二套 Task38，也不是相互竞争的实现；它是
Task38 closeout HEAD 的严格两提交后继，只增加一轮保守入口删除和说明文档。

Task38 最终科学/工程分类为：

```text
TASK038_ACCEPTED_FOR_SELECTIVE_MASTER_INTEGRATION
```

其含义是：

- 一个 `.dat` 文件已经能够唯一描述一次运行；
- method、solver、MPI、M、输出与资源限制均从同一文件读取；
- Full3D direct、Hybrid direct、Hybrid iterative、普通 2D 和 staged 3D adapter 已接入；
- 公开输入、派生配置、输入/物理/source hash 与结果 manifest 已闭环；
- 11 个普通 preset 已迁移为 dat，6 个 research/history replay 继续隔离保留；
- 数值核心、Maxwell 公式、DtN、Hybrid、block-LDU 和 ordinary solver 数学没有改变；
- 分支证据足以批准选择性合入，但不批准无审计的 whole-branch merge。

---

# 1. 两个 20260812 分支的准确关系

## 1.1 Task38 主分支

```text
branch = codex/20260812-task38-input-driven-configuration
head   = 7a756f3a3e934c9bff7059fbad63110f9f5eacd0
base   = master c2a6fc1ea2d91a42e8433ea94db8c832e1036a54
```

该分支包含 Task38 的完整功能、测试、数值对照、preset 迁移、五个旧 3D 副本删除、用户手册
和结项证据。它相对 master 为线性 `ahead 28 / behind 0`。

Task38 closeout 已记录：

```text
public command = python scripts/run_case.py input/path/to/case.dat
one dat         = one run
schema          = 5 identity keys + 9 sections + 100 public fields
full pytest     = 1119 passed / 48 skipped / 0 failed
```

## 1.2 Repository readability cleanup 分支

```text
branch = codex/20260812-repository-readability-cleanup
head   = cc7ad352d1d6974c08c14984ede3397d66c08edd
base   = Task38 head 7a756f3a3e934c9bff7059fbad63110f9f5eacd0
```

该分支与 Task38 主分支没有平行数值开发。它只多出两个提交：

```text
2e35d98e6e8f78f25b8b5fcdc1ba6fe330f6ba19
chore(repo): retire obsolete legacy entry points

cc7ad352d1d6974c08c14984ede3397d66c08edd
docs(repo): record canonical readability cleanup
```

两提交的唯一实质差异为：

### 删除五个已经由调用图判定不可达的入口

```text
run_demo.sh
run_demo_mpc.sh
run_demo_mpi.sh
src/runners/run_grating_manual.py
src/runners/run_grating_mpc_official.py
```

这些删除不移除 manual、`mpc_official`、MPI、Floquet 或端口计算能力；对应功能已由一个完整
`.dat` 文件中的 `method.constraint_backend` 与 `execution.mpi_size` 选择。

### 更新说明与导航

```text
docs/README.md
docs/repository_readability_cleanup_20260812.md
notes/parallel/parallel_v2_guide.md
notes/quick_start/pycharm_mpc_docker_setup.md
notes/theory/implementation_notes.md
notes/theory/port_total_formulation_and_run_management.md
```

该后继分支没有修改数值求解器、输入 schema、adapter、阈值或 ordinary default。其 focused
检查为 `226 passed`、`1167 tests collected`、public validate/dry-run通过、benchmark
`302/302`、compileall和diff-check通过；它没有单独运行 full repository pytest。

## 1.3 主审决定

```text
Task38功能和证据权威 = Task38主分支
readability分支角色   = 可选择加入的两提交清理层
```

不得直接以 readability 分支代替 Task38 审阅来源，也不得先 merge Task38、再 merge其严格后继
形成重复历史。正确方式是：

1. 从最新 master 建立仅本地 integration 分支；
2. 按本报告 M0–M6 选择性移植 Task38 主分支；
3. 再按 M7 单独决定是否移植 readability 的两提交内容；
4. 在最终合成 HEAD 上统一运行全部 Gate；
5. 只推送一个最终 master 线性历史。

---

# 2. Task38 已完成的能力与证据

## 2.1 单一 dat 用户入口

普通用户入口已经收敛为：

```bash
python scripts/run_case.py input/path/to/case.dat
```

普通运行不再要求：

```text
--run
--method
--mpi-size
--requested-modes
```

辅助命令仅为：

```bash
python scripts/run_case.py input/path/to/case.dat --validate-only
python scripts/run_case.py input/path/to/case.dat --dry-run
```

一个 dat 必须恰好包含：

```text
schema_version / model_id / run_id / comparison_group / dimension

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

## 2.2 严格输入合同

已实现并测试：

- TOML-compatible `.dat`，标准库 `tomllib`，无新外部依赖；
- 未知 section、未知键、重复键、错误类型和方法不适用字段 fail closed；
- 不使用 `eval()`、`exec()` 或任意 Python 表达式；
- 复数以 `[real, imag]` 表示；
- angle/grazing、材料、网格、method、solver、MPI 与输出跨字段验证；
- immutable `RunSpecification`；
- schema 与 `input/README.md` 的 100-key coverage 自动一致；
- 用户输入和程序派生量明确分离。

## 2.3 运行与结果溯源

每次运行保存：

```text
input_original.dat
resolved_config.json
run_manifest.json
input_sha256.txt
physical_model_sha256.txt
source_sha.txt
run_summary.json
numerical_output/
```

建议结果路径：

```text
results/<model_id>/<run_id>__<method>__mpi<N>__M<M-or-na>/<timestamp>/
```

`execution.mpi_size` 由外层 launcher读取并负责启动 MPI；worker 必须复核真实
`MPI.COMM_WORLD.size`，不允许用户忘记或在命令行静默覆盖。

## 2.4 已接入的方法

```text
ordinary 2D
staged 3D smoke
Full3D direct
Hybrid direct
Hybrid iterative
```

adapter复用现有 solver/runner，没有复制 Maxwell、DtN、Hybrid 或 block-LDU 数值核心。

## 2.5 正式数值证据

### T4 Full3D direct MPI1

```text
true residual = 5.520787756471226e-14
R             = 0.9997827084780738
T             = 0.00010870177442776488
A_volume      = 0.00010858974749584228
old/new shared observables delta = 0
```

### T5 Hybrid direct MPI4

```text
legacy residual = 5.014855373361551e-12
new dat residual= 3.891075584849558e-12
R               = 0.08902106910587838
T               = 0.4425867427441033
A_balance       = 0.4683921881500183
A_volume        = 0.46839218817098305
closure         = 2.096478546320668e-11
```

功率和显著复振幅差异保持机器精度数量级。exact monolithic NNZ差异被如实保留为独立QEP
基底/显著性筛选下的 diagnostic non-invariant，没有调整阈值凑相等。

### T6 Hybrid iterative MPI8

```text
iterations      = 1771
reported        = 3.061632638614486e-09
global          = 3.061639832972372e-09
bottom          = 4.880059476090313e-09
top             = 2.4282287434315664e-09
modal           = 3.106265787799924e-15
max traction    = 4.880059476090313e-09
R               = 0.3656257867289616
T               = 0.012990632358457535
A               = 0.6213835809125808
A_volume        = 0.6213835766254876
closure         = -4.287093235966211e-09
swap            = 0
```

process-tree RSS 为 `6585.01953125 MiB`，超过该 profile 的 6144 MiB preferred line，但该线是
资源偏好而不是 Task38 输入等价性的数值失败。不得将其改写为低于 6 GiB，也不得据此否定
adapter正确性。

### T7 轻量 ordinary 对照

- 2D TM PML old/new：共同 residual、mesh、DoF、orders、R/T/A 全部通过；
- Stage1 old/new：共同 mesh、DoF、matrix和solution observables通过。

## 2.6 全仓测试

最终、环境身份纠正后的无 deselect运行：

```text
python -m pytest -q
1119 passed / 48 skipped / 0 failed
1514.73 s
```

首轮隔离 worktree 因 `.venv` identity 未接线导致一个 ABI diagnostic failure；同一 code/config
parent下纠正 worktree到canonical qualified venv后，targeted node和final full均通过。该首轮
failure保留为环境证据，未通过修改测试、阈值或代码掩盖。

## 2.7 仍需保持的边界

- T4/T5 canonical selected-field comparison是 `not_run_by_capability`，不得补写成 pass；
- Task38 当前 MPI1 dat仅validate/dry-run，本轮没有 current-same-SHA Hybrid iterative MPI1 formal；
- 三个 inherited formatter debt在base和Task38均存在，不能冒充全量format pass；
- 6个research/history preset继续保留旧内部 replay，不属于普通用户 dat mapping；
- Task38改变的是公开用户入口，不是ordinary numerical算法。

---

# 3. 选择性合入总原则

## 3.1 禁止 whole-branch merge

禁止：

```bash
git merge codex/20260812-task38-input-driven-configuration
```

也禁止：

```bash
git merge codex/20260812-repository-readability-cleanup
```

禁止无清单执行：

```bash
git cherry-pick master..codex/20260812-task38-input-driven-configuration
```

Task38触及输入、launcher、兼容入口、benchmark调用、用户文档、测试和旧模块删除，必须按依赖组
选择性移植并形成职责清晰的线性提交。

## 3.2 推荐集成工作方式

从最新 `origin/master` 建立一个**仅本地、不得推送**的临时集成分支/worktree：

```text
local-only/task38-selective-integration
```

在该分支完成 M0–M7、全部测试和PDE Gate。全部通过后，将本地 `master` fast-forward到该
集成HEAD，再普通推送 `origin/master`。

不得在用户存在未提交修改的工作树中执行checkout、stash、reset、clean或覆盖。

## 3.3 公开入口与数值默认的区别

Task38经过审阅后允许：

```text
普通用户推荐入口 -> 单一 .dat
无参数 src.main   -> 不再静默运行预制案例
```

但必须继续保持：

```text
Maxwell/Hybrid/DtN数学             = unchanged
ordinary direct/iterative算法参数   = unchanged
research/history replay能力         = retained
```

不得把用户入口重构描述为新物理或新求解器。

---

# 4. M0：输入 schema、说明书与模板

选择性移植：

```text
input/README.md
input/templates/**
input/examples/**
input/official/**
input/smoke/**
input/local/.gitignore

src/io/__init__.py
src/io/input_schema.py
src/io/input_loader.py
src/io/input_validation.py
src/io/run_specification.py
src/io/resolved_config.py
src/io/execution_plan.py
src/io/preset_migration.py
```

要求：

- schema key集合与README参数表完全一致；
- 一个dat只表示一个run；
- 不引入多run/batch语法；
- 不允许raw PETSc option、authority路径/hash或内部QEP/lifecycle参数成为public key；
-模板和official/smoke文件全部通过strict validate。

---

# 5. M1：public launcher与方法adapter

选择性移植：

```text
scripts/run_case.py
src/runners/task038_launcher.py
src/runners/task038_input_worker.py
src/runners/task038_2d.py
src/runners/task038_full3d_direct.py
src/runners/task038_hybrid_direct.py
src/runners/task038_hybrid_iterative.py
```

以及以下文件的**最小Task38 hunk**：

```text
src/common/config_3d.py
src/postprocessing/diffraction_3d.py
benchmarks/run_task032_phase6_augmented.py
```

不得用Task38分支整文件覆盖master中随后可能存在的独立改动。必须逐hunk确认：

- public dat mapping；
- reporting order与outgoing DtN mode set解耦；
- Hybrid direct显式argv/config override seam；
- 无参数旧行为和research replay不被意外改变。

不得夹带新solver family、阈值变化或Task37历史campaign代码。

---

# 6. M2：兼容入口与preset迁移

选择性移植 `src/main.py` 中：

- 11个普通preset改为dat alias；
- 6个research/history preset继续走原replay；
- 无参数运行显示迁移提示并非零退出；
- normal user path只指向 `scripts/run_case.py`。

同时移植：

```text
benchmarks/cases/001_2d_tm_pml_floquet/{README.md,config.json,run.sh}
benchmarks/cases/010_3d_stage1_airbox/{README.md,config.json,run.sh}
benchmarks/cases/011_3d_stage2a_floquet/{README.md,config.json,run.sh}
benchmarks/cases/012_3d_stage2b_pml/{README.md,config.json,run.sh}
benchmarks/cases/013_3d_stage2c_fresnel/{README.md,config.json,run.sh}
benchmarks/cases/020_3d_stage4a_flat_dtn/{README.md,config.json,run.sh}
```

以及Task38中面向当前用户的README/quick-start/code-walkthrough更新。

不得批量重写纯历史论文/理论记录；历史命令应保留明确“历史资料”标记，而不是伪装成当前入口。

---

# 7. M3：测试与compact evidence

选择性移植：

```text
src/test/test_260_task038_input_schema.py
src/test/test_261_task038_input_resolution.py
src/test/test_262_task038_execution_plan_contract.py
src/test/test_263_task038_launcher_contract.py
src/test/test_264_task038_full3d_direct_adapter.py
src/test/test_265_task038_hybrid_direct_adapter.py
src/test/test_266_task038_hybrid_iterative_adapter.py
src/test/test_267_task038_preset_migration.py
```

以及下列existing tests中的Task38 contract hunk：

```text
src/test/test_13_3d_stage_entrypoints.py
src/test/test_16_2d_euv_inputs_and_mesh.py
src/test/test_27_main_preset_contract.py
```

compact records与Task38 outcomes可以进入master：

```text
docs/task038_input_driven_configuration/task.md
docs/task038_input_driven_configuration/response_v1.md
docs/task038_input_driven_configuration/outcomes/**
```

禁止提交：

```text
results/**
benchmarks/artifacts/** heavy raw files
.venv symlink
__pycache__ / *.pyc
worktree quarantine/cache目录
临时pytest日志
```

---

# 8. M4：Task38已审旧3D副本删除

Task38主分支已经通过调用图、focused tests和full pytest审计以下五个不可达旧副本：

```text
src/runners/run_3d_airbox_old.py
src/solvers/solve_airbox_maxwell_3d_old.py
src/solvers/solve_maxwell_3d_common_old.py
src/solvers/solve_maxwell_3d_stage_2_no_grating_old.py
src/solvers/solve_maxwell_3d_stage_4_grating_old.py
```

允许删除，但必须在最终integration HEAD再次确认：

```text
no current import
no dynamic registration
no benchmark replay dependency
no tracked documentation claims it as current entry
```

不得将“文件名含 old”作为唯一删除依据，也不得扩展删除到未经本报告列出的文件。

---

# 9. M5：用户文档与导航

必须将当前用户文档统一到：

```text
python scripts/run_case.py input/path/to/case.dat
```

至少包括：

```text
README.md
input/README.md
notes/quick_start/** 当前入口相关文档
notes/reference/code_walkthrough/00_repository_architecture.md
notes/reference/code_walkthrough/01_main_and_runner_dispatch.md
notes/reference/code_walkthrough/11_2d_floquet_pml_port_forms.md
```

要求：

- method、MPI、M来自dat；
- `--validate-only`/`--dry-run`不启动PDE；
- 结果目录、manifest和hash解释正确；
- 100个public fields均有类型、单位、适用性和跨字段说明；
- 不把research replay包装成普通用户入口；
- 所有display math使用 fenced `math`。

---

# 10. M6：Task38结项与项目总账

选择性移植Task38结项证据，并更新：

```text
docs/development_progress.md  # 若当前master已有同类总账，逐hunk追加
docs/README.md               # 只追加当前入口和Task38导航
```

若Task38分支本身没有修改某个总账文件，不得凭空覆盖master版本；只根据最终集成结果做最小追加。

最终master文档必须如实保留：

```text
Task38 full pytest = 1119 passed / 48 skipped / 0 failed on source branch
integration full pytest = final HEAD actual result
T6 RSS = 6585.01953125 MiB, resource preference not met
current-same-SHA Hybrid iterative MPI1 formal = not run in Task38
T4/T5 selected-field capability = not_run_by_capability
```

---

# 11. M7：readability后继清理层

## 11.1 主审结论

readability分支的两个提交与Task38方向一致，且没有数值代码变更。它们被**授权但不强制**纳入
最终master。

推荐在M0–M6完成后，按以下精确白名单手工移植或逐提交cherry-pick：

```text
2e35d98e6e8f78f25b8b5fcdc1ba6fe330f6ba19
cc7ad352d1d6974c08c14984ede3397d66c08edd
```

## 11.2 允许删除

```text
run_demo.sh
run_demo_mpc.sh
run_demo_mpi.sh
src/runners/run_grating_manual.py
src/runners/run_grating_mpc_official.py
```

前提是最终integration HEAD再次通过：

- caller/import/dynamic registration audit；
- current public dat `validate-only`/`dry-run`；
- 2D manual与`mpc_official` capability仍由dat/backend调用；
- full repository pytest。

## 11.3 失败回退

若M7引起任何调用、测试、文档或benchmark失败：

```text
只撤销/省略M7
保留Task38 M0–M6
重新运行受影响Gate
```

不得因为可读性清理失败而否定已通过的Task38 input-driven core，也不得为了保留删除项而修改
solver或测试。

---

# 12. 推荐的集成提交计划

建议形成如下线性提交；可根据真实依赖微调，但每个提交必须职责单一：

```text
feat(task038): add typed dat schema and resolved run specification

feat(task038): add single-dat launcher and method adapters

refactor(task038): migrate ordinary presets to dat aliases

test(task038): add input, launcher, adapter, and migration coverage

docs(task038): add public input manual and migrated examples

refactor(task038): remove audited unreachable legacy 3d copies

docs(task038): record equivalence evidence and closeout

chore(repo): retire audited obsolete legacy entry points       # M7 optional

docs(repo): record post-Task38 readability cleanup             # M7 optional
```

禁止：

- merge commit；
- squash成一个无法审阅的大提交；
- 将readability分支当成第二次完整Task38 merge；
- 将heavy raw evidence写入Git。

---

# 13. 最终集成静态与合同Gate

## 13.1 Source与Git

```text
origin/master fetched immediately before integration
integration base == latest origin/master
worktree clean
no untracked artifact collision
no merge commit
no force update
```

## 13.2 输入与文档合同

必须运行：

- 所有 `input/templates/*.dat` strict validate；
- 所有 `input/examples/*.dat` strict validate；
- 所有 `input/official/*.dat` strict validate；
- 所有 `input/smoke/*.dat` strict validate；
- 至少对四种方法模板运行 `--dry-run`；
- dry-run不得创建数值结果目录或启动MPI/PDE；
- schema keys与`input/README.md` coverage完全一致；
- Markdown相对链接与fenced-math合同；
- compact JSON parse。

## 13.3 Focused tests

至少运行：

```text
src/test/test_13_3d_stage_entrypoints.py
src/test/test_16_2d_euv_inputs_and_mesh.py
src/test/test_26_documentation_contract.py
src/test/test_27_main_preset_contract.py
src/test/test_260_task038_input_schema.py
src/test/test_261_task038_input_resolution.py
src/test/test_262_task038_execution_plan_contract.py
src/test/test_263_task038_launcher_contract.py
src/test/test_264_task038_full3d_direct_adapter.py
src/test/test_265_task038_hybrid_direct_adapter.py
src/test/test_266_task038_hybrid_iterative_adapter.py
src/test/test_267_task038_preset_migration.py
```

加上M7删除入口的caller/compatibility tests。

## 13.4 MPI contract tests

轻量contract fixture至少运行：

```text
MPI1
MPI2
MPI4
```

重点验证：

- launcher读取dat中的MPI数；
- worker实际MPI size一致；
- source/input/physical hash一致；
- resolved config跨rank一致；
- failure后无orphan；
- validate/dry-run不启动MPI worker。

## 13.5 静态检查

```text
ruff check
python -m compileall -q src scripts benchmarks
git diff --check
python benchmarks/check_benchmarks.py --no-write
```

格式检查采用两层合同：

1. 新增Task38 Python文件必须全部 `ruff format --check` 通过；
2. 对三个已记录的 inherited formatter-debt文件，不允许新增格式退化或借Task38大规模重排；
   必须记录base/final状态和AST等价审计，不能声称全文件format pass。

---

# 14. 最终集成数值Gate

所有重型作业必须在最终拟推送HEAD、clean source、同一qualified环境上串行运行。

## 14.1 轻量 ordinary回归

至少运行：

```text
input/smoke/2d_tm_pml_floquet_smoke.dat
input/smoke/3d_stage1_airbox_smoke.dat
```

要求与Task38记录的共同mesh/DoF/residual/physics observables一致。

## 14.2 Full3D direct adapter anchor

运行Task38 T4小型Full3D dat或等价集成fixture，要求：

```text
true residual <= recorded Gate
R/T/A finite
input/resolved/manifest/source hashes complete
no CLI physical override
```

## 14.3 Hybrid direct adapter anchor

运行Task38 T5 M160 MPI4 authority或同一冻结dat，要求：

```text
true residual <= 1e-9 or inherited formal threshold
R/T/A/A_volume/closure through accepted Gate
external orders and amplitudes finite
legacy/dat shared observables through recorded tolerance
swap = 0
```

NNZ差异继续只作diagnostic，不允许改变QEP阈值凑相等。

## 14.4 Hybrid iterative adapter anchor

运行Task38 T6冻结MPI8 dat：

```text
five multimetric residuals <= 5e-9
exact traction <= 1e-8
R/T/A/A_volume/closure pass
orders/recovery/lifecycle pass
no direct fallback
swap = 0
```

资源分类必须使用实测process-tree RSS。若仍高于6144 MiB，保持
`numerical pass / preferred resource not met`；不得把它写成数值失败，也不得静默声称低于6 GiB。

## 14.5 Full repository pytest

在M0–M7全部最终化、所有代码/测试/删除都完成后，运行一次：

```bash
python -m pytest -q
```

要求：

```text
no deselect
no xfail added to hide new failure
zero failures
qualified complex ABI identity
```

若只在readability M7层出现失败，可按11.3省略M7后重新运行；Task38 core本身的任何失败都禁止
推送master。

---

# 15. 推送 master Gate

只有以下全部满足，才允许：

```bash
git push origin master
```

条件：

- final integration HEAD基于最新origin/master；
- diff只包含M0–M6及通过Gate的M7白名单；
-没有whole-branch merge或重复Task38历史；
-所有input dat、schema、README和result provenance合同通过；
- focused、MPI contract、static、benchmark和full pytest通过；
- T4/T5/T6及轻量ordinary anchors通过；
- ordinary numerical algorithms/defaults未改变；
- public entry变更准确记录；
- worktree clean；
- `git diff origin/master...HEAD`与approved manifest一致。

推送必须是普通fast-forward/线性推送，禁止force push。

推送后确认：

```text
local master SHA  == origin/master SHA
master worktree   == clean
Task38 public dat entry present on origin/master
input/README.md present and schema-current
```

两个20260812远程分支继续作为历史证据保留；本报告不授权删除、重命名或强制移动它们。

---

# 16. Codex最终回报格式

完成后必须分别报告：

```text
A. Branch reconciliation
   master reviewed SHA
   Task38 primary reviewed SHA
   readability reviewed SHA
   proof secondary = primary + 2 commits

B. Selective integration
   local integration branch/worktree
   integration commits and one-line purpose
   exact M0–M7 files/hunks included
   exact excluded files/artifacts
   whether optional M7 was retained or omitted

C. Tests
   input validate/dry-run counts
   focused serial result
   MPI1/2/4 contract result
   Ruff/format-debt/compile/diff/benchmark result
   full pytest exact count and wall

D. Numerical anchors
   light 2D and Stage1
   Full3D direct
   Hybrid direct
   Hybrid iterative
   residual/physics/resource/swap summaries

E. Publication
   final local master SHA
   pushed origin/master SHA
   ahead/behind
   worktree status
```

不得把source-branch测试直接冒充final integration HEAD结果；必须明确区分继承证据与最终重跑。

---

# 17. 最终主审结论

```text
Task38 primary implementation         = accepted
Task38 one-dat-one-run user interface = accepted
Task38 schema/manual/provenance       = accepted
Full3D/Hybrid adapters                = accepted within reviewed capability
preset migration                     = accepted
five audited old 3d deletions         = accepted
readability child                     = strict two-commit descendant
readability extra cleanup             = authorized but optional after final Gates
whole branch merge                    = forbidden
selective master integration          = authorized
push origin/master                    = authorized after all Gates
new solver/physics work               = forbidden in this closeout
```

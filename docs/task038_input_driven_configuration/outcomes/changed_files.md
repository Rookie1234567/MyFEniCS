# Task38 changed-files 索引

基线为 Task38 初始 ancestor `c2a6fc1ea2d91a42e8433ea94db8c832e1036a54`，T9 implementation parent 为
`de2e1880fa90a442996ada58ea321c774752a5ca`。本文件所在的 T10 closeout candidate/commit
相对该基线的完整索引如下，包含此前实现与本次 closeout 文档；提交后以 closeout commit 绑定同一索引。

## 按职责分组

### schema / io / input

| 路径 | 状态 | 作用与依赖 |
|---|---|---|
| `input/README.md` | A | public schema 手册与 key coverage |
| `input/examples/.gitkeep`、`input/local/.gitignore`、`input/official/.gitkeep`、`input/smoke/.gitkeep` | A | 固定目录策略 |
| `input/examples/2d_euv_grating_direct.dat` | A | migrated 2D tutorial |
| `input/templates/full3d_direct_example.dat`、`hybrid_direct_example.dat`、`hybrid_iterative_example.dat`、`ordinary_2d_example.dat` | A | 四个完整 template |
| `input/official/grazing10_phi0_p2h5_hybrid_direct_m160_mpi4.dat`、`grazing1_phi0_full3d_direct_mpi8.dat`、`grazing1_phi0_hybrid_iterative_m120_mpi1.dat`、`grazing1_phi0_hybrid_iterative_m120_mpi8.dat`、`stage1_airbox_smoke_mpi2.dat` | A | official/identity-specific dat |
| `input/smoke/2d_complex_absorption.dat`、`2d_te_port_smoke.dat`、`2d_tm_dtn_auxiliary_smoke.dat`、`2d_tm_dtn_explicit_smoke.dat`、`2d_tm_pml_floquet_smoke.dat` | A | 2D migrated smoke |
| `input/smoke/3d_stage1_airbox_smoke.dat`、`3d_stage2a_floquet_smoke.dat`、`3d_stage2b_pml_smoke.dat`、`3d_stage2c_fresnel_smoke.dat`、`3d_stage4a_flat_layer_direct.dat` | A | 3D ordinary migrated smoke |
| `input/smoke/full3d_direct_p2_h100_mpi1.dat` | A | T4 small equivalence fixture |
| `src/io/__init__.py`、`execution_plan.py`、`input_loader.py`、`input_schema.py`、`input_validation.py`、`preset_migration.py`、`resolved_config.py`、`run_specification.py` | A | schema、strict resolution、immutable spec、plan、preset mapping |
| `src/common/config_3d.py`、`src/postprocessing/diffraction_3d.py` | M | 共享 3D mapping 与 reporting/DtN 解耦；ordinary defaults 保持 |

### task / handoff docs

| 路径 | 状态 | 作用与依赖 |
|---|---|---|
| `docs/task038_input_driven_configuration/task.md` | A | Task38 权威任务书、阶段 Gate、最终验收合同 |

### compatibility facade

| 路径 | 状态 | 作用与依赖 |
|---|---|---|
| `src/main.py` | M | 11 migrated dat alias 与 6 retained research/history replay 的薄兼容层 |

### launcher / adapters

| 路径 | 状态 | 作用与依赖 |
|---|---|---|
| `scripts/run_case.py` | A | 单 dat public entry |
| `src/runners/task038_input_worker.py`、`task038_launcher.py`、`task038_2d.py`、`task038_full3d_direct.py`、`task038_hybrid_direct.py`、`task038_hybrid_iterative.py` | A | worker contract、provenance、2D/3D/Hybrid adapters；复用现有 runners/solvers |
| `benchmarks/run_task032_phase6_augmented.py` | M | T5 显式 argv/config override seam；无参数旧行为保留 |

### tests / cases / evidence

| 路径 | 状态 | 作用 |
|---|---|---|
| `src/test/test_13_3d_stage_entrypoints.py`、`test_16_2d_euv_inputs_and_mesh.py`、`test_27_main_preset_contract.py` | M | retained/revised main and migrated input contracts |
| `src/test/test_260_task038_input_schema.py` 至 `test_267_task038_preset_migration.py` | A | T1–T7 schema、resolution、launcher、adapter、migration focused coverage |
| `benchmarks/cases/001_2d_tm_pml_floquet`、`010_3d_stage1_airbox`、`011_3d_stage2a_floquet`、`012_3d_stage2b_pml`、`013_3d_stage2c_fresnel`、`020_3d_stage4a_flat_dtn` 下的 `README.md`、`config.json`、`run.sh` | M | benchmark caller 改为 dat/identity-preserving 命令 |
| `docs/task038_input_driven_configuration/outcomes/inherited_master_audit.md`、`parameter_and_legacy_inventory.md`、`records/*.json` | A | T0 inventory 与 T4–T7 compact evidence |
| `docs/task038_input_driven_configuration/outcomes/preset_migration.md`、`legacy_cleanup.md` | A | T7/T9 evidence；T10 追加状态 |
| `docs/task038_input_driven_configuration/outcomes/summary.md`、`test_summary.md`、`input_schema_and_examples.md`、`changed_files.md`、`response_v1.md` | A | T10 closeout summary、Gate、schema索引、完整变更索引与正式答复 |

### docs / navigation

| 路径范围 | 状态 | 作用 |
|---|---|---|
| `README.md` | M | 仓库快速入口收敛为单一 `.dat` 命令 |
| `notes/quick_start/` 中当前入口、参数地图、2D/3D/Stage4 教程及历史 banner | M | 当前用户路径改为 dat；retained replay 保留 |
| `notes/reference/code_walkthrough/00_repository_architecture.md`、`01_main_and_runner_dispatch.md`、`11_2d_floquet_pml_port_forms.md` | M | architecture、dispatch、2D 调用链同步 |

### legacy removals

| 路径 | 状态 | 处置 |
|---|---|---|
| `src/runners/run_3d_airbox_old.py` | D | 不可达旧副本 |
| `src/solvers/solve_airbox_maxwell_3d_old.py` | D | 不可达旧副本 |
| `src/solvers/solve_maxwell_3d_common_old.py` | D | 不可达旧公共副本 |
| `src/solvers/solve_maxwell_3d_stage_2_no_grating_old.py` | D | 不可达旧 Stage2 副本 |
| `src/solvers/solve_maxwell_3d_stage_4_grating_old.py` | D | 不可达旧 Stage4 副本 |

## 数量、行为和合并顺序

本 Task38 closeout 的 base..closeout 完整索引共 **118 paths：A=64、M=49、D=5**；提交前以 staged/index 实算，提交后计数不变。生产依赖顺序是 schema/io → launcher/adapters → focused tests/cases → compact evidence/docs → legacy cleanup。数值行为：T4–T7 只接入既有 solver/runner，T5/T6 的研究 profile 明确 opt-in；ordinary defaults、solver 数学、retained replay 未改变。对应测试与 fresh PDE evidence 见 [`test_summary.md`](test_summary.md) 和 [`summary.md`](summary.md)。

`do-not-merge`：无。这里表示内容排除集，不构成 master merge approval。Task37/Task37c authority、历史 records、raw ignored carrier 不属于本 Task38 base..closeout 的可移植源文件；它们不能被当作新的 solver 输入或 merge artifact。

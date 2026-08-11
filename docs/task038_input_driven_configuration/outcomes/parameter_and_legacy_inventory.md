# Task38 T0：参数、preset 与 legacy 入口清单

## 1. 使用方法与九个目标 section

本清单把当前源码中已经存在的字段、CLI 和 preset 逐组登记，目的是让 T1 设计 `.dat` 白名单时知道每个值来自哪里。它不是新 schema，也不把当前 dataclass 自动变成 schema。源码证据见 [src/main.py](../../../src/main.py)、[config_3d.py](../../../src/common/config_3d.py)、[run_cases.py](../../../src/runners/run_cases.py)、[run_3d_cases.py](../../../src/runners/run_3d_cases.py) 和 [Task38 task.md](../task.md)。

Task38 要求每个正式输入固定包含以下九个 section；下表中的“拟映射”只表示 T1 的目标归属。

| section | 通俗作用 | 当前字段主要来源 |
|---|---|---|
| `geometry` | 描述计算区域、周期和 grating 尺寸 | 2D `Inputs2D`；3D `SimulationConfig3D` geometry/period/z 字段 |
| `materials` | 描述折射率、磁导率和材料标签 | `n_air`、`n_substrate`、`n_grating`、`mu_r`、labels |
| `incidence` | 描述波长、角度、偏振和幅值 | 2D `lambda0/incident_angle_deg`；3D incidence fields |
| `discretization` | 描述有限元阶次、网格尺寸和公开 Floquet/assembly 选择 | nedelec、mesh、backend、Floquet mode |
| `boundary` | 描述 PML、DtN、Robin、周期和采样边界 | 2D port/PML；3D boundary/diffraction fields |
| `method` | 说明 Full3D、Hybrid 或普通 2D 方法及其接口 | 当前 runner 分支、Task37c profile |
| `solver` | 说明 direct/iterative 求解器的公开有限选择 | PETSc profile、restart/tolerance 等；internal flags 不直接公开 |
| `execution` | 说明 MPI、内存警告、timeout 和 swap policy | watchdog/parser，部分当前源码只在 benchmark CLI |
| `output` | 说明结果目录和导出内容 | `unique_output/results_root`、reference/order/field export |

当前源码还没有把这九个 section 组合成一个输入对象；重复来源和待迁移处置如下。

处置枚举含义：`migrate_to_dat` 表示拟成为 T1 白名单键；`keep_as_internal_factory` 表示仍由内部 factory/resolver 管理；`keep_for_historical_replay` 表示只为旧命令或记录复现保留；`research_only_not_public` 表示不能成为普通输入键；`obsolete_delete_candidate` 表示仅候选删除；`legacy_alias_deprecate` 表示先保留兼容入口再逐步弃用。所有删除候选都必须理解为“仅候选；T7 等价性与 call graph 通过前不得删除”。

## 2. 2D 输入与 CLI inventory

### 2.1 `Inputs2D` 的 35 个字段

| 字段组 | 当前字段与源码默认 | 类型/单位与适用性 | 分类、拟映射和处置 |
|---|---|---|---|
| formulation/port | `calculation_method="port"`; `polarization_type="TM"`; `constraint_backend="manual"`; `scattering_background="layered"`; `port_boundary_model="dtn"`; `port_dtn_assembly="auxiliary"`; `port_use_diffraction_orders=True` | enum/bool；2D method 与 port 专用 | independent input；`method`/`boundary`；`migrate_to_dat` |
| geometry | `period_x=600`; `air_height=850`; `substrate_thickness=350`; `grating_width=300`; `grating_height=180`; `lambda0=633`; `incident_angle_deg=15` | float，长度和波长 nm，角度 deg；2D | independent input；`geometry`/`incidence`；`migrate_to_dat` |
| material | `n_air=1.0`; `n_substrate=1.45`; `n_grating=1.45` | real/complex index；2D | independent input；`materials`；`migrate_to_dat` |
| PML | `pml_top_thickness=300`; `pml_bottom_thickness=300`; `pml_alpha=5` | float，nm/无量纲；scattered/PML 适用 | independent input；`boundary`；`migrate_to_dat` |
| FE/mesh | `nedelec_degree=2`; `visualization_degree=2`; `mesh_target_size=25`; `mesh_cell_shape="triangle"`; `mesh_lock_near_field_template=False` | int/float/bool，h 为 nm；2D | independent input；`discretization`；`migrate_to_dat` |
| near field | `near_field_margin_x=25`; `near_field_air_top=100`; `near_field_sub_depth=50` | float，nm；2D postprocess | independent/output input；`output`；`migrate_to_dat` |
| metrics/order | `compute_power_metrics=True`; `diffraction_order_count=None`; `power_probe_num_points=None`; `port_use_pml=None` | bool/int/optional；method-specific | `port_use_pml` 是 boundary，其他为 output/postprocess；`migrate_to_dat` 但需 method validation |
| output | `generate_png_plots=False`; `unique_output=True`; `results_root=None` | bool/path；2D | output/provenance；`migrate_to_dat`，路径必须受控 |

`EUVGratingInputs2D` 覆盖 14 个字段：`period_x=100`、`air_height=100`、`substrate_thickness=50`、`grating_width=50`、`grating_height=50`、`lambda0=13.5`、`incident_angle_deg=0`、`n_substrate=1.1`、`n_grating=1.2`、PML 上下各 25、`mesh_target_size=1.5`、`mesh_cell_shape="quadrilateral"`、`mesh_lock_near_field_template=True`。它是 preset/factory 来源，不应产生与 `[geometry]` 平行的第二套公开键。

### 2.2 2D CLI 36 个选项

| CLI 组 | 当前 flags | 当前默认/来源 | T1 处置 |
|---|---|---|---|
| method/port | `--formulation`, `--constraint-backend`, `--scattering-background`, `--port-boundary-model`, `--polarization-type`, `--port-dtn-assembly` | parser 多为 `None`，由 `SimulationConfig()` 或组合逻辑补齐；choices 在 runner | 公开白名单；`method`/`boundary`；`migrate_to_dat` |
| FE/mesh | `--nedelec-degree`, `--visualization-degree`, `--mesh-target-size`, `--mesh-cell-shape`, `--lock-near-field-template` | None override；`BooleanOptionalAction` 用于布尔 | `discretization`；`migrate_to_dat` |
| geometry/incidence | `--period-x`, `--air-height`, `--substrate-thickness`, `--grating-width`, `--grating-height`, `--lambda0`, `--incident-angle-deg` | None override，单位在 help/source | `geometry`/`incidence`；`migrate_to_dat` |
| materials/PML | `--n-air`, `--n-substrate`, `--n-grating`, `--pml-top-thickness`, `--pml-bottom-thickness`, `--pml-alpha` | complex parser 与 float；None override | `materials`/`boundary`；`migrate_to_dat` |
| output/metrics | `--diffraction-order-count`, `--power-probe-num-points`, `--compute-power-metrics`, `--generate-png-plots`, `--unique-output`, `--results-root` | None 或 bool；results root 默认 repo/results | `output`；`migrate_to_dat` |
| near field/legacy | `--near-field-margin-x`, `--near-field-air-top`, `--near-field-sub-depth`, `--port-order-count`, `--port-use-diffraction-orders`, `--port-use-pml` | `port-order-count` 是旧 search cap metadata | near/output 可迁移；`port-order-count` `keep_for_historical_replay`，T7 前不得删 |

注意：`--formulation=both/all`、`--constraint-backend=both`、`--port-boundary-model=all` 会由 runner 展开多个 case；一个 Task38 `.dat` 应表示一次计算，不能默默继承这种 batch expansion。若保留旧命令，需 `legacy_alias_deprecate` 并显式报告。

## 3. 3D preset 输入与 64 个 runner flags

### 3.1 3D preset dataclass 字段组

当前 AST 计数为 Stage1 21、Stage2 23、Stage4 60 字段。它们是面向 PyCharm/runner 的输入载体，并不是最终 schema。

| dataclass | 字段组 | 主要字段 | 默认/处置 |
|---|---|---|---|
| `Stage1AirboxInputs3D` | identity/incidence | `stage_case`, `case`, `incident_theta_deg`, `incident_phi_deg`, `polarization_kind` | stage1/normal/None/None/None；preset 层，`keep_as_internal_factory` |
| `Stage1AirboxInputs3D` | FE/mesh | `nedelec_degree`, `visualization_degree`, `mesh_target_size`, `mesh_cell_type`, `mesh_spacing_mode`, `mesh_refined_size`, `mesh_refinement_radius`, `floquet_constraint_mode` | p1/visual1/h5/auto/auto/None/None/auto；可映射 `discretization`，但 resolved mode internal |
| `Stage1AirboxInputs3D` | physical/output | `lambda0`, `period_x`, `period_y`, `air_height`, `substrate_thickness`, `divergence_penalty`, `unique_output`, `results_root` | 633、10/10、5/5、0、0、True、None；geometry/output；`migrate_to_dat` |
| `Stage2NoGratingInputs3D` | identity/incidence/FE | 与 Stage1 同名字段 | stage2/floquet-airbox 组；用 `keep_as_internal_factory` 保持 preset identity |
| `Stage2NoGratingInputs3D` | boundary/material | `use_floquet_xy`, `use_pml`, `pml_top_thickness`, `pml_bottom_thickness`, `pml_alpha`, `n_substrate` | None/None/250/250/5/1.45；boundary/material；`migrate_to_dat` 后需 stage 校验 |
| `Stage2NoGratingInputs3D` | output | `divergence_penalty`, `unique_output`, `results_root` | 0/True/None；divergence 是实验诊断，`research_only_not_public` |
| `Stage4GratingInputs3D` | identity/incidence | source/CLI 使用 `stage_case`, `case`, `incident_theta_deg`, `incident_phi_deg`, `polarization_kind` | stage4/normal/None/None/None；Stage4 T1 public key 为 `grazing_angle_deg` + `azimuth_deg`，内部 theta=90-grazing 派生；`from_simulation_config` 会强制 `case="oblique"` |
| `Stage4GratingInputs3D` | FE/mesh | `nedelec_degree`, `nedelec_trace_degree`, `nedelec_interior_degree`, `visualization_degree`, `mesh_target_size`, `mesh_cell_type`, `mesh_spacing_mode`, `mesh_refined_size`, `mesh_refinement_radius`, `floquet_constraint_mode` | p2/None/None/1/h5/auto/auto/None/None/auto；trace pair/mesh plan需 validation |
| `Stage4GratingInputs3D` | wavelength/material/geometry | `lambda0`, `n_substrate`, `substrate_material_label`, `period_x`, `period_y`, `air_height`, `substrate_thickness`, `n_grating`, `grating_material_label`, `validation_role`, `grating_width_x`, `grating_width_y`, `grating_height` | EUV 13.5、Si complex、100/100、50/50、Si block 50、sanity；多数可进 geometry/material |
| `Stage4GratingInputs3D` | boundary/backend | `scattering_background`, `stage4_boundary_model`, `stage4_dtn_order_policy`, `stage4_dtn_assembly`, `stage4_full3d_assembly_backend`, `stage4_variable_p_cell_degree_plan`, `stage4_local_h_refinement_plan`, `stage4_pml_outer_bc` | layered/dtn/zero_order/auxiliary/standard_full/None/None/natural；public backend 只能有限 enum |
| `Stage4GratingInputs3D` | diffraction/output | `diffraction_zero_order_only`, `diffraction_order_max_m`, `diffraction_order_max_n`, `diffraction_sample_count_x`, `diffraction_sample_count_y`, `diffraction_top_probe_z`, `diffraction_bottom_probe_z`, `diffraction_probe_fraction`, `diffraction_compute_modal_diagnostic`, `diffraction_rayleigh_tol` | orders/probes 与 `export_fields`、`canonical`、`modal`、`reference_planes` 是受控 output 输入；modal diagnostic 的内部实现/容差仍 internal |
| `Stage4GratingInputs3D` | PETSc/diagnostic/output | `petsc_direct_solver_profile`, `petsc_ksp_view`, `petsc_log_view`, `petsc_extra_options`, `matrix_diagnostics_assemble_unconstrained`, `matrix_diagnostics_assemble_only`, `unique_output`, `results_root` | direct profile 是受审有限枚举并迁移到 `solver`；raw PETSc/view/log/diagnostic 仍 internal；output 可迁移 |

### 3.2 3D CLI 64 flags

| CLI 组 | flags | 当前 parser 行为 | T1 处置 |
|---|---|---|---|
| stage/FE/mesh | `--stage-case`, `--case`, `--nedelec-degree`, `--nedelec-trace-degree`, `--nedelec-interior-degree`, `--visualization-degree`, `--mesh-target-size`, `--mesh-cell-type`, `--mesh-spacing-mode`, `--mesh-refined-size`, `--mesh-refinement-radius`, `--floquet-constraint-mode` | stage/case 有 choices；其余多数 None override | stage/method section + explicit schema; `migrate_to_dat` |
| incidence/physical | `--lambda0`, legacy `--incident-theta-deg`/`--incident-phi-deg`, `--polarization-kind`, `--divergence-penalty`, `--n-substrate`, `--n-grating`, `--substrate-material-label`, `--grating-material-label`, `--validation-role` | 当前 runner/source 使用 theta/phi mapping；Stage4 public schema 不要求用户同时输入 theta，complex values来自 string；custom polarization未由该 runner直接接受 | Stage4 `lambda0`, `grazing_angle_deg`, `azimuth_deg`, polarization/material `migrate_to_dat`；内部 theta=90-grazing 派生；2D/Stage1 角度约定标适用性，divergence/role internal |
| geometry | `--period-x`, `--period-y`, `--air-height`, `--substrate-thickness`, `--grating-width-x`, `--grating-width-y`, `--grating-height` | 显式值同时更新 z_min/z_max 或 block bounds | geometry migrate；derived z/bounds 不重复输入 |
| boundary/PML | `--scattering-background`, `--stage4-boundary-model`, `--stage4-dtn-order-policy`, `--stage4-dtn-assembly`, `--stage4-pml-outer-bc`, `--use-floquet-xy`, `--use-pml`, `--pml-top-thickness`, `--pml-bottom-thickness`, `--pml-alpha` | choices + BooleanOptionalAction；boundary model 会联动 use_pml/PML | boundary whitelist + cross-field validation |
| assembly plans | `--stage4-full3d-assembly-backend`, `--stage4-variable-p-cell-degree-plan`, `--stage4-local-h-refinement-plan` | backend 三选一；variable plan path 只在对应 backend需要 | backend可迁移；plan provenance/internal |
| orders/probes | `--diffraction-zero-order-only`, `--diffraction-order-max-m`, `--diffraction-order-max-n`, `--diffraction-sample-count-x`, `--diffraction-sample-count-y`, `--diffraction-top-probe-z`, `--diffraction-bottom-probe-z`, `--diffraction-probe-fraction`, `--diffraction-compute-modal-diagnostic`, `--diffraction-rayleigh-tol` | order/probe/output 选项；Task38 output 还明确 `export_fields`、`orders`、`canonical`、`modal`、`reference_planes` | output/order/reference keys `migrate_to_dat`；modal diagnostic 内部实现/容差仍 internal |
| reference/direct | `--full3d-reference-export`, `--full3d-reference-plane-z`, `--full3d-reference-sample-count-x`, `--full3d-reference-sample-count-y`, `--petsc-direct-solver-profile`, `--petsc-ksp-view`, `--petsc-log-view`, `--petsc-extra-option`, `--matrix-diagnostics-assemble-unconstrained`, `--matrix-diagnostics-assemble-only` | 当前 source 使用 `full3d_reference_export/plane_z/sample_count`；reference/PETSc/diagnostic 由 `_config_updates` 写入 cfg；direct profile 受审枚举 | `export_fields`/orders/`canonical`/`modal`/`reference_planes`、`reference_plane_z_nm`、`sample_count_x/y` `migrate_to_dat`；旧 authority path/hash、checker comparison path、raw PETSc/diagnostic internal |
| output | `--unique-output`, `--results-root` | 默认由 `SimulationConfig3D`；relative path 归 repo root | `output`；`migrate_to_dat` |

`execution.mpi_size` 是 Task38 明确迁移的 public input；它不是 `SimulationConfig3D` 的物理字段，而是 launcher/execution 层的整数输入，范围和 method-specific constraints 留给 schema/T2 validation。authority 路径、完整 SHA、container identity、watchdog resource thresholds 仍是 provenance/internal，不随 `mpi_size` 一起公开。

## 4. Task37b/c 参数、authority 与 research-only flags

### 4.1 Frozen M10

| 键/flag | 当前值/类型 | 适用性与来源 | 拟处置 |
|---|---|---|---|
| `target`, degree/h | `hybrid`, 6, 10.0 nm；p6/h10 | `FrozenM10Profile` 的 official template 值 | `migrate_to_dat`；是显式 M10 input，不是全局 default |
| geometry/material/incidence/output | 13.5 nm、S、grazing 10°、bottom 10/top 110 nm，以及结果/output 选择 | Frozen constants；对应独立物理与执行输入 | `migrate_to_dat`；official M10 template 显式给值，不进全局 default |
| requested_modes_per_direction / interfaces | requested 120；bottom 10/top 110 nm | official M10 template 显式值；是独立 public input | `migrate_to_dat`；不是全局 default |
| candidate mode pool / dynamic DtN | candidate 240；DtN 40/endcap | adapter 根据 requested M 派生；实际 mode count、40-mode K、Woodbury/Schur size 不属于用户输入 | `keep_as_internal_factory`；candidate pool 与动态内部规模不得暴露 |
| QEP controls | beta cutoff `1e4`、near-degenerate/block rotation `1e-6` | worker/QEP 内部数值细节 | `keep_as_internal_factory` 或 `research_only_not_public` |
| operator/PC | exact monolithic operator；fixed whole-endcap ILU0 + 40-mode DtN Woodbury；subdomain 1、overlap 0、ILU 0、shift .1 | accepted M10 solver template；内部 operator/QEP/lifecycle 由 adapter 派生 | accepted solver/PC identity 与 ILU/shift/subdomain/overlap `migrate_to_dat`；exact operator/QEP/lifecycle internal |
| linear solve | right FGMRES、restart 90、max_it 1000、rtol 5e-9、zero initial | accepted M10 template | `migrate_to_dat`；显式 template 值，不是全局 default |
| execution/authority | MPI8、warning/terminate/timeout/swap policy；`--h1-authority`、`--full3d-reference`、`--task035c-p6-preflight-authority` 及 SHA 对 | execution 是输入；authority 是 watchdog/runner provenance | execution controls `migrate_to_dat`；旧 flag、authority path/hash `keep_for_historical_replay`/`legacy_alias_deprecate` |
| `--frozen-m10` | mutually exclusive profile flag | 只允许完整旧 authority pairs | `legacy_alias_deprecate`，T7 等价性前不得删除 |

### 4.2 Task37c robustness profile

| 键/flag | 当前值/允许集合 | 分类与处置 |
|---|---|---|
| `grazing_angle_deg` / `azimuth_deg` | 当前 source/CLI 用 `incident_theta_deg`/`incident_phi_deg`；资格化模板对应 grazing=1°、azimuth=-5/0/+5、内部 theta=89° | `migrate_to_dat`；Stage4 不要求用户同时输入 theta，内部 theta=90-grazing 派生；范围与 method-specific constraints 由 T1 schema/T2 validation 明确，2D/Stage1 另一角度约定标 `unresolved_for_T1`，未审自动扫描仍 research |
| `requested_modes_per_direction` | 当前资格化模板含 120 或 160 | `migrate_to_dat`；M 是独立 public integer input，范围/组合约束 `unresolved_for_T1`；一个 `.dat` 只表示一个 run |
| candidate mode pool / dynamic DtN | 当前模板对应 candidate 240/320、40-mode K 与动态实际 mode count；adapter/solver 派生量 | `keep_as_internal_factory`；不得作为普通 input |
| interfaces | bottom 10/top 110 nm；Hybrid 独立 public interface input | `migrate_to_dat`；按 method-specific geometry constraints 校验 |
| MPI | 当前资格化模板含 1 或 8 | `migrate_to_dat`；`execution.mpi_size` 的范围与 method-specific constraints 由 schema/T2 validation 明确；authority 集合仍 internal |
| traction | `scalar_cg_discrete_derivative` 或 `full3d_one_cell_exact_schur` | `migrate_to_dat`；受审有限 method enum 与 accepted Hybrid templates，ordinary default 仍 scalar，任意字符串禁止 |
| propagation | `full3d_uniform_cg` | `migrate_to_dat`；受审有限 method enum 与 accepted Hybrid templates，任意 model 字符串 `research_only_not_public` |
| operator | `exact_monolithic_hybrid_operator` | internal identity/provenance |
| solver/PC | block-LDU action full solve；fixed whole-endcap ILU0 + dynamic DtN Woodbury | accepted Hybrid iterative combo 的 solver profile `migrate_to_dat`；任意 PC identity/options 仍 internal |
| side correction | 1 或 2；2 的 identity 与 max_it 4500，1 为 max_it 1600 | `migrate_to_dat`；受审 finite enum/accepted templates，无 fallback/retry，任意步数扫描仍 research |
| common numerical | restart90、rtol5e-9、shift .1、overlap0、ILU0、zero initial、assembly-time static condensed | accepted template explicit values；不是全局默认 |
| public solver controls | `linear_solver`、`preconditioner`、`restart`、`max_iterations`、`relative_tolerance`、`absolute_tolerance`、`initial_guess`、已审 ILU/shift/subdomain/overlap/side-correction | `migrate_to_dat`；当前 Task37b/c 数值是 accepted template 值，不是全局默认；按 method-specific constraints 校验 |
| public execution controls | `mpi_size`、`warning_memory_gib`、`terminate_memory_gib`、`timeout_seconds`、`require_zero_swap` | `migrate_to_dat`；generic user policy 与历史 authority hard Gate 分开，默认/范围由 method 与 execution policy 校验 |
| internal execution/provenance | `poll_interval`、authority path/hash、benchmark 固定 resource qualification thresholds、container identity、raw PETSc options、未审 PC/内部函数、QEP 内部容差 | `keep_as_internal_factory` 或 `research_only_not_public`；不得从历史 authority 值自动变成 public 默认 |
| CLI gate | `--task037c-robustness-gate`、`--internal-traction-model`、`--task037c-two-pass-side-correction`、phi/M/MPI flags | compatibility/provenance gate；不直接成为 public `.dat` 键，`research_only_not_public` |

`make_task37c_profile` 对 phi、M、MPI、traction model、correction steps 做有限集合校验；它不是通用注册表。watchdog 原样把研究 flags传给 worker，并同时写 profile/authority/resource provenance。

### 4.3 Task37c records/checker/audit

| 组件 | 输入/输出参数 | 边界与处置 |
|---|---|---|
| `task037c_robustness.py` | profile schema、mode identity、M selection、MPI resource classification | 纯 Python contract，不读 artifact；`keep_as_internal_factory` |
| `task037c_comparator.py` | 两侧 method/MPI/phi/source SHA、record paths；读取 orders/fields/canonical/q/RTA | checker only；不能成为求解参数，`research_only_not_public` |
| `run_task037c_exact_traction_column_audit.py` | 固定 p6/h10、S、phi=-5、M160/candidate320、MPI8 opt-in | one-cell research audit；`keep_for_historical_replay`/`research_only_not_public` |
| `run_task037b_hybrid_iterative.py` | `--frozen-m10` 或 `--task037c-robustness-gate` profile | 共享 worker；ordinary defaults必须保持，Task37c flags不公开 |
| watchdog | case label/run root/output/verified SHA、profile/authority paths、resource limits | provenance/watchdog；T1 若需 launcher应重用概念，不把 raw path当物理参数 |

### 4.4 Full3D direct 与 Hybrid direct static audit

T0 另外读取了当前 master 的 `benchmarks/run_task032_phase6_augmented.py`、`benchmarks/run_task033_memory_watchdog.py` 和 `benchmarks/run_task033_full3d_watchdog.py`。下面区分“真正编排求解的入口”和只读 checker/历史 artifact：后者不能被当成 solver 参数来源。

| 入口 | 当前实际调用链与默认 | 可迁移的 public candidate | 必须保持 internal/research 的部分 |
|---|---|---|---|
| Full3D direct | `run_task033_full3d_watchdog` → `run_stage4b_block_grating_3d_case`；`target_stage4_config(degree,h_nm)`；legacy 默认 `profile=default`、`run_kind=assembly-only`、`backend=standard_full`、`mpi_size=4` | `[solver].direct_solver_profile`、`[execution]` controls 和受控 output export/reference 键 `migrate_to_dat`；物理值另入 official `.dat` | worker/run-root、authority path/SHA、container/resource qualification threshold、polling、raw PETSc options、checker/reference comparison metadata |
| Hybrid direct | `run_task032_phase6_augmented` 解析 geometry/mesh/method/solver 参数，调用 `target_stage4_config` 与 `build_hybrid_*_direct_system`；普通默认 `continuous_beta` + `continuous_qep_beta`、`standard_full` | direct solver profile、solver/execution controls、output export/reference 键及 method-specific accepted propagation/traction enum `migrate_to_dat`；不把任意 solver path 字符串公开 | raw `--full3d-reference*` mapping、Task035c gate、verified SHA、`petsc_*`、diagnostic assembly、checker comparison path 与 raw resource qualification flags |
| Hybrid iterative | `run_task037b_hybrid_iterative_watchdog` → `run_task037b_hybrid_iterative`；Task37b ordinary/Frozen M10 与 Task37c robustness 分支分开 | accepted Hybrid 组合的 `full3d_uniform_cg`、两种 traction enum、dynamic DtN、exact one-cell traction、two-pass correction `migrate_to_dat`；每个 `.dat` 仍只表示一个 run | 完整 Task37c frozen profile、未审内部函数/PC、authority identity、自动扫描/campaign、watchdog gate 与 raw provenance |
| checker / evidence | `task037c_comparator.py` 只读取 records/orders/fields/canonical/q/RTA 并重算比较状态 | 不提供 solver 输入；最多在 provenance 中引用结果 | checker、raw artifact path/SHA、历史 authority 均不能充当求解器配置 |

因此 `target_stage4_config` 仍是 internal factory；但它承载的独立物理值必须迁入 official Full3D `.dat`。factory 的可见性与物理参数的迁移是两个不同处置，不应因 factory internal 而丢失这些值。

## 5. Preset、factory、smoke 与 official anchor 处置

当前 `PRESET_INFO` 实际登记 17 个 preset。每个 preset 独立列出，避免把 smoke、demo、ordinary direct 和 official-like target 混成一类。

| preset | 当前来源/状态 | 迁移处置 |
|---|---|---|
| `2d_tm_pml_floquet_smoke` | 2D smoke，PML + Floquet | `migrate_to_dat`，保留 smoke 标记 |
| `2d_tm_dtn_auxiliary_smoke` | 2D DTN auxiliary smoke | `migrate_to_dat`，method/boundary 组合需白名单 |
| `2d_tm_dtn_explicit_smoke` | 2D explicit DTN smoke | `migrate_to_dat`，与 auxiliary 分开保留 |
| `2d_te_port_smoke` | 2D TE port smoke | `migrate_to_dat`，偏振/port 组合需校验 |
| `2d_complex_absorption` | 2D complex-material public case；不是 official anchor | `migrate_to_dat`，保留当前 evidence/status 边界，不宣称 production-qualified |
| `2d_euv_grating_direct` | 2D EUV ordinary direct active preset | `migrate_to_dat`，作为普通 2D direct template |
| `3d_stage1_airbox_smoke` | 3D stage1 airbox；当前 `ACTIVE_3D_INPUT_GROUP` | `migrate_to_dat`，显式标为 smoke |
| `3d_stage2a_floquet_smoke` | 3D stage2a Floquet smoke | `migrate_to_dat`，保留 stage identity |
| `3d_stage2b_pml_smoke` | 3D stage2b PML，实验性且非 accuracy-qualified smoke | `migrate_to_dat`，保留 experimental/non-accuracy-qualified 边界 |
| `3d_stage2c_fresnel_smoke` | 3D stage2c Fresnel，实验性且非 accuracy-qualified smoke | `migrate_to_dat`，保留 experimental/non-accuracy-qualified 边界 |
| `3d_stage4a_flat_layer_direct` | 3D Stage4 flat-layer sanity direct | `migrate_to_dat`，仅作 smoke/sanity，不称 official anchor |
| `3d_stage4b_demo_direct_h5` | Stage4b demo direct，h5 | `keep_for_historical_replay`，可在 T7 后另建 demo template |
| `3d_stage4b_demo_direct_h3` | Stage4b demo direct，h3 | `keep_for_historical_replay`，资源/精度需独立 evidence |
| `3d_stage4b_demo_mumps_ooc` | Stage4b MUMPS out-of-core profile demo | `research_only_not_public`，不作普通 solver default；与 public direct profile enum 分开 |
| `3d_stage4b_demo_mumps_blr` | Stage4b MUMPS BLR profile demo | `research_only_not_public`，不作普通 solver default；与 public direct profile enum 分开 |
| `3d_target_grating_direct_h5` | official-like target direct，h5 | `keep_for_historical_replay`，迁移须绑定独立 Full3D `.dat` 与 evidence |
| `3d_target_grating_direct_h3` | official-like target direct，h3，资源更重 | `keep_for_historical_replay`，不得由 preset 自动公开资源策略 |

| 其他对象 | 当前状态 | 迁移处置 |
|---|---|---|
| 2D factory | `EUVGratingInputs2D()` 与 `_TM_*` `replace` 对象 | `keep_as_internal_factory`；T7 等价性通过前不得删除 |
| 3D factory | `normal_incidence_airbox_config`、`oblique_incidence_airbox_config`、`target_stage4_config` | `keep_as_internal_factory`；factory internal，但独立物理值迁入 official `.dat` |
| stage factory | `run_3d_cases._stage_defaults`、`_case_configs` | `keep_as_internal_factory`；来源必须进入 resolved config |
| active preset | `ACTIVE_2D_INPUT_GROUP=2d_euv_grating_direct`；`ACTIVE_3D_INPUT_GROUP=3d_stage1_airbox_smoke` | T1 记录为 compatibility metadata；新入口不得依赖隐式 active preset |
| ordinary CLI default | `src.main` 无参数时由 `USE_PYCHARM_SETTINGS_WHEN_NO_ARGS=True` 选择 active 3D preset；runner 各自有 parser defaults | `legacy_alias_deprecate`；新 `.dat` 入口显式要求输入 |
| official benchmark anchor | Task37b/c authority path/hash、Task37c Full3D/direct/iterative records | `keep_for_historical_replay`；只进 manifest/provenance，不成为普通物理输入 |
| smoke/official boundary | smoke 只证明入口/装配可运行；official anchor 才绑定数值 evidence | `migrate_to_dat` 与 `keep_for_historical_replay` 必须分别保留，不能笼统迁移 |

## 6. 旧入口、兼容与删除候选

| 入口/状态 | 当前事实 | 处置 |
|---|---|---|
| `src/main.py` 无参数 | `USE_PYCHARM_SETTINGS_WHEN_NO_ARGS=True`，执行 active 3D preset | 旧 compatibility 保留到 T7 裁决；新 `scripts/run_case.py` 缺少 `.dat` 时必须显示简洁 usage 并退出，不得静默运行 |
| `--preset NAME` | 把 dataclass preset 展平为 CLI，再进入 runner | T1 提供映射表；暂 `legacy_alias_deprecate` |
| `src/runners/run_3d_airbox_old.py` | 仍有重复 stage defaults、case configs、argparse | `obsolete_delete_candidate`；仅候选，T7 等价性与 call graph 通过前不得删除 |
| 2D `--port-order-count` | help 明确是 legacy/search cap metadata | `keep_for_historical_replay` 或 `legacy_alias_deprecate`，不应进新 solver section |
| trailing PETSc flags | 3D `parse_known_args` 可接 `-ksp_view` 等；`petsc_extra_options` 也可接 | `keep_as_internal_factory`；不自动暴露为 public `.dat` |
| Task37c authority flags | verified-clean SHA、Full3D/reference/Task035c path/hash | provenance only；`research_only_not_public` |
| exact one-cell traction | `full3d_one_cell_exact_schur` 只在显式 Task37c gate；ordinary default 不可达 | `migrate_to_dat`；受审 Hybrid method enum 与 accepted templates，任意组合/authority 仍 `research_only_not_public` |
| two-pass correction | `--task037c-two-pass-side-correction` 仅 Task37c gate；ordinary/Frozen M10 禁止 | `migrate_to_dat`；受审 steps `1 or 2` 及 accepted templates，无 fallback/retry，任意扫描仍 `research_only_not_public` |
| dataclass 自动字段导出 | 当前没有 schema layer，但 factory 可接 arbitrary updates | `obsolete_delete_candidate` 仅指自动导出机制；T1 禁止自动暴露，T7 等价性与 call graph 通过前不得删除被调用实现 |
| `scripts/run_case.py` 缺少 `.dat` | 新 public 入口的缺失输入合同 | 必须打印 usage 并退出；不得继承 `src.main` 的无参 active-preset 行为 |

## 7. T1 白名单与多层重复的通俗解释

现在同一个“网格尺寸”可能先写在 `src/main.py` 的 preset dataclass，再被 `_pycharm_args_3d` 变成 `--mesh-target-size` 字符串，随后被 argparse 解析回 Python 值，再由 `_config_updates` 写入 `SimulationConfig3D`，最后由 `_stage_defaults` 和 factory 再覆盖或推导。这样做历史上方便 PyCharm、命令行和 stage smoke 各自工作，但也容易出现默认不一致、旧 flag 泄漏和 provenance 不清。

T1 只定义九个 section 中经过审查的键、类型、默认和文档 coverage；不实现 loader，也不在本阶段生成 resolved config：

1. `geometry/materials/incidence/discretization/boundary/method/solver/execution/output` 的公开白名单固定写在 schema/README；
2. T2 loader 再拒绝未知 section、未知 key、重复 key 和非有限值，并做 method-specific 约束；
3. T2 loader 再生成不可变 resolved spec，内部翻译为 `SimulationConfig3D`；
4. `k0`、Floquet phase、S/P vector、resolved mesh cells、active DoF、Woodbury/Schur size、PETSc raw options 和 lifecycle state只出现在 resolved/provenance，不成为用户输入；
5. Task37b/c exact traction、finite accepted propagation/traction/two-pass method enum `migrate_to_dat`，并受 method-specific constraints；authority SHA、watchdog path、temporary toggles、未审内部函数/PC 和自动扫描保持 research-only；
6. 2D preset、3D smoke、official anchor 分别逐项映射，不能用一个“preset migration complete”笼统结论替代。

## 8. T0 unresolved 清单

| unresolved_for_T1 | 为什么当前不能猜 | 下一步证据 |
|---|---|---|
| 2D `port_use_pml=None` 最终默认与 method 组合 | parser、2D config、solver 组合层共同决定 | T2 loader/resolved-config 单测 |
| `custom_polarization` 是否允许公共三复数 | 3D runner只暴露 `s/p/custom`，实际 vector 在 config 中校验 | 读取 Task38 schema决策并补 validation |
| `port-order-count` 外部使用者 | 当前只标 legacy/search cap metadata | `rg` 全部调用点与历史命令核对 |
| `src/runners/run_3d_airbox_old.py` 是否有外部入口 | 文件仍存在，但 T0 未把删除授权当作事实 | T7 call graph/equivalence |
| stage4 variable-p plan 路径的公共生命周期 | runner接收 string，backend qualification再解释 | T2 resolved spec 与 file binding |
| Task37c exact audit 是否要被 Task38 launcher复用 | 当前是固定 research runner | T6/T7 只读 runner依赖审计 |
| `PresetInfo` evidence status 的权威性 | 它是展示 metadata，不等于 numerical Gate | T1 README 明确 status vocabulary |

这些项目均标为 `unresolved_for_T1`，不在本 T0 里改名、删除或推断默认。

## 9. T0 结论

当前主线的公开入口是可工作的，但参数来源分散在 preset、CLI、stage defaults、factory、solver profile 和 provenance 记录中。T1 的最小安全方向是“显式白名单 + 文档化默认/适用性”，T2 再实现 loader、resolved config 和 provenance，而不是把 dataclass/PETSc/internal 状态全部序列化。所有删除候选均仅候选；T7 等价性与 call graph 通过前不得删除。本轮没有修改 Python、config、tests 或 input，也没有运行 PDE、MPI 或 pytest。

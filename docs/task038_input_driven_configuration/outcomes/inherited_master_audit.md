# Task38 T0：继承主线静态审计

## 1. 范围与证据身份

本文件是 Task38 的 T0 inherited audit（继承审计）：它记录当前主线已经有什么输入入口、参数和 Task37b/c 能力，供 T1 设计公开输入白名单使用。T0 不修改数值算法，也不把未经审查的任意研究组合提升为公共配置接口。

| 项目 | 当前实证 |
|---|---|
| 审计工作树 | `/tmp/myfenics-task38-input-driven-configuration-20260812` |
| 分支 | `codex/20260812-task38-input-driven-configuration` |
| HEAD / upstream | `b81ad33b97a6b33accd81eb460a31592f6b55b47` / 同 SHA 的 `origin/codex/20260812-task38-input-driven-configuration` |
| base ancestor | `c2a6fc1ea2d91a42e8433ea94db8c832e1036a54` |
| 审计起点 | `0/0`，工作树 clean；本文件和参数清单是本轮唯一待新增文件 |
| 方法 | 对源码做 `rg`、AST 定义/字段/argparse 静态提取和人工 call-graph 阅读；本轮不跑 pytest、MPI 或 PDE |
| 权威规则 | [AGENTS.md](../../../AGENTS.md)、[repository_work_principles.md](../../repository_work_principles.md)、[Task38 task.md](../task.md) |

Canonical 仓库的旧 Task37 工作树不属于本 T0 工作树范围。它的两处用户修改、index 和当前分支均未被本轮触碰；T0 也不在 master 上开发。

## 2. 当前公共入口与实际调用链

### 2.1 `src/main.py` 的入口分发

当前顶层入口同时承担“PyCharm preset 选择器”和“命令行转发器”。实际链路如下：

```text
src.main.main
  ├─ --list-presets [--verbose]
  ├─ --preset NAME
  │    └─ preset_cli_args
  │         ├─ _pycharm_args_2d -> src.runners.run_cases.main
  │         └─ _pycharm_args_3d -> src.runners.run_3d_cases.main
  ├─ 无参数且 USE_PYCHARM_SETTINGS_WHEN_NO_ARGS=True
  │    └─ ACTIVE_PYCHARM_PRESET = 3d_stage1_airbox_smoke
  ├─ 首参数为 2d/3d -> 对应 runner.main
  └─ 其他参数 -> 默认进入 run_cases.main
```

这意味着“无参数”不是空操作，而是会启动 `3d_stage1_airbox_smoke`。`preset_cli_args` 先把 dataclass preset 展平为 argparse 风格的字符串，再交给 runner 重新解析；这就是 T1 必须明确消除重复来源的第一处证据。

### 2.2 2D 入口

`src.runners.run_cases.main` 的静态链路是：

```text
argparse
  -> _normalize_method / _formulation_list / _port_model_list
  -> _base_updates
  -> _backends_for_case
  -> SimulationConfig (2D)
  -> run_case / run_te_case / run_port_case / run_te_port_case
  -> all_run_summary.json 和 backend_comparison.json
```

该 runner 的默认参数大多为 `None`，随后以 `SimulationConfig()` 的默认值补齐；因此同一个值可能存在于 `src/main.py` preset、argparse 默认、2D config 默认和 runner 的派生分支四层。`--port-order-count` 仍作为 legacy/search-cap metadata 进入配置；它不是自动 DtN 阶数选择本身。

### 2.3 3D 入口

`src.runners.run_3d_cases.main` 的静态链路是：

```text
argparse + parse_known_args
  -> _parse_petsc_option_tokens / _parse_petsc_extra_option
  -> _config_updates
  -> _stage_defaults(stage_case)
  -> normal_incidence_airbox_config 或 oblique_incidence_airbox_config
  -> _case_configs
  -> _run_stage_config
  -> stage1 / stage2a / stage2b / stage2c / stage4a / stage4b solver
  -> all_run_summary.json
```

`parse_known_args` 会把未知的 PETSc 风格 token 继续收集到 `petsc_unknown_options`；这是有意保留的运行时能力，但不应在 T1 自动变成公共 `.dat` 字段。`_stage_defaults` 先写 stage 级值，`_config_updates` 再写显式 CLI 值，最后 factory 接收任意 keyword updates。这种优先级由 T2 的 loader/resolved-config 明确化；T1 只定义字段、适用性、默认来源和文档覆盖范围。

### 2.4 Task37b/c 研究链路

```text
run_task037b_hybrid_iterative_watchdog
  -> parse_args / build_worker_command
  -> mpiexec benchmarks.run_task037b_hybrid_iterative
       -> profile_from_args
          ├─ FROZEN_M10
          └─ make_task37c_profile
       -> build_frozen_m10_setup
       -> build_hybrid_internal_mode_coupling
       -> solve_frozen_m10_linear
       -> recover_frozen_m10 / run_frozen_m10_physics
       -> online record / watchdog qualification
```

Task37c profile 只在 `--task037c-robustness-gate` 下可达；traction model、two-pass correction、phi、M、MPI 和 authority 绑定都在 runner/watchdog 中再约束一次。Task38 的 `[method]`、`[incidence]` 和对应独立输入可以 `migrate_to_dat`，并由 method-specific constraints 约束；Task37c 已资格化组合可作为 accepted template。不能公开任意内部函数、PC、authority 路径或自动扫描/campaign；完整 Task37c frozen profile 仍是 research/provenance 身份。

另有两个只读研究工具：

* `benchmarks/run_task037c_exact_traction_column_audit.py` 只做冻结 p6/h10 one-cell exact traction-column audit，不构造完整 Hybrid endcap solve。
* `benchmarks/task037c_comparator.py` 只读取 hash-bound Full3D/direct/iterative record，重算 comparator Gate，不启动 solver。

## 3. `src/main.py` 的 preset 事实

### 3.1 2D dataclass 与 preset

`Inputs2D` 有 35 个字段，`EUVGratingInputs2D` 继承它并覆盖 14 个几何/材料/网格默认。6 个公开 preset 如下；“smoke”在这里表示入口/路径验证，不自动表示数值资格化。

| preset | 实际来源/覆盖 | 当前用途与状态 |
|---|---|---|
| `2d_tm_pml_floquet_smoke` | `_TM_PML_2D`：scattered、manual、h=80、p=1 | PML/Floquet 路径 smoke，`experimental_path_smoke` |
| `2d_tm_dtn_auxiliary_smoke` | `_TM_DTN_AUX_2D`：EUV preset、h=3、auxiliary DtN | 推荐 auxiliary Fourier-DtN 路径，`test_backed` |
| `2d_tm_dtn_explicit_smoke` | 上项再设 `port_dtn_assembly=explicit` | explicit/reference cross-check |
| `2d_te_port_smoke` | EUV preset、TE、Robin、关闭 diffraction orders | TE scalar port smoke |
| `2d_complex_absorption` | EUV preset、复数 `n_substrate/n_grating` | canonical complex-material case |
| `2d_euv_grating_direct` | `EUV_GRATING_2D`：p=2、h=1.5、lambda=13.5 | 普通较细 2D direct；未作为扫描资格化 |

`ACTIVE_2D_INPUT_GROUP` 是 `2d_euv_grating_direct`。`_pycharm_args_2d` 会显式发出 method、constraint、polarization、background、port、几何、材料、PML、网格、入射角、metrics、near-field、output 等 flags，但不是所有 35 个字段都能从 CLI 回写；这必须在 T1 逐项决定。

### 3.2 3D dataclass 与 preset

当前静态 AST 计数为：`Stage1AirboxInputs3D` 21 字段、`Stage2NoGratingInputs3D` 23 字段、`Stage4GratingInputs3D` 60 字段。11 个 preset 与其实际 stage/factory 来源如下。

| preset | 实际配置来源 | 当前证据/边界 |
|---|---|---|
| `3d_stage1_airbox_smoke` | `STAGE1_AIRBOX_3D` | 10×10×10 nm、p=1、h=5，默认轻量 smoke |
| `3d_stage2a_floquet_smoke` | `STAGE2_NO_GRATING_3D` + `stage_case=floquet_airbox` | 双周期 Floquet smoke |
| `3d_stage2b_pml_smoke` | 上项 + `stage_case=pml_airbox,use_pml=True` | PML 路径；非精度资格化 |
| `3d_stage2c_fresnel_smoke` | 上项 + `stage_case=fresnel_interface` | Fresnel/PML 路径；非精度资格化 |
| `3d_stage4a_flat_layer_direct` | `_STAGE4_FLAT_3D` | 无 grating 的平层能量/DtN sanity |
| `3d_stage4b_demo_direct_h5` | `STAGE4_GRATING_3D` | demo block、p=2、h=5，非 canonical target |
| `3d_stage4b_demo_direct_h3` | 上项 + h=3 | demo 较细网格，资源较重 |
| `3d_stage4b_demo_mumps_ooc` | demo h=5 + `petsc_direct_solver_profile=mumps_ooc` | direct OOC 实验入口 |
| `3d_stage4b_demo_mumps_blr` | demo h=5 + `petsc_direct_solver_profile=mumps_blr` | compressed direct 实验入口 |
| `3d_target_grating_direct_h5` | `from_simulation_config(target_stage4_config(2,5))` | Benchmark 021 target h=5 |
| `3d_target_grating_direct_h3` | `from_simulation_config(target_stage4_config(2,3))` | Benchmark 021 target h=3，资源重 |

当前 `ACTIVE_3D_INPUT_GROUP` 是 `3d_stage1_airbox_smoke`。`PRESET_INFO` 对上述 17 个 2D/3D 名称均有记录；信息字段是 `physical_geometry`、`discretization`、`resource_class`、`evidence_status`、`purpose`，它是展示元数据而非求解配置。

### 3.3 preset 层的继承风险

* `Stage4GratingInputs3D.from_simulation_config` 从共享 `SimulationConfig3D` 复制字段，却强制 `case="oblique"`，把 `petsc_extra_options` 转成 tuple，并强制 direct preset 的 `matrix_diagnostics_assemble_only=False`。
* `target_stage4_config` 的目标物理设置与普通 `Stage4GratingInputs3D` 默认不同；若 T1 只暴露一个 “stage4” 名称，会丢失这些语义。
* `PRESETS_2D/3D`、`ACTIVE_*`、`USE_PYCHARM_SETTINGS_WHEN_NO_ARGS` 是应用行为，不应直接照搬成 `.dat` 自由字段。

## 4. `SimulationConfig3D` 继承参数与派生量

### 4.1 独立字段分组

`SimulationConfig3D` 当前有 87 个独立 dataclass 字段。下表按同源参数组列出全部字段；nm、角度和 tolerance 的单位沿用源码。`default` 指当前类默认或该组明确默认来源，factory override 另列在 4.3。

| 组 | 独立字段 | 当前默认/来源 | 分类与 T1 处置 |
|---|---|---|---|
| identity/几何 | `case_name`, `stage_case`, `geometry_kind`, `lambda0`, `n_air`, `mu_r` | `airbox3d_normal`, `stage1_airbox`, `airbox`, 633 nm、`1+0j`、`1+0j` | independent input；公共白名单候选 `migrate_to_dat` |
| 周期与 z 几何 | `period_x`, `period_y`, `z_min`, `z_max`, `air_height`, `substrate_thickness`, `grating_height`, `grating_width_x`, `grating_width_y`, `interface_z` | 600/500/-550/350/350/0/0/0/0/0 | independent input；`migrate_to_dat`，但 z 一致性由 loader 校验 |
| 材料 | `n_substrate`, `n_grating`, `substrate_material_label`, `grating_material_label`, `validation_role` | index 为 `None` 时回落 air；标签 None；`numerical_sanity_only` | 材料与证据角色分开；index `migrate_to_dat`，label 可选；role 先 `keep_as_internal_factory` |
| 背景与纵向边界 | `scattering_background`, `stage4_boundary_model`, `stage4_dtn_order_policy`, `stage4_dtn_assembly`, `stage4_pml_outer_bc` | layered、dtn_port、auto_propagating、auxiliary、natural | public boundary whitelist；T1 显式 enum |
| 周期/PML | `use_floquet_xy`, `use_pml`, `pml_top_thickness`, `pml_bottom_thickness`, `pml_alpha` | False、False、0、0、5 | independent input；与 stage schema 互斥/联动，`migrate_to_dat` + validate |
| 入射 | 当前 source/CLI 的 `incident_theta_deg`, `incident_phi_deg`, `polarization_kind`, `custom_polarization`, `incident_amplitude`, `incident_e0_v_per_m` | 0/0/custom/`(1+0j,0,0)`/1/1；`incident_theta_deg` 是 legacy/internal mapping | Stage4 T1 public key 优先为 `grazing_angle_deg` + `azimuth_deg`，内部 `incident_theta_deg=90-grazing_angle_deg` 派生；2D/Stage1 若采用另一角度约定须使用不歧义字段并标适用性，custom 规则 `unresolved_for_T1` |
| FE 阶数 | `nedelec_degree`, `nedelec_trace_degree`, `nedelec_interior_degree`, `visualization_degree` | 2、None、None、2 | p/trace pair contract；public `migrate_to_dat`，pair validation 保留 internal |
| 网格 | `mesh_target_size`, `mesh_cell_type`, `mesh_spacing_mode`, `mesh_axis_cell_counts`, `mesh_axis_z_values`, `mesh_axis_z_profile`, `mesh_refined_size`, `mesh_refinement_radius` | 140、auto、auto、None、None、None、None、None | h/mesh mode 可公开；axis/profile 是 qualified/internal provenance，先 `keep_as_internal_factory` |
| Floquet/稳定项 | `floquet_constraint_mode`, `divergence_penalty` | auto、0 | mode 是枚举输入；divergence penalty 仅实验诊断，`research_only_not_public` |
| diffraction orders | `diffraction_zero_order_only`, `diffraction_order_max_m`, `diffraction_order_max_n`, `diffraction_sample_count_x`, `diffraction_sample_count_y`, `diffraction_top_probe_z`, `diffraction_bottom_probe_z`, `diffraction_probe_fraction`, `diffraction_compute_modal_diagnostic`, `diffraction_rayleigh_tol` | zero-order True；max None；samples 24；probes None；fraction .75；modal False；tol 1e-6 | `export_fields`、orders、canonical、modal、reference_planes 及 reference plane/sample keys 是 output 白名单；modal diagnostic 内部实现/容差仍 internal |
| alias/audit internal | `dtn_y_invariant_n0_alias_preflight`, `dtn_trace_alias_overlap_tolerance`, `dtn_auxiliary_direct_projection_audit`, `dtn_auxiliary_direct_projection_tolerance` | False、1e-8、False、1e-10 | internal/qualified evidence，`research_only_not_public` |
| Full3D reference | `full3d_reference_export`, `full3d_reference_plane_z`, `full3d_reference_sample_count_x`, `full3d_reference_sample_count_y` | 当前 source 的 legacy export/plane/sample mapping | 受控 output 键 `migrate_to_dat`；只有 authority/checker path/hash internal |
| direct runtime | `petsc_direct_solver_profile`, `petsc_ksp_view`, `petsc_log_view`, `petsc_extra_options` | default、False、False、空 dict | 受审 direct profile `migrate_to_dat` 为有限 enum；raw PETSc options、view/log 仍 internal |
| release/backend | `direct_release_base_after_augmentation`, `stage4_full3d_assembly_backend`, `stage4_variable_p_cell_degree_plan`, `stage4_local_h_refinement_plan`, `stage4_cell_static_condensation`, `stage4_assembly_time_cell_static_condensation`, `direct_release_solver_before_postprocess` | False、standard_full、None、None、False、False、False | backend 只有已批准 enum 可由公共 schema 选择；释放/计划字段 `keep_as_internal_factory` |
| partition/constraint/matrix diagnostics | `stage4_preserve_structured_input_partition`, `stage4_floquet_slave_elimination`, `matrix_diagnostics_assemble_unconstrained`, `matrix_diagnostics_assemble_only`, `matrix_diagnostics_factorization_only` | 全 False | memory/qualified/internal flags；`research_only_not_public` |
| 输出/标签 | `unique_output`, `tags` | True、`Tags3D()` | unique 可公开；tags 是 mesh identity，`keep_as_internal_factory` |
| launcher execution/provenance | `execution.mpi_size`（当前不在 `SimulationConfig3D` 字段中）、watchdog authority path/hash | Task38 要求 MPI size 是独立 public execution input；authority 路径/hash 是内部绑定 | MPI size `migrate_to_dat`，范围与 method-specific constraints 留给 schema/T2 validation；authority 为 `research_only_not_public` |

### 4.2 派生属性不是独立输入

`SimulationConfig3D` 的派生属性按语义分为：

| 派生组 | 属性 | 生成内容 | T1 处置 |
|---|---|---|---|
| 单位/尺度 | `eps_r`, `k0`, `omega`, `electric_field_scale_V_per_m`, `magnetic_field_scale_A_per_m` | 由材料、波长、幅度生成 | 不接收外部同名输入；`keep_as_internal_factory` |
| 几何边界 | `x_min/x_max`, `y_min/y_max`, `physical_z_min/max`, `domain_z_min/max`, `box_lengths`, `mesh_cells` | 周期、z、PML、axis counts 推导 | resolved config 输出，非输入 |
| 网格解析 | `mesh_cell_type_resolved`, `mesh_spacing_mode_requested`, `mesh_axis_cell_counts_requested`, `mesh_axis_z_values_requested`, `mesh_refined_size_resolved`, `mesh_refinement_radius_resolved` | 校验 auto/strict/refined 和有限递增轴 | loader 输出与校验；不能让用户同时写 resolved 值 |
| FE/Floquet contract | `floquet_constraint_mode_requested`, `nedelec_fixed_trace_enabled`, `nedelec_trace_degree_resolved`, `nedelec_interior_degree_resolved`, `nedelec_fixed_trace_contract`, `petsc_direct_solver_profile_requested` | 将 shorthand 解析为实际 contract | internal validation/provenance |
| 入射向量 | `theta_rad`, `phi_rad`, `direction_vector`, `s_polarization_vector`, `p_polarization_vector`, `polarization_vector`, `wavevector`, `kx`, `ky`, `kz`, `floquet_phase_x`, `floquet_phase_y` | 角度、S/P、k 和周期相位 | resolved output；输入只保留受限角度/偏振 |
| 材料/块 | `substrate_index`, `grating_index`, `eps_air`, `eps_substrate`, `eps_grating`, `grating_x_min/max`, `grating_y_min/max`, `grating_z_min/max`, `has_grating_block`, `grating_background_eps` | None 回落、材料区域与背景 | resolved output；不允许重复输入 |

`as_jsonable()` 会同时导出独立字段和这些 derived quantity。T1 只定义“用户给的值”与文档覆盖；T2 必须区分用户值、loader 解析值和 derived 输出，否则 `.dat` 会重新形成第二个隐式 config schema。

### 4.3 factory 与 assembly backend

| 工厂/函数 | 当前行为 | 处置 |
|---|---|---|
| `normal_incidence_airbox_config(**updates)` | airbox、normal、theta/phi=0、custom Ex；接受任意 updates | 保留为 internal factory；T1 只调用白名单字段 |
| `oblique_incidence_airbox_config(**updates)` | airbox、theta≈21.131、phi≈33.690、S、custom None | 保留为 internal factory；不直接暴露 arbitrary updates |
| `target_stage4_config(degree,h_nm)` | 固定 13.5 nm target、50×25、air130/sub10、block 17×25×120、theta80、S、assembly-only diagnostics | factory 本身 `keep_as_internal_factory`；其独立物理值必须迁入 official Full3D `.dat`，不得把 factory 名称当公共输入 |
| `resolve_stage4_full3d_assembly_backend(cfg, apply=False)` | 统一 standard/full、assembly-time static condensed、variable-p condensed；兼容 legacy booleans | internal resolver；T1 用有限 backend enum |
| `qualify_stage4_full3d_assembly_backend(cfg)` | 检查 rectangular/hexa/Floquet/DtN/p5-p6/variable plan 等资格条件 | internal Gate，不公开为任意 solver flag |

## 5. Task37b/c 当前能力与边界

### 5.1 Frozen M10 与 Task37c profile

| profile | 当前冻结身份 | 允许入口 | 不能推断的结论 |
|---|---|---|---|
| Frozen M10 | p6/h10、lambda13.5、S、grazing10°、requested M120、interfaces、MPI8、已审 solver/execution/output 值；candidate/DtN/K/QEP/lifecycle 为派生项 | `--frozen-m10`，并要求旧 authority path/hash | 旧 flag 与 authority replay/internal；独立物理、requested M/interface、已审 solver/execution/output 值迁入 official M10 `.dat`；candidate/DtN/K/QEP/lifecycle 派生/internal |
| Task37c one-pass | p6/h10、grazing1°/theta89°、资格化 azimuth -5/0/+5、requested M120/160、MPI∈{1,8}、scalar 或 exact traction、max_it1600 | `--task037c-robustness-gate` + phi/M/MPI；traction model 仅两个枚举；candidate pool 由 adapter 派生 | accepted template；不改变 ordinary defaults |
| Task37c two-pass | 同上，side residual correction=2，preconditioner identity 显式变为 two-pass，max_it4500 | 在 Task37c gate 下另加 `--task037c-two-pass-side-correction` | accepted template，不是普通 PC family，也不是自动 fallback/retry |
| requested modes/interfaces | `requested_modes_per_direction` 与 bottom/top interface 是独立 public input | M、interface 受 schema/T2 method-specific constraints | `migrate_to_dat`；一个 `.dat` 只表示一个 run |
| candidate/derived mode data | candidate 240/320、动态 DtN 实际 mode count、40-mode K、Woodbury/Schur size | 由 requested M、method 和 adapter 派生 | internal/resolved output，不作为普通 input |

`Task37cProfile` 有 34 字段：profile/record schema、target、p/h/wavelength/polarization/incidence、interfaces、requested M/candidate pool、propagation/traction/operator/solver/PC identity、subdomain/overlap/ILU/shift/QEP tolerances、restart/max_it/rtol/initial/MPI/backend/two-pass steps。requested M、interfaces 与受审 method enum 可迁移；candidate pool、动态 mode count、Woodbury/Schur size 和其余 solver/QEP 派生量只作为 resolved/internal output，不能自动变成用户输入。

### 5.2 Full3D direct 与 Hybrid direct 入口审计

T0 另外阅读了 `benchmarks/run_task033_full3d_watchdog.py`、`benchmarks/run_task032_phase6_augmented.py` 和 `benchmarks/run_task033_memory_watchdog.py`。这三者不是 checker：它们分别负责 Full3D direct/watchdog、Hybrid direct 组装/求解及外层资源监控。旧 watchdog 的默认 `run_kind=assembly-only` 只是 legacy runner 事实；Task38 的 `method.kind=full3d_direct` 普通正式适配必须执行完整 direct solve，不能继承为 assembly-only 默认。

| 能力 | 当前实际入口与默认 | public/internal 边界 |
|---|---|---|
| Full3D direct | `run_task033_full3d_watchdog` 的 parent watchdog 调 `run_stage4b_block_grating_3d_case`；legacy profile=`default`、backend=`standard_full`，p/h、MPI、polarization由 CLI/qualification scope给出；`target_stage4_config`在 `_full3d_config` 中构造 | `profile` 的受审有限枚举 `migrate_to_dat` 为 `[solver].direct_solver_profile`；container、authority SHA、worker parent token、raw resource/path 是 internal |
| Hybrid direct core | `run_task032_phase6_augmented` 导入 `build_hybrid_augmented_direct_system`、`build_hybrid_modal_schur_direct_system`、`build_hybrid_modal_schur_memory_minimal_system`，再做 direct solve/field recovery；ordinary propagation=`continuous_beta`、traction=`continuous_qep_beta`、backend=`standard_full` | direct solver profile、solver path 和 method-specific accepted propagation/traction enum 可进入 controlled public schema；`--verified-clean-sha`、Full3D reference/path/hash、Task035c gate 是 provenance/internal |
| Hybrid direct watchdog | `run_task033_memory_watchdog` 的 `_worker_command` 以 `mpiexec` 调 `benchmarks.run_task032_phase6_augmented`；普通 hybrid parser 默认 `modal-schur-memory-minimal`、comparison=`fast`、M=8/candidate=16，p6/h10/M120/M160需显式 Task035c gate | Task38 T4/T5 需分别映射 Full3D/direct-Hybrid `.dat`；旧 benchmark flags 不应原样全部公开 |
| accepted research extension | 当前 Task37c iterative accepted path另由 `run_task037b_hybrid_iterative`承载 dynamic DtN、exact one-cell traction、two-pass；当前 T0 不把它与 Task032 ordinary direct 混称 | accepted finite method combination `migrate_to_dat`；独立 phi/M/interface 输入受 schema/T2 method constraints；完整 profile、未审内部函数/PC、authority 和自动扫描仍 research-only |

`run_task032_phase6_augmented.py` 还允许 `full3d_uniform_cg`、`scalar_cg_discrete_derivative` 等显式诊断选项，但普通默认仍是 continuous pair；不能把这些 benchmark 参数误写为 Full3D/direct 的普通默认。Full3D/direct 的历史 H1/Task035c authority 是 path/hash-bound evidence，不是用户输入。

### 5.3 Task37c 文件选择与排除

| 文件/能力 | 当前主线状态 | 边界 |
|---|---|---|
| `benchmarks/task037c_robustness.py` | 已选入 | 纯 profile、mode identity、M selection、resource classification；不导入 solver/PETSc/MPI/artifact |
| `benchmarks/task037c_comparator.py` | 已选入 | 只读 hash-bound record；不求解、不生成新 field |
| `benchmarks/run_task037c_exact_traction_column_audit.py` | 已选入 | research-only X2 one-cell exact column audit；冻结 case，不是通用 runner |
| `benchmarks/run_task037b_hybrid_iterative.py` / watchdog | 已选入 | 共同承载 Task37b frozen 和 Task37c gate；Task37c 选项显式隔离 |
| exact direct/heavy qualification machinery | 当前 T0 不把它列为公共输入能力 | 不自动暴露为 Task38 public runner；具体 heavy machinery 的合入边界需 T1/T7 另审 |
| `test_251_task037c_full3d_watchdog_contract.py` | 当前 master 未选入/文件不存在 | 不得在 T1 假定其可执行 |
| `test_252_task037c_hybrid_direct_contract.py` | 当前 master 未选入/文件不存在 | 不得在 T1 假定其可执行 |

### 5.4 ordinary/default 与 public/research-only 分界

普通入口仍是 `src/main.py` 的 2D/3D presets 和两个 stage runner；它们不应因为 Task37c profile 存在而获得任意内部函数、PC、authority 或 artifact path 参数。Task38 `[solver].direct_solver_profile`、`[execution].mpi_size`、独立 azimuth/M/interface 输入，以及 Hybrid `[method]` 的有限 propagation/traction/two-pass enum 均 `migrate_to_dat`，并受 method-specific constraints；它们不是自由函数字符串。完整 Task37c frozen profile、authority SHA/path、自动扫描/campaign 仍为 `research_only_not_public`。

## 6. T0 发现、风险与未决项

| 发现 | 证据 | 风险/下一步 |
|---|---|---|
| Python preset 与 argparse 都保存默认 | `src/main.py` dataclass/preset 与两个 runner parser 同时存在 | T1 必须定义单一 `.dat` source-of-truth 和明确 precedence |
| 3D runner 接受 PETSc trailing token | `parse_known_args` + `_parse_petsc_option_tokens` | 不可自动转成公共 section；保留 internal escape hatch |
| factory 接受 arbitrary `**updates` | `normal_incidence_airbox_config`、`oblique_incidence_airbox_config` | T2 loader 必须白名单，避免 dataclass 字段自动公开 |
| stage defaults 会覆盖多个物理/边界字段 | `_stage_defaults` + `_config_updates` | resolved config 要记录来源 `stage_default`/`user_override` |
| active no-args 会执行 smoke | `USE_PYCHARM_SETTINGS_WHEN_NO_ARGS=True` | 新 `scripts/run_case.py` 缺少 `.dat` 必须显示用法并退出；旧 `src.main` 行为作为 compatibility 保留到 T7 裁决，不可静默混同 |
| 旧 runner 仍在仓库 | `src/runners/run_3d_airbox_old.py` 仍含 duplicate parser/factory path | 仅候选 legacy alias/deprecate；T7 call graph 等价性通过前不得删除 |
| internal/provenance 字段与物理字段混在同一 dataclass | `SimulationConfig3D` 的 alias/audit/reference/PETSc/release 字段 | T1 schema 必须分 section 并把 internal 字段留在 resolved output |
| Task37c comparator 依赖 record/path/hash | `benchmarks/task037c_comparator.py` loader/bind functions | `.dat` 不能承诺旧 artifact 自动可复现；provenance 单列 |
| Task38 文档/README 尚未创建 | 当前 Task38 目录仅有 task.md | T0 只创建本审计和清单；后续阶段再添加允许文件 |

未能由当前静态证据确认的内容一律标为 `unresolved_for_T1`：例如 2D `port_use_pml=None` 的最终 stage 解释、`custom_polarization` 是否在公共输入中接受任意三复数、legacy `port-order-count` 的历史兼容时长，以及全部 old runner 入口是否仍被外部脚本调用。

## 7. T0 结论与边界

T0 已确认：当前代码有稳定的 runner/config/solver 链，但同一参数在 Python preset、argparse、stage defaults、dataclass 和 provenance record 之间重复表达。T1 的正确目标是建立严格白名单和来源追踪，不是把 87 个 dataclass 字段机械序列化，也不是改 solver 数学。删除候选只能写成“仅候选；T7 等价性与 call graph 通过前不得删除”。

本文件未运行 Python solver、pytest、MPI 或 PDE；T1 只定义 `.dat` schema 字段和文档，T2 才实现 loader/validator/resolved config，正式参数迁移和 preset 删除留到后续阶段，经主审批准后执行。

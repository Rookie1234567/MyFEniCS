# Task38 T7：Preset 迁移与正式轻量等价证据

本文件记录 T7 的静态迁移审计和两组真实 MPI1 轻量 PDE。旧入口与新 `.dat` 入口均绑定源码 `f86a7e42dc2c44d36c8e5ab6dfa1d9bb8ef8ed42`；所有 `/tmp` 与 `results/` 路径是本机 ignored carrier，不是可移植的 Git artifact。机器可读摘要见 [`t7_preset_migration_equivalence_v1.json`](records/t7_preset_migration_equivalence_v1.json)。

## 1. 静态迁移结论

11 个迁移项均完成真实旧 parser → runtime cfg 与新 `.dat` normalized cfg 的逐项比较；差异集合是精确集合，不是宽泛 drop。旧 `src/main.py` 没有原生 physical SHA，因此“hash 一致”采用 T7 已通过的传递证明：旧入口和 `.dat` 入口的独立物理/派生向量相同，再由 Task38 canonicalizer 计算新 hash；不把该 hash 冒充旧 runner 的原生字段。

| preset | 新 `.dat` | 静态状态 | canonical physical_model_sha256（传递 carrier） | 精确差异 | 差异解释 |
|---|---|---|---|---|---|
| `2d_tm_pml_floquet_smoke` | [`input/smoke/2d_tm_pml_floquet_smoke.dat`](../../../input/smoke/2d_tm_pml_floquet_smoke.dat) | pass | `04da435fd87d33f93ae1605ad17f85cab536f049bf1acb29b7612e98b1fa1fef` | `case_name`; `port_boundary_model`; `port_dtn_order_count` | case identity；scattered 求解不使用 port 字段 |
| `2d_tm_dtn_auxiliary_smoke` | [`input/smoke/2d_tm_dtn_auxiliary_smoke.dat`](../../../input/smoke/2d_tm_dtn_auxiliary_smoke.dat) | pass | `6c332d46ccacd9a11ab5a6e28bc11b69f4a26129b71191e6050728261af1404f` | `case_name`; `pml_bottom_thickness`; `pml_top_thickness`; `port_dtn_order_count` | case identity；DtN case 不使用 PML；旧 order-count 是 legacy metadata |
| `2d_tm_dtn_explicit_smoke` | [`input/smoke/2d_tm_dtn_explicit_smoke.dat`](../../../input/smoke/2d_tm_dtn_explicit_smoke.dat) | pass | `7e070e0699fb78fbe2a5d235ecf8d3f0d889b6d2fe5aa9b6a7b42832ca0c6cca` | `case_name`; `pml_bottom_thickness`; `pml_top_thickness`; `port_dtn_order_count` | 同上；explicit + auto_propagating 语义保持 |
| `2d_te_port_smoke` | [`input/smoke/2d_te_port_smoke.dat`](../../../input/smoke/2d_te_port_smoke.dat) | pass | `35704e6d285d9a1e07f558baea99d8b62cc2564c0608abc38234bbdf058c876f` | `case_name`; `pml_bottom_thickness`; `pml_top_thickness`; `port_dtn_order_count` | case identity；Robin port 不使用 PML；旧 order-count 不公开 |
| `2d_complex_absorption` | [`input/smoke/2d_complex_absorption.dat`](../../../input/smoke/2d_complex_absorption.dat) | pass | `3e41e6dbcadcdc4e7d964b9e4146c274472a37e3285b68ee94a3fda66a3e2372` | `case_name`; `pml_bottom_thickness`; `pml_top_thickness`; `port_dtn_order_count` | complex material 保持；其余是 inactive legacy metadata |
| `2d_euv_grating_direct` | [`input/examples/2d_euv_grating_direct.dat`](../../../input/examples/2d_euv_grating_direct.dat) | pass | `53e40349bede6b43115d0e028a36da7bea373047dfb94ebdceb948e4dc127aa9` | `case_name`; `pml_bottom_thickness`; `pml_top_thickness`; `port_dtn_order_count` | direct EUV 物理向量保持；旧 PML/order metadata 不参与该路径 |
| `3d_stage1_airbox_smoke` | [`input/smoke/3d_stage1_airbox_smoke.dat`](../../../input/smoke/3d_stage1_airbox_smoke.dat) | pass | `af2a60b47ba5918c6d6a747ac035fdf238eb158743f4a9255cce5abe7ddf5fbe` | `case_name`; `stage4_boundary_model` | case identity；Stage1 使用 strong boundary，旧 Stage4 metadata inactive |
| `3d_stage2a_floquet_smoke` | [`input/smoke/3d_stage2a_floquet_smoke.dat`](../../../input/smoke/3d_stage2a_floquet_smoke.dat) | pass | `4b92d10a2353e231811a8d427c6bda71754815a6a601ee0189a4823e13d14742` | `case_name`; `eps_substrate`; `n_substrate`; `pml_bottom_thickness`; `pml_top_thickness`; `stage4_boundary_model`; `substrate_thickness` | no-grating Floquet path 不参与这些旧 substrate/PML/Stage4 metadata；域与 active Floquet identity相同 |
| `3d_stage2b_pml_smoke` | [`input/smoke/3d_stage2b_pml_smoke.dat`](../../../input/smoke/3d_stage2b_pml_smoke.dat) | pass | `296e91cf770fc11ef9f0ac654d98de3c5a539339e7acae03fabc7ab4d2b4d192` | `case_name`; `eps_substrate`; `n_substrate`; `stage4_boundary_model`; `substrate_thickness` | PML airbox 的 active mesh/boundary/z域相同；旧 substrate 字段为 inactive metadata |
| `3d_stage2c_fresnel_smoke` | [`input/smoke/3d_stage2c_fresnel_smoke.dat`](../../../input/smoke/3d_stage2c_fresnel_smoke.dat) | pass | `10aa4a61131e8ecaa1a0fd450dd49196ab460f72e80d9a9bfc1fd3ac75d1fde1` | `case_name`; `stage4_boundary_model`; `substrate_thickness` | Fresnel active stage/polarization/PML/Floquet相同；旧 Stage4 boundary 与 substrate metadata不参与该 solver branch |
| `3d_stage4a_flat_layer_direct` | [`input/smoke/3d_stage4a_flat_layer_direct.dat`](../../../input/smoke/3d_stage4a_flat_layer_direct.dat) | pass | `659f24717901e44e83b46562ca4ea9d777c69e607f148b063c7280e6213270e5` | `case_name`; `diffraction_order_max_m/n`; `eps_grating`; `grating_index`; `grating_material_label`; `n_grating`; `reporting_diffraction_order_max_m/n` | flat layer 没有 grating block；reporting bounds 与 legacy internal 字段分离，不改变 DtN |

## 2. 四次正式 PDE 对照

旧入口的 solver summary 与新入口的 `numerical_output/run_summary.json` 是同一数值 authority；新入口 parent `run_summary.json` 只记录 worker/provenance/resource 状态。

| 对照 | exit / authority | residual | mesh / DoF / rows / NNZ | 主要共同结果 | 最大差值 | wall / RSS / swap |
|---|---|---:|---|---|---:|---|
| A1 legacy 2D | `0`; finite summary | `4.595181492041868e-15` | 400 / 633 / 608 / n/a | R=`0.02561938273503437`; T=`0.8857932785737199`; R+T=`0.9114126613087543`; A_balance=`0.08858733869124569`; A_volume=`0`; 5 orders | 0 | 2.334997 s wrapper；process RSS not measured |
| A2 `.dat` 2D | `0`; `worker_exit0` | `4.595181492041868e-15` | 400 / 633 / 608 / n/a | 与 A1 所有 power/order 数值精确相同 | abs `0` | 2.932676 s；process-tree peak `263.546875 MiB`; swap `0`; 12 samples |
| B1 legacy Stage1 | `0`; `completed`, `official_result=true` | `1.0869658196017029e-16` | 48 / 98 / 98 / 1106 | solution norm=`35.35501465073796`; Stage1 R/T/A=`not_applicable` | 唯一差异为 `mean_poynting_W_per_m2[1]` 舍入 | 4.461000 s；legacy solver-reported historical peak `214.02734375 MiB`; process RSS not measured |
| B2 `.dat` Stage1 | `0`; `worker_exit0`, numerical `completed`, `official_result=true` | `1.0869658196017029e-16` | 48 / 98 / 98 / 1106 | 与 B1 stage/status/mesh/matrix/solution observable相同 | `8.271806125530277e-25` abs；`1.2576642775177548e-16` rel | 2.184068 s；process-tree peak `221.078125 MiB`; swap `0`; 9 samples |

B1–B2 的唯一共享数值差是 `mean_poynting_W_per_m2[1]` 的浮点舍入；其余递归共享字段精确相同。A 只比较存在的 reduced residual、power metrics、5 个 order records 及全部共同数值字段。wall 是顺序运行的本次观测，JIT/cache 冷热不同，不构成 legacy-vs-dat 性能资格；RSS 采样口径也不同，不能据此计算节省比例。legacy 的 214.027 MiB 是 solver-reported 单 rank historical peak；`.dat` 的 221.078 MiB 是 launcher simultaneous process-tree peak。

正式 raw summary 路径与 SHA 已收录在 compact JSON。A1/A2/B1/B2 的 stdout/stderr/status 也保留在对应 carrier 目录。前一次 pre-fix A1 使用 `2570bcd81fffd25286eb7a00468ee2bc6335d6e9`；第一次 A2 在数值启动前因外部 cwd 导致 MPI worker `ModuleNotFoundError: No module named 'src'`，不是 solver 失败。该负证据未删除；修复 `f86a7e42...` 后重新完成了同 SHA A1/A2。

## 3. Inactive exclusions

| exclusion | 适用路径 | 为什么可以排除 | 约束 |
|---|---|---|---|
| `case_name` | 全部 11 项及 A/B | 运行身份，不改变物理或 solver | 仅允许此身份差异 |
| 2D scattered 的 `port_boundary_model`、`port_dtn_order_count` | `2d_tm_pml_floquet_smoke` | PML scattered 分支不读取 port；legacy order-count 不是 public v1 键 | runtime summary 的物理/功率字段仍须一致 |
| 2D port 的 PML thickness 与 legacy order-count | 其余 2D port/direct 项 | port 分支不读取 inactive PML；旧 order-count 不进入当前 public mapping | explicit/auto 与 TE zero-order 约束仍保留 |
| Stage2 的 substrate/PML metadata | `3d_stage2a/b/c` | legacy factory 带有不参与对应 branch 的字段；active z域、材料参与、Floquet/PML/Fresnel stage 逐项比较 | 只排除表中列出的字段 |
| `stage4_boundary_model` legacy metadata | Stage1/Stage2 branches | 旧 stage defaults 的 Stage4 字段不是实际 branch boundary；新 dat 明确表达实际 boundary | 不扩大到 geometry、mesh 或 solver 字段 |
| flat-layer grating 与 reporting legacy字段 | `3d_stage4a_flat_layer_direct` | flat 没有 grating block；reporting bounds 与 DtN mode selection 分离 | 不将 output bound 注入 PDE |

## 4. 边界、失败诊断与未运行项

| 项目 | 结论 | 证据/限制 |
|---|---|---|
| pre-fix A1/A2 | 保留负证据，不计正式 Gate | A1 使用 `2570bcd81fffd25286eb7a00468ee2bc6335d6e9`；第一次 A2 在数值启动前因外部 cwd 报 `ModuleNotFoundError: No module named 'src'`。`f86a7e42...` 同时固定 worker cwd 为当前 Task38 源码根，并保留 venv Python 绝对路径、不把 symlink resolve 成 `/usr/bin/python3.12`；随后外部 cwd MPI1 `contract_probe_pass`，并完成 36 targeted tests |
| Stage1 数值身份 | 通过轻量 old/new 等价，但不是 Full3D accuracy benchmark | canonical/selected-field comparison `not_run_by_capability` |
| research/history 保留 | 6 项不删除 | `3d_stage4b_demo_direct_h5`、`3d_stage4b_demo_direct_h3`、`3d_stage4b_demo_mumps_ooc`、`3d_stage4b_demo_mumps_blr`、`3d_target_grating_direct_h5`、`3d_target_grating_direct_h3` |
| MPI1 iterative official | 未正式运行 | [`input/official/grazing1_phi0_hybrid_iterative_m120_mpi1.dat`](../../../input/official/grazing1_phi0_hybrid_iterative_m120_mpi1.dat) 只做 validate/dry-run |
| reporting / DtN | 两者独立 | 测试实值：outgoing modes 保持 `(0,0)`；reporting 枚举由 `5x5` 改为 `3x3` |
| TE DtN | fail-closed | 2D TE + DtN 当前只允许 `zero_order`；TM explicit/auxiliary 的 `auto_propagating` 未降级 |
| 后续范围 | 历史 T7 阶段边界 | 当时本轮未跑 MPI2/4、Full3D official、Hybrid direct/iterative 新 PDE；T8/T9 已在后续阶段完成 |

## 5. T8/T9 最终状态

T8 已把 11 个 migrated 名称收敛为 `MIGRATED_PRESET_DATS` 的薄 `src.main --preset` alias；alias 直接调用同一 dat 入口，不再复制 Python 物理值。无参数、直接 `2d/3d` facade 和未知参数不会静默 dispatch；6 个 retained research/history preset 仍保留原 factory、parser、资源提示和 replay 行为。

T9 已完成当前导航收敛和五个不可达旧 3D 模块删除。benchmark caller 已改为保持原 method/physics/MPI 身份的 dat 或内部 replay 命令；Case010 的 MPI2 独立 dat 只用于 identity/validate contract，不在本轮新增 PDE。`legacy_cleanup.md` 记录删除理由、调用图、保留依赖和最终提交。

因此本报告的 T7 迁移结论不是“尚未进入 T8”；当前结论是 11 项已迁移、6 项明确保留、T8/T9 已完成。T10 只补最终汇总、测试与发布边界，不改写本节的历史 PDE 数值。

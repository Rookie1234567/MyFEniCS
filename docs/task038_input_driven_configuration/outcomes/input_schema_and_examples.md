# Task38 schema 与示例索引

本文件是结项导航，不复制完整手册；完整 public key、单位、默认、适用性和错误提示以 [`input/README.md`](../../../input/README.md) 为准。

## 固定外形

| 层级 | 内容 |
|---|---|
| identity | `schema_version`、`model_id`、`run_id`、`comparison_group`、`dimension` 五项 public identity |
| section 数 | 恰好 9 个：`geometry`、`materials`、`incidence`、`discretization`、`boundary`、`method`、`solver`、`execution`、`output` |
| public key 数 | 100 个 section fields；schema 另含上述 5 个 identity |
| 解析对象 | `load_dat_input` → `load_and_resolve` → immutable `RunSpecification` |
| hash | raw bytes → `input_sha256`；物理五 section canonical JSON → `physical_model_sha256`；resolved JSON 有独立稳定 hash |
| provenance | source SHA、environment、manifest、原始 input 与 resolved config 在 launcher/T3；solver summary 在 `numerical_output/` |

## 核心约束

- 一个 `.dat` 只表示一次 run；命令行没有物理、solver、MPI 覆盖。
- 2D 使用明确的 `tilt_from_downward_y_deg`；3D Stage4 使用 `grazing_angle_deg`，airbox/Fresnel 使用 `tilt_from_downward_z_deg`，不同时输入两套角度。
- `method.kind` 覆盖 `2d_scattered`、`2d_port`、`full3d_direct`、`hybrid_direct`、`hybrid_iterative`；未接线方法和未审组合 fail closed。
- Hybrid public 只暴露 requested M、interfaces、受审 propagation/traction/two-pass 与 solver identity；candidate pool、实际 DtN mode count、Woodbury/Schur/K/QEP/lifecycle 是内部派生量。
- `output.diffraction_order_max_m/n` 是 postprocess reporting bound，不进入 outgoing DtN selection；实测 flat 测试中 outgoing mode 保持 `(0,0)`，reporting 枚举由 `5x5` 变为 `3x3`。
- TE + 2D DtN 当前只允许 `zero_order`；TM explicit/auxiliary 可使用 `auto_propagating`。
- `source_sha`、authority path/hash、raw PETSc flags 和未审 PC 不属于 public schema。

## 完整示例索引

| 用途 | 文件 | 身份与状态 |
|---|---|---|
| 2D ordinary | [`input/templates/ordinary_2d_example.dat`](../../../input/templates/ordinary_2d_example.dat) | schema/template 示例，不宣称数值资格 |
| Full3D direct | [`input/templates/full3d_direct_example.dat`](../../../input/templates/full3d_direct_example.dat) | Full3D direct public 形状 |
| Hybrid direct | [`input/templates/hybrid_direct_example.dat`](../../../input/templates/hybrid_direct_example.dat) | `standard_full`、M160/candidate320；实际支持边界与正式等价证据见 T5 record |
| Hybrid iterative | [`input/templates/hybrid_iterative_example.dat`](../../../input/templates/hybrid_iterative_example.dat) | accepted Task37c opt-in 形状；正式证据见 T6 record |
| Full3D direct official | [`input/official/grazing1_phi0_full3d_direct_mpi8.dat`](../../../input/official/grazing1_phi0_full3d_direct_mpi8.dat) | 1°/p6/h10/MPI8，未在 T7/T10 重跑 |
| Hybrid direct official | [`input/official/grazing10_phi0_p2h5_hybrid_direct_m160_mpi4.dat`](../../../input/official/grazing10_phi0_p2h5_hybrid_direct_m160_mpi4.dat) | T5 MPI4 formal record对应 |
| Hybrid iterative official | [`input/official/grazing1_phi0_hybrid_iterative_m120_mpi8.dat`](../../../input/official/grazing1_phi0_hybrid_iterative_m120_mpi8.dat) | T6 MPI8 formal record对应 |
| Hybrid iterative MPI1 identity | [`input/official/grazing1_phi0_hybrid_iterative_m120_mpi1.dat`](../../../input/official/grazing1_phi0_hybrid_iterative_m120_mpi1.dat) | validate/dry-run only，未正式运行 |
| ordinary migrated examples | [`input/smoke/`](../../../input/smoke/) 与 [`input/examples/2d_euv_grating_direct.dat`](../../../input/examples/2d_euv_grating_direct.dat) | 11 migrated preset 的逐文件入口 |

## 结果身份

建议目录为 `results/<model_id>/<run_id>__<method>__mpi<N>__M<M-or-na>/<timestamp>/`，其中至少保存 `input_original.dat`、`resolved_config.json`、`run_manifest.json`、`input_sha256.txt`、`physical_model_sha256.txt`、`source_sha.txt` 和 `run_summary.json`。未运行的 official dat 只可写 validate/dry-run 身份，不得写成数值通过。

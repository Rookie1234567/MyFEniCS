# V7 Lane A：exact-side 完整 h4 结果

Lane A 的目标是测量当前 factor-only exact-side 路径在 5 nm h4 上的实际低内存极限，
并在 setup 通过后完成 Review 允许的唯一一次 full formal。它不是 0.7 nm production
方案：两侧仍保留完整 sparse side factor，结果只能作为当前架构的参考下界与验证 oracle。

## 最终裁决

| 裁决项 | 结果 | 证据 |
| --- | --- | --- |
| setup-only advancement | `SETUP_ONLY_ADVANCEMENT_PASS_INHERITED` | prior run `f4073ada` peak `81.056903839 GiB <= 84.039305878 GiB` |
| half-memory compatibility | `NOT_HALF_MEMORY_COMPATIBLE` | 仍高于旧 `42.019652939 GiB` 线 |
| full formal | `5NM_EXACT_SIDE_LOWER_MEMORY_CASE_RESULT` | GMRES10、recovery、physics、matched h4 direct checker 全部通过 |
| full-formal memory qualification | `PASS_BELOW_MATCHED_DIRECT` | full-formal peak `80.025856018 GiB < 93.377006531 GiB` |
| V7 memory tier | `V7_TIER_5_TO_20_PERCENT` | 相对 `93.377006531 GiB` 节省 `14.298113646%` |
| 0.7 nm scalability | `NOT_0P7NM_SCALABLE_DUE_FULL_SIDE_FACTORS` | full side sparse factors 仍是正式容量 blocker |

完整结果不能被解读为“0.7 nm 已可行”。它证明的是：在冻结的 5 nm、h4、M480、MPI8
架构上，当前 exact-side 实现低于 matched direct；它仍需保存两侧大因子，因此不能外推
到更细网格或更大物理对象。

### setup-only advancement 的历史 authority

`84.039305878 GiB` advancement 是先前唯一 setup-only run 的 Gate，不是把本次
full-formal 全流程峰值重新套到 setup-only 分类上：

| source / run root | measured peak | Gate |
| --- | ---: | --- |
| `f4073adabb91bffe5c3954b8ae8b63270efa3e15` / `results/task039_v7_h4_exact_side_limit_setup_only_mpi8_f4073ada` | `81.056903839 GiB` | `<=84.039305878 GiB`，pass |

本次 full formal 的独立资源资格只比较 matched direct `93.377006531 GiB` 与实测
`80.025856018 GiB`；两种 authority 在 compact record 中分开记录。

## 身份与 raw 证据

| 项目 | 值 |
| --- | --- |
| branch / source SHA | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` / `9e31ecf189081afcb8ca27b0374ec89af0094e2d` |
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| packet manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| packet identity SHA256 | `b3bb870fe6fa17cb262b6161f7317cc1950944755c9270d4628dd5c79e950690` |
| exact-response spool | `results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output`；仅 holdout/oracle |
| matched direct authority | `results/task039_v4_h4_hybrid_direct_formal_mpi8_icntl14_1515f095` |
| formal run root | `results/task039_v7_h4_exact_side_full_formal_mpi8_9e31ecf1` |
| run status / exit | `finished` / `0`；elapsed `10126.231902 s` |
| compact record | [Lane A full-formal record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json) |

raw 不进入 Git。run summary、manifest、stdout、marker、stage、process-tree sample、object
ledger、diagnostic 和 authority 的大小与 SHA256 固定在 compact record 中。

## 内存 Gate

“峰值”指连续采样得到的完整 process-tree RSS 最大值，不是把不同阶段 RSS 相加，也不是
把对象字节数直接相加。

| 证据 | measured result | Gate |
| --- | ---: | --- |
| complete process-tree peak | `85,927,108,608 B = 80.025856018 GiB` | `<93.377006531 GiB`，full-formal pass |
| peak stage/sample | `top_woodbury_ready`；elapsed `7394.426120 s` | full-flow authority |
| outer KSP setup ready | `82,611,388,416 B = 76.937850952 GiB` | marker/sample measured，pass |
| peak swap | `0 B` | zero-swap pass |
| matched direct | `93.377006531 GiB` | absolute saving `13.351150513 GiB` |
| relative saving | `14.298113646%` | `V7_TIER_5_TO_20_PERCENT` |
| no-saving hard stop | `100262797312 B` | not reached |

V7 6 h default timeout 未触发；进程在 `10126.232 s` 内自然完成，因此没有使用条件 8 h
延长。外层已进入且 true residual 从初始 `1.0` 降至 `3.506501655e-10`，但这只是本次
timeout decision 的审计字段，不改变“未延长”的事实。

## setup、factor 与 modal Schur

| 阶段 | process-tree RSS | 说明 |
| --- | ---: | --- |
| bottom F ready | `23.195 GiB` | bottom 构造阶段 |
| bottom factor ready | `49.313 GiB` | bottom factor 存活 |
| bottom construction cleanup | `45.386 GiB` | construction-only carrier 清理后 |
| top F ready | `51.298 GiB` | top 开始 |
| top factor ready | `79.464 GiB` | 两侧 factor 生命周期重叠 |
| top Woodbury ready / 全程峰值 | `80.026 GiB` | 峰值样本 |
| modal Schur ready | `76.742 GiB` | 单次完整构造后 |
| outer KSP setup ready | `76.938 GiB` | formal outer-ready |

| side | factor NNZ | K rank / condition | W local bytes | apply / base solve / D apply |
| --- | ---: | ---: | ---: | ---: |
| bottom | `1,057,904,352` | `296 / 8.405950934` | `84,954,624` | `976 / 976 / 976` |
| top | `not_available in compact scalar` | `304 / 43.152227335` | `84,954,624` | `976 / 976 / 976` |

factor-only side actions 在 outer-ready 为 `1/1`，最终 cleanup 为 `0/0`；global direct
factor 为 `0`，nested iterative KSP 为 `0`。side K/LU、F/C/H carrier、D carrier、
actions、modal Schur/KSP 均按 release contract 清理。

| modal Schur evidence | measured result |
| --- | ---: |
| shape / rank | `960 x 960 / 960` |
| condition | `24.67720859303036` |
| matrix repeat / LU repeat solve | `0.0 / 0.0` |
| normal equations | `false` |
| full build apply count | bottom/top `960 / 960` |
| sampled reconstruction apply count | bottom/top `10 / 10` |
| sampled columns | `0, 1, 240, 267, 479, 480, 481, 720, 746, 959` |
| sampled contract SHA256 | `8d73d77a47fe0aa614e231eaac1f939eb28cca5b01c024c70fd518a3a592f082` |

## GMRES、true residual 与 physics checker

| 指标 | measured result | Gate |
| --- | ---: | --- |
| outer KSP / PC | `GMRES`, restart `10` / exact-side block-LDU | pass |
| reported relative residual | `3.506501655e-10` | `<=5e-9` |
| global true residual | `2.869197459e-10` | pass |
| bottom / top / modal true residual | `1.732041001e-11 / 2.660035326e-10 / 5.776295397e-11` | all pass |
| all finite/nonnegative | `true` | pass |
| recovery / physics | `true / true` | pass |
| integrated checker | `TASK039_V4_HYBRID_ITERATIVE_H4_EXACT_SIDE_INTEGRATED_PASS` | matched h4 direct authority |
| power-weighted error | `2.0767447166e-12` | pass |
| primary / weak channel rows | `11/11` and `15/15` | pass |
| diffraction orders / powers / amplitudes | `80/80`, `12/12`, `12/12` | pass |

R/T/A、`A_volume`、closure、selected E/H、external key/coordinate、bottom/top traction、
normal flux、all-channel和 canonical active/full checks均由既有 recovery/authority raw
通过。Full3D secondary authority 是 `not_available`，不能伪写成通过。

## 生命周期与 packet

| 时点/对象 | 结果 |
| --- | --- |
| outer-ready factor count | bottom/top `1/1` |
| release-before-recovery | `pass=true`；actions、components、collective cleanup 全通过 |
| final factor count | bottom/top `0/0` |
| packet consumer | `qep_calls=0`；mmap/reference released=true |
| exact-response spool | 96 transient hash-read artifacts；arrays retained=false；只作 holdout/oracle |
| solution snapshot | created → recovery → destroyed，marker 顺序完整 |

exact-response spool 没有计入 candidate 的生产内存优势；它只用于冻结的验证输入，不能被
当作 producer 或 candidate 的 resident storage。

## Layer graph

层图来自真实 `owned_cell_recovery_maps + trace_constraints.expansion_by_original +
local_mesh.geometry.z_values`，不是按全局行号分桶；共享 trace row 使用
`minimum_incident_owned_cell_layer`。两侧统计结构相同：6 层、132300 rows、105038640
owned-CSR NNZ、same-layer `75327840 (0.717144091)`、adjacent-layer `29710800
(0.282855909)`、long-range `0`、block half-bandwidth `1`。这些是本次 Lane A raw
authority 中观测到的辅助统计，不是独立的 Lane C evidence；标记为
`NOT_LANE_C_INDEPENDENT_EVIDENCE`，不能替代后续独立 Lane C graph-only audit。完整
6×6 `layer_pair_nnz`、每层 rows/NNZ 与释放标签保存在 raw authority 中，临时全局
row-layer tags 已释放。

## 边界与下一步

这个结果是 5 nm exact-side 的 lower-memory case result，不是 0.7 nm scalable result：
两侧完整 sparse factors 仍是主要内存增长源，h4 的正结果不能外推到 0.7 nm。

Lane B 必须改成 streamed owner-row producer/consumer：producer 不建 base/factor、不读
exact spool、不 hydrate 1920 个 mode Vec；consumer 才建立 matrix-free side、fixed whole-endcap
ILU(0)+DtN Woodbury 与 owner-row Petrov correction。rank 64/128/256/512 必须是同一嵌套
packet/consumer 过程，首个通过即停止；本阶段尚未运行 Lane B。

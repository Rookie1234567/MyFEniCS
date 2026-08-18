# V5-2：h4 exact-side setup-only 内存归因

本阶段只测“搭建求解器所需对象时，内存在哪个生命周期阶段达到峰值”。它没有执行外层
线性求解、场恢复或 R/T/A 后处理，因此不能被称为完整 Hybrid iterative 数值结果。
“stage-aligned”表示 marker 与同一进程树的 RSS 采样按时间绑定；对象容量是矩阵/数组的
独立统计，不能与进程树 RSS 相加。

## 1. 身份与结果

| 项目 | 实测/结论 |
|---|---|
| 源码 | `2ba0c44dfbd7c43547bf2769d013f6a92f4809f1`；branch clean；fixed-case explicit opt-in |
| 范围 | 5 nm、1° grazing、phi=0°、S、p6/h4、M480、MPI8 |
| packet | `results/task039_v4_h4_m480_shared_packet_eaad0f94`；manifest SHA `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| packet 身份 | rank=8、global rows=11605、32 个 owner-row mode-major complex128 shard；external keys=600，hash=`ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a` |
| packet consumer | `qep_calls=0`、`consumer_qep_required=false`、mmap/reference 已释放 |
| run | `results/task039_v5_h4_exact_side_setup_only_mpi8_2ba0c44_rerun1`；exit=0；`setup_only_completed` |
| 数值阶段 | solve/recovery/field/RTA/canonical 均 `not_run` |
| 最终分类 | `TASK039_V5_2_EXACT_SIDE_SETUP_MEMORY_ATTRIBUTION_BASELINE_POSITIVE_ADVANCEMENT_NOT_MET` |

compact record：[V5-2 attribution record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_h4_exact_side_memory_attribution_v1.json)。

## 2. 资源与阶段边界

| 指标 | measured result |
|---|---:|
| parent wall / worker marker wall | `13124.147925 s` / `13119.365665 s` |
| process-tree RSS peak | `91672846336 B = 85.376991272 GiB` |
| peak UTC / elapsed | `2026-08-18T14:30:57.645793+00:00` / `5371.123422 s` |
| peak 所在阶段 | `bottom_factor_ready` 之后、`bottom_woodbury_ready` 之前：bottom Woodbury construction interval，factor resident |
| PSS / USS | `not_measured` / `not_measured` |
| swap | `0 B`；warning/critical/hard 均未触发 |
| sampler | `51631` process-tree samples，poll=`0.25 s`；15 个 Review marker 均有 stage-aligned RSS |

峰值位于一个 construction interval，不能仅凭时间把峰值归因给某一个对象。与已知容量线比较：

| 比较 | 派生值 | 口径 |
|---|---:|---|
| 对 V4 Hybrid direct `93.377006531 GiB` | `-8.000015259 GiB`（低 `8.567436%`） | setup-only 对 full direct 的背景比较 |
| 对 V4 full iterative `104.334560394 GiB` | `-18.957569122 GiB`（低 `18.169980%`） | 非同阶段比较，仅作背景 |
| 对 advancement line `84.039305878 GiB` | `+1.337685394 GiB`（高 `1.591738%`） | advancement baseline 未满足 |
| 对 meaningful target `74.701605225 GiB` | 高 `10.675386047 GiB` | 更严格目标未满足 |

上述百分比只比较 process-tree RSS；没有把 W/K/LU、factor 或 matrix estimate 加到 RSS。

## 3. 15 个 marker 与释放顺序

15 个 marker 各出现一次、严格有序，并全部绑定到 launcher 的 process-tree stage sample：

| 顺序 | marker | aligned RSS GiB |
|---:|---|---:|
| 1 | `bottom_F_ready` | 77.0812 |
| 2 | `bottom_factor_setup_begin` | 77.0968 |
| 3 | `bottom_factor_ready` | 85.3308 |
| 4 | `bottom_woodbury_ready` | 79.8107 |
| 5 | `bottom_construction_cleanup` | 48.4827 |
| 6 | `top_F_ready` | 53.7873 |
| 7 | `top_factor_setup_begin` | 54.0678 |
| 8 | `top_factor_ready` | 83.7078 |
| 9 | `top_woodbury_ready` | 83.7152 |
| 10 | `top_construction_cleanup` | 79.6327 |
| 11 | `both_side_actions_ready` | 79.6327 |
| 12 | `modal_schur_build_begin` | 79.8031 |
| 13 | `modal_schur_ready` | 80.5443 |
| 14 | `outer_ksp_setup_ready` | 71.8689 |
| 15 | `all_setup_objects_cleanup` | 16.0022 |

最后一个 marker 的 raw detail 为 `setup_destroyed=true`、bottom/top factor count=`0/0`，
collective cleanup 完成。outer KSP 只有 setup：FGMRES restart=90，solve 未调用，Krylov
vectors 在 solve 前未分配。packet bundle 在 consumer 侧释放，QEP workspace 未持久化。

## 4. 对象容量（与 RSS 分栏）

| 对象 | bottom | top / modal | 证据口径 |
|---|---:|---:|---|
| F | 132300²，NNZ 105038640，estimate 2521985768 B | 同 shape/NNZ，estimate 2521985768 B | derived CSR estimate |
| C/D/H | C 1955275 / D 1955275 / H 296 NNZ | C 2019329 / D 2019329 / H 304 NNZ | derived CSR estimate |
| exact factor | NNZ 1071598968，estimate 25719433640 B | NNZ 1070582184，estimate 25695030824 B | MUMPS `INFOG(1)=0`；corrected NNZ 未单独持久化 |
| W | `[15828,296]`，74961408 B | `[17118,304]`，83261952 B | local/derived object bytes |
| K/LU/pivots | K 1401856 B；LU array 1401856 B；pivots `[296]` int32=1184 B；LU+pivots combined 1403040 B | K 1478656 B；LU array 1478656 B；pivots `[304]` int32=1216 B；LU+pivots combined 1479872 B | `n_aux` + current implementation 派生；condition 8.40595 / 43.15223 |
| P/T coupling blocks | projection `[480,132300]`，NNZ 3628800，estimate 87095048 B；positive/negative traction `[132300,480]`，各 NNZ 3628800，estimate 88149608 B | 同左 | modal_schur_build_begin raw marker 的 derived PETSc CSR estimates；不是 RSS |
| modal Schur | — | 960² complex128；matrix/constraint/LU 各 14745600 B，pivots 3840 B | repeat matrix error `9.94644e-14 <= 1e-13`，LU repeat=0 |

raw 的 generic `memory_object_ledger.json` 没有回填 exact-side action/factor；这是
generic-ledger coverage gap。此处以专用 15-marker stream、`v3_v7_diagnostic.json` 和
launcher stage alignment 为 authority，不修改 raw，也不把专用对象字节误写成 RSS。

## 5. 失败/边界与后续

首次错误 packet 路径的 run `results/task039_v5_h4_exact_side_setup_only_mpi8_2ba0c44`
保留为 `invalid_preflight_invocation`，因为 argv 使用了 `eaad0c44` 路径；它没有进入
setup marker，排除在重型尝试计数之外。

此外，selected-mode packet builder 在 coupling 后返回，未呈现 ordinary
`build_frozen_m10_setup()` 路径中的 `collective_heap_cleanup` 与
`post_coupling_heap_cleanup`；这是当前实现观察，不在本次证据收口中修复。raw 中已有的
专用 bottom/interface cleanup 仍按实记录，不能宣称两条路径 cleanup 完全同构。

本阶段证明了 setup-only 的 15-stage 生命周期、packet no-QEP 和 factor/side-action
释放顺序；它没有证明 outer solve、recovery、R/T/A、field/canonical 或完整 iterative
physics Gate。V5-3 仍具备研究资格，但本阶段不启动它。

证据入口：[rerun run summary](../../../results/task039_v5_h4_exact_side_setup_only_mpi8_2ba0c44_rerun1/run_summary.json)、[worker diagnostic](../../../results/task039_v5_h4_exact_side_setup_only_mpi8_2ba0c44_rerun1/numerical_output/v3_v7_diagnostic.json)、[stage-aligned memory](../../../results/task039_v5_h4_exact_side_setup_only_mpi8_2ba0c44_rerun1/numerical_output/memory_stages.jsonl)。raw 位于 ignored results，不进入 Git。

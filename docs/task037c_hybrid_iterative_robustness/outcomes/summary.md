# Task037c R7：Hybrid 迭代鲁棒性负结果收口

## 结论

Task037c 的正式鲁棒性资格没有建立。三个方位角的 Hybrid direct 自身 Gate 均通过，
但 `phi=-5°` 和 `phi=+5°` 的 M120/M160 对 Full3D 比较都在低功率显著通道上失败；
随后按任务书允许各运行一次 M160 solver-vs-direct diagnostic，两次 iterative 都在
1600 次上限前后未达到五项 true-residual Gate。因此最终分类保持：

```text
M_robust = not_established
classification = HYBRID_MODEL_ROBUSTNESS_NOT_ESTABLISHED_BY_M160
```

这不是 production 默认能力。M10/Task37c 路径都是显式 opt-in research capability，
ordinary direct Hybrid 默认未改变；本轮 numerical solver/config/threshold 未改，收口时另有
独立 test-only Case102 空-record 合同修复 commit `12a12647f89f1b0b4f6deb080046510b8e53821a`。

这里的“静态凝聚”是先消去每个单元内部未知量，只保留界面未知量，从而减少主线性系统的
规模；“Hybrid direct/iterative”则把有限元界面场和 Fourier 外部端口模态连接起来。
这能降低某些矩阵存储，但不能自动保证不同方位角下的物理通道逐项一致，本轮结果正是对
这个边界的实测记录。

## 冻结身份与范围

| 项目 | 值 | 证据身份 |
|---|---|---|
| numerical code/config parent SHA | `65556637dd10f2de674a800d575983f24336c9d3` | measured provenance |
| branch | `codex/20260810-task37c-hybrid-iterative-robustness` | measured provenance |
| wavelength / material | 13.5 nm / existing silicon authority | measured setup |
| geometry / mesh | fixed block grating, p6/h10 | measured setup |
| polarization / grazing | S / 1° (`theta=89°`) | measured setup |
| azimuths | `-5°, 0°, +5°` | measured setup |
| interfaces | 10 / 110 nm | measured setup |
| formal MPI | MPI8 completed for R2/R3; MPI1 not run | measured / not_run |
| M candidates | 120 and 160; no M200 | measured / forbidden extension |
| default boundary | ordinary direct Hybrid unchanged | measured source audit |

“measured”表示来自运行记录或其 hash-bound artifact；“derived”表示由已保存记录重新计算；
“not_run”表示该阶段没有执行，不是通过也不是失败数值；“controlled load failure”只描述
comparator 因输入资格未满足而安全停止。

## R2：三份 Full3D direct authority

三份 authority 均为 MPI8、`task037c_full3d_robustness_pass`、return code 0、true residual
`<=1e-9`、energy closure `<=1e-5`、完整 external q/orders、五平面 field、canonical 和
swap=0。每侧 external mode count 为 `40/40`（总计80）在 phi=0，为 `42/42`（总计84）
在两个非零方位角；这说明动态枚举确实参与了正式路径。

| phi | record | record SHA256 | true residual (relative) | R / T / A | A_volume / closure | mode 数(bottom/top) | process-tree RSS/PSS/USS MiB | total wall s | 状态 |
|---:|---|---|---:|---|---|---:|---|---:|---|
| 0° | [`full3d_direct_phi_0_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r2/full3d_direct_phi_0_6555663_mpi8.json>) | `f1833112d8ae0dd5bd8b8be02885f9f96b54e2ca458501ea66e168bc2daf86a7` | `2.516379473550484e-10` | 0.3656257892 / 0.0129906324 / 0.6213835784 | 0.6213835784 / `3.94e-12` | 40 / 40 | 15332.5 / 13280.2 / 12966.1 | 236.248695 | pass, measured |
| -5° | [`full3d_direct_phi_m5_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r2/full3d_direct_phi_m5_6555663_mpi8.json>) | `31da75627c269418aafa24092c3522bdfd147d2cd9730051cafa9e2f8a084c55` | `1.0022566668533898e-10` | 0.3655957120 / 0.0129940303 / 0.6214102577 | 0.6214102577 / `3.17e-12` | 42 / 42 | 15325.1 / 13273.2 / 12958.6 | 267.569926 | pass, measured |
| +5° | [`full3d_direct_phi_p5_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r2/full3d_direct_phi_p5_6555663_mpi8.json>) | `22737a64cc396600fe95bd913de5ff9b9b0c70caac95ada39dde1c36614a1478` | `6.90430121749339e-11` | 0.3655957120 / 0.0129940303 / 0.6214102577 | 0.6214102577 / `2.80e-12` | 42 / 42 | 15080.4 / 13026.5 / 12712.3 | 234.190065 | pass, measured |

R2 的 Full3D process-tree 峰值约 14.7--15.0 GiB 是该 direct authority 的实测资源口径，
不是 Task37c Hybrid iterative 的 6 GiB preferred 口径，不能混用。

## R3：六份有效 Hybrid direct authority

下表只列有效记录。phi=+5/M120 的第一份 `hybrid_direct_phi_p5_m120_6555663_mpi8.json`
是 operator path typo 造成的 preflight 历史证据；不把它伪造成数值结果，正式有效文件是
带 `_pathfix` 的记录。

首次 phi=+5/M120 尝试的完整历史证据为
[`hybrid_direct_phi_p5_m120_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/hybrid_direct_phi_p5_m120_6555663_mpi8.json>)，SHA256
`01e3087b6c4e41f9833d5630ebd8cce9ce5d79b465b9dec7a868092187fb1019`。这是 operator path typo
触发的 preflight-only/no PDE 记录；有效 `_pathfix` 记录的 SHA256 仍为
`34448101eb497f394a16c388fde8d4b1e4b84d0378e6eb2b343d08fe27b73dc4`。

| phi / M | record | record SHA256 | R / T / A | A_volume / closure | max traction dual / max q identity | external count total | RSS MiB / total s | own status |
|---|---|---|---|---|---|---:|---:|---|
| 0 / 120 | [`hybrid_direct_phi_0_m120_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/hybrid_direct_phi_0_m120_6555663_mpi8.json>) | `5c4419012b67f5771cb5b2ebffc1fc206b5d784c4dab06e403b2ea329ae234b5` | 0.3656257892 / 0.0129906324 / 0.6213835784 | 0.6213835795 / `1.13e-9` | `8.37e-12` / `8.75e-14` | 80 | 7317.2 / 338.64 | pass, measured |
| 0 / 160 | [`hybrid_direct_phi_0_m160_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/hybrid_direct_phi_0_m160_6555663_mpi8.json>) | `ec1f90a6c99b0fdbcb352f3365bf868e5f1cad20471ed78df131f3142018121c` | 0.3656257892 / 0.0129906324 / 0.6213835784 | 0.6213835795 / `1.12e-9` | `1.20e-11` / `6.16e-13` | 80 | 7765.4 / 416.82 | pass, measured |
| -5 / 120 | [`hybrid_direct_phi_m5_m120_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/hybrid_direct_phi_m5_m120_6555663_mpi8.json>) | `5102a969ff128ef88c1654ef13f69b5cc2f4deb585e772cec65828737a0d6845` | 0.3655958062 / 0.0129940313 / 0.6214101625 | 0.6214103107 / `1.48e-7` | `3.17e-11` / `1.11e-12` | 84 | 7169.9 / 313.85 | pass, measured |
| -5 / 160 | [`hybrid_direct_phi_m5_m160_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/hybrid_direct_phi_m5_m160_6555663_mpi8.json>) | `48c8999cd6567fc392836b243df868980c296c3f7d146719c11774b6fa8717ca` | 0.3655958062 / 0.0129940313 / 0.6214101625 | 0.6214103107 / `1.48e-7` | `3.84e-11` / `1.41e-12` | 84 | 7665.0 / 377.42 | pass, measured |
| +5 / 120 | [`hybrid_direct_phi_p5_m120_6555663_mpi8_pathfix.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/hybrid_direct_phi_p5_m120_6555663_mpi8_pathfix.json>) | `34448101eb497f394a16c388fde8d4b1e4b84d0378e6eb2b343d08fe27b73dc4` | 0.3655958062 / 0.0129940313 / 0.6214101625 | 0.6214103107 / `1.48e-7` | `5.09e-11` / `2.33e-12` | 84 | 7151.2 / 312.85 | pass, measured |
| +5 / 160 | [`hybrid_direct_phi_p5_m160_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/hybrid_direct_phi_p5_m160_6555663_mpi8.json>) | `071594193a85ff0fea20bbc8a342386fbb1521ff0833424b9838a513f8876eca` | 0.3655958062 / 0.0129940313 / 0.6214101625 | 0.6214103107 / `1.48e-7` | `2.17e-11` / `9.27e-13` | 84 | 7628.0 / 379.51 | pass, measured |

六份 direct 记录均有 monolithic true residual `<=1e-9`、exact traction `<=1e-8`、q identity
`<=1e-10`、recovery/field/canonical/order Gate 通过；M120/M160 的 external mode count
按 phi 分别为 40/40 或 42/42，而不是硬编码40。

## Matrix inventory 与阶段耗时

下表使用记录中的最终 assembled numerical NNZ；它不使用 factor NNZ，也不把 PETSc
global-sum 当作 assembled NNZ。Full3D 是一个 augmented 全局系统，Hybrid 的 rows/NNZ
则是每侧 local system，二者不能直接相减解释为总规模差异。

| 方法 / phi | 矩阵身份 | rows | assembled NNZ | modal dimension |
|---|---|---:|---:|---:|
| Full3D / 0° | augmented global | 51272 | 41988896 | not_applicable |
| Full3D / ±5° | augmented global | 51276 | 42064356 | not_applicable |
| Hybrid direct / 0° / M120 | each local side | 8464 | 6156544 | M120 |
| Hybrid direct / 0° / M160 | each local side | 8464 | 6156544 | M160 |
| Hybrid direct / ±5° / M120 | each local side | 8466 | 6194274 | M120 |
| Hybrid direct / ±5° / M160 | each local side | 8466 | 6194274 | M160 |

Full3D 的三次运行分别为单一 augmented 全局系统；Hybrid 的每个运行同时有 bottom/top
两个同规模 local system。这里的 `modal dimension` 只区分 M120/M160 内部模态，不能
替代 external mode count。

阶段耗时均为各记录直接报告的 measured seconds，不是由 wall time 估算：

| 方法 / phi / M | 主要阶段(s) | postprocess / physical reconstruction(s) | total wall / recorded total(s) |
|---|---|---:|---:|
| Full3D / 0° | stage4 assembly+solve 219.335199 | 9.132969 | 236.248695 |
| Full3D / -5° | stage4 assembly+solve 249.792659 | 7.916975 | 267.569926 |
| Full3D / +5° | stage4 assembly+solve 215.246425 | 8.953008 | 234.190065 |
| Hybrid / 0° / M120 | QEP 0.824423; bases 50.053914; local FE-DtN 162.570459; modal coupling 47.710957; primary build 28.461989 | physical reconstruction 24.264035 | 338.640490 |
| Hybrid / 0° / M160 | QEP 2.679890; bases 97.050630; local FE-DtN 163.719861; modal coupling 66.271922; primary build 29.797753 | physical reconstruction 30.919383 | 416.815373 |
| Hybrid / -5° / M120 | QEP 2.442246; bases 39.500598; local FE-DtN 163.452226; modal coupling 47.576589; primary build 17.105868 | physical reconstruction 24.503548 | 313.854632 |
| Hybrid / -5° / M160 | QEP 0.833061; bases 76.175254; local FE-DtN 161.772480; modal coupling 66.452507; primary build 19.007682 | physical reconstruction 31.341285 | 377.416392 |
| Hybrid / +5° / M120 | QEP 3.001537; bases 39.801125; local FE-DtN 161.041952; modal coupling 47.562409; primary build 17.458091 | physical reconstruction 23.897224 | 312.851019 |
| Hybrid / +5° / M160 | QEP 3.117193; bases 75.348622; local FE-DtN 162.332849; modal coupling 66.245286; primary build 20.211088 | physical reconstruction 30.829970 | 379.512395 |

## R3 selection 与负结果

[`m_robust_selection_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r3/m_robust_selection_6555663.json>)
SHA256 `2d7861cc44023fd27c4a082b14ae8bbdec1f040e6b890ccfee2ce6a489e83de6`：

| 条件 | 结果 | 身份 |
|---|---|---|
| 三个 phi 的 M120-vs-M160 | 全部通过 | measured |
| phi=0 的 M120/M160-vs-Full3D | 通过 | measured |
| phi=±5 的 M120/M160-vs-Full3D | significant-order relative Gate失败 | measured |
| `M120_pass` / `M160_pass` | false / false | derived selection |
| `M_robust` | `not_established` | derived final decision |

失败只涉及 11 个低功率显著通道，最大 relative delta 约 `2.4023e-3`，冻结阈值是 `1e-4`；
absolute delta 约 `9e-12`--`7.4e-11`。R/T/A/A_volume/closure、坐标、interface 与
middle E/H 均通过。M120 到 M160 的这些通道最大变化约 `7.37e-7`，远低于 `1e-4`，因此不能用增大 M 解释或修复，
也不能修改比较阈值。

## R4 允许的 solver-vs-direct diagnostic

两次诊断不是正式 R4，也不计入 three-way pass。它们使用 M160、MPI8、restart90、max_it1600、
zero initial 和原 fixed block-PC；均因 linear Gate失败而没有 recovery、traction、RTA、orders、
canonical、selected E/H 或 modal comparison。

| phi | summary / SHA256 | iterations / reason | reported / global / bottom / top / modal residual | linear solve / solver total s | peak RSS MiB / swap | 状态 |
|---:|---|---:|---|---:|---:|---|
| -5° | [`iterative_phi_m5_m160_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r4_diagnostic/iterative_phi_m5_m160_6555663_mpi8.json>) / `32f0e96535bba5dbb7c874d42c634dc351aaba3700e7a3e5238f6421716b4a8d` | 1600 / -3 | `7.545517759740e-5 / 7.545517759899e-5 / 9.880761454674e-5 / 6.100164476634e-5 / 2.616209774211e-15` | 332.132941 / 273.999675 | 6711.598 / 0 | solver-vs-direct diagnostic, numerical negative |
| +5° | [`iterative_phi_p5_m160_6555663_mpi8.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r4_diagnostic/iterative_phi_p5_m160_6555663_mpi8.json>) / `d086547e010cb98c6aa692d30f43251328801def26bb1bf0d142c198a3d6ee99` | 1600 / -3 | `5.246731334440e-5 / 5.246731334581e-5 / 7.628915705605e-5 / 4.203047804366e-5 / 2.532308173224e-15` | 323.890140 / 267.236788 | 6714.578 / 0 | solver-vs-direct diagnostic, numerical negative |

两份 controlled comparator 都只做 fail-closed load：

| phi | comparator / SHA256 | 结果 |
|---:|---|---|
| -5° | [`compare_iterative_phi_m5_m160_vs_direct_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r4_diagnostic/compare_iterative_phi_m5_m160_vs_direct_6555663.json>) / `a58068d90180ecb73773aa8daebacb982644443be09835f3d097416ec10ad955` | `load:watchdog has failures`; not_run_due_linear_gate |
| +5° | [`compare_iterative_phi_p5_m160_vs_direct_6555663.json`](</home/Projects/MyFEniCS/benchmarks/artifacts/task037c/r4_diagnostic/compare_iterative_phi_p5_m160_vs_direct_6555663.json>) / `a58068d90180ecb73773aa8daebacb982644443be09835f3d097416ec10ad955` | `load:watchdog has failures`; not_run_due_linear_gate |

modal residual 约 `1e-15`，但 bottom/top FEM true residual 停在 `1e-4`--`1e-5`；证据指向
fixed endcap/FEM preconditioned convergence bottleneck，而不是 QEP modal residual。任何“如果再
迭代若干步”的外推都只能标为 derived diagnostic，不能变成资格证据，也没有改变冻结的1600上限。

## 未运行项与边界

| 项目 | 状态 | 说明 |
|---|---|---|
| formal R4 Hybrid iterative | not_run_by_gate | M_robust 未建立，不能进入正式 R4 |
| formal R5 three-way | not_run_by_gate | iterative authority 缺失 |
| formal R6 MPI1 | not_run_by_gate | 只有对应 MPI8 iterative 通过才可运行 |
| MPI1 resource floor | not_run | 不估算、不外推实测 |
| M200 / 新 PC / 参数扫描 / 更多角度 / P 偏振 | forbidden / not_run | 任务书明确禁止 |
| 0.7 nm | out_of_scope | 未资格化 |

原 R2/R3 JSON、九份 comparator、selection、phi=+5 path-typo 历史和两份 R4 diagnostic
均保留在 ignored artifact 中；本轮不删除或覆盖。

## 用户授权研究扩展最终资格化

以下结果属于用户明确授权的 research extension，不追溯改写原冻结阶段结论。它把端面通量改为
真实 10 nm 三维 H(curl) 单元 Schur 列，并在两侧固定 ILU(0)+40-mode Woodbury 作用后做一次
确定性的残差修正；代价是额外的侧向算子作用和更长迭代时间；资源preferred仍未通过。`f2d7719` 是数值代码/配置父身份，
完整证据见 [MPI8 compact record](../../../benchmarks/cases/102_hybrid_iterative_robustness/records/task037c_mpi8_three_way_qualification_v1.json)
和 [MPI1 compact record](../../../benchmarks/cases/102_hybrid_iterative_robustness/records/task037c_mpi1_identity_and_resource_v1.json)。

### MPI8 三种方法

表内给 reported residual / iterations，完整 reported/global/bottom/top/modal 见 compact record；Full3D 与 direct 的单值为
各自 true residual。`RSS` 是 Full3D/iterative 的 simultaneous process-tree peak；direct
使用其 watchdog 的 `max_simultaneous_worker_rss_mb` 字段，二者保留原始采样口径差异。

| phi | 方法 | R / T / A / A_volume | residual / iterations | RSS MiB | total wall s | own Gate |
|---:|---|---|---|---:|---:|---|
| 0° | Full3D | .365625789179 / .012990632411 / .621383578410 / .621383578414 | 6.770520252e-11 / — | 15374.609 | 257.409715 | pass |
| 0° | Hybrid direct M120 | .365625789179 / .012990632411 / .621383578411 / .621383579539 | 5.765468683e-11 / — | 7693.633 | 449.431714 | pass |
| 0° | Hybrid direct M160 | .365625789178 / .012990632411 / .621383578411 / .621383579529 | 3.103124270e-11 / — | 8124.754 | 533.128482 | pass |
| 0° | Hybrid iterative M120 | .365625786729 / .012990632358 / .621383580913 / .621383576626 | 3.061697359e-9 / 1771 | 6542.090 | 1041.404664 | pass; preferred RSS fail |
| -5° | Full3D | .365595712018 / .012994030264 / .621410257718 / .621410257720 | 9.001849713e-11 / — | 15248.820 | 230.831346 | pass |
| -5° | Hybrid direct M120 | .365595712014 / .012994030264 / .621410257722 / .621410258879 | 7.449018674e-11 / — | 7481.434 | 421.923375 | pass |
| -5° | Hybrid direct M160 | .365595712013 / .012994030264 / .621410257724 / .621410258872 | 1.159358963e-10 / — | 8002.000 | 494.679228 | pass |
| -5° | Hybrid iterative M120 | .365595709120 / .012994030376 / .621410260504 / .621410260826 | 3.163761941e-9 / 3945 | 6623.156 | 1738.933491 | pass; preferred RSS fail |
| +5° | Full3D | .365595712019 / .012994030264 / .621410257717 / .621410257720 | 4.905910037e-11 / — | 15124.184 | 245.132864 | pass |
| +5° | Hybrid direct M120 | .365595712014 / .012994030264 / .621410257723 / .621410258880 | 4.543355137e-11 / — | 7550.172 | 422.165235 | pass |
| +5° | Hybrid direct M160 | .365595712013 / .012994030264 / .621410257723 / .621410258871 | 3.905341864e-11 / — | 8015.836 | 493.817763 | pass |
| +5° | Hybrid iterative M120 | .365595709299 / .012994030228 / .621410260473 / .621410256101 | 3.429167916e-9 / 2832 | 6475.238 | 1356.707269 | pass; preferred RSS fail |

三角度 Full3D、direct M120/M160 与 iterative M120 的 own Gate 均通过；9 份 M120/M160/Full3D
comparison 也全部通过，因此授权扩展的 `M_robust=120`。三角度 iterative 的完整五项残差、
阶段时间、watchdog SHA 与 raw path 以 compact record 为准，不把该扩展写成
`production-qualified`。

### MPI1 iterative 资源与数值

| phi | iterations | residual max / modal | R / T / A / A_volume | RSS MiB / total wall s | identity / resource |
|---:|---:|---|---|---:|---|
| 0° | 1472 | 4.953887173e-9 / 2.452093037e-15 | .365625794231 / .012990632482 / .621383573287 / .621383578463 | 1751.320 / 1903.921641 | pass / engineering; preferred fail |
| -5° | 2160 | 4.845818350e-9 / 2.135024973e-15 | .365595714284 / .012994030084 / .621410255632 / .621410254316 | 1662.109 / 2194.594255 | pass / engineering; preferred fail |
| +5° | 3338 | 4.999743003e-9 / 2.026232764e-15 | .365595710967 / .012994030395 / .621410258638 / .621410262566 | 1744.570 / 2777.664623 | pass / engineering; preferred fail |

MPI1 的 1536 MiB 是 preferred、2048 MiB 是 engineering 边界；三角度均数值/identity通过、
RSS 未过 preferred 但未超过 engineering，swap=0。MPI8 迭代峰值为 6475.238--6623.156 MiB，
均未过 6144 MiB preferred；资源失败不等于数值失败。

直观地看，MPI8 iterative 为 6475--6623 MiB，低于同 phi direct M120 的 7481--7694 MiB
与 Full3D 的 15124--15375 MiB，但 direct 采样字段不同且 iterative 未过 6 GiB preferred；
MPI1 为 1662--1751 MiB，是最低实测区间，代价是 total wall 约 1904--2778 s。

### Gate 与限制

| 项目 | 结果 | 边界 |
|---|---|---|
| 原 `6555663` scalar/max_it1600 阶段 | 历史负结果保留 | 不由本扩展追溯改写 |
| final `f2d7719` Full3D/direct/iterative | 三角度 own Gate 与三路 comparison 全 pass | `M_robust=120` 仅限授权扩展 |
| MPI8 资源 | 数值通过，preferred 未通过 | process-tree 6475.238--6623.156 MiB vs 6144 MiB |
| MPI1 资源 | engineering 通过，preferred 未通过 | 1662.109--1751.320 MiB vs 1536/2048 MiB |
| mirror | 3/3 power-only pass | 复振幅 `not_run_without_phase_map` |
| production status | not production-qualified | 不追加 M200、新 PC、参数扫描或 continuum claim |

最终限定分类为
`TASK037C_S_POL_1DEG_AZIMUTH_ROBUSTNESS_PASS_UNDER_USER_AUTHORIZED_RESEARCH_EXTENSION`。

# V7 Lane A：exact-side setup 极限测量

本阶段只测量一次 post-compaction exact-side 的完整 setup。它的作用是回答“在进入真正外层
求解之前，现有 exact-side 路径最多占多少进程树内存”，不是一次完整的物理仿真。setup
通过后，才有资格另行审查一次 full formal；本次没有运行 outer solve、recovery、field 或
R/T/A。

## 结论

| 裁决项 | 结果 | 解释 |
| --- | --- | --- |
| setup advancement | `SETUP_ADVANCEMENT_PASS` | process-tree peak `81.056903839 GiB <= 84.039305878 GiB` |
| half-memory compatibility | `NOT_HALF_MEMORY_COMPATIBLE` | 仍高于旧 V6 `42.019652939 GiB` 线 |
| exact-side full formal | `FULL_FORMAL_ELIGIBLE` | outer-ready、生命周期、packet/QEP release 和 swap Gate 均通过；尚未运行 |
| ordinary default | unchanged | 仅显式 V7 setup-only profile |

因此 Lane A setup advancement 通过，但这不是完整 Hybrid iterative 的数值或容量结论。下一步
只能先审查现有 full-formal outer/recovery 路由，再决定那一次唯一的 full formal；不得把本次
setup-only 结果当作 R/T/A 或 0.7 nm 资格。

## 身份与原始证据

| 项目 | 值 |
| --- | --- |
| source SHA | `f4073adabb91bffe5c3954b8ae8b63270efa3e15` |
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| packet manifest SHA | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| packet identity file SHA | `b3bb870fe6fa17cb262b6161f7317cc1950944755c9270d4628dd5c79e950690` |
| exact-response spool | `results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output` |
| run root | `results/task039_v7_h4_exact_side_limit_setup_only_mpi8_f4073ada` |
| run status / exit | `finished` / `0` |
| observed elapsed | `10649.634795 s`；final cleanup marker `10644.903732 s` |
| raw compact record | [task039 V7 Lane A record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_limit_setup_v1.json) |

raw 的 `run_summary.json`、`run_manifest.json`、worker stdout、marker、stage 和 process-tree
sample 文件的 byte 数与 SHA256 均固定在 compact record 中；raw 目录不进入 Git。

## 内存 Gate

“峰值”这里指完整进程树在连续采样中的最大 RSS，不是把对象字节相加，也不是把不同
阶段的 RSS 累加。

| 证据 | measured result | Gate |
| --- | ---: | --- |
| complete process-tree peak | `87,034,187,776 B = 81.056903839 GiB` | `<=84.039305878 GiB`，pass |
| peak sample | `2026-08-20T05:03:51.568872Z`，elapsed `3180.845112 s` | 位于 `bottom_interface_blocks_heap_cleanup` 到 `bottom_F_ready` 的边界窗口 |
| outer KSP setup ready | `83,233,230,848 B = 77.516986847 GiB` | marker/sample measured，pass |
| peak swap | `0 B` | zero-swap pass |
| hard stop | `90,236,517,581 B`，`84.039305878 GiB` | 运行时实际执行的 V7 absolute limit |

峰值样本是 marker 对齐窗口中的 process-tree 证据，不能独立归因给某一个矩阵或因子。
旧的 `42.019652939 GiB` half-memory line 没有达到，因此本结果不能称 half-memory compatible。

## setup、factor 和 modal Schur

V7 复用了 factor-only side action：它保留 PETSc factor Mat、Woodbury 状态和小型 modal
Schur，销毁不再需要的 F/C/H carrier；没有调用 outer solve。

| 阶段/对象 | bottom | top |
| --- | ---: | ---: |
| factor NNZ | `1,057,904,352` | `991,254,240` |
| factor count at outer-ready | `1` | `1` |
| final factor count | `0` | `0` |
| K rank / condition | `296 / 8.405950933966242` | `304 / 43.15222733417726` |
| W local bytes | `81,070,848` | `81,131,520` |
| side apply count | `970` | `970` |
| side base/D solve count | `970 / 970` | `970 / 970` |

modal Schur 是两个 side action 的小型耦合块；它只在 setup 中构造一次完整矩阵，并重构
冻结列检查，而不是保留第二个完整矩阵。

| modal Schur evidence | measured result |
| --- | ---: |
| shape / rank | `960 x 960` / `960` |
| condition | `24.677208593174512` |
| matrix repeat / LU repeat solve error | `0.0 / 0.0` |
| normal equations | `false` |
| full build apply count | bottom/top `960 / 960` |
| sampled reconstruction apply count | bottom/top `10 / 10` |
| sampled columns | `0, 1, 240, 267, 479, 480, 481, 720, 746, 959` |
| sampled contract SHA | `8d73d77a47fe0aa614e231eaac1f939eb28cca5b01c024c70fd518a3a592f082` |

outer KSP 只完成 `setUp`：实际类型为 `gmres`、restart `10`，`solve_called=false`，
Krylov vectors 在 solve 前未分配。

## 生命周期与 packet 隔离

| 时点 | factor 状态 | 其他证据 |
| --- | --- | --- |
| outer-ready | bottom/top `1/1` | global direct factor `0`；modal Schur ready |
| final cleanup | bottom/top `0/0` | `setup_destroyed=true`，cleanup 顺序 `coupling -> bottom -> top -> packet_bundle` |
| packet consumer | 不物化 QEP | `qep_calls=0`，mmap released，packet/QEP refs released=true |
| exact-response spool | 只作 holdout/oracle | 96 个 transient hash-read artifacts，`arrays_retained=false` |

本次 candidate 没有把 exact-response 输出当作生产内存优势；spool 只用于既定验证合同，且
训练/正式 setup 与它的身份绑定保持可审计。

## V6 layer-graph audit 的继承结果

本次 setup 中 layer graph 已完成并写入 raw。它来自真实 owned-cell recovery map、trace
constraint expansion 和 mesh z geometry；共享 trace row 采用 incident owned cell layer
的最小编号，不使用全局行号均匀分桶。

| 图统计 | bottom/top（相同 measured 结构） |
| --- | ---: |
| rows / NNZ | `132,300 / 105,038,640` |
| same-layer NNZ / fraction | `75,327,840 / 0.717144091` |
| adjacent-layer NNZ / fraction | `29,710,800 / 0.282855909` |
| long-range NNZ / fraction | `0 / 0` |
| block half-bandwidth | `1` |
| layer count | `6` |
| temporary global row-layer tags | released |

完整 6×6 `layer_pair_nnz`、每层 rows/NNZ、边界和 mapping source 保存在 compact record，
不在此重复展开大型 raw marker。

## 未运行项与边界

| 项目 | 状态 |
| --- | --- |
| outer solve / recovery / field / R/T/A | `not_run` |
| exact-side full formal | `eligible`, pending separate review；本次未启动 |
| Lane B streamed owner-row Petrov | `not_run` |
| Lane C graph-only campaign | `not_run`（本次 graph 仅为 setup telemetry） |
| 0.7 nm PDE / new Full3D heavy | `not_run` |

本结果只证明当前 post-compaction exact-side setup 越过 V7 advancement line；它没有证明
完整 workflow 低于 direct，也没有改变 ordinary defaults。full formal 的 no-saving stop
边界应使用 matched direct 的精确 `100262797312 B`，并沿用 swap>0 立即停止、默认 6h，
只有已进入 outer、峰值仍低于 direct 且残差客观下降时才允许一次总计 8h 的条件政策；这些
是下一阶段设计合同，不是本次运行行为。

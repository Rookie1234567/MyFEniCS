# Task037-extra G2.6 D3c-c response：LOR-HX contraction 证据与 G2_FAIL

本轮只从唯一正式 raw run 固化证据。本轮没有运行新 PDE、没有修改代码/raw；这里只固化
本轮证据。结论是 `G2_FAIL`，不是 `G2_PARTIAL`；因此不进入 G3，也不提出修复或参数扫描。

## 先解释这次测量在判断什么

固定 low-storage V-cycle 是一种局部近似逆：它用便宜的边缘修正，再借助标量 H1 和向量
H1 辅助空间把误差送到更粗层，最后只在很小的最粗层使用精确因子。它的目标是避免
p6 trace 上的大 ILU；代价是要长期保留 LOR 转移矩阵、H1 层级和 setup 时间。

`rho` 是 correction 后 exact shifted full-space Schur 残差范数除以输入残差范数：
`rho<1` 表示该方向缩小，`rho>1` 表示放大。`measurement_qualified` 只表示 raw
字段、重复作用和派生计算自洽，不表示 V-cycle 性能通过。

## 当前结论

| 范围 | 状态 | 准确边界 |
|---|---|---|
| G2.4 LOR transfer | `pass_transfer_build_and_algebra_only` | 拓扑、周期 identity、`T/T^H`、determinism/adjoint 通过 |
| G2.5 LOR-HX build | `pass_build_only` | hierarchy 可构建；retained-payload memory signal 失败；未由 build-only 推断收敛 |
| G2.6 contraction raw | `measurement_qualified` | raw 完整且 finite/deterministic；minimum、strong 失败，apply-time overall false |
| G2 overall | `G2_FAIL` | minimum contraction 已失败；不享有 rooted local repair |
| G3 | `not_started_and_prohibited_by_G2_FAIL` | 禁止启动 |

G2.5 当时的 `not_claimed` 只保留在 D3b 历史阶段语境；当前 G2.6 已完成测量，overall
分类现在明确闭合为 `G2_FAIL`。没有 official field、official RTA 或物理收敛结果。

## 运行身份与 solver screen

| 项目 | raw 值 |
|---|---|
| source / branch | `30e179799b8eb6dee1be1bb976002550424bb40d` / `codex/20260806-task37-iterative-extra-development` |
| scope | p6/h10/S、MPI1、M2c never-materialized、M3a overlap0.125 partition、screen20 |
| flags | identity + LOR transfer + LOR-HX oracle + contraction；factor inventory=false；G0=false |
| run directory | `benchmarks/artifacts/101_task37_extra_development/g2_slab14_lor_hx_contraction_mpi1_screen20_30e17979` |
| watchdog | `task037_extra_g2_slab14_lor_hx_contraction_measurement_qualified`；return `0`；failures `[]`；swap `0` |
| solver | 20 步 `DIVERGED_MAX_IT(-3)` |
| true / reported residual | `0.04474243612765` / `0.04474243612765121` |
| official result / RTA | `false / false` |

固定 20 步边界说明 solver 没有达到收敛 Gate；watchdog 的 qualification pass 只表示
raw 证据完整、自洽，不能把它解读成性能通过。

## Slab14 identity 与 transfer

| 字段 | 值 |
|---|---:|
| owner / cells / unique blocks | `0 / 54 / 6` |
| full / interior / trace rows | `32724 / 24300 / 8424` |
| physical / active / periodic-slave edges | `38304 / 36288 / 2016` |
| partial cells / incomplete trace rows | `18 / 6264` |
| missing writer | `0` |
| parent ID hash | `ac7e3532a1ecf55826a25a99b1f5197fb7c9952a084bf88f4ca15bad79511023` |
| physical edge hash | `69b351698907f0067b09cf14c0f889d1566a86d1bcfec78d7a48121659635054` |
| active edge hash | `a359da92b3a781ff447f5bf81ce7dc845c1be022464948526ee489874c77010a` |
| shared / complete C max error | `1.7200665360018798e-15 / 9.56091885020216e-16` |
| retained transfer payload | `18735740 B` |

identity 的 3 个 deterministic vectors 误差为 `2.9248960201709676e-15`、
`2.978578754981666e-15`、`2.6617554455542794e-15`。真实 iter20 source 是 solver
内部的 `r=b-Ax`，norm2 为 `0.42723143961943305`，residual SHA256 为
`3aa610ed9bbb63047188b64d21d5dcab04184ffc6316196458e99aab520bb195`，identity error
为 `1.7721399154913289e-15`。这些是 identity 证据，不是 contraction performance pass。

## G2.5 build-only storage

LOR-HX build 使用 affine volume proxy：curl coefficient `(1,0)`，material tags 1/3
有 complex mass coefficient；无 DtN surface proxy，不是 literal p6 Galerkin，exact
outer operator 未改变。

| 项目 | 值 |
|---|---:|
| full/interior/trace rows | `32724 / 24300 / 8424` |
| transfer / D2c hierarchy / total retained payload | `18735740 / 3109473612 / 3128209352 B` |
| factors | `2`，coarsest-only=true |
| fine p6/full/trace/intermediate/large LOR factors | 全部 `0` |
| parent topologies / persistent RHS / global dense | 全部 `false` |
| transfer / HX build seconds | `51.72637021099217 / 607.4379243750591` |

任务规定的 trace-ILU baseline 为 `122023588 B`，0.60 threshold 为 `73214152.8 B`。
HX/trace=`25.63610366874313`，故 retained-payload memory signal 为 `FAIL`。这是
numeric payload lower bound，不是 RSS，也不含 Python object、allocator 或 permutation。

## G2.6 三源、四方法

iter0 和 iter20 是 M3a screen 的真实 residual，不是 B4 i200/long-tail residual。
B4 long-tail raw 本轮未单独测量；mixed/high 是固定归一化组合
`normalize(v0 + (0.5-0.25j)*v1 - 0.125j*v2)`，并且是任务要求的独立 source。

| source | current trace ILU | B4 GMRES(4) | LOR-HX 1V | LOR-HX 2V | best LOR |
|---|---:|---:|---:|---:|---:|
| real M3a iter0 | 2.422027189163481 | 0.9440411915945912 | 5611759.4667701805 | 4885392465721929.0 | 5611759.4667701805 (1V) |
| real M3a iter20 | 1.2604899530937386 | 0.755818683406265 | 3465823.613309288 | 1651097278181490.5 | 3465823.613309288 (1V) |
| manufactured mixed/high | 4.455510654442446 | 0.8584226047142137 | 61738549.74675689 | 1.4084260534619966e16 | 61738549.74675689 (1V) |

iter20 另列 G2.3 full-space p6 ILU comparator `rho=1.806246468352144`。它来自 source
SHA `1a2dd825e295c38e3cecf30e98fa62b7a3510e1d` 的不同 run，但共享上述 iter20 residual
hash；不能当作本 run 的同一 timing sample。

| measured Gate | 阈值 | 结果 |
|---|---|---|
| minimum：iter20、mixed/high | LOR-HX best `<= (2/3) * B4` | `false / false` |
| strong：iter0、iter20 | LOR-HX best `<= 2 * ILU` | `false / false` |
| apply-time：每源至少一个 1V/2V `<=10x` ILU | iter0 `312.2772206993064 / 4.246395389906666`；iter20 `1842.4615404593533 / 81.26242051814305`；mixed `1.272784014360302 / 1.4723523740894053` | `true / false / true`；overall `false` |

所有 rho 都由 exact shifted full-space Schur post-action 计算，`proxy_self_score=false`、
`global_matrix_materialized=false`。1V best 仍约 `5.61e6 / 3.47e6 / 6.17e7`，2V
更差，不是数值边界误差。mixed/high 的 best rho `61738549.74675689` 远大于
`(2/3)*0.8584226047142137`，因此 task-level minimum hard stop 已确定失败，不依赖
未单独测量的 B4 long-tail raw，也不允许为此补跑。由 minimum 失败，任务书 hard stop
直接给出 `G2_FAIL`。

## 资源与阶段口径

| 指标 | raw 值 |
|---|---:|
| process-tree authority | `8333.12890625 MB = 8.137821197509766 GiB` |
| worker RSS/PSS/USS | `8319.29296875 / 8267.7822265625 / 8223.19140625 MB` |
| swap | `0` |
| transfer build interval peak | `1180.78125 MB` |
| HX build-start interval peak | `5529.8125 MB` |
| HX ready interval peak | `7924.58984375 MB`；包含后续既有 trace-factor setup，不能叫纯 HX peak |
| historical cgroup peak | `13279.546875 MB`；不是当前 authority |
| warning / memory termination / timeout | `false / false / false` |

## Raw evidence

紧凑记录为
[`g2_slab14_lor_hx_contraction.json`](/home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/g2_slab14_lor_hx_contraction.json)。完整 argv 保留在 raw `watchdog_summary.json`，record 只保存命令身份，避免复制整个 raw。

| raw 文件 | SHA256 |
|---|---|
| `watchdog_summary.json` | `b52125f40f946da4bbf792174224beb4a1526c1d20eab04e3b3bc748da95b2f4` |
| `run_summary.json` | `a6e53c655f896ddb26de3ef86fd39e147da3b74bfda558fd4998870e9ec32f65` |
| `task037_f3_core_audit.json` | `a87537cc899d3ae6df8068a8f797fbd5da4061e32e7400c32d20f33e3595f9e4` |
| `progress_3d.jsonl` | `db8c0f2e8de7f6924dc953b65026f74abfc304c1f0eda8d43fb0c49f2664227d` |
| `task037_f3_residual_history.jsonl` | `75f0bc3ebec3648b60fdfc55daa9afd036b81cf6d5fe0ef1f7051a83e0f24940` |
| `memory_timeline.csv` | `ca7ff04921b5be4e8b1cb31f356f7baff9eda1203479f0ca666fe9b193759dad` |
| `parent_launch_descriptor.json` | `19854ce17d27bfe2fde1e6dfb4de280249fc4f49ddad4605c29542094c756b57` |
| `worker_stdout.txt` / `solver_log.txt` | `a6a3509af15b95064729acfd1ba0c1904b44fb14826d4a4b6c9e6663b50a5dde` |
| `NO_OFFICIAL_FIELD_OUTPUT.txt` | `e11465d92e416af3e4321c581b7291b7d4df5c932b425541f9b0114e259d3f38` |

## 停止结论

G2.5 build-only 与 G2.6 raw measurement 均保留；G2.3 plain full-space ILU route closed
和 G2.4 transfer/algebra-only 结论不变。当前唯一整体结论是 `G2_FAIL`，不是
`G2_PARTIAL`；G3 为 `not_started_and_prohibited_by_G2_FAIL`。本 response 不宣称
production promotion、full solve 或物理收敛。

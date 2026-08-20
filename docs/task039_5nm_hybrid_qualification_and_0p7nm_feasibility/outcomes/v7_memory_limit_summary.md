# Review V7：内存—残差—时间 Pareto 收口

本页把“完整 workflow”与“单个 component”分开。完整 workflow 包含 setup、outer solve、recovery 和物理检查；component 只说明某一段确实占用了多少内存，不能替代完整资格结果。

## 统一结果表

| 阶段 | 身份/方法 | 范围 | 峰值 RSS（GiB） | 时间（s） | 数值/资源结论 |
|---|---|---|---:|---:|---|
| matched direct | h4 direct reference | 完整 workflow | 93.377006531 | **7131.113596** | matched baseline；inherited authority |
| Lane A setup-only | exact-side setup-only | setup component | 81.056903839 | **10649.634795** | `<=84.039305878` advancement pass；不是 full-workflow Gate |
| Lane A full formal | exact-side、single-build modal Schur、outer GMRES10 | 完整 workflow | **80.025856018** | **10126.232** | 1 iter；physics/recovery/checker pass；相对 direct 节省 14.298113646%，唯一完整 workflow 正结果 |
| Lane B producer | streamed owner-row basis producer | producer component | 11.630760193 | 约 415.6 | packet/coverage/lifecycle/resource pass；没有 holdout solve |
| Lane B consumer | streamed bottom Petrov rank ladder | bottom component | 23.038208008 | 约 632.8 | resource/ownership/lifecycle pass；rank512 仍 numerical fail |
| Lane C | bottom→destroy→top→destroy graph-only | graph component | not_measured | not_measured | graph measured；没有 QEP、factor、PDE 或正式 Pareto RSS |

因此，最低测得 component RSS 是 producer 的 `11.630760193 GiB`；最低合格的完整 workflow RSS 是 Lane A full formal 的 `80.025856018 GiB`。二者不能混称为同一种内存优势。

## V7 full-workflow 分级线

分级线以 direct `93.377006531 GiB` 为基点。Lane A full formal 的 14.298113646% saving 只进入 `5_TO_20_PERCENT`，没有达到 20% 线；component 的更低 RSS 不改变这一判断。

内存下降伴随一个基于现有可用总时长的 derived comparison：Lane A full formal 的 parent/observed elapsed 为 `10126.231902 s`，matched direct 的 inherited `worker_total` 为 `7131.113596 s`，derived difference 为 `2995.118306 s`、约 `42.0007%`。两者属于 non-identical timing authorities，因此这不是 strict performance qualification。Lane A 只有 1 次 outer iteration；额外时间主要出现在两侧 factor 与 modal-Schur setup，而不是更多 outer iterations。Lane B streamed 路径因 bottom numerical Gate 失败，没有完整 workflow wall time 或 iteration tradeoff，不能从 component 时间推测。

| 目标节省 | 对应峰值上限（GiB） | V7 结论 |
|---:|---:|---|
| 0% / direct | 93.377006531 | reference |
| 5% | 88.708156204 | Lane A full pass |
| 20% | 74.701605225 | not_reached |
| 30% | 65.363904572 | not_reached |
| 40% | 56.026203919 | not_reached |
| 50% | 46.688503266 | not_reached |
| 60% | 37.350802612 | not_reached |

旧 `42.019652939 GiB` half-memory line 也未达到。Lane A setup-only 的 `84.039305878 GiB` 是独立 advancement authority，不是 full formal 的替代阈值。

## Lane B rank Pareto：残差与 coarse-E 条件数

下表的 `preferred max` 是 modal+/modal−/external 三个 preferred probe 的最大 true residual；五个非退化 holdout 中任一 mandatory residual 超过 `1e-2` 即失败。`E` 是 consumer 中实际构造的 `Y^H F Z`，不是 producer 的 `Y^H Z` warning。

| rank | E 有效秩 | E condition | setup（s） | apply（s） | holdout（s） | worst mandatory | preferred modal/external max | common process-tree envelope | Gate |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 64 | 64 | 3.219938404e3 | 4.840 | 10.835 | 11.301 | 219.375773963 | 219.375773963 | 23.038208008 GiB（四级共同） | fail |
| 128 | 128 | 6.778370040e3 | 10.035 | 10.928 | 11.393 | 310.531296720 | 210.180979804 | 23.038208008 GiB（四级共同） | fail |
| 256 | 256 | 5.383690736e4 | 21.593 | 11.481 | 11.953 | 1143.092533433 | 1143.092533433 | 23.038208008 GiB（四级共同） | fail |
| 512 | 512 | 2.788596049e5 | 51.070 | 11.522 | 11.989 | 1521.816092530 | 1521.816092530 | 23.038208008 GiB（四级共同） | fail |

各级 finite、repeat、linearity、E full-rank/condition 和 resource Gate 均通过；失败来自 source-family 对五个 mandatory holdout 的 true residual。RSS 是同一 consumer 进程的共同 process-tree envelope，未按 rank 隔离测量，不能把 `23.038208008 GiB` 解读为四个独立 rank 峰值。具体 modal、external 和 random 数值见 [bottom consumer Pareto outcome](v7_petrov_bottom_pareto.md) 及 [compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_petrov_bottom_consumer_v1.json)。

## 生命周期与证据边界

- Lane A full formal：outer-ready factor `1/1`，最终 cleanup `0/0`，packet/QEP released，1 次 outer iteration；Full3D secondary 为 `not_available`。
- Lane B producer：同一 packet 包含 64/128/256/512 prefix，4 个 mmap 从 4 降到 0；没有 holdout、exact spool、QEP、global basis 或 direct factor。
- Lane B consumer：ownership remap、mmap/spool/fixed-action release、base factor `1`、exact/global `0/0`、nested KSP `0` 均通过；它仍是 bottom component，不是 full workflow。
- Lane C：6 层、132300 rows、105038640 NNZ 的 bottom/top local-F graph 均与 reference pattern 一致；wall/RSS/cleanup inventory 为 `not_measured`，不得拿作 Pareto RSS。DtN global low-rank coupling 被明确排除在该 local-F graph 之外。

Lane B 的 `Y^H Z` 病态只作为 producer conditioning warning；正式 Gate 使用 consumer 的 `E=Y^H F Z`，四级 E condition 均低于 `1e12`。这不是把 warning 改写成通过，也不是新增 producer 停止线。

V7 因 bottom rank512 numerical Gate 失败关闭 streamed Petrov 的 top/both/full 路径。V7 没有建立 0.7 nm PDE 或可扩展性结论。

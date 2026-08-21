# V10：内存—残差—时间 Pareto

本表把完整 workflow 与 component 诊断分开。component 的低 RSS 不能直接写成完整任务节省；完整 workflow 仍以 Lane A full 为唯一正式低于 direct 的结果。

| 路线 / 方法 | 口径 | peak RSS | wall / 时间 | 数值摘要 | 资源与生命周期 |
|---|---|---:|---:|---|---|
| matched h4 direct | 完整 workflow baseline | `93.377006531 GiB` | inherited worker_total `7131.113596 s` | baseline | direct authority |
| V7 Lane A exact-side full | 完整 workflow | `80.025856018 GiB` | observed parent `10126.231902 s` | 1 outer iteration；full formal pass | swap0；相对 direct RSS 下降14.298113646% |
| V9-1 J1 | bottom component | `23.8684272766 GiB` | setup/holdout/apply inherited | worst bare-F `50.7689715097` | construction pass；retained not_run |
| V9-2 SN2-J / SN2-SGS | bottom component，共同 process envelope | `22.8126640320 GiB` | inherited `473.941922 s` total | 两候选 nonfinite | construction pass；retained not_run；factors3→0 |
| V10-2 factor integrity | bottom component | `41.0968208313 GiB` | inherited `~473.942 s` | B0/B1/B2 conventional/factor-only finite | construction pass；retained not_applicable |
| V10-3 SN2-J | bottom component | `27.0815505981 GiB` | inherited `~300 s` | advancement pass；side residual fail | construction/retained pass；factors3→0 |
| V10-4 J1-preconditioned side FGMRES | bottom component | `22.0071983337 GiB` | parent wall `300.860810 s`；16-step checkpoint `5.378–5.489 s/RHS` | worst true residual `0.9989849199`；no unified budget | construction `<=45` pass；retained `19.4346771240 GiB <=30` pass；swap0；factors6→0 |

V10-4 的 five-RHS FGMRES 没有达到 `r<=1e-2`，所以不能拿 `22.0071983337 GiB` 作为 full-workflow saving，也不能进入 V10-5。其后的 V10-6 response-packet full producer 与独立 compression 已运行并完成资源/生命周期审计；producer 的 response residual 通过，但 compression 的 holdout generalization 为正式负结果。第一次 compression root 是 SHA 透传 implementation failure，已原样保留；不能把它与修复后 component 结果混为数值失败。

## Review V10-6/V10-7：full side-response packet

| 阶段 | 口径 | peak RSS | wall / 时间 | 数值与生命周期 | 结论 |
|---|---|---:|---:|---|---|
| full response producer | bottom component | 50.7548675537 GiB | 4390.176657 s measured | 960 modal max true residual 1.52248376596e-10；payload 2034244800 B；factor 1→0；swap0 | producer PASS |
| successful 16-column pilot producer | bottom component | 43.20536804199219 GiB | setup 2361.916216508951 s；solve 21.45196287811268 s；projected full 3650.374736875594 s | 16-column worst true residual 1.0251447633580063e-10；actual payload 33868800 B；projected payload 2034244800 B；factor 1→0；swap0 | pilot PASS |
| successful pilot consumer | bottom component | 1.649871826171875 GiB | not_measured | packet released；factor/global 0/0；swap0 | pilot PASS |
| first compression attempt | bottom component | 约1.634716 GiB | exit2 | main 漏传 producer SHA；算法未开始；swap0 | IMPLEMENTATION_FAILURE |
| repaired compression | bottom component | 15.4776763916 GiB | worker 236.720152 s；parent 约239.730152 s | one TSQR + small-R SVD；packet released；factor/global/nested 0/0/0；swap0 | execution/resource/lifecycle PASS |
| sequential V10-6 envelope | component envelope | 50.7548675537 GiB | producer + compression phases | 不是完整 workflow peak，不能转成 saving | evidence only |

四次 pilot wiring/lifecycle 失败均为 exit2、swap0，且没有形成合格 pilot；`not_measured` 表示 raw 未提供可绑定的正式 wall，不作估计。它们不是同一个“算法未开始”结论：e353d97d 在 pre-profile 失败、算法明确未进入；a7f237ae 与 955466b3 的算法是否已开始无法由 raw 建立；d0353dec 已完成主体计算/packet 阶段后才在 finalizer telemetry 失败。具体 root、source SHA、峰值和 raw hash 见 compact record。

| pilot failure root | component peak RSS | failure stage | evidence classification |
|---|---:|---|---|
| `e353d97d` | 1.6369743347 GiB | pre-profile | `algorithm_started=false`；profile None / AttributeError |
| `a7f237ae` | 42.9734916687 GiB | spool-remap | `algorithm_started=not_established`；缺 shard descriptors |
| `955466b3` | 42.9833679199 GiB | response-map-readonly | `algorithm_started=not_established`；assignment destination read-only |
| `d0353dec` | 41.9813041687 GiB | finalizer-telemetry | `algorithm_started=true`；主体已运行，finalizer telemetry KeyError |

compression 的 rank64/128/256/512 training optimal errors 为 0.5922391025、0.3517745690、0.1611181515、3.8908212468e-12；对应 holdout worst 为 0.9999934115、0.9999772293、0.9676601222、0.9673241512。最大 rank 仍有 0、1、480、481 四列约0.9673，因此 generalization/compressibility negative，不能提升为 production PC、top 或 full Hybrid。

producer 的 50.7548675537 GiB 只描述 bottom component。完整 workflow authority 仍是 direct 93.377006531 GiB 与 Lane A full 80.025856018 GiB，正式节省 14.298113646%；20% 与 50% tier 未达到。

compact 数字源为 [V10-6 packet record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v10_side_response_packet_v1.json)，详细表格为 [V10-6 outcome](v10_side_response_packet.md)。top、both-side、full Hybrid、V10-5 modal cost model 和 0.7 nm PDE 仍 not_run。

## 口径提醒

```math
\text{full-workflow saving} \ne \text{component RSS reduction}.
```

Lane A full 相对 direct 的RSS下降是已测完整 workflow 结果；V10-4 只是一次 bottom side component 诊断。PSS/USS 在本次 V10-4 raw 中 `not_measured`，不能从 RSS 推断。所有 raw root 与大型 JSONL/ledger 均为 ignored local artifacts，compact evidence 只提交 hash-bound 元数据。

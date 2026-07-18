# Task006 memory report

## Persistent exact-audit storage

| 项目 | 结果 |
|---|---:|
| private persistent local CSR | **0 bytes** |
| borrowed work vectors / rank | 0.753–0.762 MiB |
| borrowed layout metadata / rank | 0.068 MiB |
| owns global action/scatter | 否 |
| ordinary path auditor allocation | 0 |

P1 qualification 为 equivalence 临时逐 slab 加载 reference CSR，最大 ephemeral
12.095 MiB，用完立即释放。该 reference 不属于 runtime persistent ledger。

## Hypothetical proxy storage

Task005 `A_D0_R64` 四模型 owner estimate 为 27.824 MiB。下表把四个 R4
certificate storage 作为未来 four-slab owner 的代表估计，并加 P1 最大 work
vector 0.762 MiB；它只判断存储是否是本轮 blocker，不代表 proxy usable。

| proxy | certificate / four slabs | model + proxy + work | Gate |
|---|---:|---:|---|
| q64 two-seed | 0.750 MiB | 29.336 MiB | preferred storage feasible |
| q256 two-seed | 2.250 MiB | 30.836 MiB | preferred storage feasible |
| q512 two-seed | 4.251 MiB | 32.837 MiB | preferred storage feasible |
| q1024 two-seed | 8.250 MiB | 36.836 MiB | speed-first only |
| q2048 two-seed | 16.250 MiB | 44.836 MiB | speed-first only |

因此 P2 失败不是 storage failure。q64–512 可落在 33.670 MiB preferred，
q1024–2048 仍低于 50.505 MiB speed-first；但 12/12 family 均未通过 false-reject
Gate，不能进入 P6 lifecycle 或 P7 external RSS shadow。

## External peak

| run | peak | ratio vs P0 | swap |
|---|---:|---:|---:|
| P0 baseline | 1.608242 GiB | 1.00000 | 0/0 |
| P1 borrowed qualification + full solve | 1.613209 GiB | 1.00309 | 0/0 |

P7 paired live shadow 未运行，故不得把 P1 peak ratio写成最终 shadow memory Gate。

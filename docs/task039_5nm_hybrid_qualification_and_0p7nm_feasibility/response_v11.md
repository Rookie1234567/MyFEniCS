# Task039 Review V10：V10-7 阶段响应

## 结论先行

V10-6 的 full side-response producer 和 status-independent recheck 通过，修复后的独立
compression consumer 也通过执行、资源和生命周期检查；但是 compression 的 holdout
projection error 在 rank 512 仍约 0.9673，说明这批 response 不能作为 production
preconditioner 或完整 side inverse。第一次 compression 失败是 main 漏传 producer SHA 的
implementation failure，和后来的 compressibility negative 必须分开记录。

最高分类为 5NM_EXACT_SIDE_RESPONSE_AUTHORITY_AND_COMPRESSION_EVIDENCE。top、both-side、
full Hybrid、V10-5 modal cost model 和 0.7 nm PDE 均未运行。ordinary defaults 与 master
未改变。

compact 唯一数字源是
[task039_v10_side_response_packet_v1.json](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v10_side_response_packet_v1.json)；
阶段 outcome 是
[v10_side_response_packet.md](outcomes/v10_side_response_packet.md)。

## Review V10 §14：十二个问题

### 1. Inf/NaN 首先在哪条 factor/scatter/action 路径出现？

历史观测的首次非有限出现在 V9 combined-action output：SN2-J 输出 Inf、SN2-SGS 输出
NaN。这是 fixed two-layer supernode historical controlled numerical failure。V10-2 的
conventional、factor-only、scatter 边界和当前 combined action 均得到 finite 结果；
V10-6 producer/compression 的 tested output 也 finite。因此 V10 forensic 没有定位
conventional、factor-only、scatter 或 combined action 中的因果实现错误，根源仍为
not_established，不把它升级为通用 MUMPS 或 factor API bug。

### 2. 三个 principal supernodes 是否有可量化的 singular/near-resonance 证据？

V10-2 的三组 factor-integrity residual、ownership 和 cleanup 证据通过，但该阶段没有
产生可用于 principal supernode near-resonance 结论的独立 singular-value/condition
证据。答案是 not_established。V10-6 的 numerical rank 478 和 condition 5500.3434688
属于 960-column response packet，不是三组 supernode 的谱证据。

### 3. 零 RHS 在单块和组合路径上是否严格为零？

在已测试路径上是。V10-2 conventional/factor-only zero output norm 为 0；V10-3/V10-4
的 zero-map 也通过；V10-6 producer 的 physical-side-rhs 输出 finite、norm 0，compression
consumer 重算 zero-map 同样通过。physical zero 的 relative residual 是退化量，因此不
计入 mandatory residual；这不掩盖其 output finite/zero 的独立 Gate。这个结论限于已测
路径，不外推到未运行的 top/full。

### 4. 是否做了最小实现修复？修复前后 raw root 是什么？

factor forensic 本身没有“修复前/修复后 root”：V10-2 三条 conventional/factor-only/
scatter 边界路径均通过，旧 V9 非有限只在历史 combined-action output 观察到，不能凭空
补一个数值修复。另一条 Lane C response-packet 路线则确有可定位的 wiring/lifecycle
failure。成功 pilot 的 producer root 是
`results/task039_v10_h4_side_response_packet_pilot_producer_mpi8_a335ab52`，consumer root 是
`results/task039_v10_h4_side_response_packet_pilot_consumer_mpi8_a335ab52`。四个失败 producer
root 共享完整前缀 `results/task039_v10_h4_side_response_packet_pilot_producer_mpi8_`，
分别为 `e353d97d`（profile None / AttributeError）、`a7f237ae`（spool remap 缺 shard
descriptors）、`955466b3`（read-only response mapping）和 `d0353dec`（主体完成后 finalizer
telemetry KeyError）；四个 root 都保留，且未形成合格 pilot。随后 compression root
`results/task039_v10_h4_side_response_packet_compression_mpi8_5efc715a` 因 main 漏传 producer source SHA exit 2，才做了窄接线修复；修复后 source SHA
为 30b40d4303a1da90769557aee8d0f493c784591f，root 为
results/task039_v10_h4_side_response_packet_compression_mpi8_30b40d43，formal worker
exit 0。producer root、packet root 和所有前后 raw hashes 均绑定在 compact record 中。

### 5. J1 inner FGMRES 的 4/8/16/32 true residual 是什么？

V10-4 五个 mandatory RHS 的 0/4/8/16 true residual 如下；条件 32 未授权，不能把空值
写成 32 结果。

| RHS | 0 | 4 | 8 | 16 | 32 |
|---|---:|---:|---:|---:|---|
| modal traction positive | 1.0000000000 | 0.9978292301 | 0.9976800874 | 0.9971014671 | not_run |
| modal traction negative | 1.0000000000 | 0.9985402273 | 0.9983000205 | 0.9981152471 | not_run |
| external DtN coupling | 1.0000000000 | 0.9985105758 | 0.9981784041 | 0.9979895526 | not_run |
| fixed random repeat 0 | 1.0000000000 | 0.9995553367 | 0.9992101130 | 0.9989785112 | not_run |
| fixed random repeat 1 | 1.0000000000 | 0.9995393321 | 0.9992146644 | 0.9989849199 | not_run |

五个 RHS 没有达到统一 side Gate，preferred inner budget 不存在；32 没有运行。这是
V10-4 的 J1 numerical negative，不是本轮 response packet 的 residual。

### 6. 是否存在第一个通过的 bottom budget？

V10-4 没有。4、8、16 都没有同时满足五个 mandatory 的 side Gate，32 也没有获授权。
V10-6 的 producer 是 response authority，不是 inner FGMRES budget；因此不能用它填补
preferred inner budget。

### 7. top 与十列 modal cost model 是否运行？

没有。top、both-side、full Hybrid 和 V10-5 modal cost model 均 not_run；V10-4 没有统一
preferred budget，V10-6 的 holdout 只用于 compression generalization audit。

### 8. response-packet lane 是否激活？pilot/full 的 RSS、时间、payload、residual 如何？

已激活并完成最终 16-column pilot、961-column full producer 与独立 compression。pilot/full
必须分开报告：

| 阶段 | peak / swap | wall | payload / residual | 生命周期 |
|---|---|---|---|---|
| successful pilot producer | 43.20536804199219 GiB / 0 | solve 21.45196287811268 s；setup 2361.916216508951 s；projected full 3650.374736875594 s | actual 16-column payload 33868800 B；projected payload 2034244800 B；worst residual 1.0251447633580063e-10 | factor 1→0 |
| successful pilot consumer | 1.649871826171875 GiB / 0 | not_measured | packet released | factor/global 0/0 |
| full producer | 50.7548675537 GiB / 0 | measured 4390.176657 s | 960 modal residual finite；max 1.52248376596e-10；payload 2034244800 B | factor 1→0 |
| repaired compression | 15.4776763916 GiB / 0 | worker 236.720152 s；parent 约239.730152 s | one TSQR/SVD；holdout generalization negative | packet released；factor/global/nested 0/0/0 |

四个 pilot wiring/lifecycle roots 和第一次 compression SHA 透传 failure 都是 implementation
evidence，不是算法 positive；每个 root 的 raw hashes 见 compact record。

### 9. 最佳完整 workflow 是否仍是 80.025856018 GiB？

是。direct baseline 是 93.377006531 GiB，Lane A full 是
80.025856018 GiB，正式完整 workflow 节省 14.298113646%。V10-6 producer 的
50.7548675537 GiB 是 sequential component envelope，不能重新定义完整 workflow saving。

### 10. 20% 和 50% saving 的 blocker 是什么？

主要 blocker 是算法与 response generalization，而不是本次 compression 的内存执行：
V10-4 的 bare-F/J1 inner residual 没有达到 side Gate；V10-6 虽然 rank512 的训练
tail 已到 3.8908212468e-12，但 holdout 仍有四列约 0.9673。component RSS 不能替代 full
workflow evidence；因此 20% 和 50% tier 都未达到。

### 11. 哪些基础设施可复用，哪些只能 research-only，哪些不应提升？

Selective merge 应明确分三组：

| 分组 | 内容 | 边界 |
|---|---|---|
| reusable | owner-row packet manifest/hash/coverage/lifecycle 合同、流式 memmap writer、rank-deficient TSQR + small-R SVD 诊断、factor-integrity tiny fixtures | research infrastructure；不改变 ordinary solver/default |
| research-only | h4 exact response producer、16-column pilot、full packet、compression consumer | 依赖冻结 source/input/spool；不作为默认 PC 或完整 workflow |
| do-not-promote | 本次低秩 response basis、V8/V9 未通过 action、component RSS 到 full workflow 的推断 | 不进入 top、full Hybrid 或 0.7 nm solver |

owner-row packet 是可复用的 oracle/内存管线，但 exact-factor producer 与 holdout
generalization negative 使它不能直接外推为 0.7 nm solver。

### 12. top、both、full、0.7 nm 是否运行？

均未运行。V10-5 modal cost model、top、both-side、full Hybrid、其他 candidate 扫描和
0.7 nm PDE 都是 not_run，不应改写成失败。V7/V8/V9 的历史正负 evidence 与首次接线
失败仍保留；owner-row packet 的低内存管线也不能越过 exact-factor 与 holdout Gate
直接外推到 0.7 nm。

## 资源、身份与收口边界

producer 使用 60 GiB hard stop，compression 使用 30 GiB retained limit；两阶段 swap
均为 0。producer 的 full factor ready/cleanup 为 1→0，consumer factor/global/nested
为 0/0/0。PSS/USS 未测量。所有数值、shard hash、950 singular values、四级 rank
reports、10 列 holdout 数组和 raw artifact hashes 见 compact record。

V10-7 closeout itself only changed docs/evidence；不提交 raw artifacts，不运行 heavy/PDE/MPI。

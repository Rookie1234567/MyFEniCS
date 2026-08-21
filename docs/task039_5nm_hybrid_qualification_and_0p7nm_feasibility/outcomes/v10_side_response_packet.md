# V10-6：完整 side-response packet 与压缩性结论

## 先给结论

这一步把 bottom side operator 对 960 个 modal 输入的响应逐列写成 owner-row packet，再由独立
consumer 读取 packet 做低秩压缩。producer 的 exact response、资源和清理都通过；第一次
compression 尝试是明确的 SHA 透传接线失败，算法尚未开始；修复后 compression 的执行、内存
和生命周期通过，但响应本身并不具有足够的低秩可压缩性。

因此本阶段的最高分类为
5NM_EXACT_SIDE_RESPONSE_AUTHORITY_AND_COMPRESSION_EVIDENCE。它证明了一个可复核的
research-only response 数据管线，不证明压缩 basis 可以成为 production preconditioner，
也不打开 top、both-side 或 full Hybrid。

“owner-row”表示每个 MPI rank 只保存自己拥有的矩阵行；“TSQR”是先在各 rank 做 QR、再只
对小的 R 因子做全局合并，避免复制整个 132300 行响应矩阵。训练列用于构造 basis，holdout
列完全留出，用来检查 basis 对未参与训练的响应是否仍然有效。

## 身份与 provenance

| 项目 | 权威值 |
|---|---|
| compact schema | task039.v10.side_response_packet.v1 |
| producer source SHA | dbc5e9bfdf9ad0520881caa168c7a27316d50f10 |
| producer recheck source SHA | 5efc715a81049abcac94233ece51594b3b773d3c |
| compression source SHA | 30b40d4303a1da90769557aee8d0f493c784591f |
| full producer schema / method | task039.v10.h4.exact_side_response_packet.full.v1 / task039_v10_h4_side_response_packet_full_producer |
| compression schema / method | task039.v10.h4.exact_side_response_packet.compression.v1 / task039_v10_h4_side_response_packet_compression |
| input SHA256 | 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811 |
| physical model SHA256 | 8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c |
| resolved config SHA256 | f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883 |
| selected/exact spool manifest SHA256 | 2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067 |
| inherited frozen holdout catalog | 8 producer ranks、6 labels、96 response artifacts；catalog SHA256 a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384 |

完整 compact record（含 950 个 singular values、8 个 shard 描述和四级 holdout 数组）见
[task039_v10_side_response_packet_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v10_side_response_packet_v1.json)。
大矩阵、memmap、JSONL 和原始 worker 输出仍留在 ignored results，不进入 Git。

## Pilot 与历史 implementation failures

最终成功的 16-column pilot 也必须和 961-column full producer 分开看。pilot producer
使用 root results/task039_v10_h4_side_response_packet_pilot_producer_mpi8_a335ab52，
consumer 使用 root results/task039_v10_h4_side_response_packet_pilot_consumer_mpi8_a335ab52。

| pilot 项目 | 实测值 |
|---|---:|
| producer peak / swap | 46391410688 B = 43.20536804199219 GiB / 0 |
| 16-column worst true residual | 1.0251447633580063e-10 |
| pilot solve wall | 21.45196287811268 s |
| setup wall | 2361.916216508951 s |
| projected full 961-column wall | 3650.374736875594 s |
| projected full payload | 2034244800 B |
| actual 16-column packet payload | 33868800 B |
| producer factors | 1 → 0 |
| consumer peak / swap | 1771536384 B = 1.649871826171875 GiB / 0 |
| consumer factor/global/nested | 0/0/0；packet released |

四次 pilot implementation/lifecycle failure 都是 exit2、swap0，且没有形成合格 pilot；
root、source SHA、峰值和每个 root 的 raw file hashes 均在 compact record 中保留：

| root suffix | peak RSS | failure stage | 原因 |
|---|---:|---|---|
| e353d97d | 1.6369743347 GiB | pre-profile | profile None / AttributeError；明确未进入主体 |
| a7f237ae | 42.9734916687 GiB | spool-remap | fixed-budget spool remap 缺 shard descriptors；是否已开始数值算法 not_established |
| 955466b3 | 42.9833679199 GiB | response-map-readonly | assignment destination is read-only；response mapping 进度不作猜测 |
| d0353dec | 41.9813041687 GiB | finalizer-telemetry | 主体计算/packet 阶段已运行，随后 finalizer telemetry KeyError |

这些是 Lane C 的 wiring/lifecycle failures，不是 producer 数值 negative。之后的
compression root 5efc715a 另有 SHA 透传 implementation failure；修复后才得到本 outcome
中的 successful compression。

## Producer、接线失败与修复后的 compression

| 阶段 | 结果 | 关键实测 |
|---|---|---|
| full producer | PASS | 960 个 modal residual 全部 finite，最大 true residual 1.52248376596e-10，小于 1e-9；physical zero output norm 0 |
| producer resource | PASS | process-tree peak 50.7548675537 GiB，小于 60 GiB；wall 4390.176657 s；payload 2034244800 B；swap 0 |
| producer lifecycle | PASS | exact-side factor 1 → 0；global direct 0；packet 961 列写完后释放 |
| status-independent recheck | PASS | 15/15 checks true；保留旧 parent contract_mismatch 状态和原始 reason，不覆盖 raw |
| first compression attempt | IMPLEMENTATION_FAILURE | root 5efc715a；exit 2；peak 约 1.634716 GiB；swap 0；因 main 漏传 producer SHA，算法未开始 |
| repaired compression | execution/resource/lifecycle PASS | worker 236.720152 s；parent 约 239.730152 s；peak 15.4776763916 GiB，小于 30 GiB；swap 0；packet released；factor/global/nested KSP 0/0/0 |
| compressibility | FORMAL NEGATIVE | rank 512 仍有四列 projection error 约 0.9673，不能提升为 production basis |

第一次 compression root 和 traceback 保留原样；它是接线实现失败，不是数值结果。修复后的
consumer 使用 producer SHA 显式校验 manifest，且没有装配 PDE、system、factor、QEP 或
selected packet。

## 结构化分类

| evidence | classification | 是否允许 promotion |
|---|---|---|
| full producer | PASS | 只作为 exact response authority |
| 16-column pilot | PASS | 只作为 pilot/component evidence |
| compression execution/resource/lifecycle | PASS | 只作为 component execution evidence |
| compression generalization/compressibility | NEGATIVE | production_promotion_allowed=false |

最大 rank 的 effective rank 为 478，但 holdout indices 0、1、480、481 仍约有 0.9673
projection error；因此 top_full_advancement_allowed=false。算法执行通过不等于算法质量
通过，也不等于 production preconditioner 通过。

## Packet 分区与 owner-row evidence

正式 packet 是 132300 行、961 列的 complex128、Fortran-order owner-row shard：

| 分区 | 数量 |
|---|---:|
| nonzero modal columns | 960 |
| training columns | 950 |
| holdout columns | 10 |
| physical zero validation column | 960 |
| train/holdout | 冻结 0..959 的互斥并集 |
| shard 数 | 8 |
| coverage | exact |

holdout 固定为 0、1、240、267、479、480、481、720、746、959；physical zero 是第 960
列，不进入训练或 holdout。8 个 shard 的 global ownership ranges、shape、dtype、layout 和
file SHA256 全部写入 compact record；每个 rank 的 local hash 与 manifest 一致。

## Compression 方法与全局矩阵证据

consumer 只 mmap rank-local shard。它先做一次 owner-row TSQR，再对合并得到的小 R 做一次
SVD；没有使用 Gram matrix 或 normal equations。各 rank 的 Q block 与全局系数通过 MPI
规约组合，holdout projection 也是全局 projection，不是 rank-local 自证。

| 指标 | 实测值 |
|---|---:|
| singular values | 950 个，全部 finite |
| numerical rank | 478 |
| condition | 5500.34346880272，finite |
| SVD tolerance | 7.74997341977e-09 |
| TSQR reconstruction error | 1.19799109281e-14 |
| zero-map output | finite，norm 0，pass |
| one TSQR / one small-R SVD | true / true |

singular values 的完整 950 项数组在 compact JSON 中保存。首五项为
263.8153998896912、238.4944129972675、219.80581437232115、218.71335629338412、
203.49422294739955；末五项为 2.2784018948563284e-12、2.248172468418629e-12、
2.1388415901966705e-12、2.0785509480105793e-12、1.9100445209482403e-12。

## Rank ladder：训练误差与 holdout 误差

训练 optimal Frobenius error 是同一分解的 singular-value tail；holdout error 是每个
未参与训练的响应列独立投影后的真实相对误差。四级没有重新做四次 TSQR/SVD，而是切同一个
分解的 rank prefix。

| requested rank | effective rank | training optimal error | Q orthogonality error | worst holdout |
|---:|---:|---:|---:|---:|
| 64 | 64 | 0.5922391025 | 4.6010123806e-14 | 0.9999934115 |
| 128 | 128 | 0.3517745690 | 7.1836714191e-14 | 0.9999772293 |
| 256 | 256 | 0.1611181515 | 1.1424021162e-13 | 0.9676601222 |
| 512 | 478 | 3.8908212468e-12 | 1.6092009437e-13 | 0.9673241512 |

| holdout index | rank64 | rank128 | rank256 | rank512 |
|---:|---:|---:|---:|---:|
| 0 | 0.9999872240 | 0.9999772293 | 0.9673335421 | 0.9673241512 |
| 1 | 0.9999931094 | 0.9999191512 | 0.9673326450 | 0.9673236877 |
| 240 | 0.4347138582 | 0.0113945051 | 0.0089579889 | 1.4461398330e-11 |
| 267 | 0.1961827612 | 0.0020576042 | 8.8036850e-06 | 6.1136257629e-12 |
| 479 | 0.9988540780 | 0.9783766014 | 0.9676601222 | 1.0935706127e-10 |
| 480 | 0.9999845364 | 0.9999769483 | 0.9673335906 | 0.9673241335 |
| 481 | 0.9999934115 | 0.9999189081 | 0.9673325808 | 0.9673236766 |
| 720 | 0.8859612683 | 0.0185884831 | 0.0139252039 | 1.4030368309e-11 |
| 746 | 0.08066781499 | 0.0014738831 | 5.2974792e-06 | 4.0724605e-12 |
| 959 | 0.9995786529 | 0.9881361461 | 0.9661375968 | 1.2652438067e-10 |

最大 rank 仍有四个响应列 0、1、480、481 的误差约 0.9673。这说明训练 singular-value
tail 很小并不等于未见 response 的 projection 误差很小；本次 packet family 对 holdout
generalization 不足。

## 内存、时间与边界

producer 的 50.7548675537 GiB 是 sequential component envelope，不是完整 workflow 的
节省率。完整 workflow 的唯一正式低于 direct authority 仍是 Lane A full：
direct 93.377006531 GiB，Lane A full 80.025856018 GiB，节省 14.298113646%。V10-6
component 的低 RSS 不能替代这个完整 workflow authority；20% 和 50% tier 都没有达到。

compression construction 不适用，retained interval 为 15.4776763916 GiB，30 GiB Gate
通过；PSS/USS 没有测量。producer 与 compression 都是 bottom research component，不能
据此宣称 0.7 nm PDE 或 full Hybrid 可行。

top、both-side、full Hybrid、V10-5 production promotion、modal cost model 和 0.7 nm PDE
均 not_run。owner-row packet 可以作为复用的 response oracle/内存管线，但 exact-factor
producer 与 holdout generalization 的 negative evidence 使它不能直接外推为 0.7 nm solver。
ordinary defaults、master 和历史 V7/V9 negative records 未改变。

## Selective merge 边界

| 分组 | 可保留内容 | 边界 |
|---|---|---|
| reusable infrastructure | owner-row writer/loader、manifest/hash/coverage/lifecycle 合同、rank-deficient TSQR 与 small-R SVD 诊断 | 作为 research infrastructure，不改变普通 solver |
| research-only | h4 exact response producer、16-column pilot、full packet、compression consumer | 依赖当前 source/input/spool identity；不作为默认 PC |
| do-not-promote | 本次低秩 response basis、V8/V9 未通过 action、component RSS 到 full workflow 的推断 | 不进入 top、full Hybrid 或 0.7 nm solver |

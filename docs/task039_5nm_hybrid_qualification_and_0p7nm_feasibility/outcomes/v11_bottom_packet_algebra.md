# V11-1 bottom response-packet algebra audit

## 结论

本阶段是一次正式的、只读的 bottom response-packet algebra component audit。response packet 把每个冻结 modal source 对应的 bottom response 作为列保存；本审计用 fresh action system 检查这些列是否仍满足原方程、Schur 组合和 V7 canonical bottom trace。它不是完整 Hybrid solve，也没有创建 factor、KSP 或 QEP。

结论为 **formal algebra negative / controlled stop**。这不是 implementation failure、内存失败，也不是完整 Hybrid solve 失败。V11-1 Gate 失败后，V11-2 至 V11-7 依赖路线全部停止并记为 not_run。

| 项目 | 实测值 | Gate/状态 |
|---|---:|---|
| 960 列 metadata identity/order/provenance/provider/layout | exact | pass |
| physical RHS equation | 0.0 | pass；degenerate zero |
| independent zero-map output norm | 0.0 | pass |
| 10 sampled AX=source 最大相对误差 | 700.7944864636039 | `<=1e-9` fail |
| packet Schur contribution relative error | 132.34347758005742 | `<=5e-9` fail |
| modal-amplitude action relative error | 132.34347758005742 | `<=5e-9` fail；与 Schur 同一量的明确 alias |
| V7 bottom trace relative error | 31.80044571619504 | `<=5e-9` fail |
| V7 active-trace round trip 最大绝对误差/相对误差 | 3.2616290216610626e-17 / 2.29546617364909e-16 | pass |
| block/Schur/trace action count | 12 / 960 / 1 | measured |

### 十个 sampled columns

冻结列为 0、1、240、267、479、480、481、720、746、959。对应 AX=source 相对误差按列为：

| column | relative error |
|---:|---:|
| 0 | 311.7597565148893 |
| 1 | 318.0894412830888 |
| 240 | 254.2009324008069 |
| 267 | 362.3046447112934 |
| 479 | 700.7944864636039 |
| 480 | 312.81546813720075 |
| 481 | 318.0915956668195 |
| 720 | 255.4528074577953 |
| 746 | 365.3019145318697 |
| 959 | 685.8676762741122 |

这十列是数值 source-action 检查；其余 950 列参加 streamed Schur action，但没有被表述为逐列重新计算了 source equation。

## 身份、生命周期和资源

正式 root 为 `results/task039_v11_h4_bottom_packet_algebra_mpi8_677ab26d`，源码 SHA 为 `677ab26dcfef79f0f754b88f2cfb8832edac4285`。冻结 input、selected packet、response packet、exact-spool provenance 和 V7 authority 的路径与 hashes 见 [compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v11_bottom_packet_algebra_v1.json)。

system、packet、projection 和 selected provider/context 均在结束时释放；packet destroy 已调用，factor/KSP/QEP 为 0/0/0，PDE 为 not_run。sign contract 本身通过，但这不是允许手工翻符号的理由；本轮没有翻 sign、改 normalization 或重跑 packet。

projection 阶段使用 `row_flush_then_final`，没有 materialize trace mass matrix，使用 reusable form action；canonical negative trace 的 peak-live count 为 1，返回后的 retained count 为 0。过程树峰值为 13,723,365,376 B = 12.7808799744 GiB，swap=0，wall 约 655.209 s；45 GiB hard stop 没有触发。

此前 7bd981d4/8fba71ba 阶段的 45.277 GiB 与后续 projection 内存受控停止 raw 仍保留。row-flush 和 streamed resource fixes 只说明本阶段的 projection implementation blocker 已解除；当前代数 Gate 失败，不能据 12.7808799744 GiB 宣称 solver 或 packet 正确。

## 原始证据

compact record 绑定 diagnostic、raw markers、memory stages、ledger、run summary、run manifest 及 identity files 的 SHA256；raw 目录 ignored，未提交。V11 后续路线不是“算法失败”，而是因本阶段 Gate 失败而未运行。

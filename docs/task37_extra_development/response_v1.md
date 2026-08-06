# Task037-extra G0 response v1

## 本轮回答

| 问题 | 回答 |
|---|---|
| 1. 是否复现 M3a MPI1 identity 和安全内存范围？ | 是。唯一 M3a MPI1 screen20 的 watchdog screen pass，source SHA 为 568f1ac189f98227541722b1de66cd7804e0cc80；process-tree RSS authority peak 为 6.259979248046875 GiB，swap 为 0，低于 10/14 GiB warning/terminate 线。solver 不是收敛：20 步后为 DIVERGED_MAX_IT (-3)，postprocess skipped，不能称 official RTA。 |
| 2. residual snapshot 能否按 canonical global row identity 导出？ | 能。iter0 和 iter20 各有 51192 rows，身份为 active_trace_residual_global_row，按 ascending active-row global ID；rank ownership 不参与 identity。只保证本次 canonical global-row identity，未宣称 repartition-invariant numbering。 |
| 3. hardest/control slab 是什么？ | 本轮审阅切片选择 slab14 为 primary：iter20 local residual 0.4272314396194324、ILU rho 1.2604899530937426、B4 rho 0.7558186834062683。slab5 为 control：0.16307530842059187 / 1.247711710628995 / 0.8512896925857695；slab2 是 upper-median comparator。slab14 的 ILU ablation damage 为 -0.14960520299020064，但最大正 damage 是 slab13 的 +0.038332237714445494，因此不存在单一无歧义排名。 |
| 4. current trace ILU 与 B4 GMRES(4) 差多少？ | 在同一 iter20 residual 上，global ILU rho 为 1.3887891254775173，global partition-weighted B4 rho 为 0.7836817168192864，B4 低约 0.6051074086582309。iter0 对应值为 2.445965881188012 与 0.9556993251952722。这些是一次 stationary apply contraction oracle，不是外层 FGMRES 收敛结论。 |
| 5. 是否具备进入 one-slab full-space identity 的前置条件？ | 仅具备进入一块 slab full-space identity 实现/验证准备（G2.2）的证据；尚未实现或证明全局 candidate、minimum contraction、full solve 或 production promotion。 |

## 运行与数值边界

本轮只运行一次 Case101：M3A overlap 0.125、partition interpolation、MPI1、screen20；global A/F 未物化，global direct factor count 为 0，stored factor NNZ 为 91,415,952。watchdog pass 只说明身份、因子、有限 residual 和资源安全 screen 通过。

active-trace residual 是把近似解代回 condensed 方程后剩下的 dual/load 误差 r=b-Ax，不是物理场 coefficient。true residual 为：

| iteration | true residual |
|---:|---:|
| 0 | 1.0 |
| 10 | 0.14446444295860594 |
| 20 | 0.04474243612765 |

iter0/20 snapshot manifest、canonical hash 和 rank shard hash 已写入 compact authority record；iter10 没有 raw vector。compact record 同时把零 local residual 的 ILU/B4 rho 写成 null，因为该比值无定义；原始旧 artifact 的 0.0 只作为 provenance，不代表完美收缩。

## 负结果与未运行项

- solver 在 20 步上限达到 DIVERGED_MAX_IT (-3)，所以没有 official field output、RTA 或物理结论。
- B2 i2500、M3A iter100/late、B4 iter20/100/200 的 raw vectors 在当前 checkout 不可得，均标记 pending/not_available；没有从 scalar residual 伪造 vector。
- 没有运行 full、B2-2500、独立 B4 campaign、G1/G2 full-space/LOR-HX、G3 或任何第二次 PDE。

## evidence

- compact authority：benchmarks/cases/101_task37_extra_development/records/g0_authority.json
- ignored raw run directory：benchmarks/artifacts/101_task37_extra_development/
- raw hashes、snapshot hashes、资源 authority 和 contraction arrays：见 compact record
- 本轮语义修正：零 local residual 的 ILU/B4 rho 返回 None，不再以 tiny denominator 产生 0.0

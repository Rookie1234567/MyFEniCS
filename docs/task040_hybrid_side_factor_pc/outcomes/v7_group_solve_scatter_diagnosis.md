# V7 group solve / scatter 诊断

本页把“每个 group 的局部解是否稳定”和“四个贡献合并时是否稳定”分开。两层都通过 raw
checker 的证据合同，但没有因此成为 production qualification。

## Layer A：group solve

三尺度、三个 deterministic source 共用三组已建立 factor。每个 group 对同一个
`A_IGamma*x_Gamma` 连续 solve 两次，记录 `rhs_norm`、两次 solution norm、solve
count before/after/delta、factor identity 和 backward terms。checker 重算的最大 relative 值如下。
backward 的独立 Gate 是 `1e-10`，solve-repeat 的独立 Gate 是 `1e-11`；两者不是同一个阈值：

| scale | backward relative max | backward Gate ≤1e-10 | solve-repeat relative max | solve-repeat Gate ≤1e-11 |
|---|---:|:---:|---:|:---:|
| `2^-10` | `1.8694367572622566e-13` | PASS | `2.7937730047529037e-14` | PASS |
| `1` | `2.616388896859513e-13` | PASS | `3.009963464523332e-14` | PASS |
| `2^10` | `2.5893256268097257e-13` | PASS | `4.848802691567973e-13` | PASS |

因此 `group_refinement_trigger=false`。本阶段没有执行一次 group refinement；该布尔值不是
缺少 refinement 的替代证据。

## Layer B：四个独立贡献

四个 caller-owned canonical contribution 依固定顺序写入独立目标，再按
`+middle_boundary - middle_correction - lower_correction - upper_correction` 合成。最大
Layer B repeat 为 `1.0113286276645048e-14`，最大 linearity 为
`1.9760809450364223e-13`；每项 finite，未发现局部 contribution instability。

## Layer C：D0/D1 合并

D0 与固定顺序 D1 都独立和 full elimination 交叉比较。D0/D1 identity relative 最大值分别
为 `2.685834896609515e-14`、`2.6174083534938076e-14`；D0/D1 之间 eta 最大
`2.773231975131262e-14`。三尺度的 Layer C linearity 最大值分别为
`2.7968651487346226e-14` 和 `2.9707308811271427e-14`。D0、D1 candidate 都为 true，
selected candidate 是 `d0_lower_memory`；D1 没有偷用 D0。

结构方面，canonical coverage、15120 joint rows、owner distribution、factor ready=3、
per-apply scratch=0、numeric allgather=false 和 full-interface replica=false 均按 raw
结构字段审计。`partition_audit_trigger=false` 是 checker 的条件路由结果；本轮没有执行
独立 separator closure audit，不能把它写成 separator pass。

证据来源为：
`/home/fenics/Projects/MyFEniCS/results/task040_v7_scale_normalized_identity_mpi8_e7fee3c2_native/worker/rank0000/v7_scale_normalized_identity_bundle.json`。
logical raw/checker SHA 分别为
`a2aa1a72655bb695d663ec2c67b33115409715c75c0513e7b8fdf04d26bb59c6` /
`768d094726ff6d458906885fe2ef602edbcdb13e9e20ceb2e008b8fc081193a4`。

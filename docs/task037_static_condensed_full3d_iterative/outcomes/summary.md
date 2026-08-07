# Task037 V7 结果总览

## 结果总表

| 路线 | 结果 | 状态 |
|---|---|---|
| E0 Matrix-free DtN | 80/80 modes，primary C/D `0/0`，global A/F `false/false` | pass；component Gate |
| M3a iterative | MPI1/2/4/8 full solve 通过；MPI4 final official result true | explicit opt-in research baseline |
| canonical active/full | relative L2 `1.2553897989392794e-06` / `7.880394014572244e-07` | both pass at `1e-5` |
| F | frozen ideal-capacity oracle negative | closed |
| E | E1 basis pass；E2 late residual `6/6` fail | closed research candidate |
| A/B2/B4/C/D/R7-p4 | negative、plateau、partial 或 closed | 不生产化 |
| E3–E5 | 未运行 | `not_run` |

## 数值与资源

| E0 指标 | 值 |
|---|---:|
| action / recovery max | `1.2367630350859273e-15` / `1.1141146096537195e-15` |
| RHS identity / oracle | `0` / `1/1` |
| wall / peak / swap | `304.9213732070057 s` / `0.662296 GiB` / `0` |

| M3a MPI | peak GiB | wall s | status |
|---:|---:|---:|---|
| 1 | 4.600 | 1999 | pass |
| 2 | 5.683 | 1153 | pass |
| 4 | 8.266 | 712 | pass |
| 8 | 12.593 | 471 | pass |

M3a final MPI4 的 residual 为：reported=`9.923273221632137e-07`、
condensed=`9.923273222042328e-07`、full-augmented=`9.923273222042328e-07`、
full-FE=`9.923273521134805e-07`，KSP 为
`CONVERGED_RTOL/365`，12/12 powers 与 12/12 amplitudes 通过；
`R=0.0007628813414780547`、`T=0.6027016365247433`、
`A_volume=0.396535483656842`、closure=`1.0000000015230635`。
coarse dimension 为 75，16 slabs，overlap=`0.125`，coarse condition estimate/number
为 `4754.709602715809`，
global factor=`0`。约 `91.4M` p6 local factor NNZ 使它成为研究基线，而不是
`0.7 nm` scalable qualification。

```math
A_{\mathrm{condensed}} = F - C H^{-1}D
```

## Canonical evidence

| 空间 | manifest SHA256 | common | missing/extra/duplicate | relative L2 |
|---|---|---:|---:|---:|
| active | `e01458aa9380276fa02522ca230e5a913e654e71e7c22a73211634feda389d23` | 60402 | `0/0/0` | `1.2553897989392794e-06` |
| full | `095c19eeae37bed2b605e54d0247e034376f50f36fb016329827b6ea3bb6b004` | 173802 | `0/0/0` | `7.880394014572244e-07` |

两者均在 `relative_tolerance=1e-5` 下通过。比较使用 canonical entity identity，
不把不同 MPI partition 的 ownership-order 当作跨运行 global row identity。

## 测试与 provenance

| Gate | 结果 |
|---|---|
| serial targeted | `85 passed / 7 skipped` |
| MPI2 targeted | 每 rank `58 passed / 2 skipped` |
| MPI4 targeted | 每 rank `9 passed / 1 skipped` |
| small smoke | assembled 与 action-only 各 `1 passed` |
| telemetry patch | serial `8 passed`；MPI2 每 rank `1 passed` |
| full pytest 唯一一次 | `849 passed, 48 skipped, 3 failed`，`1115.51s` |
| 后续最小闭环 | test53 最终 `3 passed/223.86s`；test69 `3 passed/0.25s` |

full pytest 原始结果保持为 exit=1，不伪装成全套 PASS；后续失败均已由最小
合同/历史对象闭环处理，未修改 production 数值代码或 test69。

最终数值 SHA 为 `0fcf08a3f09e3beb137212d41f411823cb2e24e8`。reviewed source 为
`d8b16c349f7726b4873ce1932668c12a1ba78926`；V7 review commit 为
`229aaf743072550fa07bb0f03f9c4104e6a25d63`，V7.1 handoff commit 为
`d8b16c349f7726b4873ce1932668c12a1ba78926`。

## Evidence index

- [response_v7.md](../response_v7.md)
- [review_report_v7.md](../review_report_v7.md)
- [review_report_v7_1_task37b_remote_handoff.md](../review_report_v7_1_task37b_remote_handoff.md)
- [Case100 README](../../../benchmarks/cases/100_static_condensed_full3d_iterative/README.md)
- [direct authority record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_direct_authority_v2.json)
- [M3a scaling record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_m3a_mpi_scaling_v1.json)
- [E2 closeout record](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_v6_e2_modal_capacity_closeout_v1.json)

Task037 已结项。A–F/E negative evidence 保留为 research evidence，ordinary defaults
保持不变；本 docs commit 形成时 Task37b 尚未创建，只有 master 成功 push 后才按
V7.1 创建并 push，且不开发。

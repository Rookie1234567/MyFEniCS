# V3-2：二维 TE 参考网格收敛

本阶段用二维 TE `2d_port`/DtN 求解建立离散参考比较。单个算例的 own Gate 只验证残差、DtN 原始证据、43 个唯一阶和 selected field；相邻 pair Gate 才判断网格是否足够接近。

## 最终判定

冻结合同要求连续两对相邻网格全部通过。`h2↔h1.5` 六项全部通过，但 `h4↔h3` 与 `h3↔h2` 失败。因此 P1 未建立，本阶段为：

`V3_2D_CONTROLLED_STOP_REFERENCE_NOT_YET_QUALIFIED`

V3-3 至 V3-10 为 `not_run_by_gate`，h1 为 `not_run_by_contract`。h1.5 的单对通过不能被称为 P1 或连续参考。

## 五个 own authority

五个 run 均 `exit_status=0 / worker_exit0`；43 行唯一、top `-19..0`、bottom `-19..-1`、selected shape `(7,40)`、swap=0。closure 限值 `1e-8`，reduced linear residual 限值 `1e-9`。RSS/PSS/USS 为 launcher 进程树峰值，单位 MiB。

| 网格 | R | T | A_balance | A_volume | closure | residual | cells / DoFs / rows | NNZ / reduced NNZ | time (s) | RSS / PSS / USS |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| h5 | 0.746419642 | 0.000214172 | 0.253366186 | 0.253366183 | -3.18923e-9 | 3.36858e-13 | 336 / 12337 / 12337 | 785569 / 783936 | 2.05243 | 407.535 / 386.299 / 374.023 |
| h4 | 0.734167797 | 0.000221496 | 0.265610707 | 0.265610703 | -3.26440e-9 | 4.86920e-13 | 540 / 19747 / 19747 | 1261729 / 1259640 | 2.78751 | 509.336 / 488.116 / 475.859 |
| h3 | 0.732675416 | 0.000222867 | 0.267101717 | 0.267101713 | -3.29457e-9 | 6.76069e-13 | 882 / 32155 / 32155 | 2057377 / 2054592 | 4.03689 | 666.012 / 644.689 / 632.340 |
| h2 | 0.732589429 | 0.000222932 | 0.267187639 | 0.267187636 | -3.29571e-9 | 1.71095e-12 | 1890 / 68623 / 68623 | 4409761 / 4405752 | 12.23782 | 1261.859 / 1240.614 / 1228.344 |
| h1.5 | 0.732588692 | 0.000222932 | 0.267188376 | 0.267188373 | -3.29558e-9 | 3.93459e-12 | 3420 / 123907 / 123907 | 7976689 / 7971264 | 31.45525 | 2420.512 / 2399.134 / 2386.758 |

## Pair Gate

每格为 `actual / limit / pass`。scalar 是四个 R/T/A 量的最大绝对差；primary 是 11 个 `max(power)>=1e-6` 传播行的最大相对功率差；weighted 使用全部 top/bottom 43 行；H 是拼接 Hx、Hz 的 relative L2。

| pair | scalar | closure | primary power | weighted power | E | H concat | overall |
|---|---:|---:|---:|---:|---:|---:|---:|
| h5↔h4 | 1.22518e-2 / 1e-6 / FAIL | 3.26440e-9 / 1e-8 / PASS | 5.40494e-1 / 1e-4 / FAIL | 1.64832e-2 / 1e-5 / FAIL | 2.49268e-2 / 1e-3 / FAIL | 2.44913e-2 / 2e-3 / FAIL | FAIL |
| h4↔h3 | 1.49238e-3 / 1e-6 / FAIL | 3.29457e-9 / 1e-8 / PASS | 6.40047e-3 / 1e-4 / FAIL | 2.04230e-3 / 1e-5 / FAIL | 2.57557e-3 / 1e-3 / FAIL | 4.14171e-3 / 2e-3 / FAIL | FAIL |
| h3↔h2 | 8.59871e-5 / 1e-6 / FAIL | 3.29571e-9 / 1e-8 / PASS | 2.93539e-4 / 1e-4 / FAIL | 1.17862e-4 / 1e-5 / FAIL | 2.16862e-4 / 1e-3 / PASS | 7.21615e-4 / 2e-3 / PASS | FAIL |
| h2↔h1.5 | 7.37055e-7 / 1e-6 / PASS | 3.29571e-9 / 1e-8 / PASS | 2.51575e-6 / 1e-4 / PASS | 1.01040e-6 / 1e-5 / PASS | 9.06950e-6 / 1e-3 / PASS | 6.13807e-5 / 2e-3 / PASS | PASS |

所有 pair 坐标 exact，primary count=11；完整 43 行和 Hx/Hz 分量保留在 ignored comparison JSON：

| pair | raw comparison path / SHA256 |
|---|---|
| h5↔h4 | `results/task039_5nm_v3_1deg_s5/pair_convergence/h5_vs_h4.json` / `5f774570a2ea836675b5d2bb22bcfbb5568e5f47af5ee594f0a359e64cfb2b26` |
| h4↔h3 | `results/task039_5nm_v3_1deg_s5/pair_convergence/h4_vs_h3.json` / `57e25761b79cf37622256cf8394a9dec96af7abeca8cbb6aa26804eaba59df7a` |
| h3↔h2 | `results/task039_5nm_v3_1deg_s5/pair_convergence/h3_vs_h2.json` / `3337e3e526ea8896a321f1cccffdc5eeb2b1647fdc0ff75fdeb5b4cc1d8d6e34` |
| h2↔h1.5 | `results/task039_5nm_v3_1deg_s5/pair_convergence/h2_vs_h1p5.json` / `2c9c6dbbf0488f17c8e8130d212910d73ac62ca9529da6b9b5db73dba788825d` |

## 失败记录与身份

首次 h5 run `results/task039_5nm_v3_1deg_s5/task039_v3_2d_te_p6h5_direct_mpi1__2d_port__mpi1__Mna/20260815T004009.820115Z` 原样保留。它的首次 checker 假失败来自内存 complex `alpha` 与 JSON `[real, imag]` 的表示差异，不是数值失败；窄修提交 `020d14585a9ab824f96bb9610cf32fc9a0d08b13` 只比较正式 raw contract 字段。

h5/h4 的 run source SHA 为 `020d1458...`，h3/h2/h1.5 为 `768a535c...`。后者是 checker-only 后继，没有 solver/config 数值路径变化；该身份差异只记录，不作为 convergence Gate。

紧凑证据见 [task039_v3_2d_te_reference_funnel_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_2d_te_reference_funnel_v1.json)，checker 与测试见 [pair checker](../../../benchmarks/task039_2d_pair_convergence.py) 和 [test_281](../../../src/test/test_281_task039_v3_2d_pair_convergence.py)。

```math
P_{\mathrm{weighted}} =
\frac{\sum_k |p_{L,k}-p_{R,k}|}
{\max(\sum_k \max(p_{L,k},p_{R,k}),10^{-30})}.
```

该阶段只完成二维离线收敛取证；没有把任何未运行或未通过项提升为物理资格结论。

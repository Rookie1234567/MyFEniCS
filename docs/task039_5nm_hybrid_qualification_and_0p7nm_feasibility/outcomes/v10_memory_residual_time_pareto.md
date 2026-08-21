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

V10-4 的 five-RHS FGMRES 没有达到 `r<=1e-2`，所以不能拿 `22.0071983337 GiB` 作为 full-workflow saving，也不能进入 V10-5。其后置 response-packet pilot（V10-6）尚未运行；下一步只按授权实现代码和 focused tests，先不启动 pilot。

## 口径提醒

```math
\text{full-workflow saving} \ne \text{component RSS reduction}.
```

Lane A full 相对 direct 的RSS下降是已测完整 workflow 结果；V10-4 只是一次 bottom side component 诊断。PSS/USS 在本次 V10-4 raw 中 `not_measured`，不能从 RSS 推断。所有 raw root 与大型 JSONL/ledger 均为 ignored local artifacts，compact evidence 只提交 hash-bound 元数据。

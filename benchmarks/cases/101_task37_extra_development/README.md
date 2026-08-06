# Case101：Task037-extra G0 最小 screen

Case101 只定义本轮的一个受限运行：Task037 M3a overlap `0.125`、partition
插值、MPI1、screen20，并显式启用
`--task037-extra-g0-diagnostics`。它不是 Case100 历史 full-solve 证据，也不
产生 official RTA。

固定运行约束：

- p6/h10/S、`assembly_time_static_condensed`、`--task037-m2c-never-materialized`；
- `poll=0.25` s、warning `10` GiB、terminate `14` GiB、timeout `1800` s；
- 不使用 `--allow-swap`，因此要求 zero swap；
- source SHA 在运行时取本次 implementation 的 `git rev-parse HEAD`，并同时传给
  `--verified-clean-sha`；preflight 文件及其 SHA256 固定为 config 中的值。

G0 只保留 true residual `b-Ax` 的 iter0/iter20 snapshot，按 active-row global
ID 升序写 canonical residual manifest；同时记录 16 个 slab 的 local residual、
current trace ILU、B4 fixed GMRES(4)、global one-apply、ablation、fixed
two-step 和完整 M3a two-level contraction 字段。raw snapshot、timeline 和
其他大型输出必须留在 ignored artifact 目录；`records/` 不预置占位文件。

`expected.json` 只列本轮实际 Gate：identity、factor inventory、有限 residual、
snapshot iterations、canonical manifest、16 slab metrics、contraction 字段、
zero swap 和 `<14 GiB` 内存。它不填本机运行后的百分比或 scalar 结论。

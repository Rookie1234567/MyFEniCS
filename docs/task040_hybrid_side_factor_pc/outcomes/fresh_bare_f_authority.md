# V5-2 fresh current-layout bare-F authority

## 当前状态

`FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED`。这是“部分完成后资源/执行窗口停止”，不是
operator identity 失败，也不是 bare-F numerical residual 失败。正式 root 原样保留：

```text
results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41
source = fd7bea41d7d7b7869dd3ade4407129b00900ef7d
```

## 已完成与未完成的 producer inventory

| 项目 | raw observed |
|---|---|
| one-cell source factor | construction `1`、apply `2`、RHS columns solved `4`；实际生命周期 `1→0`，并在 full-side setup 前销毁 |
| current-layout outputs | 五个 current-layout RHS 及 owner-sharded canonical/`Gamma_L`/`Gamma_U` layout 已写出 |
| full-side bare-F factor | 只到 `v5_bare_f_factor_setup_begin`；没有 factor-ready；full-side factor `1→0` 未完成 |
| exact outputs / residual | exact-output packets `0`；bare-F residual 未运行 |

## 实测边界

| 项目 | 实测值/状态 |
|---|---|
| authorized wall window | `21600 s`；factor construction 阶段耗尽 |
| process-tree RSS peak | `45432283136 B`（约 `42.31 GiB`） |
| preferred / warning / hard | `59055800320 B`（55 GiB）/ `62277025792 B`（58 GiB）/ `68719476736 B`（64 GiB） |
| swap authority | readable，`0` |
| factor-ready / exact packet | factor-ready 未出现；exact-output packets `0` |
| QEP / PDE | `0` / `not_run` |
| classification reason | `authorized 21600s wall/resource window exhausted during factor construction` |

该 root 的 one-cell source factor 已完成并清理，但没有通过 full-side `factor-ready`、完整
`1→0`、exact packet 或 bare-F residual Gate。peak 未越过 55/58/64 GiB，也不能把它改写为
64 GiB hard stop或 current operator 数值失败；wall window 到期时的 OS 清理不能冒充 PETSc
factor lifecycle 通过。它触发了 Review V5 的 Route C fallback。Route C 另在 fresh process
中运行，没有读取该失败 root 的 exact factor。

## 约束与后续

V5-2 的范围是 bottom-only current-layout bare `F` 诊断 authority；不能进入 production
side inverse。由于 Route C 后续得到 `ROUTE_C_NO_SIGNAL`，bounded rank、packet-independent
rebuild、Level B、bottom/top/both-side、full Hybrid、h3 和 0.7 nm PDE 均为
`not_run_by_route_c_no_signal_and_resource_authority_gate`。

历史失败 root 不覆盖、不删除；本页只记录其真实执行窗口和资源口径。

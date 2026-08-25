# V11 S4：LOR-edge geometric multigrid 小型 oracle

## 结论

S4 的 16 个小案例和 8 个 MPI1/MPI2 identity pair 均通过了原 aggregate checker。这里的“通过”只表示固定 p2/p3 oracle 在小网格上的 transfer、PC、残差和跨 MPI 证据闭合；它不是 p6 solver、物理 Maxwell 或 production default 的通过证明。该 aggregate 只授权进入 S5 容量审计。

| 项目 | 结果 |
|---|---|
| aggregate checker | `passed=true`，`contract_errors=[]`，`gate_failures=[]` |
| individual cases | 16/16；每案 `rho < 1e-8` |
| MPI identity pairs | 8/8；provenance 与 dynamic action bound 均通过 |
| process-tree resource | 最大 `286,695,424 B`，所有 swap `0 B` |
| p2/method | `p2 -> 1`，fixed right GMRES/restart20，均 60 步 |
| p3/method | `p3 -> 1`，fixed right GMRES/restart20，按 source 完成 1,880–2,960 步 |
| scope | small-case oracle only；不等于 p6、PDE 或 physical pass |

## 不可变 aggregate 身份

本文件与两个 compact JSON 是对既有 aggregate checker 的确定性摘要；没有重跑任何 case，也没有修改或重分类历史 aggregate。

| evidence | path | SHA256 |
|---|---|---|
| 原 aggregate checker | `benchmarks/artifacts/task038_extra_full3d_lor_edge_geometric_mg_v1/2b2df645418ee28c68681832661e58993897166d/aggregate_check.json` | `56b7eec1435abc69a38c38af056d8803e8f62a3ff6768b87faa594670c916c4e` |
| S4 compact manifest | `outcomes/records/lor_edge_geometric_mg_oracle_v1.json` | `5d132e21915c1a3fb1fa9af0c1fe3a4b711005b8bdedac08e04ee56b96b1cfb6` |
| S4 compact checker摘要 | `outcomes/records/lor_edge_geometric_mg_oracle_v1_checker.json` | `8e2b552fbc773bda94d2605a5a8184e1d3ee35929964e84903a80c1fa39bb38b` |

前四个 p2-MPI1 案例来自源码 `ca5171ac3bd6dd6ab333619cd76fd771524520e6`；其余 12 案来自 `2b2df645418ee28c68681832661e58993897166d`。后一个 SHA 的变更只修复了 watchdog 的 MPI launch 生命周期，aggregate checker 仍按固定 input/operator/physical identity 和 dynamic action bound 接受；它没有改变 transfer、operator 或数值参数。

## 16 个 individual case

`rho` 是 checker 从每案 raw evidence 绑定的最终 explicit true residual；`peak` 是外部 process-tree watchdog 的峰值。

| 顺序 | case/source | source SHA | iterations | rho | peak (B) | swap (B) |
|---:|---|---|---:|---:|---:|---:|
| 1 | p2-mpi1/random | `ca5171ac…` | 60 | 3.9948626309604484e-9 | 141017088 | 0 |
| 2 | p2-mpi1/gradient | `ca5171ac…` | 60 | 3.25310382535185e-10 | 141168640 | 0 |
| 3 | p2-mpi1/curl | `ca5171ac…` | 60 | 5.091224143942273e-10 | 141119488 | 0 |
| 4 | p2-mpi1/checkerboard | `ca5171ac…` | 60 | 3.417129297272225e-09 | 140943360 | 0 |
| 5 | p2-mpi2/random | `2b2df645…` | 60 | 4.136064677452021e-09 | 264179712 | 0 |
| 6 | p2-mpi2/gradient | `2b2df645…` | 60 | 3.2856679620394e-10 | 264032256 | 0 |
| 7 | p2-mpi2/curl | `2b2df645…` | 60 | 5.130698689690218e-10 | 263917568 | 0 |
| 8 | p2-mpi2/checkerboard | `2b2df645…` | 60 | 3.5462840455740654e-9 | 264196096 | 0 |
| 9 | p3-mpi1/random | `2b2df645…` | 2000 | 9.891883798422905e-9 | 154349568 | 0 |
| 10 | p3-mpi1/gradient | `2b2df645…` | 2220 | 9.58588584878323e-9 | 154468352 | 0 |
| 11 | p3-mpi1/curl | `2b2df645…` | 2560 | 8.8655645455621e-9 | 154873856 | 0 |
| 12 | p3-mpi1/checkerboard | `2b2df645…` | 2340 | 9.074003354422413e-9 | 154214400 | 0 |
| 13 | p3-mpi2/random | `2b2df645…` | 1880 | 9.933358713345764e-9 | 286695424 | 0 |
| 14 | p3-mpi2/gradient | `2b2df645…` | 2500 | 9.372360341341475e-9 | 284643328 | 0 |
| 15 | p3-mpi2/curl | `2b2df645…` | 2960 | 9.844698995593758e-9 | 286298112 | 0 |
| 16 | p3-mpi2/checkerboard | `2b2df645…` | 2220 | 9.618468797692642e-9 | 285081600 | 0 |

## 8 个 MPI identity pair

pair 的 `action_relative` 与 `dynamic_bound = rho1 + rho2 + rhs_identity + 1e-11` 均来自原 aggregate；没有在 S6 重新计算或放宽 bound。

| degree/source | action relative | dynamic bound | source identity | rhs identity | within bound |
|---|---:|---:|---:|---:|---|
| p2/random | 2.512321637167716e-10 | 8.140928911410351e-9 | 1.417734557397384e-15 | 1.6029978812022376e-15 | true |
| p2/gradient | 1.7451358685706666e-11 | 6.638781571460329e-10 | 1.6222171816489272e-15 | 9.78406907963663e-16 | true |
| p2/curl | 1.6756996927993017e-11 | 1.03219372628878e-9 | 2.042338716606187e-15 | 1.4429255308456253e-15 | true |
| p2/checkerboard | 4.95713542420865e-10 | 6.9734159863653165e-9 | 7.0527624724249594e-15 | 2.6435190265449354e-15 | true |
| p3/random | 4.232191972635982e-9 | 1.9835245347849893e-8 | 8.077695473723443e-16 | 2.8360812222556585e-15 | true |
| p3/gradient | 3.743015643432162e-9 | 1.8968248421847413e-8 | 1.1440074370323148e-15 | 2.2317227056883823e-15 | true |
| p3/curl | 2.7952571609978787e-9 | 1.8720267106040988e-8 | 7.797108724221802e-16 | 3.564885129170979e-15 | true |
| p3/checkerboard | 3.299275674528969e-9 | 1.8702484256395807e-8 | 3.1905695505564654e-15 | 1.2104280752274292e-14 | true |

## 边界

S4 的结果说明固定小型 LOR-edge oracle 在这些 p2/p3 cases 上闭合，但不能外推 p6/h10。S5 随后以 fresh source/root 执行容量审计；S5 的 6→3 energy Gate 失败后，S6 停止，不再启动任何 S4 修复、p6 physical Maxwell、p6/h5 或 0.7 nm PDE。

保留的旧历史事实包括 Q0 500-step negative、foundation-E 3020-step PASS、旧 global spectral audit controlled negative、HX/PCGAMG closed，以及所有此前启动失败 root。它们不被本文件覆盖。

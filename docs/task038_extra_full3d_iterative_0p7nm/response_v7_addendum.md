# Review V7 补充：additive-v2 small qualification hard stop

本补充记录用户授权的唯一 additive HX v2 小型 qualification campaign。它不是新的 review，也不改写既有 `response_v7.md`、L2 negative、K0 evidence 或 ignored raw campaign。

## 1. 结论

| 项目 | 事实 |
|---|---|
| 路线 | 独立 Krylov-based additive HX v2；不是第三个变体 |
| source SHA | `cc042c26aefcf6aab659c4d41e09f46d3bf71aba` |
| formal scope | p2/h50，四个 source，MPI1/MPI2；按固定 K1 suite 顺序运行 |
| 已完成 | 5 案：4 个 PASS，1 个真实 numerical Gate FAIL |
| 停止分类 | `SMALL_MPI2_KRYLOV_ROBUSTNESS_FAILURE` |
| 路线状态 | `ADDITIVE_LOR_HX_ROUTE_FORMALLY_CLOSED` |
| 未运行 | 其余 11 案、aggregate、MPI identity、p3、L3/L4/L5、p6、PDE、official physics |

通俗地说，additive-v2 把同一个原始残差分别送入六个固定校正，再把六个结果直接相加。MPI1 的四个 source 在80步内达到目标，但同一 p2 random source 在 MPI2 的并行路径到第200步仍未达到目标，因此不能把四个 MPI1 结果合并解释成整条路线通过。

本轮首个 additive-v2 authority 已通过；随后按冻结顺序运行到 `p2-mpi2/random`。该案 checker 独立重算 `contract_errors=[]`，但有唯一数值 Gate failure：

| stop Gate | 实际值 | 限值 |
|---|---:|---:|
| explicit true residual at iter 80 | `5.890364694544531e-4` | `1e-8` |
| explicit true residual at iter 200 | `4.380523556760784e-6` | 仅趋势，不可补救80步 Gate |

因此不再启动后续 case，不进行参数扫描、restart 调整或第三变体。

## 2. 不可变的旧结论

- 旧 L2 one-apply authority `rho=1.7348663090876784 > 0.45` 仍是永久 `FAIL`，本轮不重分类。
- 旧 K0/K1 v1 evidence 和首次 additive authority raw 保持原样。
- 先前 small qualification v1 的历史结论保持：MPI1 random 在第58步通过，而 MPI2 到第196步才通过；其80步 Gate 仍为 FAIL，旧证据不覆盖。
- 本轮 additive-v2 的 one-apply `rho` 全部只是 diagnostic，不与旧 L2 rho 混用，也没有进入生产 PC。

## 3. additive-v2 定义与实现边界

冻结的算子是

```text
z = J(r)
  + G M_n^{-1} G^H(r)
  + Pi_x M_n^{-1} Pi_x^H(r)
  + Pi_y M_n^{-1} Pi_y^H(r)
  + Pi_z M_n^{-1} Pi_z^H(r)
  + J(r)
```

六项都读取同一个原始 residual `r`，不使用前一项更新后的 residual；两次 edge Jacobi、一次 gradient 和三个方向校正均保持冻结。omega 为 `2/3`，所有 nodal correction 共用一个既有 scalar PCGAMG hierarchy，每项恰好一次 V-cycle。B0、transfer、source、GMRES 设置均未改动。

实现和测试绑定 source commit `cc042c26aefcf6aab659c4d41e09f46d3bf71aba`。本次 closeout 没有修改 solver、runner、checker 或参数；只复制证据并新增本文件与 campaign compact。

实现阶段已确认的测试事实为：focused serial 共 `50 passed, 2 skipped`（对应 `src/test/test_295_task038_lor_hx.py` 与 `src/test/test_299_task038_lor_hx_krylov_suite.py` 的已记录 focused invocation）；actual MPI2 additive smoke 为每个 rank `1 passed, 7 deselected`；随后 `test_299_task038_lor_hx_krylov_suite.py` 为 `13 passed`。`compileall` 和 `git diff --check` 通过；ruff 在当前环境不可用且未安装。本次 closeout 只做 JSON、hash、路径和 diff 机械核验，不声称未确认的测试或 CI。

## 4. 已完成案

| case/source | checker | first true pass | final true residual | iter/reason | matvec/PC/monitor | one-apply rho |
|---|---|---:|---:|---:|---:|---:|
| p2-mpi1/random | PASS | 76 | `9.370522115232511e-09` | 76 / 2 | 76 / 153 / 77 | `5.276736888140158` |
| p2-mpi1/gradient | PASS | 65 | `7.93951495726592e-09` | 65 / 2 | 65 / 131 / 66 | `4.929390658112743` |
| p2-mpi1/curl | PASS | 75 | `8.468921524678114e-09` | 75 / 2 | 75 / 151 / 76 | `5.518241470360782` |
| p2-mpi1/checkerboard | PASS | 76 | `9.538193917617094e-09` | 76 / 2 | 76 / 153 / 77 | `4.14150869540027` |
| p2-mpi2/random | FAIL | — | `4.380523556760784e-06` | 200 / -3 | 202 / 403 / 201 | `5.246445407250461` |

五案均记录 `finite=true`、`repeat_relative=0`、`input_unchanged=true`。失败案的完整 0..200 explicit true-residual history保存在 worker record，并在 campaign compact 中保留；通过案的完整 history 仍在各自 worker record 中。关键 checkpoint 如下：

五个 worker 均 `rc=0` 自然写出事实；四个通过案 checker `rc=0`，失败案 checker `rc=1` 且只有上述数值 Gate failure。

| case/source | iter 0 | iter 1 | iter 2 | iter 5 | iter 10 | iter 20 | iter 40 | iter 80 | iter 200 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| p2-mpi1/random | 1 | `2.6303e-1` | `1.0535e-1` | `3.3841e-2` | `9.3013e-3` | `1.2220e-3` | `1.9166e-5` | not run after convergence | not run after convergence |
| p2-mpi1/gradient | 1 | `2.0333e-1` | `6.6399e-2` | `1.8807e-2` | `4.2468e-3` | `2.1768e-4` | `1.9436e-6` | not run after convergence | not run after convergence |
| p2-mpi1/curl | 1 | `2.5763e-1` | `1.2953e-1` | `4.4735e-2` | `1.1482e-2` | `1.2001e-3` | `1.5523e-5` | not run after convergence | not run after convergence |
| p2-mpi1/checkerboard | 1 | `2.2475e-1` | `9.7147e-2` | `1.9692e-2` | `8.6538e-3` | `9.7584e-4` | `1.2328e-5` | not run after convergence | not run after convergence |
| p2-mpi2/random | 1 | `4.8763e-1` | `4.1175e-1` | `1.6560e-1` | `7.1795e-2` | `4.2968e-2` | `1.6447e-2` | `5.890364694544531e-4` | `4.380523556760784e-6` |

## 5. 资源口径

资源来自 `/usr/bin/time -v`。这些是单 MPI1 worker 或 MPI2 launcher 的 GNU time 观察值，不是 process-tree/cgroup authority，也不是完整 setup 的2GB证明。

| case/source | wall | max RSS | swap |
|---|---:|---:|---:|
| p2-mpi1/random | 11.65 s | 128,307,200 B | 0 |
| p2-mpi1/gradient | 9.96 s | 126,775,296 B | 0 |
| p2-mpi1/curl | 10.86 s | 126,509,056 B | 0 |
| p2-mpi1/checkerboard | 11.04 s | 127,156,224 B | 0 |
| p2-mpi2/random | 14.69 s | 125,886,464 B | 0 |

上述资源事实不能宣称2GB setup Gate通过：本轮没有运行 p6 setup，也没有形成 N2/L3 的完整生命周期、process-tree 或 cgroup 资格证据。

## 6. 证据索引

原始 ignored campaign 永久保留于：

```text
benchmarks/artifacts/task038_extra_full3d_lor_hx_krylov_pc_additive_v2/cc042c26aefcf6aab659c4d41e09f46d3bf71aba/
```

tracked record/check 副本和汇总 compact 位于：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/
```

具体文件前缀为 `lor_native_complex_hx_krylov_pc_additive_v2_`，包含 `p2_mpi1_random`、`p2_mpi1_gradient`、`p2_mpi1_curl`、`p2_mpi1_checkerboard`、`p2_mpi2_random` 及对应 `_check`；campaign 汇总为 `lor_native_complex_hx_krylov_pc_additive_v2_campaign_v1.json`。每份副本都已与 ignored source 逐字节 hash 核对，compact 同时绑定 worker record、checker、GNU time、marker 和 raw manifest SHA256。

## 7. 关闭范围与 selective merge

本次准确关闭的是 small MPI2 Krylov robustness lane，不是“4/5 通过所以整体通过”。以下项目均为 `not_run` 或 `not_run_by_gate`：剩余11案、aggregate MPI identity、p3、L3、L4 exact-A、L5 20/100/150/200、p6、2GB setup qualification、PDE、official physics。

新 additive-v2 lane 只保留为 research evidence / `do-not-merge`。不得把它提升为 ordinary production default，也不建议用参数扫描、restart 或其它未授权变体绕过失败；若未来继续，必须由新的 review 明确开启新的算法族。FC3、Candidate A/B/C、trace-harmonic 及其它已关闭 family 保持 `do-not-merge`，不整体合并本分支。

## 8. 本次 closeout 状态

- 本轮只做证据副本、campaign compact 和本 addendum；没有运行新的测试、formal case 或 PDE。
- JSON parse、record/check/hash 闭合、Markdown 路径检查和 `git diff --check` 已完成。
- formal source commit 为 `cc042c26aefcf6aab659c4d41e09f46d3bf71aba`；当前 worktree 有且仅有12个预期新增 closure 文件，因此尚未 clean。本轮不 commit、不 push。

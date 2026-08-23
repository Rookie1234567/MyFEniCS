# L2：native-complex LOR-HX positive oracle

## 结论

L2 验证的是一个正定辅助算子上的一次预条件应用：它用低阶、细化的 H(curl) 辅助空间近似高阶正定算子 `B_h`。通俗地说，`rho` 衡量一次修正后残差还剩多少；越小表示一次修正越有效。本阶段不是物理 Maxwell 算子，不包含 DtN、散射、R/T/A 或 PDE 结果。

本次实际只执行到 `p2/h50/MPI1` 首案。首个冻结 source `random` 的一次应用超过固定 contraction Gate，worker 按合同停止后续 source 和 CG。该结论是 L2 的真实数值负结果，不是本次已核对出的 ABI、JIT 或 worker 生命周期故障。

| 项目 | 事实 |
|---|---|
| L2 source SHA | `91992c0ac3aa467f74955fa7da944a10da8f0fbb` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| case | `p2-mpi1` |
| runner rc | `0`；事实 record 已写出 |
| checker rc | `1`；独立 checker 真实负裁决 |
| record status | `facts_written_not_qualified` |
| aggregate | `passed=false`, `hard_stop=true`, `contract_errors=[]` |
| L2 classification | `CONTROLLED_NEGATIVE_BY_POSITIVE_AUXILIARY_CONTRACTION_GATE` |

## 冻结命令与数值结果

```bash
python -m benchmarks.run_task038_full3d_lor_hx --stage l2 --case p2-mpi1 \
  --raw-dir benchmarks/artifacts/task038_extra_full3d_lor_hx_l2_v1/91992c0/p2-mpi1 \
  --record docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_native_complex_hx_oracle_p2_mpi1_v1.json \
  --expected-source-sha 91992c0ac3aa467f74955fa7da944a10da8f0fbb \
  --expected-mpi-size 1
python -m benchmarks.task038_full3d_lor_hx_checker --stage l2 \
  --record docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_native_complex_hx_oracle_p2_mpi1_v1.json \
  --output docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_native_complex_hx_oracle_v1.json
```

| source / fact | measured value | frozen limit / status |
|---|---:|---:|
| `random` rho | `1.7348663090876784` | `<= 0.45`，**FAIL** |
| random residual norm | `583.0377018610059` | finite |
| finite | `true` | pass |
| input unchanged | `true` | pass |
| repeated PC output relative | `0.0` | `<= 1e-13`，pass |
| phase | `algebraic_slave_zero_action_internal_finalized_mpc_once` | exact contract，pass |
| `gradient` / `curl` / `checkerboard` | 未测 | `not_run_by_gate` |
| fixed CG (`rtol=1e-8`, `max_it=40`) | 未启动 | `not_run_by_gate` |

独立 checker 从 canonical residual 与 applied output 重算
`true_residual = residual - applied_output` 和 `rho`，得到上表数值；没有使用 worker 写入的 rho 或 status 覆盖重算结果。

## fixture audit 快照边界

record 中的 `fixture_audit.hx_audit` 是 fixture 构造时写入的结构快照，不是本次 source apply 完成后的动态状态。其动态字段仍为：

| 字段 | record 值 | 解释 |
|---|---:|---|
| `apply_count` | `0` | 构造快照未在 apply 后刷新 |
| `last_nodal_correction_count` | `0` | 构造快照未在 apply 后刷新 |
| `last_output_finite` | `false` | 构造快照未在 apply 后刷新 |

这些字段属于 `non-authoritative stale diagnostic snapshot`，不是 checker 或 static-PC 结构合同的权威来源；不能据此声称本次没有执行 apply。真实执行由 `l2_source_random` marker、`pc_output`/`applied_output`/`true_residual` canonical raw 以及 checker 独立 rho 重算共同证明。该快照边界不改变本次数值 Gate，也不为此重跑已触发 hard stop 的 formal。

## Marker、资源与证据

实际 marker 顺序为：

```text
paths_ready
→ source_identity_closed
→ runtime_identity
→ fixture_built
→ l2_source_random
→ canonical_packets_gathered
→ record_written
```

资源数字来自本次 `/usr/bin/time -v` 的单进程辅助观察，不是 Review 的 process-tree qualification：

| 口径 | 值 | 边界 |
|---|---:|---|
| wall | `2.12 s` | `/usr/bin/time -v` |
| maximum resident set | `134468 KiB = 137,695,232 B` | 单进程观察 |
| swap | `0` | 单进程观察 |
| process-tree `<2 GB` | 未作 L2 Gate 声明 | 本阶段不以该单进程值替代 process-tree authority |

| evidence | 路径 | SHA256 |
|---|---|---|
| worker record | [`lor_native_complex_hx_oracle_p2_mpi1_v1.json`](</home/shenjh/Projects/MyFEniCSx_task37_extra/docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_native_complex_hx_oracle_p2_mpi1_v1.json>) | `0a6ccfdb6a28b003167046e3ca3fc5e4de0d40825784786319661901a65389f3` |
| checker aggregate | [`lor_native_complex_hx_oracle_v1.json`](</home/shenjh/Projects/MyFEniCSx_task37_extra/docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_native_complex_hx_oracle_v1.json>) | `eaea740a3b379066204f9b4055e217718305a708d912cc2cdd9ba72339672f50` |
| ignored raw root | `benchmarks/artifacts/task038_extra_full3d_lor_hx_l2_v1/91992c0/p2-mpi1` | 14 canonical `.npy` files + marker ledger |
| marker ledger | `stage-rank0.jsonl` | `571abce21302801d236cc4410f7a809553628b79fb69964af65af30f781f984b` |

Raw canonical hashes（同名组共享相同 key hash时仍按实际文件语义列出）：

| 文件组 | bytes | SHA256 |
|---|---:|---|
| `source_before_keys`, `source_after_keys`, `pc_output_keys`, `pc_repeat_keys` | `253056` each | `cf3b1fa144f896e2433e5365b5542f0952efdc16f021d539d01add5a4e70595d` |
| `source_before_values`, `source_after_values` | `15936` each | `591abf95704315e327fed60692a8a9d955b8c077b1619f1dbf40e34bf149c907` |
| `pc_output_values`, `pc_repeat_values` | `15936` each | `e7bfb86e8ae195bc582491f7ef3a71754467b8c4751f816e15bb2a1df4a3dd2e` |
| `residual_keys`, `applied_output_keys`, `true_residual_keys` | `196736` each | `34cb6d7a2411a22e6cdcf39e70525ea061e85f1d44383b21dff00272932bec3d` |
| `residual_values` | `12416` | `00472db041de47a35bd03002a593dbe5a093a71c6bced647974feef12a43a580` |
| `applied_output_values` | `12416` | `82c0543f2ca3ae59394f2bea4570d945240ae6ee20034301962b98fe952f8b15` |
| `true_residual_values` | `12416` | `030457993ef8cde38cf2ca48bc795ec7e4980031e0cd82df380267d16d92bdbf` |

Raw 只保留在 ignored artifact root；numeric root gather 是 evidence-only，record 的 production audit 仍为 `numeric_allgather=false`、`global_transfer_matrix=false`、`high_order_global_aij=false`、`global_direct_coarse=false`、`physical_action=false`。

## 根因边界与后续

L1 已正式通过 transfer/de Rham、orientation、Floquet/MPC、owner routing 和 MPI identity。L2 本次已经闭合的范围是：qualified ABI、fixture 构造、canonical artifact 角色与 finite 检查、输入不变、重复一致性、独立 checker 重算和 contract 审核。需要同时披露：`fixture_audit.hx_audit` 的动态字段是上面的 `non-authoritative stale diagnostic snapshot`；它不影响 `contract_errors=[]` 或独立 rho 裁决，也不能被当作数值 Gate 原因。

正式证明的最小结论是：冻结的复合 `M_H^{-1}` 对首个 `random` positive source 没有满足一次 contraction Gate。此前开发诊断把现象解释为高低阶谱缩放/提升后的过校正，这只是与开发观察一致的推断，不是本次 formal 直接测量的根因。不得据此在本轮调 `omega`、加 shift、缩放或扫描参数。

| 后续 case / 阶段 | 状态 |
|---|---|
| `p2-mpi2` | `not_run_by_gate` |
| `p3-mpi1` | `not_run_by_gate` |
| `p3-mpi2` | `not_run_by_gate` |
| L3 p6/h10 setup | `not_run_by_L2_gate` |
| L4 exact-A contraction | `not_run_by_L2_gate` |
| L5 20/100/150/200 screen | `not_run_by_L2_gate` |

## 测试边界

此前实现收口事实保留如下：`31 passed in 424.05s`（包含 test294/test295/test297），随后针对最新 runner/checker 改动的 test295 为 `13 passed`；compileall 与 `git diff --check` 通过。首次 synthetic test 为 `12 passed / 1 failed`，失败是测试中 CG residual 同步的局部 bug，修复后为 `13 passed`，不是 formal 数值失败。formal 本轮没有重跑 pytest。

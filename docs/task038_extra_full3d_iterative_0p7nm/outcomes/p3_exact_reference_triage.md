# V10 Q0：p3 exact-reference triage closeout

## 结论先行

Q0 在固定的 p3/h50、MPI1、random、positive high-order `B_H` 上实际执行到两套小规模诊断参考：

| 参考 | 作用 | 实测结论 |
|---|---|---|
| Reference E | 把高阶 dual residual 送到 LOR edge、做 exact `B_L` edge solve，再送回高阶 primal correction | exact edge 代数通过，但 500 步后的 explicit true residual rho=`4.203423379090078e-4`，超过 `1e-8` |
| Reference N | 保留 frozen multiplicative-v1 的 edge Jacobi、gradient、`Pi_x/Pi_y/Pi_z` 顺序，只把四个 nodal solve 换成 exact direct solve | direct nodal algebra通过；最终 rho=`2.1958595524302254e-3` 仅作 diagnostic；`edge_jacobi_pre` 的一项 evidence composition 为 `2.8019257502717445` |

因此按 Review V10 §4.4，Q0 的 formal 分类是：

```text
LOR_AUXILIARY_FOUNDATION_FAIL
```

E 的失败独立于 N 的 evidence 表示问题；不重跑 Q0，不进入 Q1–Q5，也不把 N diagnostic 改写成通过。

## 方法和为什么停止

这里的“exact reference”是一个小模型诊断：用 PETSc `PREONLY+LU/MUMPS` 直接解辅助 LOR 矩阵，暂时替代近似预条件器，观察问题是否来自 LOR 基础代数。它不是生产 PC，也没有改变 `NativeComplexLORHX`、omega、GAMG、transfer、Floquet/MPC 或 GMRES 参数。

外层求解固定为 right-preconditioned GMRES、restart=20、每20步 residual replacement、最多500步；每个20步周期销毁 KSP/basis，并用 explicit unpreconditioned true residual 作为权威。E 在 25 个周期后到达 500 步，仍为：

```text
rho = 4.203423379090078e-4 > 1e-8
```

这说明即使 LOR edge inverse 换成 exact direct solve，当前高阶到 LOR 再回高阶的复合路线在这个 p3 anchor 上也没有达到 Q0 的收敛要求。它不是内存、swap、ABI 或生命周期失败。

## 代数与合法性事实

| 指标 | Reference E | Reference N |
|---|---:|---:|
| exact direct residual | `9.13154427545479e-16` | gradient `5.241317476841507e-16`；Pi_x `5.162059150282312e-16`；Pi_y `5.134041203635995e-16`；Pi_z `5.209957454888207e-16` |
| outer iterations | 500 | 500 |
| cycles | 25 | 25 |
| matvec / PC applies | 524 / 525 | 524 / 525 |
| KSP destroy count | 25 | 25 |
| final explicit residual rho | `4.203423379090078e-4` | `2.1958595524302254e-3`（diagnostic） |
| finite | `true` | `true` |
| input unchanged | `0.0` | `0.0` |
| repeat relative | `0.0` | `0.0` |
| high primal constraint | `0.0` | `0.0` |

另有 `high_rhs_repeat_relative=0.0`、source unchanged relative=`0.0`、owner inventory 相等、orientation consistency=`true`、phase=`finalized_floquet_mpc_once`。canonical component hashes 已在 record 的 `component_hashes` 和 `route_audit` 中逐项绑定。

矩阵事实为：edge `3018×3018`、102,368 NNZ，index bytes=421,548、numeric bytes=1,637,888；node `1120×1120`、32,844 NNZ，index bytes=135,860、numeric bytes=525,504。production audit 保持 `high_order_global_aij=false`、`global_transfer_matrix=false`、`global_numeric_allgather=false`、`production_pc_direct_factor_applied=false`。

## N composition 的只读根因审计

checker 的原始 Gate 是：

```text
||stored_remaining - (stored_n_low_input - stored_edge_action)||
    / ||stored_n_low_input||
= 2.8019257502717445
```

raw 数值复核如下：

| packet | norm |
|---|---:|
| `n_low_input` | `730.0973355673666` |
| `n_edge_jacobi_pre_remaining` | `1197.8581513891497` |
| `n_edge_jacobi_pre_edge_action` | `2108.19431364797` |
| `n_edge_jacobi_pre_result` / `edge_delta` | `376.8775259972526` |
| `remaining + edge_action`（由 trace packet 推出的 inferred/derived 重编码初值） | `2758.242171099465` |

五组 packet 的 key 集合完全相同。现有 raw 没有单独保存经过 `low_dual_owner_packet` 重编码后的初始 `n_low_input`。因此 `remaining + edge_action` 只是由两个 trace packet 推出的 inferred/derived re-encoded initial；它与自身比较为 `0.0` 是定义性闭合，不是独立 raw 初值验证。该 inferred 值与直接保存的 `n_low_input` 相对差为 `2.8019257502717445`，最大逐项绝对差为 `422.0200003255364`。因此本次可复核边界是 evidence representation mismatch：

1. `low_input_from_high_dual` 在 `src/solvers/fullspace_lor_hx_root_cause.py:573-578` 返回高阶 dual restriction 的原 owner packet，同时构造 raw low vector。
2. runner 在 `benchmarks/run_task038_full3d_lor_hx_q0.py:478-480` 用 raw low vector 进入 replay，但在 `:570-584` 将 `n_low_input` 写成原 owner packet。
3. trace 的 `remaining` 和 `edge_action` 在 runner 的 `:572-574` 以 `dual` 类型保存，经过 `low_dual_owner_packet`（`fullspace_lor_hx_root_cause.py:581-622`）的 raw low `Tt_apply` 和 owner additive re-encoding。
4. replay 本身在 `fullspace_lor_hx_root_cause.py:494-510` 从 raw low residual 初始化 remaining，并在 `:507-519` 用 edge action 更新它；raw 允许计算出 trace packet 的 derived `remaining + edge_action` 与 inferred initial 相对差为 `0.0`，但这不是独立 replay PASS 证据。
5. checker 在 `task038_full3d_lor_hx_q0_checker.py:569-598` 将两种表示当作同一坐标相减，产生该 Gate failure。

所以，`2.8019257502717445` 是 checker 记录的真实原始失败事实；当前证据足以把 checker failure 定位为 packet 坐标混用，但不独立证明整个 N replay PASS。checker FAIL 原样保留；该判断不改变 E 的 `4.203423379090078e-4` hard stop；本轮不修改 checker 或 numerical path。

## formal 身份、路径偏差与资源

| 项目 | 事实 |
|---|---|
| source SHA | `47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| ABI | Python 3.12.3；PETSc 3.19.6；DOLFINx 0.10.0.post2；Basix 0.10.0；SLEPc 3.19.2；complex128/int32 |
| threads | MKL/OMP/OPENBLAS 均为 `1` |
| record/checker contract | `contract_errors=[]`；worker rc=0；checker rc=1 |
| cycle process-tree diagnostic | 最大记录 RSS=`185102336 B`；swap=`0`；status readable |
| `/usr/bin/time -v` | wall=`3:41.69`；Maximum resident set size=`293908 KiB`；Swaps=`0`；这是单 worker 口径，不是 cgroup/process-tree 峰值 |

实际 worker 使用了不含 `full3d` 的路径：

```text
raw:    benchmarks/artifacts/task038_extra3d_q0_v10/47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f/p3-mpi1/random
record: docs/task038_extra3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1.json
```

worker 和 checker 完成后，两份 compact JSON 做了 byte-preserving relocation 到正式任务目录；JSON 内部的 `command`、`record_path`、`raw_dir` 保持实际调用路径，未假称原始 worker 写入了正确路径，也没有因为 relocation 重新分类。

| relocated evidence | SHA256 |
|---|---|
| `outcomes/records/p3_exact_reference_triage_v1.json` | `2d767143ce3b28ac9a4b45962faf370770e1e637f05b4f0b62bb279fe7f6ca82` |
| `outcomes/records/p3_exact_reference_triage_v1_checker.json` | `be70e0e559fea32023dfde58e4ede11009574c18f51e4b914d9b5034832a35ea` |
| raw `stage-rank0.jsonl` | `0af96262408061ba37cf107fc3df7bd99329680ad1f13b33a5a964240e22d16c` |
| raw deterministic manifest（147 files） | `028e29553c3325fafd2001bde0cfb4711326a960735f79c862fd3f70fe13493f` |

## 后续状态与旧结论

| 阶段 | 状态 | 原因 |
|---|---|---|
| Q1 p3 50,000-step eventual convergence | `not_run_by_Q0_hard_stop` | Reference E 未达到 Q0 residual Gate |
| Q2 p6/h10 setup-only | `not_run_by_Q0_hard_stop` | Review V10 Q2 的启动前提是 Q0 Reference E PASS；本次未满足，因此不启动 |
| Q3 route decision | `controlled_stop_by_Q0` | 实际触发 `LOR_AUXILIARY_FOUNDATION_FAIL` |
| Q4 p6 positive | `not_run_by_Q0_hard_stop` | Q0 hard stop |
| Q5 physical Maxwell MPI1 | `not_run_by_Q0_hard_stop` | Q0 hard stop |

V8 M0 negative、orientation fix、scalar owner debt、old L2 one-apply FAIL、old 80-step v1 FAIL、additive-v2 CLOSED，以及 V9 P0 PASS 均原样保留。没有 0.7 nm full PDE、2 TiB complete-workflow、p6 physical、MPI2 physical 或 official physics 结果；本次 Q0 的约185 MB cycle RSS 不能外推为 p6/h10 或 2 TiB 可行性。

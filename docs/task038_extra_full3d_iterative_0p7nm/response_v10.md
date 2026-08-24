# Task038-extra Review V10 Q6 closeout

## 结论先行

本轮 V10 Q0 实际只执行到 p3/h50、MPI1、random 的 exact-reference triage。Reference E 用 exact LOR edge direct solve 代替近似 edge auxiliary solve；direct algebra residual 通过，但冻结的 right GMRES/restart20/residual-replacement/500-step诊断后，explicit true residual rho 为 `4.203423379090078e-4 > 1e-8`。

按 Review V10 §4.4，当前 LOR auxiliary foundation 分类为 `LOR_AUXILIARY_FOUNDATION_FAIL`，因此停止 Q0，Q1–Q5 均为 `not_run_by_Q0_hard_stop`。N 的 `2.8019257502717445` 经 raw/code 审计确认是 evidence packet 坐标混用；它不把 N 改成 PASS，也不改变 E 的独立 hard stop。

## 1. 身份、环境和实际命令

| 字段 | 实际事实 |
|---|---|
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| formal source SHA | `47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f` |
| base / origin-master merge-base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| upstream | `origin/codex/20260820-task38-extra-full3d-iterative-0p7nm` at pre-run `9d946e2f409f1dff60638f6f2963923973e6daeb` |
| ahead/behind | `1/0`；这是 formal 结束、Q6 提交前的 measured snapshot，不是最终 closeout 状态 |
| worktree | formal 运行后未再改 Python；当前未提交项只有 Q6 docs/compact；code-only commit 已包含三个 Q0 Python harness/checker/test 文件 |
| ABI | qualified activation=1；Python 3.12.3；PETSc 3.19.6；DOLFINx 0.10.0.post2；Basix 0.10.0；SLEPc 3.19.2；complex128/int32 |
| threads | `MKL_NUM_THREADS=1`、`OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1` |

本 V10 code-only commit `47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f` 实际新增并提交了 Q0 runner、独立 checker 和 focused test；它们是 research benchmark harness/checker/test，不是 production numerical core。production numerical core 与 ordinary default 未改。最终代码验证为：Q0 focused `7 passed`；旧 `test300`+`test302` M0/P1 回归 `26 passed`；compileall、AST 和 `git diff --check` 通过；Ruff 在资格化环境不可用且未安装。Q6 阶段只修改 docs/compact，没有重跑 pytest。

实际 worker 命令是：

```text
source scripts/activate_myfenics_wsl.sh && python -m benchmarks.run_task038_full3d_lor_hx_q0 --stage q0 --case p3-mpi1 --raw-dir benchmarks/artifacts/task038_extra3d_q0_v10/47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f/p3-mpi1/random --record docs/task038_extra3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1.json --expected-source-sha 47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f --expected-mpi-size 1
```

独立 checker 命令是：

```text
source scripts/activate_myfenics_wsl.sh && python -m benchmarks.task038_full3d_lor_hx_q0_checker --record docs/task038_extra3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1.json --output docs/task038_extra3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1_checker.json --expected-source-sha 47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f
```

worker 自然退出 `rc=0`；checker `rc=1`，`contract_errors=[]`，不是 runner/lifecycle/ABI 异常。marker 顺序为：`paths_ready → source_identity_closed → runtime_identity → fixture_built → source_built → reference_e_built → reference_n_built → outer_e_built → outer_n_built → canonical_packets_gathered → rank_metadata_collect_enter → rank_metadata_collect_exit → record_build_begin/end → record_encode_begin/end → record_write_begin/end → record_written`。

### 路径抄写错误和 byte-preserving relocation

V10 正确任务目录前缀含 `full3d`，但本次实际 command 误用了 `benchmarks/artifacts/task038_extra3d_q0_v10/...` 与 `docs/task038_extra3d_iterative_0p7nm/...`。raw 数值目录没有移动、删除、覆盖或改写。worker/checker 完成后，两份 compact JSON 从错误 docs 目录 byte-preserving relocation 到：

```text
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1.json
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/p3_exact_reference_triage_v1_checker.json
```

迁移前后 SHA 完全相同；JSON 内 command、record_path、raw_dir 仍忠实保留实际 formal 路径，没有重新运行 checker，也没有因目标路径改变分类。

## 2. Q0 measured/derived 结果

“exact reference”是用小模型 direct LU/MUMPS 解辅助矩阵，检查近似预条件器之外的基础路径。它只属于 Q0 诊断，未进入 production PC、Q1、Q2 或 ordinary default。

| 指标 | Reference E | Reference N |
|---|---:|---:|
| direct algebra residual | `9.13154427545479e-16` | gradient `5.241317476841507e-16`；Pi_x `5.162059150282312e-16`；Pi_y `5.134041203635995e-16`；Pi_z `5.209957454888207e-16` |
| outer cycles / iterations | `25 / 500` | `25 / 500` |
| matvec / PC applies | `524 / 525` | `524 / 525` |
| KSP destroys | `25` | `25` |
| final explicit true residual rho | `4.203423379090078e-4` | `2.1958595524302254e-3`，diagnostic only |
| finite / repeat / input unchanged | `true / 0 / 0` | `true / 0 / 0` |
| high primal constraint | `0.0` | `0.0` |

另有 high RHS repeat relative=`0.0`、source unchanged=`0.0`。owner inventory、high↔LOR route、orientation consistency、phase exactly once 和 canonical component hashes 均由 raw record 绑定。E edge matrix 为 `3018×3018`、102,368 NNZ；N node matrix 为 `1120×1120`、32,844 NNZ。production forbidden flags 仍为 no high-order global AIJ、no global dense transfer、no numeric allgather、no production direct factor。

## 3. N composition failure 的边界

checker 原始 Gate failure 是：

```text
N edge_jacobi_pre remaining update: 2.8019257502717445 > 1e-12
```

| packet | norm |
|---|---:|
| 直接保存的 `n_low_input` owner packet | `730.0973355673666` |
| 保存的 pre remaining | `1197.8581513891497` |
| 保存的 pre edge action | `2108.19431364797` |
| `pre remaining + pre edge_action` | `2758.242171099465` |

key 集合相同，但现有 raw 没有单独保存经过 `low_dual_owner_packet` 重编码后的初始 `n_low_input`。`pre remaining + pre edge_action` 是由两个 trace packet 推出的 inferred/derived re-encoded initial；它与自身的相对差为 `0.0` 是定义性闭合，不是独立 raw 初值验证。该 inferred 值与直接 `n_low_input` 的相对差就是 `2.8019257502717445`；源码显示 runner 对 `n_low_input` 传入 `low_input_from_high_dual` 返回的原 owner packet，而 trace 的 dual packet 通过 `low_dual_owner_packet` 再做 raw low `Tt_apply`/owner additive re-encoding。故这是 evidence coordinate mismatch 的根因边界，但不独立证明整个 N replay PASS，也不改变 checker FAIL。

checker 的 Gate failure 事实原样保留；主审根因判断仅说明该 failure 不能直接当作 replay 数学失败。E 的 residual failure 不依赖 N 这组 artifact，因此 Q0 hard stop 不变。相关源码位置为 runner `:478-480`、`:570-584`，replay `fullspace_lor_hx_root_cause.py:494-519`，dual re-encoding `:573-622`，checker composition `task038_full3d_lor_hx_q0_checker.py:569-598`。

## 4. 资源、provenance 和证据 hash

| 资源/证据 | 实测 |
|---|---:|
| cycle process-tree 最大 RSS | `185102336 B` |
| cycle process-tree swap | `0 B` |
| `/usr/bin/time -v` wall | `3:41.69` |
| GNU time Maximum RSS | `293908 KiB` |
| GNU time Swaps | `0` |
| raw files / bytes | `147 / 67621815` |
| raw deterministic manifest SHA | `028e29553c3325fafd2001bde0cfb4711326a960735f79c862fd3f70fe13493f` |

GNU time 最大 RSS 是单 worker 进程观察，不是 MPI process-tree/cgroup 峰值；cycle process-tree RSS 是 record 内的边界诊断。没有把非-dedicated `/init.scope` 历史值写成本 case peak，也没有资源 Gate 被误报为通过或失败。swap 为零，但 Q0 的主要停止原因是 E 数值 Gate。

| evidence | SHA256 |
|---|---|
| relocated Q0 record | `2d767143ce3b28ac9a4b45962faf370770e1e637f05b4f0b62bb279fe7f6ca82` |
| relocated Q0 checker | `be70e0e559fea32023dfde58e4ede11009574c18f51e4b914d9b5034832a35ea` |
| raw marker `stage-rank0.jsonl` | `0af96262408061ba37cf107fc3df7bd99329680ad1f13b33a5a964240e22d16c` |

source start/end SHA 都为 `47c3e5b1ab7205ac5cd8f37b63f33e0a6f46355f`，clean start/end 均为 true。record/checker 中的 raw artifact descriptors 和 component hashes 保留完整 canonical evidence。

## 5. Q1–Q5 的停止状态

| 阶段 | 状态 | 未执行内容与原因 |
|---|---|---|
| Q1 | `not_run_by_Q0_hard_stop` | 未运行 p3/h50 50,000-step eventual-convergence formal；E 未达到 Q0 residual Gate |
| Q2 | `not_run_by_Q0_hard_stop` | Review V10 Q2 的启动前提是 Q0 Reference E PASS；本次未满足，因此不启动；未测 rows/NNZ/maps/hierarchy/cold peak/10 apply |
| Q3 | `controlled_stop_by_Q0` | 实际选择 Review V10 的 `LOR_AUXILIARY_FOUNDATION_FAIL` 分支，关闭当前 family |
| Q4 | `not_run_by_Q0_hard_stop` | 未运行 p6/h10 positive longrun |
| Q5 | `not_run_by_Q0_hard_stop` | 未运行 p6/h10 physical Maxwell MPI1；MPI2 physical 在 V10 本来也未授权 |

没有 p6/h10、p6/h5、0.7 nm full PDE、2 TiB complete-workflow、official E/H 或 R/T/A 结果。V10 不允许从这次约185 MB p3 small diagnostic 外推 2 TiB feasibility。

## 6. 旧结论、验证与合入边界

V8 M0 negative、orientation fix、scalar owner debt、old L2 one-apply `1.7348663090876784 > 0.45`、old 80-step v1 FAIL、additive-v2 CLOSED、V9 P0 PASS 和 P1 p3 fixed-cap negative 均原样保留。Q0 不重分类它们。

formal 结束后未再改 Python；Q6 只修改 docs/compact。Q0 harness/checker、focused test、formal records 和 closeout docs 在本次 formal negative 下均属于 research-only/do-not-promote；若保留归档，测试必须与 harness 同组，production core 没有变更。该 family 不进入 ordinary default；若要继续，必须先有新的 review 明确真正不同的修复边界，不能用参数扫描、增大 restart 或再次重跑绕过本 hard stop。上表的 `1/0` 是 formal 结束、Q6 提交前 snapshot，不应被读作最终永久未 push 状态。

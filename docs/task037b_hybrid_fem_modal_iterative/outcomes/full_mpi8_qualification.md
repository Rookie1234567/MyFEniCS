# Review V4 唯一 MPI8 full-solve 资格化记录

## 1. 运行身份与结果层次

固定 action 是把局部端盖近似逆冻结成一个可重复调用的线性操作；它只提供外层 FGMRES
需要的局部修正，不把另一个局部 Krylov 求解器嵌入 callback。outer operator 仍是 exact
matrix-free block operator。

| 层次 | raw / derived 结果 | 结论 |
|---|---|---|
| source | `eb1fc88483dd4d9cb5eabb071f8af0e87f91ba49`，parent `d3b15af96d4719f04dcf006c6caf98d1a2503366` | clean，唯一 formal source |
| V3 provenance | `v3_provenance_gate.pass=true`；六项 V3 expected SHA 与 observed SHA 相等 | raw summary 直接记录 |
| run | MPI8；p6/h10；modal p6/h10；13.5 nm；S；10°；10/110 nm；M120/candidate240；40/endcap | frozen |
| solver | right FGMRES，restart90，rtol `1e-6`，atol0，zero initial，max_it700 | frozen |
| KSP | reason2，iteration534 | measured |
| numerical disposition | `FIXED_ILU0_WOODBURY_BLOCK_PC_FULL_NEGATIVE` | controlled local-block Gate miss |
| resource | RSS `6.289192199707031 GiB` | `>6.0 GiB`，resource negative |
| formal physics | recovery and official outputs | `not_run_dependency_gate` |

完整 compact record 见 [Case101 V4 record](../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v4_mpi8_full_qualification_v1.json)。

## 2. Residual authority

每个 history row 同时保存 reported 与 exact true residual；compact 只保存审查所需 checkpoint，
完整 535 rows 保留在 raw solver record，并由 `61f0f33a8f962dbf37f312a5fba33a0e7c432432089bbbad7a3b0baf6a94b8ad`
绑定。

| iteration | reported | global | bottom | top | modal | PC | bottom/top action |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 0.47312934919105415 | 0.4731293491910546 | 0.7915576229904723 | 0.4144951475878447 | 2.7011301558523683e-15 | 20 | 527 / 527 |
| 60 | 0.1127207148684223 | 0.11272071486842282 | 0.2032001429319691 | 0.06665913881529464 | 2.5454113396942133e-15 | 60 | 607 / 607 |
| 100 | 0.022267181511820375 | 0.022267181511820732 | 0.02427052205015629 | 0.01791884170341418 | 1.662848140283262e-15 | 100 | 687 / 687 |
| 200 | 0.0015751888272091388 | 0.0015751888272089055 | 0.0024392066956133935 | 0.0010989265634579726 | 1.0150435351696175e-15 | 200 | 887 / 887 |
| 534 | 9.83224189598995e-7 | 9.832241902112744e-7 | 1.3641751886101987e-6 | 7.290772097898545e-7 | 1.2365161175289584e-15 | 534 | 1555 / 1555 |

以下趋势审计直接扫描 raw 中的535行，而不是从这5个 checkpoint 推断：

| residual 列 | 全 history 正向回升次数 | 最大相邻两行归一化残差绝对回升 | 最后90个迭代间隔回升次数（iteration 444→534） | 最后90个迭代间隔净改善 |
|---|---:|---:|---:|---:|
| reported | 0 | 0.0 | 0 | 5.519040810567769e-6 |
| global true | 0 | 0.0 | 0 | 5.519040810155802e-6 |
| bottom true | 12 | 0.9199767157497346 | 0 | 9.91213625931228e-6 |
| top true | 0 | 0.0 | 0 | 3.4213609649988075e-6 |

Modal residual 是 finite；modal 不要求单调性。Global、top 和 modal true residual 通过；bottom
为 `1.3641751886101987e-6`，比冻结的 `1e-6` 上限高36.4175%。因此4个 scalar residual
列总体下降且最后90个迭代间隔（iteration 444→534）没有回升，但 bottom 在更早的完整 history 中有12次回升。这不是
发散或平台。Review V4 §9.4 关于发散/平台/700步远高于 Gate 的措辞不能精确描述这一事实；
本记录保留 controlled local-block Gate miss，不声称 fixed ILU0-Woodbury family 无法收敛。

## 3. Algebra 与 object ledger

| Gate | measured 证据 |
|---|---|
| global operator | Python matrix-free；global A/direct=not materialized/0；bottom/top A 与 global F false |
| explicit blocks | C/D counts `0/0` globally、per side |
| local factor identity | bottom/top direct `0/0`；ILU `1/1`；global direct `0` |
| callback certificate | identity 0/0；linearity `1.873328098581355e-15 / 1.9553874565674403e-15`；determinism 0；hash equal；apply increment 7/side |
| K | rank 40/side；condition `3.0331668903694333 / 4.162687539173756`；finite |
| modal Schur | shape `[240,240]`；complex128；rank 240；condition `1160.2452412629682`；repeat errors 0；normal equations false |
| Schur build | 480 applies per side |
| online PC | `487 -> 1555` per side；increment `1068=2*534` |

raw lifecycle 顺序为：

```text
pc_context -> bottom_fixed_ilu -> top_fixed_ilu
-> bottom_woodbury_wklu -> top_woodbury_wklu
-> action_modal_schur -> bottom_components -> top_components
-> outer_action_matrix -> outer_action_context
```

KSP/PC workspace 销毁时 modal Schur 仍被保留；retained solution snapshot 与 borrowed exact
actions 仍可用于 lifecycle contract。随后两侧 fixed factors 都从 `1 -> 0`，两侧 Woodbury
carriers 和 components 被销毁，main postprocess 释放了 static-condensation caches、coupling、
modal bases 和 QEP operators。`release_pass=true` 与 `no_orphan=true` 是 raw lifecycle 事实，
不是由 numerical status 推断得到的。

FGMRES basis estimate 是 derived，不是 measured RSS：

```math
estimated_bytes = (2 * restart + 1) * rows * complex128_bytes
```

raw estimate 为 global/sum `49,486,848` bytes、rank0 local `7,471,680` bytes、max-rank
`9,244,032` bytes。

## 4. Resources、timing 与 memory-authority caveat

authority metric 是 simultaneous process-tree RSS。Worker RSS/PSS/USS 是8个 rank 的同步
sum；PSS 和 USS 是 timeline `smaps_rollup` 列的独立最大值，不是累计 allocation size。

| metric | measured maximum | 阶段 / status |
|---|---:|---|
| process-tree RSS | 6440.1328125 MiB = 6.289192199707031 GiB | `v4_worker_cleanup_finished`，authority |
| worker RSS sum | 6425.453125 MiB = 6.2748565673828125 GiB | same sample |
| worker PSS sum | 5326.6474609375 MiB = 5.201804161071777 GiB | same sample，smaps_rollup |
| worker USS sum | 5144.26171875 MiB = 5.023693084716797 GiB | same sample，smaps_rollup |
| peak elapsed | 419.3236320320284 s | timeline sample |

峰值出现在 release/cleanup 之后，可能是 allocator high-water，而不是 live-object inventory；
因此 PSS/USS 不能替代 RSS authority。Resource-positive `<=6 GiB`、engineering `<=5 GiB` 和
stretch `<=3.77 GiB` 均为 false。Warning10、terminate14 和 timeout7200 均未触发。

Timeline 与 process-tree 观测到的 swap 均为0，但 all-live authority/swap readability 为 false，
job cgroup 也不是 dedicated。因此 summary 保留 `no_swap=false` 与
`terminated_for_authority_unreadable=true`：zero-swap qualification 尚未建立。Worker 自然
完成且未使用 SIGKILL，process group 已退出；这不是 OOM kill。

| stage | max-rank seconds |
|---|---:|
| cross-section/QEP | 0.8889220430282876 |
| positive/negative bases | 53.283052755054086 |
| action/coupling | 210.08973653102294 |
| V4 setup | 56.02552783791907 |
| outer | 96.9506127560744 |
| release | 0.004097130033187568 |
| total | 417.24723999900743 |

## 5. Downstream 与 checker boundary

Numerical failure 发生在 recovery 之前。因此 external q、full-FE、own field、R/T/A、A_volume、
orders、12+12、canonical、direct-Hybrid 和 Full3D comparisons 均为
`not_run_dependency_gate`。H1 modal/canonical/selected-field payloads 分别为
`not_run_authority_payload_gap`；不能用零值或 summary label 替代缺失数组。

唯一独立 checker 的 exit 为0，且 `evidence_integrity_pass=true`、
`candidate_evidence_pass=true`、`authority_bindings_pass=true`、
`recognized_controlled_negative=true`。其 `pass=false`，failure 为
`h1_authority_payload_gap`；offline wall 为 `0.05152548989281058 s`，historical
checker-process `ru_maxrss` 为 `35.13671875 MiB`，`online_rss_included=false`。该 exit code
只代表 evidence integrity，不代表 full qualification。

## 6. Artifact index 与 test boundary

| artifact | repo-relative path | SHA256 |
|---|---|---|
| solver | `benchmarks/artifacts/task037b/v4_full_double_block_pc_eb1fc88_mpi8/solver_record.json` | `1d3b51398efcb55be819f080797f2dc175f50e3252065f47a7abd0b9c5d3193d` |
| summary | `benchmarks/artifacts/task037b/v4_full_double_block_pc_eb1fc88_mpi8.json` | `3838cc17d705453dec6764ba1fa0e838c202cad1d1e96cc755873ee1ad1ea44a` |
| embedded history | raw solver record | `61f0f33a8f962dbf37f312a5fba33a0e7c432432089bbbad7a3b0baf6a94b8ad` |
| stages | `benchmarks/artifacts/task037b/v4_full_double_block_pc_eb1fc88_mpi8/memory_stages.jsonl` | `08c051a0ba3504f25b0c2c915b7d94aaaa964b3e68c10942dbe04e72a3f2cc24` |
| timeline | `benchmarks/artifacts/task037b/v4_full_double_block_pc_eb1fc88_mpi8/memory_timeline.csv` | `3d8253a4bd73f07800a65043a353479fd32128fa4b168cf8a340f93bc9520899` |
| stdout | `benchmarks/artifacts/task037b/v4_full_double_block_pc_eb1fc88_mpi8/worker_stdout.txt` | `309b30ce76218516021e8403cec5aa76c1712c21e82f6f2a03a4a95631bfbdd4` |
| checker | `benchmarks/artifacts/task037b/v4_full_double_block_pc_eb1fc88_mpi8/independent_checker.json` | `bb3998f35d498e21b42999b1b7e3bca6dd3bde40148471807400734a43dad326` |

最终 focused evidence 为 serial `18 passed`、MPI2 key action/lifecycle 每 rank `5 passed`、
MPI4 每 rank 同为 `5 passed`；touched-file Ruff/format/compileall/diff checks 均 pass。
Full pytest、test240、extra PDE 和 CI 均为 `not_run`。

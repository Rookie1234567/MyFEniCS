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

## Review V5：同一 candidate 的唯一多指标正式运行

V5 把“是否达到线性停止条件”定义为五个量同时达标：PETSc reported residual、exact
global residual、bottom/top block residual 和 modal residual 都必须 finite、非负且不超过
`1e-6`。这样可以避免只看一个全局标量而漏掉某一侧端盖的局部误差。以下内容来自 V5
raw record；本节不覆盖 V4 历史。

### 身份、运行次数与 postprocessor 边界

| 项目 | 精确值 | 语义 |
|---|---|---|
| V5 implementation checkpoint | `770e74513b4444f032adb7f61c5d350fb53d9458` | 允许的实现基线 |
| unique formal candidate source | `892f186b39c0eb89f1912640430fd79599d86318` | 唯一 MPI8 numerical source |
| formal run count | `1` | 无 retry、warm start、continuation 或参数修改 |
| pure postprocessor correction | `11c01d5268f1e0fc8eb307945179b540ccfcb2aa` | 只读同一 solver record 的合同修正 |
| raw parent result | exit `1`; `task037b_v4_implementation_gate_failed` | `terminal V4/V5 record legacy-field completeness contract` 与 `official-not-run energy evaluator contract`；非 solver raw 物理结论 |
| corrected read-only evaluation | contract/numerical/recovery=`true`; physics=`false`; failures=`[]` | 正确 disposition 为 `MULTIMETRIC_LINEAR_PASS_RECOVERY_OR_PHYSICS_FAIL` |

postprocessor 没有再次启动 solver，不改变 raw solver、物理数值或运行次数。raw parent 的
`physics_contract`、`record_status_mismatch`、`qualification_disposition_mismatch` 和
`v5_disposition_mismatch` 原样保留；它们是上述两个合同错误产生的四个 parent failure label，不能把 parent exit1 写成第二次数值失败。

### 线性 Gate 与 checkpoints

| iteration | reported | global | bottom | top | modal | multimetric max | elapsed s | ksp reason | PC apply | bottom/top action |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 2.2424710600856975e-6 | 2.242471060163116e-6 | 3.4111266901058858e-6 | 1.5835805727648354e-6 | 1.4094975322947167e-15 | 3.4111266901058858e-6 | 81.33067819301505 | 0 | 500 | 1487 / 1487 |
| 520 | 1.4265563629448059e-6 | 1.4265563629094859e-6 | 2.0548396968980893e-6 | 1.0386858184740322e-6 | 1.5241312777460737e-15 | 2.0548396968980893e-6 | 84.56075759895612 | 0 | 520 | 1527 / 1527 |
| 534 | 9.832241894524608e-7 | 9.832241891202619e-7 | 1.364175187660687e-6 | 7.290772088419766e-7 | 1.6064823432658189e-15 | 1.364175187660687e-6 | 86.82920670497697 | 0 | 534 | 1555 / 1555 |
| 540 | 8.137715143365693e-7 | 8.137715143585267e-7 | 1.2167293120702838e-6 | 5.8057495384064e-7 | 1.925960881288701e-15 | 1.2167293120702838e-6 | 87.80791945999954 | 0 | 540 | 1567 / 1567 |
| 550 | 7.243836969791837e-7 | 7.243836969886748e-7 | 1.1057248017639442e-6 | 5.104540257008618e-7 | 1.0202967889790073e-15 | 1.1057248017639442e-6 | 89.45420049794484 | 0 | 550 | 1587 / 1587 |
| 557 | 6.457740108721289e-7 | 6.45774010063497e-7 | 9.811891391712585e-7 | 4.5634977013685214e-7 | 1.3354878193519844e-15 | 9.811891391712585e-7 | 90.59673926699907 | 2 | 557 | 1601 / 1601 |

raw 中共有 558 条连续 authoritative history row（iteration `0..557`，每个 iteration 一条）；
因此 560、580、600、630、700 是 `not_reached`，不是补写的零或预测值。iteration 534 的
decision 仍为 `ITERATING`，实际终点 557 的 KSP reason 为 `2`。retained solution 上的
postsolve explicit audit 只执行一次，五个值均通过 `1e-6`，所以 `numerical linear pass=true`。

### Recovery、own physics 与 official boundary

| Gate | raw 结果 | 结论 |
|---|---|---|
| external q identity | bottom/top relative residual `0.0 / 0.0`；各40 mode，finite、unique | pass |
| full-FE bottom | linear `7.128867121665533e-7`；interior relative `1.964774406457519e-12`；interior max `8.726571982174999e-13` | pass |
| full-FE top | linear `7.31449061294792e-7`；interior relative `2.0030607460888172e-12`；interior max `1.123510764743594e-12` | pass |
| interface E | bottom/top relative L2 `5.112828439237629e-7 / 5.438313443889813e-7` | pass |
| exact traction dual | bottom/top `9.609121539153052e-7 / 4.5634977013685214e-7`，限值 `1e-8` | fail；唯一 own-physics failure |
| energy diagnostic | closure `-1.002582173281752e-6`；`A_balance-A_volume=1.002582173337263e-6` | raw diagnostic pass |

因此 `recovery=true`、`own_physics=false`，overall 为
`MULTIMETRIC_LINEAR_PASS_RECOVERY_OR_PHYSICS_FAIL`。R/T/A、`A_volume`、orders、field、
12+12、canonical、direct-Hybrid 和 Full3D comparison 全部 `not_run`；energy diagnostic
不是 official output。H1 的 modal/canonical/selected-fields 数值 payload gap 仍在，且 own
physics 未通过，所以 conditional direct-Hybrid authority export 为
`not_run_dependency_gate`，不能用 hash 或零值补齐。

### 生命周期、资源、时间与证据入口

| 项目 | raw measured/derived 结果 |
|---|---|
| fixed factors / actions | bottom/top direct `0/0`，ILU `1/1`；nested KSP/direct fallback=false |
| K | rank `40/40`；condition `3.0331668903694333 / 4.1626875391737554` |
| modal Schur | `240x240` complex128；rank240；condition `1774.3032595169025`；normal equations=false |
| online applies | each side increment `1114=2*557` |
| release-repeat | pre/post global `6.45774010063497e-7 / 6.45774010063497e-7`；relative difference `0.0`；borrowed exact actions usable |
| snapshot | postsolve、保存和最终四项 destroy/release 均 pass |
| online RSS authority | process-tree `7218.7734375 MiB = 7.049583435058594 GiB`；worker RSS `7204.125 MiB = 7.0352783203125 GiB` |
| worker PSS / USS | `5500.109375 MiB = 5.3712005615234375 GiB` / `5225.45703125 MiB = 5.102985382080078 GiB` |
| peak stage | `v4_worker_cleanup_finished`；cleanup 后 high-water，不等同 live-object inventory |
| resource | `<=6 / <=5 / <=3.77 GiB` 全部 false |
| timing total | `422.9385745129548 s`；outer `90.62511192599777 s`；action/coupling `208.7397422080394 s`；setup `47.39639616198838 s` |

离线只读 timeline audit 共 1428 行：worker-count 为 `{0: 2, 8: 1426}`；1426 条
all-eight-live 行的 `smaps_readable_count=8`，worker/process-tree swap 观测均为0。首行是
尚未拉起 worker 的 `process_start`，末行是 `v4_worker_cleanup_finished` 后正常的 0-worker
terminal drain。这里可称 `corrected offline audit zero-swap qualified`，但 immutable raw
parent summary 的 `no_swap=false` 与 `terminated_for_authority_unreadable=true` 必须保留，
因为它们来自修复前 terminal/postprocessor 分类；本次不是 memory kill，worker 自然结束且
未使用 SIGKILL。

本次 V5 compact record 见
[task037b_v5_mpi8_multimetric_full_qualification_v1.json](../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v5_mpi8_multimetric_full_qualification_v1.json)。
raw summary、solver、stages、timeline、stdout 和诊断 NPZ 的路径及 SHA 均在 compact 中绑定。

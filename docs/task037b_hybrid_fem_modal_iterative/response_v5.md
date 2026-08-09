# Task037b Review V4 response：唯一 MPI8 full solve 的受控结项

## 结论

本轮对 Review V4 没有算法异议。V4 是一个显式、research-only 的 full-solve 入口：它把两个
端盖都换成固定的 ILU(0)+40-mode Woodbury action，再用 exact matrix-free block operator 做
外层 right FGMRES。固定 action 的作用是让每次局部预条件调用的代价和对象所有权可审计；它不
改变方程，也不把局部迭代器偷偷放进外层求解。

| 层次 | 结果 | 数据身份与边界 |
|---|---|---|
| source | `eb1fc88483dd4d9cb5eabb071f8af0e87f91ba49` | 唯一 formal run；无 wiring retry、无参数修改 |
| numerical | negative | 五个 true residual 中 bottom 为 `1.3641751886101987e-6`，超过 `1e-6` |
| numerical disposition | `FIXED_ILU0_WOODBURY_BLOCK_PC_FULL_NEGATIVE` | 保留 raw 精确字符串 |
| process-tree resource | negative | RSS peak `6.289192199707031 GiB`，超过 `6.0 GiB` |
| engineering / stretch | false / false | 分别未达到 `5.0 / 3.77 GiB` |
| official physics | all `not_run` | recovery、field、R/T/A、orders、12+12、canonical、direct/Full3D 均未运行 |
| next step | awaiting review | 不重跑、不调参、不启动新候选 |

bottom residual 的局部 Gate miss 不能按发散或平台解释：global、top、modal residual 已过
门槛，且 raw-history audit 显示总体下降：reported/global/top 全史没有正向回升，bottom 全史有
12 次正向回升；四列在最后90个迭代间隔（iteration 444→534）均无回升并有正向净改善。Review V4 §9.4 的“发散/平台/700 远高于 Gate”分类与本
次事实并不完全吻合；本记录将它准确表述为 controlled local-block Gate miss，而不是
Woodbury/ILU PC 家族失去收敛能力。

## 冻结身份与运行边界

| 字段 | 值 |
|---|---|
| branch | `codex/20260807-task37b-hybrid-iterative-development` |
| source / parent | `eb1fc88483dd4d9cb5eabb071f8af0e87f91ba49` / `d3b15af96d4719f04dcf006c6caf98d1a2503366` |
| case | p6/h10；modal p6/h10；13.5 nm；S；10°；interfaces 10/110 nm |
| modes | requested/candidate `120/240`；40 external modes per endcap |
| operator | static-condensed；`full3d_uniform_cg` / `scalar_cg_discrete_derivative` |
| outer | right FGMRES；restart 90；rtol `1e-6`；atol 0；zero initial；max_it 700 |
| MPI / image | MPI8；`myfenics-stage4:task28`，digest bound in compact record |
| formal runs | exactly one；没有第二次 numerical run |

Full3D authority 与 p6 preflight authority 只作 source/launch identity 校验。Full3D record 没有
在 candidate 进程中加载作比较；H1/V3 raw 也只按 hash 绑定。raw summary 的 emitted worker
command、parent watchdog 的 frozen fields、authority hash 与 run routing 写入
[V4 compact record](../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v4_mpi8_full_qualification_v1.json)。
其中 `v3_provenance_gate.pass=true` 且六项 V3 compact/raw artifact 的 expected SHA 与 observed
SHA 相等。

## Numerical Gate 与 checkpoints

外层迭代使用 reported residual 进行 PETSc 进度判断，同时每步用 exact operator 重算 global、
bottom、top、modal true residual。下表保留 Review 要求的冻结点；完整 0–534 history 不复制
进 Git，而由 raw solver record 和 embedded-history SHA 绑定。

| iteration | reported | global true | bottom true | top true | modal true | PC apply | bottom/top action apply |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 20 | 0.47312934919105415 | 0.4731293491910546 | 0.7915576229904723 | 0.4144951475878447 | 2.7011301558523683e-15 | 20 | 527 / 527 |
| 60 | 0.1127207148684223 | 0.11272071486842282 | 0.2032001429319691 | 0.06665913881529464 | 2.5454113396942133e-15 | 60 | 607 / 607 |
| 100 | 0.022267181511820375 | 0.022267181511820732 | 0.02427052205015629 | 0.01791884170341418 | 1.662848140283262e-15 | 100 | 687 / 687 |
| 200 | 0.0015751888272091388 | 0.0015751888272089055 | 0.0024392066956133935 | 0.0010989265634579726 | 1.0150435351696175e-15 | 200 | 887 / 887 |
| 534 | 9.83224189598995e-7 | 9.832241902112744e-7 | 1.3641751886101987e-6 | 7.290772097898545e-7 | 1.2365161175289584e-15 | 534 | 1555 / 1555 |

KSP reason 为 `2`，实际 iteration 为 `534`。global、top、modal 通过 `<=1e-6`，bottom
比上限高 `36.41751886101987%`，所以五 residual Gate 为 false。所有 residual finite；535 行 raw
audit 显示 reported/global/top 全史无回升，bottom 有12次回升但最后90个迭代间隔（iteration 444→534）无回升且净改善；
这是一项局部块 Gate negative，不是 breakdown、发散或平台。

## Algebra、inventory 与生命周期

| 项目 | 实测结果 |
|---|---|
| global operator | Python matrix-free；global A/direct factor `false/0`；bottom/top A 与 global F 均未 materialize |
| explicit C/D | global、bottom、top 均 `0/0` |
| local factors | bottom/top direct `0/0`，ILU `1/1`；nested KSP/direct fallback `false/false` |
| callback | wrapper identity `0/0`；linearity `1.873328098581355e-15 / 1.9553874565674403e-15`；determinism `0`；repeat hash 相等；每次证书 apply 增量 `7` |
| K | rank `40/40`；condition `3.0331668903694333 / 4.162687539173756`；arrays finite |
| modal Schur | `240x240` complex128；rank `240`；condition `1160.2452412629682`；matrix/LU repeat error `0`；normal equations false |
| Schur build | 每侧 `480` 次 apply |
| online PC | 每侧 `487 -> 1555`，increment `1068 = 2*534` |

释放顺序由 raw ledger 记录为：PC context → bottom/top fixed ILU → bottom/top Woodbury
W/K/LU → modal Schur → components → outer matrix/context。KSP、PC context 已释放；solution
snapshot 是为审计/后续 Gate 显式保留的对象，raw 没有 `snapshot_destroyed` 证据，不能宣称它已销毁。
borrowed actions 在 PC 销毁后仍存活，随后两侧 factor 从 `1`
降为 `0`。main postprocess 的 static-condensation cache、coupling、modal basis 与 QEP
对象也记录了真实 destroy call；release pass 为 true，无 orphan。

FGMRES restart basis 只是 derived estimate，不是 RSS：

```math
estimated_bytes = (2 * restart + 1) * rows * complex128_bytes
```

global/sum 为 `49,486,848` bytes，rank0 local 为 `7,471,680` bytes，max-rank 为
`9,244,032` bytes。W、K/LU 和 basis 的 recorded/derived 语义没有与进程 RSS 混用。

## Recovery、official physics 与独立 checker

因为 bottom true residual 没有通过，V4 在 recovery 前受控停止。external auxiliary、full-FE
recovery、own field/R/T/A/A_volume、diffraction orders、12+12、canonical、direct-Hybrid 和
Full3D comparison 均为 `not_run_dependency_gate`。H1 authority 没有 modal 数值数组、canonical
数值 manifest 或 selected E/H 数组，因此 modal、canonical、selected-fields 另记
`not_run_authority_payload_gap`；没有用 hash、pass 标签或零值冒充数值载荷。

唯一独立 checker 已运行一次，exit 0 只表示 evidence integrity pass：

| checker 字段 | 结果 |
|---|---|
| `evidence_integrity_pass` | true |
| `candidate_evidence_pass` / `authority_bindings_pass` | true / true |
| `recognized_controlled_negative` | true |
| `pass` | false |
| failure | `h1_authority_payload_gap` |
| comparisons | dependency-gated；不生成 q/orders/energy/12+12/Full3D 假结果 |
| offline wall / ru_maxrss | `0.05152548989281058 s` / `35.13671875 MiB` |
| online RSS included | false |

checker 的 exit 0 不能解释为完整 qualification pass，也不改变 solver 的 numerical negative。

## 资源与 swap 口径

process-tree simultaneous RSS 是本次资源权威；worker RSS/PSS/USS 是 8 个 MPI rank 同一采样
时刻的同步总和，PSS/USS 来自 timeline 的 smaps_rollup 列，绝不是累计对象体积。

| 指标 | measured 值 | stage / 解释 |
|---|---:|---|
| process-tree RSS peak | 6440.1328125 MiB = 6.289192199707031 GiB | `v4_worker_cleanup_finished`；RSS authority |
| worker RSS sum peak | 6425.453125 MiB = 6.2748565673828125 GiB | 同步 rank sum |
| worker PSS sum peak | 5326.6474609375 MiB = 5.201804161071777 GiB | `v4_worker_cleanup_finished`，smaps_rollup max |
| worker USS sum peak | 5144.26171875 MiB = 5.023693084716797 GiB | `v4_worker_cleanup_finished`，smaps_rollup max |
| peak elapsed | 419.3236320320284 s | watchdog timeline sample |

RSS 峰值发生在 release/cleanup 之后；它可能反映 allocator high-water，而不等同于此时仍存活
的 solver object inventory。因此不能用 PSS/USS 替代 RSS authority，也不能把 release 后的
峰值解释为 live factor 仍然存在。

timeline 与 process-tree 的观测 swap 都是 `0`，但 all-live memory/swap authority samples
并非全部可读，job cgroup 也不是 dedicated；summary 因而保留 `no_swap=false` 与
`terminated_for_authority_unreadable=true`。这表示正式 zero-swap/memory-authority Gate 未
资格化，不表示 worker 被内存杀死：本次 worker 自然结束、未触发 10/14 GiB 阈值、未超时、
未使用 SIGKILL，process group 也已退出。

## 时间、测试与停止边界

| 阶段 | max-rank seconds | 数据身份 |
|---|---:|---|
| cross-section/QEP | 0.8889220430282876 | measured |
| positive/negative bases | 53.283052755054086 | measured |
| action/coupling | 210.08973653102294 | measured |
| V4 setup | 56.02552783791907 | measured |
| outer | 96.9506127560744 | measured |
| release | 0.004097130033187568 | measured |
| total | 417.24723999900743 | measured |

focused serial 合计 `18 passed`；MPI2 key action/lifecycle `5 passed`，MPI4 同为 `5 passed`。
五个 touched Python files 的 Ruff check、Ruff format-check、compileall 与 git diff-check 均
通过。full pytest、test240、额外 PDE、CI 均 `not_run`；不把本地 focused evidence 写成 CI。

正式 V4 的结论是：固定 action、matrix-free block operator、modal Schur、factor inventory
和 lifecycle 合同均通过；数值结果因 bottom local-block residual 超过 `1e-6` 受控为 negative；
资源也未达到 `<=6 GiB`。不重跑，不调 ILU/shift/overlap/tolerance，不启动新的候选或 full
physics lane，等待下一轮审阅。

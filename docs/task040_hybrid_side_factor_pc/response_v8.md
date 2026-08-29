# Task040 Response V8：V7 moving-PML 资源 Gate 收口

## 当前裁决

V7 尺度归一化 identity 已形成有效 raw/checker candidate：D0、D1 和三层误差证据均通过，
但 `formal_adjudication=false`。随后 full-spectrum canonical H(curl) transform 在 MPI8 formal
中暴露了两个具体实现问题；修复后的 targeted regression 通过，但按一次 corrected formal
纪律没有第三次 full-spectrum heavy run。

moving-PML 路线的 provider 接线修复后，唯一 corrected formal 在第一个 source checkpoint
前达到六小时 wall Gate。本轮唯一正式 moving 结论是：

```text
classification = INCONCLUSIVE_RESOURCE_GATE
signal         = SIGNAL_UNAVAILABLE
adaptive       = NOT_RUN_DUE_TO_TRUE_RESOURCE_GATE
merge approval = NO
Task040        = open / review required
```

`SIGNAL_UNAVAILABLE` 不是 `PML_NO_SIGNAL`：五源没有到达 one-apply 或 FGMRES checkpoint，不能
把“没有数据”写成无信号，也不能写成 positive。

## 身份、提交链与正式命令

正式 moving run 开始前的快照为：branch
`codex/20260822-task40-hybrid-side-factor-pc`，source/HEAD/upstream 均为
`7b237ea653ea5afa0a731b30739663f0ea2374fc`，worktree clean，ahead/behind `0/0`。

`86014171` 之后的提交 ledger 为：

```text
253199e2 docs(task040): record v6 factor-stage forensic
3d8f58bb feat(task040): add full-interface Schur action
7c3f068f feat(task040): add V6-2 interface identity runner
0b66b633 feat(task040): add V6-2 exact qualification loader
53e75340 feat(task040): add V6-2 exact family consumer
41d09404 feat(task040): complete V6-2 exact authority bridge
a8531b1a docs: define controller-executor workflow
875f3234 feat: complete Task40 V6-2 exact qualification evidence
72975fff fix: recognize native Task40 activation
8199929b fix: adapt V6 resource gate to native Linux
82bd1109 fix: bridge frozen RHS to native bare F
3bdf4439 docs(task040): close V6-2 identity gate
c351eb8f docs(task040): add review v7 scale-normalized identity adjudication
e7fee3c2 feat(task040): add V7 identity and full-spectrum screen
ab51cad1 fix(task040): route quantized canonical trace levels
a2acb934 fix(task040): handle empty canonical probe ranks
e6f5d49b feat(task040): add moving-PML full-state pilot
5e6ce061 bench(task040): add moving-PML five-source screen
7b237ea6 fix(task040): bind moving-PML modal source provider
```

formal moving root：
`/home/fenics/Projects/MyFEniCS/results/task040_v7_moving_pml_mpi8_7b237ea6_native_rerun1`；
worker root 是其 `worker` 子目录。精确命令为：

```text
python -m benchmarks.task040_level_a_watchdog --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v7_moving_pml_mpi8_7b237ea6_native_rerun1 --source-sha 7b237ea653ea5afa0a731b30739663f0ea2374fc --v7-moving-pml-full-state --watchdog-enabled --bottom-route-only
```

该 root 没有 `run_summary.json`、moving manifest、五源 raw screen 或外部 checker 输出。关键
artifact SHA256 如下：

| 文件 | SHA256 |
|---|---|
| `watchdog_summary.json` | `4d846cdd463f3e8574393fc05f5574cfde0cc71e13695000402acfa4e078cf02` |
| `memory_stage_markers.raw.jsonl` | `1b5ee5ee5adea55a4f7c42f1d2f83f1b16d0561a7284eab6cab249c5ce964f15` |
| `memory_stages.jsonl` | `ce17e30c528892f5314a38f174e48e1d5842bfb975cb7cba454a06771182e244` |
| `process_tree_samples.jsonl` | `053ccfe05b497c013199ee83d26399944f3401b0115ce443d2b55ece19b95771` |
| `worker/operator_semantics_audit.json` | `55a9533d27ce8a7b7cc3f9396b8d9295ac0b408c388635429b85451da37e16db` |
| `worker_stdout.txt` | `555e300bc6d61f7d967108c43565d0f15f28808c313cc27aa6256690ca1dd350` |

## V7 scale identity 与旧结论

scale root：
`/home/fenics/Projects/MyFEniCS/results/task040_v7_scale_normalized_identity_mpi8_e7fee3c2_native`。
rank0000 bundle 文件 SHA 为
`dfc137c13e5811aa9b84c107400f6406b8a945f47a2a9d3ddf7631ced637c40e`；bundle 内 raw/checker
logical SHA 分别为 `a2aa1a72655bb695d663ec2c67b33115409715c75c0513e7b8fdf04d26bb59c6` 和
`768d094726ff6d458906885fe2ef602edbcdb13e9e20ceb2e008b8fc081193a4`。三尺度为 `2^-10,1,2^10`，
identity source 为 indices `0,1,2` 共9条，linearity source 为 `10,11`，
`alpha=0.37-0.21j` 共3条。checker `evidence_valid=true`、`checker_pass=true`、D0/D1
candidate 均为 true，selected=`d0_lower_memory`，`formal_adjudication=false`；refinement 与
partition audit trigger 均为 false。完整 raw norm、relative、backward 与 A/B/C 表见
[V7 scale outcome](outcomes/v7_scale_normalized_identity.md)。

V6-2 的 absolute-threshold negative 完整保留：Gamma action
`3.783538480529195e-10`（限值 `1e-10`）、interior
`1.2298155651030158e-9`（`1e-10`）、linearity `6.766170711131541e-9`（`1e-11`）、
repeat `1.4161645932820494e-9`（`1e-11`）；zero=0、roundtrip=0。状态仍为
`completed_v6_2_identity_gate_negative`，classification
`V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL`，`checker_pass/evidence_valid=true`、
`gate_pass=false`、`executed_exact=false`，不是 exact numerical negative。

## Full-spectrum 与 moving 路线

full-spectrum tiny serial/MPI2 canonical/FFT/DFT regression 通过，但 MPI8 formal 没有形成
可审计 sweep 数值。第一次 e7 formal 在 scale candidate 后报
`ValueError: full-spectrum metadata failed: Gamma entity extent is not one periodic cell`；
量化 level 修复后的 ab51 formal 又在合法 empty-local ownership 上报
`ValueError: canonical full-spectrum probe is invalid`，造成 rank divergence。C5 的
collective-safe empty-rank 修复 `a2acb934` 及 targeted serial/MPI2 regression 通过，但没有
第三次 MPI8 formal。详见 [full-spectrum outcome](outcomes/full_spectrum_floquet_sweep.md)。

moving-PML 的首个 root
`/home/fenics/Projects/MyFEniCS/results/task040_v7_moving_pml_mpi8_5e6ce061_native` 是
provider 接线 implementation failure：`build_current_bare_f_rhs` 拒绝没有
runner-supplied hash-bound selected-mode provider；`7b237ea6` 只复用既有
`_v5_selected_mode_provider(comm)` 修复该 bug。corrected root 随后在
`v7_moving_pml_sources started` 后达到真实 resource Gate。

当前没有 five-source `r8/r16/r32/r64/r128`、one-apply、route signal、PML positive 或 PML
no-signal。adaptive Schwarz 保持 `NOT_RUN_DUE_TO_TRUE_RESOURCE_GATE`，不能由此推断 0.7 nm
无解。

## lifecycle、resource 与 operator

corrected run：outer rc=`2`，watchdog worker rc=`1`，`termination_reason=wall_timeout`，
elapsed=`21601.760233s`，last authoritative sample=`21600.410422s`；peak process-tree RSS
`40560816128 B`（约 `37.78 GiB`），peak swap=`0`，authoritative samples=`34834`。
进程组完整退出，`sigkill_required=false`，无 traceback；stdout 中的 X11 authorization 行是
已知非致命噪声。

identity/resource preflight、system ready 和 one-cell source factor `1→0` 已完成；moving
setup 记录 `factor_ready=3`，但停在 sources started，故 moving factor `3→0`、最终
cleanup/readback 和 numeric residual 均未形成。operator audit 记录
`explicit_current_bare_F`、`qep_calls=0`、`C/D/H=0`、无 physical DtN；计划与已有 route
metadata 保持 `numeric_allgather=false`、`full-interface numeric replica=false`。本次
`operator_identity_bridge` 未执行/未判定，不能写 null/pass/fail；moving RHS 使用既有
`build_current_bare_f_rhs`。

full-spectrum、moving-PML、adaptive、factor-free local service、完整 Hybrid、h3、0.7 nm
capacity derivation 和 arbitrary Full3D architecture handoff 均未取得资格证据。master、
Task39、physics、M480、physical DtN、ordinary defaults 均未修改；selective merge none。
closeout 本地 serial=31 passed、MPI2 两 rank 各 3 passed，ABI 通过，详见
[test summary](outcomes/test_summary.md)；这些不是 CI 证据。

等待 ChatGPT 与用户逐文件审核本次 V8 closeout 及 Review V7 stop Gate。

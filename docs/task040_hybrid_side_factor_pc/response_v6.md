# Task040 Review V5 执行响应：Route C 受控负结果收口

## 一句话结论

V5-2 的 fresh current-layout bare-`F` authority 在授权的 `21600 s` factor-construction
窗口耗尽，转入低内存 Route C。Route C 在两个规定 RHS 上完成到 128 步的连续 right-FGMRES
screen，但没有出现正信号；独立 checker 重算为：

```text
checker_pass = true
evidence_valid = true
gate_pass = false
overall_candidate_gate_pass = false
classification = VALID_NEGATIVE_ROUTE_C_NO_SIGNAL_RESOURCE_AUTHORITY_GAP
```

这里的 `checker_pass=true` 只表示原始证据、哈希、结构和独立重算一致；`gate_pass=false`
表示 Route C 的 no-signal stop Gate 已触发，且 process-tree resource authority 有完整性
缺口。它不是继续 rank 或进入生产化的通过条件。

## 执行身份与证据入口

| 字段 | 值 |
|---|---|
| branch | `codex/20260822-task40-hybrid-side-factor-pc` |
| implementation/evidence HEAD before docs closeout | `7f1d8f978551f1aab44642c0a6501e3c71f4ef54`；这是文档收口前的实现/证据快照 |
| final docs commit SHA | 不在文件中自嵌，由提交后 handoff 精确报告 |
| formal Route C source | `b5b765ef02d52a877184b14fb8d72ad16a0432f8` |
| checker source | `7f1d8f978551f1aab44642c0a6501e3c71f4ef54` |
| formal root | `results/task040_v5_route_c_online_long_fgmres_mpi8_b5b765ef_retry1` |
| derived checker | `results/task040_v5_route_c_teardown_adjudication_b5b765ef/checker.json` |
| checker artifact SHA256 | `2db1741dfa0bdb877d1a3f548f66d521ed27328724f1f32d1fbd0b96c49f0a23` |
| V4 compact record | `task040_v4_1_exact_authority_compatibility_v1.json`；SHA `5ededd4bb9acfb9e4e3a403a410cecb37fb1490e7bf6056ca4644c7bfda7c36a` |
| worktree snapshot | pre-closeout-commit snapshot：V5 outcomes/`response_v6.md` 文档收口待提交；未改写 raw result、compact record、review、代码、测试或 master |

正式 root 是 fresh Route C root；旧 V4 root、V5-2 resource-blocked root 和早期无效尝试均不
被覆盖。checker 输出位于 formal root 之外，且没有读取 NPY 数值向量。

| 冻结身份 | SHA256 |
|---|---|
| official input | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical model | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected manifest | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| selected identity | `cfd5704b48bff980fa2d819f4deee9a59bb9a3db39bc24a70c53f42f067d39e9` |
| tracked probe manifest | `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` |
| resolved configuration | `f965c38abe08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883` |
| external canonical key list | `046afb0b3d3531f728dc958c1b0c8a321ffa51fb8a0e6ecf6834d462d5ab37e5` |
| resolved mode metadata | `dde523dc62c73f7bd50953958fde42d42d0cfd5756c16329b16915e13c4742da` |
| legacy beta metadata | `a58a3c6bc335bb5ae7f6b929a7abce4c193dedb27b115f17304091afb353318c` |
| frozen Task040 authority source | `112ac4913a531ae5c5aab941ac88f005a95b9dc4` |
| frozen spool producer source | `7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f` |

## 本轮提交链

以下是从 V5 review 进入 implementation/evidence HEAD 的完整提交 ledger；标题按 Git 原文列出：

| SHA | 内容 |
|---|---|
| `f1996d8ad218e6d61cac50b577dda11c06e345d2` | `docs(task040): add review v5 accelerated side-inverse funnel` |
| `c34b6c94f26bd10ecc071242d5919d907c625e08` | `docs(task040): register Case104 active research contract` |
| `1a4286401825881e67be3e04aed027783e3b7956` | `docs(task040): align Case104 V5 navigation` |
| `61b37a75b8fb6cb2ec140e6db4eb5e40f74a7ef1` | `feat(task040): add fresh bare-F authority producer` |
| `182b6bb1b19cbabc59a5210b46a4fd83368394f8` | `fix(task040): separate resolved and legacy mode metadata hashes` |
| `1105ba6a25a031f93145db682f128373b21d2a77` | `fix(task040): canonicalize frozen external mode order` |
| `5be39ac4fee0c0d0042be4e0d9cb679f72a39dd9` | `fix(task040): guard optional MPC cleanup` |
| `25573a6fabb2a1edcdc823d0158e9f4871a26d72` | `fix(task040): preserve V5 identity stop markers` |
| `fd7bea41d7d7b7869dd3ade4407129b00900ef7d` | `fix(task040): map replicated exact source rows to owners` |
| `56e005f0b98d4a6c516f176387c71b9f9cad4470` | `feat(task040): add V5 Route C online direction sampler` |
| `b5b765ef02d52a877184b14fb8d72ad16a0432f8` | `fix(task040): require Route C watchdog controls` |
| `e64f75df7402418ed07277d9bc7afba3e8af96e9` | `fix(task040): exclude completed watchdog teardown samples` |
| `7f1d8f978551f1aab44642c0a6501e3c71f4ef54` | `bench(task040): adjudicate Route C negative closeout` |

## V5-1 / V5-2 authority 语义

“authority”在这里指可以回答“这个 RHS/解属于哪个离散算子”的可核验证据，并不等于已经
通过生产化。旧 spool 的 action 是 `ResearchExactSideLuAction` 的 Woodbury-associated
语义；它的 modal RHS 是 `setup.coupling.bottom.positive_traction/negative_traction`
columns，external RHS 是 pre-action `components.C`，random RHS 是旧 owner-row formula。
这些旧值不能跨布局直接当作 current bare-`F` 数值 authority。

V5 current path 保持 frozen `full3d_one_cell_exact_schur` modal source definition，只取
selected columns 281/283；external 只构造生成 RHS 所需的两个 surface components，未物化
完整 C/D/H，也未调用 Woodbury inverse。Route C 实际使用显式 current bare `F` action carrier，
不消费 V5-2 未生成的 exact output packet。

| 事实 | 状态 |
|---|---|
| current operator | `explicit_current_bare_F` |
| modal source semantic | `full3d_one_cell_exact_schur`；不是 scalar-CG 替代 |
| physical DtN / Woodbury / C-D-H | 未构造；`C=D=H=0` |
| QEP | `0` |
| operator audit | `worker/operator_semantics_audit.json`，SHA `e7bfe8258dc359bd1fd58e31d3237e5dde6eebc47dc31985493faf378b0f5a91` |
| audit qualification | static path 与 source identity 已绑定；runtime residual/lifecycle 仍由各阶段 Gate 决定 |

## V5-2 fresh bare-F producer

formal root `results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41`（producer source
`fd7bea41d7d7b7869dd3ade4407129b00900ef7d`）原样保留。它是“部分完成、完整 authority
Gate 未通过”的 producer：

| producer inventory | raw observed |
|---|---|
| one-cell source factor | construction `1`；apply `2`；RHS columns solved `4`；同一 source factor 生命周期完成 `1→0`，并在 full-side setup 前销毁 |
| current-layout RHS/layout | 五个 current-layout RHS 已写出；owner-sharded canonical layout 与 `Gamma_L/Gamma_U` layout 已写出 |
| full-side diagnostic bare-F factor | 只到 `v5_bare_f_factor_setup_begin`；从未出现 factor-ready；要求的 full-side `1→0` lifecycle 未完成 |
| exact output / residual | exact-output packets `0`；bare-F residual 未运行 |
| authorized window/resource | `21600 s` wall window；process-tree peak `45432283136 B`（约 `42.31 GiB`）；swap authority readable 且为 `0` |
| V5 producer thresholds | preferred `59055800320 B`（55 GiB）；warning `62277025792 B`（58 GiB）；hard `68719476736 B`（64 GiB） |

它在 `21600 s` 的授权 wall/resource window 内停留在 factor construction，准确分类是：

```text
FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED
authorized 21600s wall/resource window exhausted during factor construction
```

这不是 64 GiB hard stop，也不是 numerical residual 或 operator identity fail；peak 未越过
55/58/64 GiB 阈值。进程组在 wall window 到期退出；OS 层清理不能改写成 PETSc full-side
factor 已完成 `1→0`。没有为它重跑或延长窗口，它只按 Review V5 触发 Route C fallback。

## Route C 数值信号

Route C 在 fresh MPI8 / 每 rank 1 thread / bottom-only 进程中只运行两个 RHS：
`external_dtn_coupling` 和 `fixed_random_repeat_0`。每个 RHS 使用连续 right-FGMRES、restart
32，并保存 16/32/64/128 的 explicit true residual 和 lower/upper canonical interface
residual trace。

| RHS | r64 | r128 | `log10(r64/r128)` | independent result |
|---|---:|---:|---:|---|
| `external_dtn_coupling` | `0.8906247440000827` | `0.9116861468870889` | `-0.010150598869495011` | no signal |
| `fixed_random_repeat_0` | `1.036891675911675` | `1.0585987178847864` | `-0.008997975654488713` | no signal |

独立条件是每个 `r128>0.9`、`log10(r64/r128)<0.05`，且没有跨至少两个 restart 的稳定共享
慢方向。两个条件均满足，`shared_slow_directions.count=0`、`stable_components=[]`；只有
三个孤立 correlation match，不能当作共享方向。两源的 `final_iteration=128`，conditional
256 的 `authorized=false`、`completed=false`。

因此 `route_c_no_signal_stop_gate_triggered=true`、
`route_c_positive_signal_gate_pass=false`，下一步是停止当前 coupled-response coarse family，
不是扩大 RHS、迭代次数或 rank。

## raw 与 derived watchdog/resource 口径

checker 保留 raw summary 与派生判断，不把派生值写回原文件。原 watchdog summary 的
`return_code=0`、`termination_reason=natural_exit`；checker 观察到外层 `rc=2`，它只对应
teardown telemetry/readability adjudication，不是 numerical exception。原 summary 记录
`sample_count=21297`、`authoritative_sample_count=21297`、
`all_status_readable=false`、`swap_authority_readable=false`、
`terminal_teardown_excluded_count=0`。

| 口径 | raw / derived 值 |
|---|---|
| timeline raw rows | `21297`；raw recorded authoritative true count `21297` |
| strictly excluded suffix | rows `21296, 21297`；均为 `v5_route_c_cleanup=complete`、unreadable、`post_sample_return_code=null` |
| suffix row detail | timestamps `12:45:24.624672` / `12:45:25.133539`；各 RSS `15327232 B`、swap `0` |
| derived non-excluded rows | `21295`；其中 `21293` readable，rows `5825,5826` 仍 live/unreadable |
| live unreadable rows | `5825,5826`，stage `v5_route_c_interface_projection_ready`，RSS `13245878272 B`，未被 terminal rule 排除 |
| raw max process-tree RSS | `30254075904 B`，低于 hard `48318382080 B`（45 GiB） |
| raw observed max swap | `0 B` |
| dedicated cgroup | `dedicated_cgroup_present=false`；dedicated-swap `0` 是诊断值，不是 authority |
| derived resource authority | `resource_authority_gate_pass=false`；失败是 readability/completeness，不是 RSS 越线 |

故 `teardown_adjudication_gate=true`，但
`process_tree_authority_complete_after_terminal_exclusion=false`、
`rss_authority_complete=false`、`swap_authority_complete=false`。这些失败与 raw bounds
`raw_observed_rss_below_hard_stop=true`、`raw_observed_swap_zero=true` 同时存在，必须分开
表达，不能把此次结果写成内存 hard stop 或完整 zero-swap authority pass。

## 构造与生命周期 inventory

| 项目 | raw observed |
|---|---|
| MPI / threads / route | `8 / 1 / bottom-only` |
| system / RHS | `system_created=true`；`rhs_vectors_loaded=2` |
| exact output | `exact_output_vectors_loaded=0`；`exact_output_vectors_consumed=0` |
| factored operator | `explicit_current_bare_F`；无 full-side exact factor |
| group diagnostic factors | construction `3`、destruction `3`、after `0`；`pc_setup_count=1` |
| QEP / PDE | `qep_calls=0`；`pde_solve=not_run` |
| external minimal path | conceptual kind `1`、surface components `2`、construction calls `2`、instances `4`、peak live `2` |
| forbidden objects | physical DtN `false`、Woodbury inverse `false`、C/D/H `0` |
| direction audit | interface projection/basis persistence observed and pass；owner-local canonical storage，`replicated=false` |

Route C 的 inventory 证明了本次 screen 没有加载 exact packet、没有建立 full-side factor，
但不证明 production side inverse 已通过。外部 checker 的 8 个 raw input hash 如下，便于
复核原始输入没有被文档覆盖：

| raw input | SHA256 |
|---|---|
| `memory_stage_markers.raw.jsonl` | `2d69f4d9db85e362951e993ced82dc0ffd38b469f1744a63eb9077e807fbd0d3` |
| `memory_stages.jsonl` | `70ca1470b9657d81cfb11755e84bb24a1dd850c9b019972053e94850c5b4351c` |
| official input | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| `process_tree_samples.jsonl` | `bba360ac7dfefab506e001cde96bf8f063df29a47a9a64aaccc6b70184ddae92` |
| `watchdog_summary.json` | `36adc74af7054540d8eeee8e734a0038324071789aedccebecd78c6aeb0c53f3` |
| `worker/route_c_manifest.json` | `0e572bd3fd4550a02e859804cbde2af3efb21f9b88feac43beb81591ded20409` |
| `worker/run_summary.json` | `0e572bd3fd4550a02e859804cbde2af3efb21f9b88feac43beb81591ded20409` |
| `worker_stdout.txt` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

## Route A/B/C ledger与后续 Gate

| 路线/阶段 | 状态 | 原因与下一步 |
|---|---|---|
| V5-1 semantics audit | completed with hash-bound raw audit | 只完成 source/operator 语义审计，不替代 residual/lifecycle Gate |
| V5-2 fresh bare-F authority | resource-blocked | `21600 s` factor-construction window exhausted；转 Route C |
| Route A dual/composition | `not_run_by_route_c_no_signal_and_resource_authority_gate` | 没有 fresh exact trace/lift qualification，且 Route C 已触发 stop |
| Route B response-enriched coarse | `not_run_by_route_c_no_signal_and_resource_authority_gate` | 没有建立 R1/R2/R3 train/holdout candidates |
| Route C screen | completed controlled negative | 两源到 128，无正信号；不能继续同一 family |
| bounded rank `64/128/256/512` | `not_run_by_route_c_no_signal_and_resource_authority_gate` | no-signal stop；不得增加 rank或RHS |
| packet-independent online rebuild | `not_run_by_route_c_no_signal_and_resource_authority_gate` | 未取得正的 bounded coarse |
| Level B / bottom bare-F candidate | `not_run_by_route_c_no_signal_and_resource_authority_gate` | 未运行，不是算法失败 |
| bottom A-side / same-config top / both-side | `not_run_by_route_c_no_signal_and_resource_authority_gate` | 未运行 |
| full Hybrid | `not_run_by_route_c_no_signal_and_resource_authority_gate` | 未运行；不得由 Route C inventory补写 |
| h3/p6 scaling | `not_run_by_route_c_no_signal_and_resource_authority_gate` | 未运行 |

Route C 的 stop Gate 优先于“继续完成 V5 漏斗”的一般授权。当前不补跑后续 formal，不扫描
512/1000 iterations，不使用旧 exact packet 追逐共享方向。

## 历史 root 隔离

| root | 分类 | 使用边界 |
|---|---|---|
| `results/task040_v5_2_fresh_bare_f_authority_mpi8_61b37a75` | controlled identity negative | producer identity stop raw；保留，不作为 numerical Gate |
| `results/task040_v5_2_fresh_bare_f_authority_mpi8_182b6bb1` | controlled identity negative | source/mode identity stop raw；保留，不作为 numerical Gate |
| `results/task040_v5_2_fresh_bare_f_authority_mpi8_1105ba6a` | `implementation_failure` | 保留原 raw；不作为 numerical/identity Gate |
| `results/task040_v5_2_fresh_bare_f_authority_mpi8_5be39ac4` | `implementation_failure` | 保留原 raw；不作为 numerical/identity Gate |
| `results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41` | `FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED` | 21600 s factor-construction window；保留，未生成 exact packet |
| `results/task040_v5_route_c_online_long_fgmres_mpi8_b5b765ef` | invalid operational attempt | 上一 turn 被中断；保留，不作为数值/资源 Gate |
| `results/task040_v5_route_c_online_long_fgmres_mpi8_b5b765ef_retry1` | current formal | 唯一 Route C raw authority；checker 派生结论来自此 root |
| V4 `..._a64d33e6` | implementation failure | raw global-row remap 跨 ownership 无效；不得引用 residual |
| V4 `..._1c68da98` | incomplete/superseded | 不得作为 formal 结论 |

## 测试与未运行测试

| 检查 | 结果 |
|---|---|
| V4 test313 | serial `12 passed`；MPI2/MPI4 各 `12 tests per rank passed` |
| V4 test314 | `22 passed` |
| V5 consolidated closeout focused | 资格化 activation 下 `94 passed, 2 skipped in 11.31s`；包含 test298、315、316、317、24、25、26 |
| V5 consolidated command | `python -m pytest -q src/test/test_298_task040_level_a_watchdog.py src/test/test_315_task040_v5_bare_f_authority.py src/test/test_316_task040_route_c.py src/test/test_317_task040_v5_route_c_checker.py src/test/test_24_repository_work_principles.py src/test/test_25_benchmark_contract.py src/test/test_26_documentation_contract.py` |
| qualified ABI preflight | exit `0`；activation `1`、Python `/home/Projects/MyFEniCS/.venv/bin/python`、PETSc `complex128`/`int32`、Linux DOLFINx/MPI stack |
| post-doc contract smoke | 文档改动后，test24+test25+test26：`26 passed in 1.35s` |
| V5 implementation lint/compile | 同一实现快照的 touched Ruff、compileall 已通过；本轮文档后另行执行 `git diff --check` |
| checker CLI | `rc=0`；`checker_pass=true`、`evidence_valid=true`、`gate_pass=false` |
| full repository pytest | `not_run` |
| additional PDE/QEP | `not_run`；Route C raw `qep_calls=0` |
| CI | 未声称 CI；以上均为本地 qualified activation 证据 |

文档收口后仅运行文档合同、仓库原则和 `git diff --check` 等轻量检查；不会因为文档修改
重跑 formal。`full repository pytest=not_run` 明确保留。

## 0.7 nm / 2 TB 边界

| 类型 | 本轮结论 |
|---|---|
| measured | h4 producer：process-tree RSS `45432283136 B`、wall `21600 s`、swap authority `0`；h4 Route C：两源 r64/r128、128-step interface traces、process-tree RSS `30254075904 B`、raw swap `0` |
| derived | Route C no-signal；末尾 teardown suffix 合法排除；resource authority completeness gap |
| predicted | `2TB_FEASIBILITY_NOT_ESTABLISHED`；没有 capacity prediction |
| not_run | 0.7 nm PDE、h3 scaling、bounded rank、packet-independent rebuild、Level B、bottom/top/both/full Hybrid |

`CURRENT_SIDE_INTERFACE_FAMILY_NO_POSITIVE_SIGNAL_NOT_A_CANDIDATE`。由于 Route C 是
no-signal stop，当前 side-interface family 不是后续 candidate。2 TB 是整机物理内存，不等于
单进程可用 RSS；本轮没有证明显式 bare `F`、local factor、coarse rank 或 allgather 随网格
增长的行为。因此不能宣称 0.7 nm production feasibility，也不能宣称其不可能。

## Selective merge 边界

`merge approval = NO`。V5 研究提交按依赖组理解：

| 组 | 文件/范围 | 边界、测试与合入建议 |
|---|---|---|
| production numerical/core | 现有 ordinary production path/default；V5 bare-F/helper 不构成 production qualification | ordinary 数值行为未改变；无 fresh production PDE，不提升本轮研究代码 |
| reusable runner/watchdog | `benchmarks/task040_level_a.py`、`benchmarks/task040_level_a_watchdog.py`、`src/solvers/hybrid_bare_f_authority.py`、`src/solvers/hybrid_route_c.py` | opt-in V5 route、markers、resource/cleanup wiring；不改变其他默认 route；test315/316与watchdog focused 支撑，仍需单独 review |
| checker/benchmark | `benchmarks/check_task040_v4_exact_authority.py`、`benchmarks/check_task040_v5_route_c.py`、test314/test317 | 独立读取 raw JSON/JSONL，不调用 solver、不读 NPY；checker rc0 是 evidence 合同，不是数值 pass |
| compact evidence/docs | V4 compact record、V5 outcomes、`response_v6.md` | 只记录 measured/derived/controlled-stop/not-run；不改写 raw root；文档提交需另行审批 |
| research-only | one-cell source audit、fresh bare-F diagnostic producer、Route C sampler、ignored roots与operator audit | 研究/诊断用途；不作为 ordinary production side inverse |
| do-not-merge | 旧 raw-row remap、a64 无效 residual、被中断 root、任何未运行下游结论 | 保留证据但禁止提升或混入 production |

## 最终边界

本响应没有给出新的 R/T/A、DoF、field、bottom/top/full Hybrid、h3 或 0.7 nm 数值。当前
最强可复核结论是：在给定 V5 frozen 5 nm h4 配置和 Route C 两源 screen 下，没有建立稳定
共享慢方向；同时 watchdog process-tree authority 有中段 unreadable gap。下一步必须等待
新的 review 决定是否改变算法路线或资源证据合同；在此之前不继续 V5-2→V5-10 下游，不把
本次 no-signal 写成生产失败，也不把 checker negative 写成 candidate pass。

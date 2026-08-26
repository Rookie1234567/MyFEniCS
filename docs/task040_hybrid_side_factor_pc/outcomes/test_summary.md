# Task040 测试与证据检查

本页区分已绑定的实现/focused Gate、V1-8 文档合同检查和正式 Run B。没有把缺少
`worker/run_summary.json` 的资源停止伪装成 checker 数值通过。

| 检查 | 结果 |
|---|---|
| test297 serial/MPI2/MPI4 | 各 `8/8 passed`；由未变更的 solver/core commit 绑定 |
| test298 watchdog/runner | `3 passed after package-invocation repair` |
| test299 raw checker tamper regression | `1 passed`；hash-valid status/gate 篡改不改变重算结论 |
| test300 Petrov / test302 core / test303 checker | 实现阶段通过 serial/MPI2/MPI4 focused selectors；详见对应提交审计 |
| V1-2 formal checker | attempted；因 resource stop 前没有 `worker/run_summary.json`，不能完成 numeric recomputation |
| raw watchdog resource audit | completed from `watchdog_summary.json`、markers 和 process samples；hard stop/peak/swap/process-group exit 可复核 |
| JSON parse | passed for compact record and frozen probe manifest |
| Markdown links / math delimiters | passed；无缺失相对链接、无双美元数学分隔符 |
| compileall | passed in qualified environment |
| git diff --check | passed |
| check_benchmarks --no-write | `302/302 passed` |
| Ruff / format | implementation stages passed；本轮仅修改 Markdown/JSON |
| full repository pytest | `not_run` |
| PDE/QEP | `not_run`；V3-1 component producer and V3-2 full-span component consumer completed |

## Review V5 当前检查与正式 Route C

| 检查 | 结果 |
|---|---|
| consolidated closeout focused | 资格化 activation：`94 passed, 2 skipped in 11.31s` |
| consolidated command | `python -m pytest -q src/test/test_298_task040_level_a_watchdog.py src/test/test_315_task040_v5_bare_f_authority.py src/test/test_316_task040_route_c.py src/test/test_317_task040_v5_route_c_checker.py src/test/test_24_repository_work_principles.py src/test/test_25_benchmark_contract.py src/test/test_26_documentation_contract.py` |
| included test scope | test298 watchdog、test315 producer、test316 Route C、test317 checker、repository principles、benchmark contract、documentation contract |
| qualified ABI preflight | exit `0`；activation `1`、Python `/home/Projects/MyFEniCS/.venv/bin/python`、PETSc `complex128`/`int32`、Linux DOLFINx/MPI stack |
| V5 checker | checker CLI `rc=0`；`checker_pass=true`、`evidence_valid=true`、`gate_pass=false` |
| explicit benchmark CLI | 资格化 activation：`python -m benchmarks.check_benchmarks --no-write`；`302/302 passed` |
| post-doc contract smoke | 文档改动后：`python -m pytest -q src/test/test_24_repository_work_principles.py src/test/test_25_benchmark_contract.py src/test/test_26_documentation_contract.py`；`26 passed in 1.35s` |
| formal Route C checker | source `7f1d8f978551f1aab44642c0a6501e3c71f4ef54`；raw read files `8`，无 NPY；独立重算 no-signal 与 teardown suffix |
| formal Route C raw | worker natural `rc=0`；Route C `ROUTE_C_NO_SIGNAL`；outer observed `rc=2` 仅对应 telemetry/readability adjudication，不是 numerical exception |
| final docs-related tests | 上述 consolidated run 已包含 test24、test25、test26；不另称 CI 或 full repository pytest |
| full repository pytest | `not_run` |
| additional PDE / QEP | `not_run`；Route C `qep_calls=0` |

Route C 后续 bounded rank、packet-independent rebuild、Level B、bottom/top/both/full Hybrid、
h3 和 0.7 nm PDE 均为 `not_run_by_route_c_no_signal_and_resource_authority_gate`。没有把
普通 focused tests、checker 通过或 no-signal stop 写成 production/CI 通过。

V1-2 Run B 的独立 checker 命令为：

```text
python -m benchmarks.check_task040_v1_run_b --run-root results/task040_v1_2_v1_3_run_b_mpi8_16ecba56
```

它因 `worker/run_summary.json` 不存在而不能完成完整 checker schema；这与 watchdog 的
resource hard stop 一致。compact record 只记录 raw watchdog/marker/process evidence 和
该 checker blocker，不伪造 V1-2/V1-3 numerical Gate。

## V2-A1 producer 与 checker-fix

| 检查 | 结果 |
|---|---|
| producer formal | 已完成一次；source `942c43881e4162085348c48b09c79fbbdac18cd9`，未重跑 |
| 首次 checker | implementation schema failure；physical report 缺少 `finite` marker，producer raw 保留 |
| checker 修复 | commit `bd70ab98009de2a2b45561793be6418a6a9bfcc8`；改为从真实 physical schema 的显式数值字段重算 finite；未放宽任何数值阈值/Gate |
| test306 serial / MPI2 / MPI4 | 各 `6/6 passed` |
| fresh independent checker | `rc=0`；packet_complete 与全部 checks 通过 |
| packet | 34 files / 653,804,117 B；24 owner-row shards |
| resource | peak `28.706954956054688 GiB`，preferred `<=45 GiB` pass，swap `0`，55 GiB 未触发 |
| V2-B2 consumer formal | source `40b25d3281d9ce1707f6069607bfdbbf6a3ab48d`；resource/remap/one-apply implementation subset通过；FGMRES 数值负，分类 `THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT` |
| V2-B2 formal process wall | `1077.3351624270435 s`；producer component wall `1202.5501016210765 s`，两者不相加为 full workflow time |
| V2-B2 immutable checker | `rc=2`；expected numerical negative，resource/identity/lifecycle 独立重算通过；原始 watchdog teardown false 未覆盖 |
| V2-C/D/E/F | `not_run_by_gate` |

fresh checker 读取原 packet，不修改 producer 数值 artifact；输出为
`checker_recomputed_after_fix.json`，首次空的 `checker_recomputed.json` 仍作为失败现场保留。
本阶段没有把 checker schema 修复误写成 producer 或算法负结果。

## V2-B2 与 V2-G 轻量检查

| 命令/检查 | 实际结果 |
|---|---|
| qualified JSON parse（consumer compact + frozen probe manifest） | `passed`，2 files |
| 变更 Markdown 链接/双美元数学分隔符检查 | `passed`，13 files |
| `python -m pytest -q src/test/test_183_development_model_registry_markdown.py` | `5 passed` |
| `python -m benchmarks.check_benchmarks --no-write` | `302/302 passed` |
| immutable consumer checker（formal root + packet，expected source `40b25d328...`） | `rc=2`；resource pass，数值分类 `THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT` |
| `git diff --check` | `passed` |

仓库通用 `src/test/test_26_documentation_contract.py` 同时报告 `18 passed, 1 failed`；唯一
失败是其既有 numbered-case 白名单未包含已经存在的 `104_5nm_hybrid_side_factor_pc`
目录，不是本轮 Markdown/JSON 内容失败。本轮不改测试/代码，因此该基线问题单独保留。
代码 focused 20 tests、Ruff、format、compileall 沿用同一
`0919ed2fa3bd1541f543057721fff84fa110f3d4` 的已通过结果；文档改动没有触发重复
heavy/MPI/PDE。

## V3-1 augmented packet

| 检查 | 结果 |
|---|---|
| augmented checker source / artifact | `9e79443ccf808372feb24160d89c13eb9f0ac4eb`；`checker_recomputed_augmented_9e79443c.json` SHA `ddace4647e2dddefc72fc92cb2af4cf3f1a7c22b3cc258f064bf6d17b3860267` |
| augmented CLI | rc `0`；JSON 可序列化；`packet_sufficient=true`；`COUPLED_INTERFACE_ALGEBRA_EVIDENCE_VALID` |
| test308 final | serial `6 passed`；MPI2 `3 passed, 3 skipped`；MPI4 `3 passed, 3 skipped` |
| current complete documentation-contract file | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_26_documentation_contract.py`；`13 passed, 1 failed`，唯一失败仍为 Case104 registration gap；未修改 `test_26` |
| augmented formal evidence | manifest/run/watchdog SHA 与 source 绑定；factor `3→0`；RSS/swap `28.426311493 GiB / 0 B`；joint rank `776`，condition `72530856.63880321` |
| legacy preservation | immutable V2 packet 仍记录 `COUPLED_PACKET_INFORMATION_INCOMPLETE`；未覆盖首次错误 artifact |
| V3-2 formal consumer | source `c11aea058d01e86052d5490a71575a375e3fe207`；worker natural rc0；独立 checker rc2，分类 `COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL`；evidence_valid=true，resource/identity/lifecycle checks 全真 |
| V3-2 formal resource | peak `28,044,996,608 B = 26.118938446045 GiB`；swap `0`；1770/1770 authoritative samples；process-sample wall `892.680907273083 s` |
| V3-2 numerical screen | 五源 phase1 `r4/r8/r16` 均 finite；r16=`0.9706859881–0.9832307912`；conditional32/64=false；first preferred=null |
| V3-2 compact/evidence | record JSON parse、raw/checker hash binding 和 V3 outcome 已更新；首次 checker rc2 artifact 保留，修复后 checker 不改变 raw |
| V3-2 focused checker/runner regression | `python -m pytest -q src/test/test_312_task040_v3_2_checker.py src/test/test_311_task040_v3_2_runner.py`；`36 passed` |
| V3-2 immutable checker | `python -m benchmarks.check_task040_v3_full_span --run-root results/task040_v3_2_full_span_mpi8_c11aea05 --packet-root results/task040_v3_1_middle_schur_producer_mpi8_fa1720d8/worker/interface_packet --expected-source-sha c11aea058d01e86052d5490a71575a375e3fe207`；`rc=2`，预期数值负结果 |
| documentation registry | `python -m pytest -q src/test/test_183_development_model_registry_markdown.py`；`5 passed` |
| full documentation-contract file | `python -m pytest -q src/test/test_26_documentation_contract.py`；`13 passed, 1 failed`，唯一失败仍是已有 Case104 numbered-case registration gap |
| V3-8 benchmark no-write | `python -m benchmarks.check_benchmarks --no-write`；`302/302 passed` |

## Review V4-1 final checker and focused tests

| 检查 | 结果 |
|---|---|
| test313 serial | `12 passed` |
| test313 MPI2 | `12 tests per rank passed` |
| test313 MPI4 | `12 tests per rank passed`；仅有 pytest 临时目录清理 warning，不影响结果 |
| test314 checker | `22 passed` |
| Ruff / compileall / diff-check | 均通过 |
| documentation contract + repository principles | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_24_repository_work_principles.py`；`20 passed, 1 failed`；唯一失败是既有 Case104 numbered-case registration gap，未修改测试 |
| committed V4-1 checker | `rc=0`；`37/37 checks`；`105 read files`；无 NPY 读取 |
| formal MPI8 | metadata-only controlled identity stop；未运行 numerical solver/PDE |
| full repository pytest | `not_run` |
| CI | 未声称 CI 通过；以上为本地证据 |

V4-1 在构造 system、裸 `F`、interface mass、Vec、factor、QEP 和 PDE 前停止。除唯一的
`canonical_source_binding` 外，冻结身份检查通过；V4-2 至 V4-10 以及本轮额外 PDE/QEP 均
`not_run_by_v4_1_identity_gate`。证据与状态见
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

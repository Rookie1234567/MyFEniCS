# Test and evidence summary
## 2026-09-23：Review V6 F3c4 收口

F3c4 两个轻量 mock 模块最终 `99 passed`, `rc=0`，父侧 wall 约 `11.40 s`；第一次失败的 cap 断言与历史 RHS-manifest fixture 记录保留，后续只修测试期望/fixture，production validator 未改。四次 5 nm fixed-eight service 尝试不是 pytest 通过：前三次分别是 release 诊断接线错误、condensed factor 接口错误、旧 RSS cap 停止；cap64 第四次有 16 个响应但 2/8 top 配对超过 `e_x/e_A <=1e-8`。见 [V6 outcome](transfer_fix_5nm_24h_v6.md) 与 [machine record](records/task041_v6_transfer_5nm_24h.json)。本轮不运行 full repository pytest、PDE、QEP、F3a 或新 ABI。

## R3i3：MPI8 tiny-FE 受控负结果

一次 MPI8 场的 ABI 八 rank/CPU1–8 通过；旧 full p4 bottom/Q transfer consistency 为 `1.3116919128020489e-11 > 1e-11`，原 p4 A4 为 `6.795828778707217e-11 <= 1e-10`。新 cell-condensed、PC、side.apply、top 未运行，因此不能写成凝聚实现失败或响应/速度资格。

| 项目 | 结果 | 限制 |
|---|---|---|
| 资源 | tree/authority 峰 `4636389376 B`；dedicated current `2565689344 B`；PSS/USS `2828743680/2582614016 B`；swap/pswp `0` | 126 samples；PSS/USS 稀疏；minAvailable `2142846394368 B` 高于 `412316860416 B` |
| 终态 | worker `rc=1`、termination null、unit `68.728670s`、专属树清场 | 非正常求解完成，不是资源 watchdog stop |
| NUMA | ABI rank assert 派生 CPU1–8；`numa_maps` policy=`default` | FE 私有页首触未保存，严格 membind0 未资格化 |

原始 stdout、summary、memory stages、journal 与 hash-bound test/launcher 见 [R3i3 compact v2](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3i_mpi8_side_20260922/run_20260921T195057.555038315Z/r3i3_compact_v2.json)。V5 ledger 本次只追加一次 `68.728670s`；R3h5/R3h6 通过历史与 R3h1–3 诊断负结果均保留。

## R3h8：p4 凝聚组件与 tiny FE 证据（R3–R6尚未完成）

通俗地说，p4 单元凝聚先消去单元内部未知量，解较小的保留耦合系统，再回代恢复完整 FE/端口修正，并用原 A4 和完整残差检查；这不是降低精度的近似。p6 已凝聚，不重复凝聚；cell_condensed 只在显式后端选择时使用，默认 full 与正式 runner 不变。

R3c 是早期 synthetic 单端口资格，R3d2 才证明双端口/preallocation；R3f 是 p4/port 完整逆对照，R3h5 是 side/backend 回归，R3h6 才是同一 side/layout old/new Q/PC tiny FE。R3h6 数值、A4/backsolve、全程 RSS/专属 cgroup、稀疏 PSS/USS、swap 和清场通过；167 秒与82秒不是提速结论，也不是正式 MPI8/13.5/5/2nm资源资格。R3h1–3 的 rc59、gdb、trace 保留，首轮 ABI NameError 后仍跑 pytest 的观察不计资格，Cython 底层成因未证明。详见 [R3h8 record](records/task041_v5_condensed_speed.json) 与 [R3h7 compact](../../../results/task041_review_v5_cpu_numa_condensed_speed/r3h_validation_20260921/r3h7_compact.json)。R3h8 已一次追加 `288.010923037 s`，累计 `7600.153469588 s`；后续文档纠偏未再计费。R3–R6 尚未完成。

## Review V5 R1i：2666复测证据（历史快照）

R1i 不是 pytest、PDE、MPI 或 QEP 测试；它只复核 BIOS `Auto→2666 MT/s` 后的有界 CPU/NUMA 诊断。四组路径三窗为：local socket0→node0 `35.63788506479269 / 35.664033252580786 / 35.6967308849817`、local socket1→node1 `35.648371306083156 / 31.66995975917892 / 11.024863223982754`、cross socket0→node1 `23.562553384022838 / 22.956933903624012 / 13.10402684910857`、cross socket1→node0 `23.408224743881927 / 22.924688775860275 / 21.682633764800535 GB/s`。node1路径仍骤降，CPU1未准入；首窗正常不算修复。
两批 `rc=0`、清场完成；43+43硬件/BMC文件、16 DIMM、688对温度值差值 `[-1,+1]°C`。六个 TEMPLO 与两个 TEMPMID 的原始事件、PCI/BMC异步差和SHA见 [R1i tracked compact](records/task041_r1i_2666_retest_20260921.json)，ignored 原件为 [compact v3](../../../results/task041_review_v5_cpu_numa_condensed_speed/r1i_2666_retest_20260921/r1i_2666_two_batch_compact_v3_20260921.json)，未改阈值或保护，R2仍 blocked。

## Review V5 R1h：硬件/调度诊断（历史，已由R1i更新）
R1h 不是 pytest、PDE、MPI 或 QEP 测试。固定 driver 父侧 `CLOCK_MONOTONIC` wall 为 `629.724913916 s`、rc0；16/16 worker 各完成3×60 s。CPU socket0 的 OS CPU1–8 → memory node1 三窗为 `22.648688106036644 / 21.977584096329075 / 7.395682818558859 GB/s`，CPU socket1 的 OS CPU25–32 → memory node0 为 `19.789193732901627 / 19.759391333017003 / 18.843317623093906 GB/s`；前者约降67.35%，后者约降4.78%，因此 `CPU1_NOT_QUALIFIED_SOCKET1_THROUGHPUT_ANOMALY_REPRODUCED_NO_UNIQUE_CAUSE`，不把 rc0 写成硬件通过。

两阶段开始与 near-end 均为预期远端 node 的 `8/8`，活跃 Bzy_MHz 约 `3600.33/3599.55`、CoreThr=0。22 hardware samples、110 final-read、44×48行 MSR 输出均成功绑定；358 resource samples 的最低 MemAvailable 为 `2114795454464 B`，swap `299008`、pswpin/out `0/73`、新增 global delta 0。16 worker 的 minor/major/stime delta 均为0，CPU0/CPU1 最大 wait 比为 `0.0009933352281917688`/`0.0008195138298330328`，共享 cgroup 的 `nr_throttled/throttled_usec/high/max/oom/oom_kill` 均为0；完整 process-tree/cgroup RSS 峰未测。所有 e24 为0仅削弱持续外部 MEMHOT，不能排除内部热控或采样间瞬态。结果与 hash 入口见 [R1h outcome](cpu_numa_condensed_speed_v5.md)、[R1h compact](records/task041_v5_cpu_numa.json)。R2–R6、R3、PDE/MPI/QEP 均 `not_run`。

## Review V5 R1d-B：有界匹配负载（非测试）

本批不是 pytest、PDE 或 MPI 测试，而是一次获准的 CPU/NUMA 诊断负载。driver 使用固定脚本 SHA `37bea39b72656f2c8e0ce3bb293bbfc8ff41d7a17fa28fd1fc0cedf90976a584`，父侧 `CLOCK_MONOTONIC` wall `630.795106023 s`、rc0；16/16 worker 各完成 3×60 s。CPU0/socket0/node0 三窗总吞吐为 `32.173939890 / 32.183022717 / 32.190473984 GB/s`，CPU1/socket1/node1 为 `33.263204952 / 28.338248830 / 9.265976385 GB/s`，第三窗相对首窗约降 `72.14%`，故 `CPU1_NOT_QUALIFIED_SOCKET1_THROUGHPUT_COLLAPSE`，不能写成 driver 成功即硬件通过。

启动/near-end NUMA 均为两侧各 `8/8` local；活跃 turbostat 为约 `3.6 GHz`、CoreThr=0，DIMM 峰为 `64/78°C`、状态 ok。R2–R6、R3 p4 草稿测试和新负载均 `not_run`。完整 raw JSONL、21 个硬件 raw、600 个 turbostat 采样帧、资源 Gate、PID 清场和 ledger 绑定见 [R1d-B compact](records/task041_v5_cpu_numa.json) 与 [R1d-B outcome](cpu_numa_condensed_speed_v5.md)；不把本诊断混入既有 pytest 通过数。

## C2d：C2 raw 的离线 checker 复核

C2d 没有重新运行 service、MPI、PDE 或 pytest；它只复核已有 C2 raw，并对摘要中的
`common_layout_equivalence.apply_count` 做了 ignored 派生修正 `8 → 16`。原始 service
仍是 `PAIRING_SETUP_FAILURE` / `service_boundary_failure`、systemd exit3；离线派生视图
才是 `COMMON_LAYOUT_EQUIVALENCE_PASS`。结果不是新的 service 成功或 full consumer 资格。

| 项目 | 实际证据 |
|---|---|
| raw 完整性 | 16 audits、8 pairs（每侧4）、16 response manifests/128 shards、16 diagnostic manifests/128 shards |
| 离线 checker | 原 summary SHA `3085fae95fbf1ca198a25f6af743b3b22e054f11e0cbfe2def528137396a74ac`；派生 SHA `8219a9777b866f5d09ebc983eeefc2b392588b8fedb0164ef8154dfe9419a93f`；唯一字段差异为 `apply_count` |
| 重算响应门 | `max e_x=3.0316012438358734e-9`、`max e_A=8.229180550916894e-9`；bottom residual max `0.009208186034505522/0.009208186034505515`，top `0.009453705395968726/0.009453705395971615`（legacy/optimized） |
| C2 raw身份 | unit `task041-c1c-common-layout-equivalence-5b57375d.service`，Invocation `a8eac10299194a9a98d0ed18adfdac00`，CPU1–8、数学线程配置1；runroot与完整路径见 compact/index |
| C2 service 收尾/资源 | public run_summary nested/total wall `6121.790274919942/6124.439315116033 s`；service phase `6125.609746061964 s`、parent-from-unit `6125.770416472 s`、finalizer elapsed `6126.252856925 s`（来源层级分开、不相加）；全树 RSS 峰 `51501744128 B` / cap `53221163008 B`，job/global swap delta `0`，cgroup 清空、post-hash/ledger 完成；原 service 仍 exit3/service_boundary_failure |
| C2 C3 / P / PH / PC | 原 `consumer_summary.setup.admission_audit.sides.*.balanced_pc` 的 P/PH global relative 均 `0`；PC relative bottom `6.149584203535856e-13`、top `2.2220413770924415e-13`（门 `1e-8`），PC call count `266/298`；C1b/R2e tiny-FE 也有 P/PH=`0` 的独立证据 |
| C1b serial/MPI2 | test346 v2 alternation serial `1 passed`、MPI2 empty-owner/alternation 每 rank `3 passed`；[serial evidence JSON](../../../results/task041_side_balh_component_audit/c1b_c2_validation/serial_test346_v2_alternation.json) SHA `6317ee2a0f9cfc6e061c1a341d447338d6b3373adb90bb1737b7136c15ee8f32`；[MPI2 evidence JSON](../../../results/task041_side_balh_component_audit/c1b_c2_validation/mpi2_test346_v2_empty_owner.json) SHA `13d0242fc7f32514449ebcbc2e9b6e6e4fda8aa8b38e5d9bb72a2fe73cd242b7` |
| C2c 轻量复核 | `27 passed, 21 deselected`；[selector log](../../../results/task041_side_balh_component_audit/c2c_validation_20260916_5b57375d/test351_selector.log) SHA `1db9a11707c900a4b2c7a7c1da80b5eb684c88d722f22cb5912f6534cf041a4d`；对应离线复核 wall `2.714138631 s`，未重跑旧 FE/MPI |
| 通知/采样边界 | 完成通知未通过既有 RPC 唤醒主控是通知事故；sampler 连续，非资源采样断档 |
| 相关源码 | C2c checker source `5b57375d50c777abb5d0096db843095683f49b5f`；计数修复已提交 `caeb678225d63f16bd95272ba60b08b16caf36af` |
| 账本 | C2c ABI/static/selector/offline 父侧 wall 合计 `7.820470533 s`，本次文档 JSON/diff 检查另计 `0.066910437 s`；唯一 ledger used `17762.27669256989 s`，shared remaining `3837.723307430111 s`，SHA `e5803851257eabd643be7048e81fae2c8d5e9957c4309c7f433b75ddd3805e27` |

命令、父侧 `CLOCK_MONOTONIC`、返回码、原始日志和 checker 结果见
[C2c offline index](../../../results/task041_side_balh_component_audit/c2c_validation_20260916_5b57375d/c2c_offline_review_index.json)
；正确路径为 `results/.../c2c_validation_20260916_5b57375d/c2c_offline_review_index.json`。
这项离线结果不改变旧 `PAIRING_IDENTITY_UNPROVEN`、S1f 双侧 RSS 受控停止，也不启动
13.5 nm、full 5 nm、full Schur/outer/recovery/RTA、QEP 或额外/重复 optimized run。

## V4-A0 历史启动前阻塞（保留）

以下仅记录 A0 当时的安全同步和宿主只读 Gate；另一项 Full3D heavy 仍在运行，因此当时 V4 C1 尚未实现，
C1–C3、MPI8 主响应 `0/16`、响应 pairs `0/8`，以及 layout/P/PH/PC/response 等价均为
`not_run`。本阶段没有运行 pytest、MPI、PDE、service 或 ABI 数值栈探针，也没有新的 RSS/
speedup 数据；这不改变历史 R1/R2 测试和旧负结果。最终只做了 `python -m json.tool`
与 `git diff --check`，均 exit `0`，父侧 `CLOCK_MONOTONIC` wall=`0.063355920 s`；
账本前次静态核对后又补记四次此前遗漏的失败：按 `tool_reported_command_duration` 一次
追加 `0.180794456 s`；当前 used=`11145.889606652894 s`、shared remaining=`10454.110393347106 s`，
ledger SHA=`1473ad466c95a05bf4f4c186864d03f3304f58b904873a9ae6ecca08a7535953`，原始记录见
[`v4a0_final_json_diff_check.json`](../../../results/task041_side_balh_component_audit/v4a0_preparation_20260916_b5d0a39e/v4a0_final_json_diff_check.json)。
此前四次静态失败的 execution id、UTC、exit1、duration 和原始原因保留在 compact
`documentation_checks`；两次最终静态命令仍为通过记录，不把四次失败合称为测试失败。

| 证据 | 入口 |
|---|---|
| V4 compact | [common_layout_equivalence_v4.json](records/task041_common_layout_equivalence_v4.json) |
| 宿主保护快照 | [active_heavy_protection.json](../../../results/task041_side_balh_component_audit/v4a0_preparation_20260916_b5d0a39e/active_heavy_protection.json)，SHA256 `8b3b1ce344bfcb66ad313db6fd714f01fda53375cbb6509432577b39541ff98d` |
| V4 review | [review_report_v4.md](../review_report_v4.md) |

## V4 计划边界（未执行）

后续获准后才执行 C1 小 fixture、C2 一次 MPI8 同布局组件运行和 C3 八对响应比较；总主响应
为 16 次，不能把历史 R2/R2g 的 8+8 分侧结果写成 V4 已通过。`PAIRING_IDENTITY_UNPROVEN`
与 S1f 双侧 RSS 受控停止保留为独立历史状态。

## S5a S1f 结果整理

S1f 的固定八 RHS baseline 在代表性 RHS 前因 `process_tree_rss_limit` 停止，`0/8`；S5a
整理阶段未再运行 PDE/MPI；已审 S1d/S1c6 证据中的 105 focused pytest、6 targeted
pytest 与 Ruff/compileall/diff 静态检查分开记录，本阶段未运行 full repository pytest。外层原始 evidence 与 compact
索引见 [S5a report](schur_speed_v2.md)、[S0/S1 compact](records/task041_schur_speed_v2.json) 及
`results/task041_side_balh_component_audit/s5a_s1f_resource_stop_20260915_1c1d36b1/s5a_completion_evidence.json`。

| 项目 | 结果 |
|---|---|
| S1f numeric/coverage | `not_run` / fixed RHS `0/8`；停止点 `top_factor_setup_begin` |
| S1f resource | outer RSS `53331742720 B` > cap `53221163008 B`；job swap `0`、global baseline `8192 B` 且新增 delta `0`，终止原因为 RSS cap |
| S1f lifecycle | public PGID gone，但 parent `pre_exit_members_clean=false`；之后 systemd 清空 cgroup，finalizer 保留 `service_boundary_failure` |
| prior source/tests | source `1c1d36b168bfb3939314ee2faf5b943cca804382`；已审 focused/static/服务资格证据不因 docs-only 收口重跑 |
| full suite/CI | `not_run` |

## S1d/S1c6 可审计证据入口

| 证据 | 实际路径与 SHA256 |
|---|---|
| S1d result index | `results/task041_side_balh_component_audit/s1d_validation_20260915_3890cdd/s1d_result_index.json`；`1b1f76c52de24a81ed47bb8086b190f9481bee97cf04db7d5164198ff4b09f53`（105 focused + 6 targeted/static） |
| S1c6c qualification | `results/task041_side_balh_component_audit/s1c6_service_qualification/s1c6c_qualification_summary.json`；`43e2d3a1a8879943d46f09b1fa9c2f200088f64049dc6e7b0b72e627853466a5` |

S5a 最终文档合同检查使用 native activation，`python -m pytest` 为 `15 passed`、exit `0`；
ABI/JSON/8 条 manifest 绑定核对与 `git diff --check` 同一外层
`CLOCK_MONOTONIC` wall=`1.110528022 s`、exit `0`。原始命令输出与哈希摘录见
`results/task041_side_balh_component_audit/s5a_s1f_resource_stop_20260915_1c1d36b1/s5a_document_validation_final.json`。
首次同一文档检查由独立公开命令 `exec-8aeefee0-c65b-41ba-840e-96497cc1c563`
保留为 `1.125902230 s`，第二次为 `exec-264fa7da-838b-43d7-86b8-6cbe117ba429`、
`1.110528022 s`；两次均分别计入 shared；最终账本 used=`2881.0536036838917 s`、
SHA=`902e8bbd40c5df4cbfef0a1f9c501d33575516e084fed6a10c54c275add26f7a`。不把 pytest
内层时间或 nested CPU time 写成完整 wall。

## H4 当前结果证据与边界

H2/H3 的正式 raw comparison 已由 frozen comparator 独立重算；本轮 H4 不重跑
PDE、MPI、producer、QEP 或 full repository pytest。H3 comparator 命令在 native
环境退出 `1`，但 `numerical_pass=true`、`comparison_contract_pass=true`；exit1
来自 candidate public supervisor/resource evidence 缺失，不是数值失败。原始结果和
`TASK041_SIDE_BALH_NUMERICAL_OR_RESOURCE_FAIL` 分类保持不变。

| 证据 | 结果与绑定 |
|---|---|
| H2 13.5 nm comparison | `TASK041_SIDE_BALH_COMPARISON_PASS`；80 channels 全行保留；artifact SHA=`c8d3c7bf259d8d78a0b8d1152f7184216156824bf764c8366604fb72d374387d` |
| H3 5 nm comparison | numerical/comparison contract PASS；600 channels、4 canonical role 和 8 checkpoint shard 均有 hash-bound raw evidence；comparison SHA=`7c3838fe565c10fac0b880b0fc2d7dce99f8cfcfef88d56e4f820df1f2f6a969` |
| H3 resource/exit | consumer resource false；public parent/summary 缺失，orphan terminal row false，TERM/KILL 与 notification failure 如实保留；最终分类 `RESOURCE_COMPARISON_INCONCLUSIVE` |
| H4 文件 | [中心报告](side_balh_transfer_v1.md)、[compact record](records/task041_side_balh_transfer_v1.json)、[completion audit](../../../results/task041_side_balh_component_audit/h3h_final_20260914_51694bbc/h3_completion_audit.json) |
| H4 未运行 | Full3D secondary、新 producer/QEP、全仓 pytest、CI；只做文档/JSON合同检查 |

H3 candidate 的 worker 数值结果和内部 cleanup 仍保留；不能以缺失的 public
summary 抹掉数值结果，也不能用 worker-local `rss_drop` 补成 MPI 全树资源通过。

## H3f-B 已审核的 focused evidence

| 范围 | 结果与绑定 |
|---|---|
| focused tests | `96 passed`；最终 fixture `61 passed`；MPI2 每 rank `1 passed` |
| 静态检查 | scoped Ruff、compileall、`git diff --check` 通过 |
| 证据绑定 | [`h3f_b_validation_summary.json`](../../../results/task041_side_balh_component_audit/h3f_b_validation_summary.json)、[`h3f_b_result_index.json`](../../../results/task041_side_balh_component_audit/h3f_b_result_index.json)；index 中 11 个 `source_files` hash 与最终源码一致 |

这些是最终源码上的轻量/接口证据，不替代 H2/H3 正式 PDE；full repository pytest、CI 和
未运行的 Full3D secondary 仍明确为 `not_run`。

## H4 文档检查

| 命令 | 结果与原始日志 |
|---|---|
| `source .venv/bin/activate_myfenics_native.sh && python -c 'import json,sys,numpy as np; from mpi4py import MPI; from petsc4py import PETSc; import basix,dolfinx,mpi4py,petsc4py; print(json.dumps({"marker": __import__("os").environ["MYFENICS_NATIVE_COMPLEX_ENV"], "executable": sys.executable, "python": sys.version.split()[0], "numpy": np.__version__, "mpi_size": MPI.COMM_WORLD.size, "petsc_scalar": str(np.dtype(PETSc.ScalarType)), "petsc_int": str(np.dtype(PETSc.IntType)), "basix": basix.__file__, "dolfinx": dolfinx.__file__, "mpi4py": mpi4py.__file__, "petsc4py": petsc4py.__file__}, sort_keys=True))'` | exit `0`；[`h4_doc_abi_preflight.log`](../../../results/task041_side_balh_component_audit/h4_doc_abi_preflight.log) |
| `source .venv/bin/activate_myfenics_native.sh && python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py` | `15 passed`，exit `0`；[`h4_document_contracts_pytest_final.log`](../../../results/task041_side_balh_component_audit/h4_document_contracts_pytest_final.log) |

## 历史 response_v1 docs-only

历史 response_v1 阶段只修订 evidence 文档和 checkpoint v2；没有重跑 pytest、MPI、PDE、
QEP、MUMPS、FGMRES、full suite、Ruff 或 compileall，没有启动新 heavy。
以下为此前最终代码阶段已审核的 focused evidence，不把主控审核代替为
测试结果。

## P1 sampled exact-side

| 命令/范围 | 结果 |
|---|---|
| python -m pytest -q src/test/test_task037c_exact_one_cell_traction.py -k sampled_direct_relift_contract | 6 passed, 16 deselected |
| python -m pytest -q src/test/test_343_task041_exact_side_consumer.py -k 'sampled_contract_requires_selected_mode_packet_manifest or fresh_sampled_contract_is_bound_to_current_manifest or run_task041_consumer_full_mock_keeps_release_and_authority_evidence' | 6 passed, 35 deselected |
| real P2 serial: test_real_p2_double_floquet_endpoint_and_local_interface_identity | 1 passed |
| real P2 MPI2: mpiexec -n 2 同一 node | 每 rank 1 passed |
| compileall / diff-check | pass |
| Ruff | 仅历史 baseline，无 fix |

P1 证明 fixed 8-column sampled direct relift、full operator transfer 和
identity mapping；没有缩小最终 operator，也没有改变物理或 solver identity。

## P2 sparse telemetry 与 terminal race

| 命令/范围 | 结果 |
|---|---|
| python -m pytest -q src/test/test_344_task041_public_supervisor.py | 42 passed |
| python -m pytest -q src/test/test_263_task038_launcher_contract.py::test_task039_default_sampler_requests_smaps_without_changing_fake_sampler | 1 passed |
| TemporaryDirectory + supervisor._run_phase + real mpiexec -n 2 teardown smoke | returncode=0；process_group_gone=true；sample_count=6；swap=0；smaps_complete=1 |
| compileall 两个 production 文件及 test_344 | pass |
| diff-check | pass |
| Ruff | 无新增诊断；仅历史 baseline |

smoke 使用资格化环境、Barrier/sleep child 和真实 process-group teardown，
不是 PDE。途中 fake probe 的缺目录和参数名仅是 implementation harness
纠正，不构成数值或正式运行证据。

## P3 lifecycle 与 modal condition

| 命令/范围 | 结果 |
|---|---|
| test_344 selected focused nodes | 4 passed，0.59 s |
| test_241 selected focused nodes | 3 passed，1.42 s |
| packet lifecycle focused node | 1 passed，1.59 s |
| compileall / diff-check | pass |
| Ruff | 15 项历史 baseline，无 fix |

P3 的 packet consumer cleanup、terminal authority transition 和 singular
value condition path 均有 targeted evidence；没有以这些测试推断 heavy
性能改善。

## ABI、未覆盖与证据边界

上述测试均使用 native complex128/int32 栈，五个数学线程为1。M800/M1200
正式 roots 的 residual、physics、resource 和 lifecycle 另由 raw
summary/marker/telemetry 记录；本轮不复制大型对象。

没有 post-change QEP performance isolation，没有 M1600/2 nm formal，也没有
5 nm MPI1 full equivalence。M1200 已运行一次受控 consumer continuation，
其 own physics negative；不能写成“本轮未运行”。

M800/M1200 own physics negative 不被测试或 scalar comparison 改写为 pass；
workflow peak=max(producer,consumer)，producer 退出后才启动 consumer。
当前 M1200 candidate 采用更严格的 224/256 GiB workflow envelope 和
21600 s consumer phase cap；它不替换 task.md 原 1.50 TiB 历史规划。

## Task041 V3 / Response V4 文档收口（R4a/R4b，2026-09-16）

整轮已经包含 R1 实现、R2c A1/A2 优化、轻量测试和两场分侧八项运行；S5a/R4
文档阶段未再运行 formal production PDE/MPI。105 focused、6 targeted pytest 与
静态检查分开记录，不能合称一个“105 个 focused/static”结果；本地检查也不是 CI。

| 阶段 | 实际结果、边界 | hash-bound 入口/命令 |
|---|---|---|
| R1 | r1h index 记录 137 passed 发生在后续 `__all__`/`pairwise` 机械修正前；最终受影响 9 passed、静态通过，tiny-FE serial/MPI2 另有独立证据 | [`r1h_validation_index.json`](../../../results/task041_side_balh_component_audit/r1h_validation_20260915/r1h_validation_index.json)，SHA `ca30f4df99d9ab248d2fbbcf21741fefb726b3e4a02389314231a1f7a26234e4`；命令和失败/修复日志在同目录 |
| R2d pure/接线 | pure346 最终 9 passed，builder349 4 passed，profile351 1 passed；首轮 Ruff import-order 失败后修复，最终静态通过 | `r2d_validation/pytest_346_pure_after_ruff_fix.log` SHA `a60c1c8fa5227a32d0727d957c260099194421dced9082187a2c97f8ca04ce7f`，命令为 `python -m pytest -q src/test/test_346_task041_balh_trace_bridge.py -k 'batched_owner or batched_empty or complex_adjoint_helper'`；`pytest_349_builder.log` SHA `9309c90b7bd0fdee72f5c773c3925ec741748555b3f88373eeeb042aee8f240d`；`pytest_351_profile.log` SHA `f8af2f3de9c2b6b1dd079864c69af6cddfc4c478528abd6071006029d3104203` |
| R2d static | Ruff/compileall/diff final all pass after local import-order repair | `ruff_final_after_import_fix.log` SHA `faaee09c51ec21a099ed3c303056cc159b800f5f797404521e788b03164ba56d`；`compileall_final_after_import_fix.log` SHA `14a1315b5b6c7da261992052e9ad32d90b8babbd390dc8a9c62362bca7d3093b`；`diff_check_final_after_import_fix.log` SHA `1ee0dda1778ad983cc34adfcb3ff162533f6735d59a7fc6952f8eeb7ba95a7c6`；首轮失败 `ruff_final.log` SHA `a9ad21ff1d80c405c18a1588777a6872ca164172e49674ad5de08347ede24ceb` |
| R2e serial | 2 passed；R2e source/test 内容仍绑定 pre-commit SHA，未声称 commit 后重跑 | `r2e_validation/pytest_346_serial.log` SHA `4cf89003ce4005b964d42c4acb842c398814448fbb2f745e1392f7ebbcbb6e11`；命令含两个真实 tiny-FE node，outer wall `59.009665886 s` |
| R2e MPI2 | 每 rank 4 passed；rank0/socket0core0、rank1/socket0core1；数学线程配置1 | `r2e_validation/pytest_346_mpi2.log` SHA `90200a7b7f7102b0d0ce998a847faef8da4372bf7efd48ba2c551967d91c18d1`；`mpiexec -n 2 --bind-to cpu-list:ordered --cpu-list 0,1 --report-bindings ...`；outer wall `63.633586239 s` |
| R2e static/ABI边界 | static final pass；ABI 探针的计时在同一 Python 进程内，属于 in-process preflight，不是完整 subprocess outer wall | `r2e_validation/static_final.log` SHA `0b69c84a3ab4f936bde557c325dcabd26834906eb1a417cd4625649c900b2883` |

R2 分侧结果不是完整双侧资格：baseline/唯一 optimized R2g 各完成 bottom/top 四项，
own residual 与生命周期证据保留，但跨 fresh-run condensed-row identity 未证明，最终
状态为 `PAIRING_IDENTITY_UNPROVEN`。旧 S1f 的 `process_tree_rss_limit`、旧 H3 事故和
负结果不改写。

本轮唯一 shared ledger 为 `used=11145.609111173893325 s`、shared remaining
`10454.390888826106675 s`、S2/S4=`0`；R4b 文档合同测试为 15 passed，JSON/路径/hash 自检与 `git diff --check` 均通过。最终 compact 为
`153382 B` / `7f5d84e6a2a9a6809d9438bbb6e9444a4ffead9d6272728b394d3346401852df`。三份 harness-only 自检失败日志仅记录工具断言错误，不属于文档合同测试失败；其实际外层时间已按一次 shared ledger 记录。
R2h v1、R2h v2 和 R2g 原 index 均保留；未重跑已绑定测试、FE/MPI、service、PDE 或 QEP。

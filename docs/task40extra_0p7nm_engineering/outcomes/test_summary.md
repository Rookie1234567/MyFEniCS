# Task40extra 当前测试摘要：Review V6 closeout

| 检查 | 命令 / 证据 | 结果与边界 |
|---|---|---|
| postprocess preflight regression | source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_v5_postprocess_preflight.py | 7 passed；检查授权后历史失败接续和 preflight 行为；无 PDE |
| fresh independent checker | python -m benchmarks.check_task40_review_v5_gx784 对已保存 comparison 输出 fresh JSON（qualified activation 下） | tested_x_agreement_pass、无 failure reasons；fresh JSON 与保存 checker 记录相同；仅读保存场 |
| qualification and compilation | Task40 qualified activation ABI preflight；targeted compileall | PASS；PETSc complex128/int32、Linux ABI、MPI1；没有运行 MPI4 |
| final documentation and Task40 contracts | source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py src/test/test_task40_v5_postprocess_preflight.py | 31 passed；含 response、summary、registry、run-index 文档合同及 preflight regression，无 PDE |
| whitespace / JSON identity | git diff --check；compact record、run index 和 artifact hashes | PASS; 14 raw artifact hashes and compact-record/run-index binding verified |
| broader checks | full repository pytest / MPI4 / Ruff / CI / new PDE / target-scale / dot | not_run；本 closeout 不涵盖 |

V6 PDE source=2374d0d556aed7a415202757daa2b94b76ad399b，postprocess source=fea2b6c01b34940a6393bd47a4f545d6d53d61b4。旧尝试的 positive/negative evidence 和历史测试范围仍保留在下文；本节不把旧测试改归到本轮 source。

---

# Task40extra 测试与文档检查摘要

## Review V5 Gx784 安全预检与定向回归

实现 source 969b4086320b844d44fb0b67092ffe5af2d760b1，qualified WSL activation：

| 检查 | 结果 |
|---|---|
| 后处理预检、V5/V4 review fixtures、worker time policy 与 clock | 35 passed in 0.33 s；命令：source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_v5_postprocess_preflight.py src/test/test_task40_review_v5_gx784.py src/test/test_task40_review_v4_volume_runner.py src/test/test_task40extra_v5_worker_time_policy.py src/test/test_physical_schur_v14_runtime_clock.py |
| 被本次改动触及的 V20 lifecycle | 12 passed in 13.71 s；source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task39extra_v20_y1_lifecycle.py |
| 环境 / 静态检查 | qualified ABI preflight：complex128、int32、MPI1；compileall 与 git diff --check 通过 |
| 文档合同 | source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_183_development_model_registry_markdown.py src/test/test_29_task_retrospective_contract.py：13 passed in 0.02 s |
| 未运行 | full repository pytest、MPI4、Ruff、CI；没有 formal service、worker 或 PDE 重跑 |

两个测试命令分别报告，不将不同 fixture 集合合并为一次完整测试。通过单元测试只验证代码路径，不证明 Gx784 数值通过。

---

## Review V4 交叉网格收口验证

| 检查 | 命令 / source | 结果 | 证据边界 |
|---|---|---|---|
| V4 定向测试 | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_review_v4_volume_runner.py src/test/test_task40_review_v4_directional_cross.py src/test/test_task40_p3_mode_staircase.py`；source `55feda2c6f5c0e0b9ec4b57a341d209ec8b566d2` | `8 passed in 0.68 s` | runner/watchdog 启动与隔离、父进程不导入 FE、方向/交互量和模式分母 helper；不运行 PDE |
| Python 编译、命令入口 | 三个新增/相关模块 `py_compile`；volume/modes runner `--help` | PASS | 静态语法和入口参数检查；不代表完整仓库编译 |
| whitespace | `git diff --check` | PASS | V4 文档及 metadata 最终版检查 |
| Ruff | qualified environment 中 `python -m ruff` | `not_run`：环境没有安装 ruff 模块 | 未安装或临时增加依赖 |
| 项目文档合同测试 | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_183_development_model_registry_markdown.py src/test/test_29_task_retrospective_contract.py`；source `55feda2c6f5c0e0b9ec4b57a341d209ec8b566d2` | `13 passed in 0.02 s` | registry 表格结构与 retrospective 文档约定；不涉及 PDE |
| full repository pytest / MPI4 / CI | 未运行 | `not_run` | 本轮只运行 V4 focused 与两个文档合同测试；不声称 CI 通过 |
| V4 保存场后处理 | 4-corner directional volume worker 和 all-340-mode/power pass | 已完成，非 pytest | volume 用一个受 subreaper 监督的离线 worker，退出码 0、后代清空；mode 分析读取保存记录。无新 PDE/网格/factorization |

首个 volume launcher 曾在任何 run 包载入前失败：parent 用文件路径启动导致 repository root 未进入 `sys.path`，`benchmarks` 模块解析失败。该事件准确归类为**工程 launcher startup failure**，不是场恢复、积分、PDE、残差或物理失败；无 saved run 被读取，也没有恢复或积分发生。随后的 launcher 修复改为 `python -m benchmarks...`，focused runner test 覆盖这一模块启动路径。此失败保留，不由后续成功覆盖。

## 当前文档检查

| 检查 | 状态 |
|---|---|
| V4 compact JSON 与 artifact SHA | `PASS`；run index、接口包及两个原始分析 artifact 均可解析；接口 SHA、两项 artifact SHA 和 F3 source correction 均与索引一致 |
| 本轮 Markdown 合同 | `PASS`；response/summary/test-summary、Task40 README、development_progress、development_model_registry 六份文档新增区共 23 个表格列数一致，新增相对链接目标均存在，`git diff --check` 通过；无独立多行公式 |
| GitHub rendered view | `NOT_VERIFIED`；待推送后检查当前分支上的 summary/response 页面 | 缓存或页面不可读时如实保留未验证状态 |
| full repository pytest / MPI4 / Ruff / CI | `not_run`；不外推 |


## 测试结果

| 范围 | 命令/输入 | 结果 | 证据边界 |
|---|---|---|---|
| N2 tiny p2 diagnostic | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_n2_tiny_task40_stage4_static_condensed_diagnostic` | `1 passed`；solver `8.608 s` | source commit/base `036dec55beb0fdb1f3cae7693fddfc0225921eb9` 加未提交实现 diff `7cd587b76d90670bc396dc3e82f4641fbd1cce3b1f65d2f4c71058bb6dd977e1`；60-cell p2 diagnostic，不是 G0/G1 official |
| Task40 focused regression suite（历史阶段；并非 profile smoke） | 5 个目标文件，精确命令见下方 | `41 passed, 1 deselected in 9.20 s` | 含 Task40 几何/launcher 与 Task038 staging/watchdog 回归，也含 V19 真实 FFCx/MPC 小 FE action、V18 小 FE 的真实 LU factor/solve；`-k` 排除 N2 测试。额外执行的 V19/V18 真实 FE/factor 测试超出 N2 单一 tiny fixture 范围；总耗时为 9.20 s，各 fixture 次数与单独耗时均 `unknown`。这不是 G0/G1 正式 PDE。该运行早于 `1ee85bc`，精确 HEAD 与未提交 diff 身份未保留，记为 `unknown` |
| ledger identity 与 G0/G1 capacity fixtures | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger src/test/test_task40_nonseparable_geometry.py::test_task40_capacity_context_binds_frozen_axes_and_live_class_metadata` | `3 passed, 10 deselected in 0.76 s` | source `1ee85bc2133b783da419d31dbe429643eb2c1191`；一个 ledger fixture、G0/G1 两个 capacity fixture；不包含 PDE |
| final mesh metadata fixture | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py::test_task40_same_mesh_levels_preserve_air_void_audit_metadata` | `1 passed in 3.89 s` | source `59bad0d977f0e23555098d923a95afbf2e9f5bf4`；真实 G0 mesh/FE/MPC fixture，不装全局矩阵或因子 |
| compileall / diff whitespace | compileall for modified solver modules；`git diff --check` | `PASS` | 在最终 source 修复后完成；不等于 full test suite |
| full repository pytest / MPI4 / Ruff / CI | 未运行 | `not_run` | 本行仅说明初始N0–N6阶段与R5收口；Review V2已有的targeted MPI2资格见下方，不得由此行误读为未做任何MPI2测试 |

历史 focused regression suite 的原始命令（该运行早于 `1ee85bc2133b783da419d31dbe429643eb2c1191`）：

```bash
source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_nonseparable_geometry.py src/test/test_337_task038_full3d_jit_staging.py src/test/test_task39extra_v30_monitor_policy.py src/test/test_task39extra_v19_p6_cell_condensed_action.py src/test/test_task39extra_v18_cell_condensed_core.py -k 'not n2_tiny_task40_stage4_static_condensed_diagnostic'
```

该 41 项 suite 的精确 HEAD 与未提交实现 diff SHA 未保留，因此 source identity 为 `unknown`；不能把它归到 `1ee85bc`。N2 diagnostic 则有独立运行记录：`source_head=036dec55beb0fdb1f3cae7693fddfc0225921eb9`，另绑定未提交实现 diff SHA256 `7cd587b76d90670bc396dc3e82f4641fbd1cce3b1f65d2f4c71058bb6dd977e1`。

两个 systemd service-log SHA 保留在原始 Task40 run records；日志未作为独立文件出现在本工作树，因此本轮只校验可见 artifact，不声称重新计算了这两项。 Task39 V31 首个 instrumentation failure 的原始注释仍保存在父任务记录 [`projection_layout_v31_resource_reaudit.json`](../../task039_extra_physical_multilevel/outcomes/records/projection_layout_v31_resource_reaudit.json)；该事件属于父任务。Task40 仅记录自身两次 G0 worker implementation failures，不覆盖或重分类父任务记录。

## 当前文档检查

| 检查 | 结果 | 范围 |
|---|---|---|
| 证据 JSON parse 与 identity/hash 对照 | `PASS`；10 个 JSON 可解析，G1 hash 与 geometry plan 一致；input、ledger 及当前可见的 9 个 raw run files 逐项复核 | `outcomes/records/*.json` 与 ignored raw runs |
| whitespace/diff check | `PASS`；`git diff --check` 与新增文本行尾空白检查通过 | 本轮文档与 metadata |
| Markdown fenced math / 表格 / 相对链接 | `PASS`；8 个相关 Markdown 的表格列数、围栏、相对链接检查通过；修复一条原模型登记表中指向 ignored artifact 的旧链接 | 新建/修改 Task40 Markdown 与项目索引 |
| GitHub rendered view | `NOT_VERIFIED` | 推送后尝试打开 summary、response 与 material identity 页面；页面读取返回 `Cache miss`，因此未确认 GitHub 渲染结果 |

## 2026-09-30 主控续算入口验证

资格化 complex128 / PETSc 3.19.6 环境下，`python -m pytest -q src/test/test_task40_bug_continuation.py src/test/test_task40_nonseparable_geometry.py::test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger`：**4 passed in 1.10 s**。仅 mock/账本测试，无 FE/FFCx/因子：验证第三次预约保留两次历史和累计成本、授权只能消费一次、G1不获额外额度，以及授权不匹配/数值失败保持拒绝。未重跑已合格的字段修复网格 fixture。

## G0 JIT 缓存路径修复

最终组合执行 `python -m pytest -q src/test/test_task40_qualified_jit_cache.py src/test/test_task40_bug_continuation.py src/test/test_task40_nonseparable_geometry.py::test_task40_worker_identity_opens_the_reserved_v14_runtime_ledger`：**5 passed in 1.15 s**；compileall、diff 检查通过。此前隔壁单独路径 fixture 为 **1 passed in 0.19 s**，成本保留。测试只核对显式父 artifact 绑定、旧 V31 配置与账本，不建立 FE 矩阵/因子。父缓存路径是本笔记本显式配置，不声称跨机器自动可用；新 FFCx 表单仍按签名编译。


## 2026-09-30 attempt4 N6 evidence closeout

本轮只整理已落盘 attempt4 数值 Gate 和主控离线数组复核；没有改数值源码、重跑 FE/KSP/PDE，也没有新增测试。raw KSP status/reason 未持久化，callback因果为source-derived。

Task40 仓库根执行以下轻量检查，输出为：PASS: 3 JSON parse; 9 raw SHA match; identity normalization consistent.

命令1：
python3 -c 'import json,hashlib; from pathlib import Path; d=Path("docs/task40extra_0p7nm_engineering/outcomes/records"); [json.loads((d/n).read_text()) for n in ("g0_attempt4_identity_gate_stop.json","run_index.json","phase_I_results.json")]; r=Path("results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_g0_iterative_v1__full3d_iterative__mpi1__Mna/20260929T230709.246850Z"); c=json.loads((d/"g0_attempt4_identity_gate_stop.json").read_text()); a={"worker_summary_sha256":"task40extra_nonseparable_0p7nm_p6q4_summary.json","run_manifest_sha256":"run_manifest.json","run_summary_sha256":"run_summary.json","watchdog_summary_sha256":"watchdog/summary.json","release_gate_packet_sha256":"release_gate_failure/v20_release_gate.json","monitor_residuals_sha256":"monitor_residuals.jsonl","iterations_sha256":"iterations.jsonl","x2_retained_final_npz_sha256":"x2_retained_final.npz","x2_terminal_residual_npz_sha256":"x2_residual_0008_0002.npz"}; assert all(hashlib.sha256((r/v).read_bytes()).hexdigest()==c["artifacts"][k] for k,v in a.items()); assert abs(c["gate_metrics"]["native_identity_difference_norm"]/c["gate_metrics"]["native_identity_operation_scale"]-c["gate_metrics"]["native_identity_relative_recomputed"])<1e-25; print("PASS: 3 JSON parse; 9 raw SHA match; identity normalization consistent.")'

命令2：
git diff --cached --check

结果：两条命令均通过。该检查不是pytest、MPI、Ruff或CI。此前targeted tests的source SHA和范围仍按历史记录保存，不归到attempt4。




分组来源补充（不混入上表43项合计）：

- exact-geometry / R3 修复 fixture：15 项通过，提交 source 33b773d161b5e5dc218a29b122cdb4044ca01800；见 identity-recovery root-cause record。
- 非零 RHS 实算 action fixture：3 项通过，命令与范围见 identity_policy_decision_v1.json 的 current_abi_fixtures[0]，源测试为 test_task39extra_v19_p6_cell_condensed_action.py::test_real_ffcx_mpc_action_only_matches_augmented_schur_and_nonzero_rhs。
- local recovery/native residual oracle 与 non-Hermitian port fixture：2 项通过、9 项 deselected，见同一 record 的 current_abi_fixtures[1]；它与上一组的3项分开记录。

## R4 review_v1 runs and R5 documentation closeout

- R4 official execution used source SHA 393e5c0dddb933848945ab2e18edb73cf69cc224 for the direct reference; the G0/G1 source SHA is b8a20bd24848a83f2f4fa50b1ccaaa4ec9be9672. Targeted code checks recorded before the runs passed 34 cases across test_372, test_373 and test_task40_direct_reference_identity, plus 9 cases in test_374_reference_incident_quadrature.py, total 43. The 15 exact-geometry/R3 repair tests and separate nonzero-RHS groups (3 and 2 cases) are distinct earlier evidence and are not counted in these 43. This is not full-repository pytest, MPI2/4, Ruff or CI.
- R5 changed compact records and documentation only; no PDE, factorization, solver or new test suite was run for closeout. Final JSON parse, source/artifact identity checks and git diff checks are recorded after the last doc edit.
- direct reference independent saved-array audit: reference_full_residual.npz SHA256 0e8c5b1fc8a8718d56e7b0ab0bc9b7407d941022addbb9b72ada5314c64da630; recomputed norm(b-Ax)/norm(b)=5.055376131651821e-11 and maxabs(r-(b-Ax))=0.
- direct execution route deviation: user-service wrapper was not used; the observed cgroup was /init.scope. The independent process-tree watchdog completed with exit 0 and cleared descendants. No rerun was made.


## Review V2累计测试与本轮文档检查

| 范围 | 已有命令/输入 | 结果 | 身份与边界 |
|---|---|---|---|
| P4 same-M mode helper | `src/test/test_task40_p3_mode_staircase.py`定向fixture | `4 passed` | P3/P4保存场比较helper；P4不启动PDE。测试源代码由`benchmarks/postprocess_task40_p3_mode_staircase.py`所绑定的V2 commit `3f36014253525f5fc7e0e2ee56348bc3628e9024`识别 |
| P6 bounded diagnostic fixtures | `src/test/test_task40_p6_local_growth_v2.py` | `2 passed` | P6 source `5f9efdbae1c668ffa4426731156ec4afe9325eb2`；serial targeted fixture，不创建完整高M全局factor |
| Review V2 earlier serial/MPI2 qualification | V2实现阶段已运行的serial与MPI2 targeted tests及相关qualification | 已运行；本compact test summary未保留逐条命令、完整case count、耗时和每次source SHA，均记`unknown` | 不把未知写成未运行；不将MPI2结果扩展为MPI4或完整solver qualification。既有结果按原测试回执边界使用 |
| source checks during V2 implementation | targeted `compileall`及和数值实现相关的focused regression，见各代码阶段记录 | 通过的范围见既有代码阶段回执 | 不把实现阶段测试回填成本文档收尾新测试；不等于全库pytest |
| 本轮P7/文档收尾 | 10个compact JSON parse及身份/hash断言；234个Markdown表格列数、347个本地链接、7个编辑Markdown的围栏/尾空白；`git diff --check` | `PASS` | 只核对compact evidence与文档合同；没有新PDE、operator、factor、KSP或full test suite |
| full repository pytest / MPI4 / Ruff / CI | 未运行 | `not_run` | 不声称full pytest、MPI4、Ruff或CI通过 |

Review V2的正式F1/F2/F3/F5/E1/E2计算发生在此前campaign阶段，见run_index与各自raw run summaries；“本轮文档收尾没有新PDE”不等于整个Review V2没有正式运行。P1和P4都是保存场offline后处理。

## Review V7 文档与索引定向检查（2026-10-04）

| 检查 | 命令/范围 | 结果 | 边界 |
|---|---|---|---|
| 资格化本地 WSL preflight | `source scripts/activate_myfenics_wsl.sh` 后核验 lexical `sys.executable` 位于仓库 `.venv`、`sys.prefix` 与 `.venv` 一致、PETSc complex128/int32、PETSc/SLEPc/DOLFINx complex Linux ABI、Basix/mpi4py Linux 路径、Open MPI 4.1.6、MPI1 | PASS | 仅本地文档测试环境，不是原生工作站 W0 收据 |
| 文档合同与历史/模型注册合同 | `python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py` | 24 passed；pytest 报告 0.06 s | 没有 FE、MPI 多进程、full-repository pytest 或 PDE |
| 两次 preflight 脚本误报 | attempt 1 把 venv 符号链接目标误要求在 venv 内；attempt 2 把 SLEPc 安装目录误要求与 PETSc 同根。两次均在 pytest 启动前停止 | 保留为 agent assertion errors | 都不是项目/ABI 失败；单次耗时无 monotonic 收据，记 unknown，不记零或收费 |
| compact JSON / index / diff | 新 V7 link 和增量账 JSON parse；run index stage/status pointers、原四角哈希和 Gx784/F5 输入身份断言；`git diff --check` | PASS | 只验证本地文档/evidence；没有触及 ignored raw、工作站 FE 或历史 V6 ledger |

这组结果对应本轮新增文档与索引，不替代原生机器 ABI/resource Gate，也不改变 W0/W1/W2 状态。

原生 W0 的一次延迟导入闭包尝试由控制端报告，完整 packet 尚待无损移交，因此下列摘要字段还没有在本地对原始 packet 复算哈希：source `5be1210aa79f25c13a7677cc291a4a766a548650`，UTC 窗口 `2026-10-04T03:24:37Z–03:24:38Z`，导入链 `dtn_port_3d → common_3d_utils → solve_vector_maxwell → postprocess` 因缺少 `pyvista` 以 exit 1 停止；FE worker/checker、PDE、残差和 raw 场均未启动。控制端报告的 trace SHA256 为 `343939c7bec310f03c05134763e4aef504d9997abb40f06956bdb08dcf2af01a`，closure receipt SHA256 为 `64f65b92b8379c432cf87c6f6d97b62108236e67512eade1699b22cdde9c20b7`，ABI receipt SHA256 为 `4ef26bf3d4ea0b3c16170b030694e7de7a303108e5fd78b3309835d0c4aa5102`。这些是 FE 前导入 blocker，不属于数值测试或 PDE 失败；完整 W0 elapsed/charge 仍 unknown。控制端同时报告宿主 `SwapUsed=21,600 KiB` 且 Metrology/Task42 作业仍活动，因此资源 Gate 未通过。该记录不改变上面 `24 passed` 的本地文档合同测试结果。

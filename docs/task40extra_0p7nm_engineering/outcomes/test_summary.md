# Task40extra Review V22 定向测试与文档收口

| 检查 | source / 命令 | 结果 | 证据边界 |
|---|---|---|---|
| V22 production gate/checkpoint tests | frozen source `ae3f1a4bc557170dc9af51669139683a8ab032a5`；3 个 V22 定向测试（详见 [receipt](records/targeted_tests_v22.json)） | 3 passed in 0.78 s | checkpoint fail-fast、MPC/component filter 与终端重算；没有运行 PDE |
| py_compile / diff check | 同一 frozen source | PASS | 软件静态检查；Ruff 因 qualified runtime 无模块而 NOT_RUN |
| LU≤3 same-factor correction / MUMPS lifecycle fixtures | 本轮受固定窗口截止限制 | NOT_RUN | 不把未完成 fixture 记作通过 |
| V21 read-only CLI 对 V22 raw root | `task40_v21_readonly_recheck.py` main 仍要求旧 E2 的 `task40_v10_p6_candidate_summary.json` | FileNotFoundError；V22 receipt 由主控转用公共 `validate_stage_receipt_semantics` API 核验 | CLI 接线问题，不是 worker/PDE 失败；API 结果以主控回执为准 |
| full repository pytest / MPI4 / CI / new PDE | 本轮 | NOT_RUN | 不声称全仓、MPI4、CI 或数值求解通过 |

---

# Task40extra Review V21 定向测试与只读复核

| 检查 | source / 命令 / 回执 | 结果 | 证据边界 |
|---|---|---|---|
| None 零块与局部 p6 action regression | `src/test/test_task39extra_v19_p6_cell_condensed_action.py`、`src/test/test_task39extra_v30_streamed_ports.py`；日志 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v21_wsl/p6_action_regression_attempt03.log` | 28 passed in 119.45 s | 核对缓存零块/None、condensation 与 streamed 兼容；不是全局 target MPC/PDE |
| 主控最终联合复核（solver source 未在本次复跑期间改变） | `source scripts/activate_myfenics_wsl.sh`；同 shell ABI preflight；`python -m pytest -q src/test/test_task39extra_v19_p6_cell_condensed_action.py src/test/test_task39extra_v30_streamed_ports.py` | **28 passed in 129.61 s** | Task40 runtime、activation marker=1、PETSc complex128/int32、MPI1；组件与 80-mode carrier fixtures，不是 global target MPC/PDE；全仓/MPI4/Ruff/CI 仍 `NOT_RUN` |
| 旧 streamed class-call 兼容性修复 | V30 直接类调用 fixture；日志 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v21_wsl/streamed_compatibility_targeted_attempt02.log` | 3 passed、2 deselected in 0.26 s | 初始合并回归曾因 `_streamed_cell_action` 调用签名改变而有 3 项失败；已恢复兼容并跑 focused suite，失败原因与最终通过分别保留 |
| 阶段 receipt、checker 与 E2 byte arithmetic | qualified activation 后：`python -m pytest -q src/test/test_task40_v21_readonly_recheck.py src/test/test_task40_v20_routes.py::test_original_target_unapproved_heavy_stages_stop_before_geometry`；[targeted test receipt](records/targeted_tests_v21.json) | **15 passed、0 failed、0 skipped in 0.16 s** | 覆盖 authorization denial、resource stop、stage complete、stage failure、q0/q-all 语义、q CSR hash 绑定、cleanup 未知拒绝、partial checker integration；没有启动 worker/PDE |
| V21 最终 focused reruns | qualified activation 后分别运行 V21 recheck、heavy-authorization route 和 p6 cell-action 测试 | 12 passed in 0.12 s；3 passed in 0.12 s；23 passed in 0.76 s | 与更早 combined 15 passed receipt 相互补充；没有启动 worker/PDE |
| 主控修正尾部空白后的 checker 复验 | `src/test/test_task40_v21_readonly_recheck.py`，同 shell ABI preflight | 12 passed in 0.08 s | 绑定修正后 source SHA；只测 checker fixtures，没有启动 worker/PDE |
| 最终文档合同测试 | documentation/model registry/retrospective/markdown contracts | 29 passed、134 subtests passed in 0.23 s；在最终摘要/索引编辑后重跑 | 仅文档与索引合同，不是 full repository pytest、Ruff 或 CI |
| 主控最终文档合同复核 | 同上四个合同测试；Task40 qualified activation、PETSc complex128/int32、MPI1 | 29 passed、134 subtests passed in 0.08 s | 在本轮最终 response/summary/test receipt edits 后复跑；不含 FE/PDE、全仓 pytest、Ruff 或 CI |
| E2 raw-event只读复核 | `python -m scripts.task40_v21_readonly_recheck --run-directory <saved E2 run> --output docs/task40extra_0p7nm_engineering/outcomes/records/e2_partial_recheck_v21.json` | `E2_PARTIAL_RESOURCE_STOP_RECHECKED`；event line=97,311；byte arithmetic deficit=149,505,816 B | 读取已有 JSON/JSONL，不启动 worker；旧 `NO_PARTIAL_FOOTER`、worker/outer exit 与 `cleanup=UNKNOWN` 均保留 |
| 目标端口几何映射 readback | qualified WSL DOLFINx mesh-only HDF5；source ba897281f3b8ed227f73e645dc60b7210f46db73；command/receipt path 与 SHA 见右侧 raw artifacts | 4,352 rows；每侧2,176 facets/unique cells；bottom/top 28/26 classes，54/60 class catalog；后端整条命令1,047 ms | 纯读回/完整准备耗时、reader PID、CPU/RSS/cgroup/swap均UNKNOWN；17/60方向资格不变；无FE/MPC/carrier/q CSR/factor/PDE；21.328 TB仍为条件情景 |
| V21 boundary inventory mapper tests | qualified activation; python -m pytest -q src/test/test_task40_v21_boundary_inventory.py | 5 passed in 0.08 s | Pure helper fixtures only; does not read raw HDF5 or establish carrier support |
| Geometry readback documentation-contract rerun | qualified activation; four documentation/model-registry/retrospective/markdown contract files | 29 passed, 134 subtests passed in 0.23 s | Rechecked after V21 geometry mapping summary edits; no FE/PDE |
| 文档/whitespace 检查 | `git diff --check` | PASS | 只做本地 whitespace 检查；不代表 markdown renderer、Ruff 或 CI 通过 |
| full repository pytest / MPI4 / Ruff / CI / PDE | 本轮 | `NOT_RUN` | 不声称全仓、MPI4、Ruff、CI 或原尺寸数值资格通过 |

本次最终 focused reruns 使用 Task40 qualified WSL activation（marker=1，PETSc complex128/int32，MPI1）；ABI preflight 通过。 原始命令完整保存在 sibling v21_boundary_mapping_command.txt（SHA-256 92528b83494272441d89a34c8f07a4a5466730acd2df8a4546209ed564765295），tool receipt SHA-256 4d7c9b59e2b374b0e37a0acae2135077924ff2f3b4af8d09c21b01826e6bca6d；backend duration 为1,047 ms，不代表纯读回或完整准备时长。PID 2179667 是 read_campaign_state API 观察进程。V21 raw-event receipt 与 port inventory 是只读/离线整理，没有触发 worker、PDE 或额外资源门。fixed-window sample 是主控 read_campaign_state 的只读结果，没有修改 campaign ledger/window。

## 固定窗口主控只读 sample

同一 V19 窗口未刷新：T0 2026-10-09T01:45:00.727771902Z，deadline 2026-10-10T01:45:00.727771902Z，600 s closeout reserve；window SHA-256 b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0。此前主控 qualified read_campaign_state sample 为2026-10-10T00:38:20.741056830Z（interval 15,480.292692466 s；projected cumulative 82,400.02111048152 s；remaining 3,399.9788895184756 s），保留为历史值。最新只读sample为2026-10-10T01:17:38.378013Z：interval 17,837.929648505 s、UTC-minus-monotonic discrepancy 1,784.9477480050991 s、projected cumulative 84,757.65806652053 s、扣除600 s reserve后的 numerical remaining 1,042.3419334794744 s。持久账本 SHA-256 7ea9e880520accf2fd87d8ee63b894c7e3e1ec366308dd0c8bb4492abd705a11，83,032 行/seq 83031，尾部已写 cumulative 66,919.72841801553 s。该投影是只读 as-of 值，无新扣账、无 ledger/window 修改；未结算值保持 unknown。详见 [Response V21](../response_v21.md) 与 [V21 run index](records/run_index.json)。


---

# Task40extra Review V20 收口测试摘要

| 阶段 / source | 命令、身份或收据 | 结果 | 证据边界 |
|---|---|---|---|
| E1 V19 startup-scope repair (controller coordination evidence) | failure source `f23d907bbb60249cbd2844921ca86cfd43f84658` had no V18 Ny8 witness for q_count=4; repair only skips the V18 startup comparison unless q_count=8; receipt `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/e1_startup_scope_repair_v1.json`, SHA-256 `a0cb71fd4926445de73bbd39b460ddbe1fbecae17d0a29a86e1df76c2e7966e7` | 54 passed in 3.33 s | repair source file SHA `029e85c2e1de2655ca1b2897a901075d73aa240a8d6c4c0add223cdb030ba0b1`; test file SHA `0357846488d17129b13db563f991edbc211a21f43cb345507d1d415f2a7deb4a`; software validation only, not an E1 PDE pass; original worker failure remains preserved |
| V20 route + ABI repair | 冻结源码 `c319719433e99fe652754f2844c5d79669b111cb`；定向 route 与 ABI suites | 42 passed、1 skipped in 0.58 s；compileall 与 diffcheck PASS | 只验证精确 V20 route/profile/ABI 合同，不建 FE、不运行 PDE；receipt `controller_v20_target_runtime_source_freeze.json` |
| target actual pre-mesh route | 同一 frozen source；`controller_target_actual_pre_mesh_chain.json` | `FE mesh=0, q CSR=0, factor=0`；target contract PASS | 只验证路由和轻量拒绝，不是 geometry/PDE 结果；receipt SHA-256 `8ed9ce90941e697bf773a5cf71c1fee05db0594b67481898e4eb1132f82feebd` |
| V20 component-resume targeted tests | Earlier patch-validation receipt; latest receipt `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/patch_validation/v20_local_port_resume_targeted_pytest_20261010_v2.json` (SHA-256 `730b0846efc2a3d8e5ddfd9f2f95492abe330b5ca7a4cb7564b5538607fd44b9`), log SHA-256 `300377b7ca47518f8e58601f2223af547757cb8cd3136653f8d74266ebc028ff` | Earlier run: 32 passed, 1 skipped in 0.32 s; latest recorded run: 35 passed, 1 skipped | Software/record fixtures only; no full-size FE/PDE or new service run |
| final ABI preflight + documentation contracts | HEAD `c319719433e99fe652754f2844c5d79669b111cb`；ABI receipt `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/doc_closeout/v20_doc_abi_preflight_final.json` SHA-256 `69711e67e26d422c9d0eb5845cfec90e693e1740fddc2b5f09031d28b50490c2`；`python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py src/test/test_183_development_model_registry_markdown.py` | 29 passed、134 subtests passed in 0.23 s；在最终摘要/索引编辑后重跑；日志 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v20_wsl/doc_closeout/v20_docs_contract_attempt02.log` SHA-256 `14104cd9cd29e0661324d98d6b2347203f15630934cb0ed90ab2a3ffe660c1c2` | 文档、模型登记和回顾合同；只做 qualified complex128/int32、MPI1/runtime provenance 预检，不含 FE/PDE |
| V20 E2 full case | source `4b004d09b17d07a1f19f4c9d8443e76153e69a4b`；input and physical hashes in formal compact | `RESOURCE_CONTROLLED_STOP` before numeric factor; checker `NO_PARTIAL_FOOTER` | 这是资源/PDE evidence，不是 pytest pass；完整分层身份见 run index |
| target geometry/local-port | source `f88d0606a8c351e7185afd9e839e8c8ddfd9bb81` | geometry PASS; local/port PARTIAL, 17/60 direction classes matched | bounded component evidence only; no global FE/MPC/q CSR/factor/field |
| full repository pytest / MPI4 / Ruff / CI | 本轮 | NOT_RUN | 不声称全仓、MPI4、Ruff 或 CI 通过 |

V20 前两次 E2 full-input 入口失败（campaign-window 与 ABI）、早期 target local-component failure、控制器中断的 engineering fixture 均保留为独立记录；它们不计为数值 Gate 或 pytest pass。最终合同测试结果及日志 hash 见上表和 [run index](records/run_index.json)。V19 与更早的测试记录原文保留在下方。

---

# Task40extra Review V19 收口测试摘要

| 阶段 | 命令/身份 | 结果 | 边界 |
|---|---|---|---|
| ABI轻量 preflight | Task40 local_w0_wsl qualified activation；Python、MPI、PETSc/SLEPc、DOLFINx、Basix位于同一Linux runtime prefix；PETSc complex128/int32 | PASS；activation flag=1 | 仅核验环境，无FE/PDE |
| E1启动scope修复 | frozen source 71042327e5f3a77cd39a1be7b5dfa46afe52db6b 的独立定向收据 | 57 passed in 3.48 s | 修复前失败 attempt 保留；不是本轮文档合同套件 |
| V19 focused suite 初次通过 | Task40 V19启动scope、输出checker、Ny8 operator reuse、p6 support/MUMPS/y-orbit、FE component、文档/模型登记/回顾合同；日志 benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/v19_closeout_targeted_pytest_02.log，SHA-256 deb35beccbae3e690f163eb6c977b156fabe748e047a9a13fc0cc988391040c9 | 132 passed、134 subtests passed in 5.40 s | 无新PDE；其后只补本文件与run index并进行末次复跑 |
| compileall / Ruff / MPI4 / CI | 本轮只有文档、JSON和索引修改 | not_run | 未改Python源码；不声称MPI4或CI通过 |
| full repository pytest | 未运行 | not_run | 本轮执行Task40定向套件，不扩展全仓 |

收口定向 suite 最近一次复跑（早于最终口径 copyedit）：132 passed、134 subtests passed in 4.85 s；日志 benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/v19_closeout_targeted_pytest_05.log，SHA-256 7993e3292d60561522108e46193f2d8cc836cf485111069aeffb856262dbe644。前次04日志及其5.59秒结果保留。所有正式数值、失败证据和P4材料均来自此前已完成的运行/离线检查，本轮没有重跑FE/PDE。

主控在最终口径修订后检查四份文档合同与p6支持计数器：36 passed、134 subtests passed in 0.46 s；日志 benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/controller_v19_final_docs_and_counter_tests.log，SHA-256 2d532dd68c57f002425d24ea6dd58b3541224bd498ac44647f747fafea8f7d1b。最终JSON/hash与whitespace核验通过；无新FE/PDE。

---
# Task40extra Review V18 测试摘要

本节只登记 V18 新增或本轮重新检查的内容。正式 Ny8 PDE、E1 resource stop 与旧 Ny4 recovery 按各自原始 run/receipt 分类；它们不折算为 pytest 数。完整 historical tests 保留在下方 V17 及更早章节。

| 测试 / 检查 | 命令或输入 | 结果 | 证据范围 |
|---|---|---|---|
| C1 ABI preflight | 在同一 shell source scripts/task40_fresh_c1/activate_local_wsl_complex.sh，并核验指定 runtime_prefix、PETSc scalar/int、MPI 和 module roots | PASS；Python 3.12.13，PETSc complex128/int32，MPICH 5.0.1，MPI1；petsc4py、mpi4py、DOLFINx、SLEPc、Basix、UFL 均来自 qualified runtime_prefix | Task40 专用 C1 路径；未加载 FE 计算对象 |
| 初始 preflight path assertions | 两次本地检查脚本分别错误假设解释器必须位于仓库 `.venv`、且 activation 必须设置 `CONDA_PREFIX`；两次都在 compile/test/runner 前退出 | 失败的是本地断言条件；Task40 activation 用其显式 runtime_prefix 启动的 qualified Python 与 ABI 随后 PASS | 没有把这两次断言失败记作 ABI 或环境失败；原始 attempt01/02 log 保留 |
| V18 source-freeze targeted qualifications | 读取各 source-freeze 收据：`4da30b9` 初始 focused 120 passed/2 skipped；`aafa3ef` 5 passed；`abc2ce2` 21 passed；`b9dbe54` 22 passed；`b8d2ae5` 与 `c411a4b` 各 66 passed；`9214436` final related 66 passed；`3b9457e` C1 related 116 passed/1 skipped、executor targeted 56 passed/1 skipped；`168a727` checker identity 34 passed | 每个冻结源码的 compileall/diff 和实际 worker 分类分开保留；总账不把这些不同阶段数字相加成覆盖率 | [run index](records/run_index.json) 列出 source SHA、收据/日志路径与 hash；Ruff 未运行，不声称 CI |
| 两个研究入口 compileall | python -m compileall -q benchmarks/task40_v18_p6_support_bounds.py benchmarks/task40_v18_saved_field_comparison.py | PASS | 只验证两个新增入口语法，不等于 full repository compileall |
| P3 全模式 support bounds | C1 activation 后运行 `benchmarks/task40_v18_p6_support_bounds.py`，输出到 v2 sidecar；runner SHA `13eb5b50d1c003ae174d9d97db7c25a0d78d7e6e650f408bc591b78fd86f88ab` | DERIVED_BOUNDS_COMPLETE；32,060 modes；Ny4/Ny8 分开推导 | 未建目标 FE/CSR/factor/PDE；v2 output SHA `b8af3fc45488b1927cab63be9f9d39116680cc29b665ec5d5633f16c7c0d72c6`；v1 保持原文件和身份 |
| Saved modal arrays v4 | qualified C1 后运行 `python benchmarks/task40_v18_saved_field_comparison.py --modes-only`，输出至新 v4 sidecar | SAVED_ARRAY_DIAGNOSTIC_COMPLETE；532 channels；incident arrays bitwise equal；显著模式 Gate NOT_EVALUATED_NO_FROZEN_B0_SIGNIFICANT_MODE_SET | 只读 NPZ；runner SHA `b7c7e4f177a43a2570f171eb4cda9708ccd2e6bfcd56eed699ef6325717cce61`；artifact SHA `8a45423765ecaaf353594ef2a0b3bb27834ff733fb8f57345255bc958eea362e`；v1/v2/v3 保留 |
| Research entrypoint no-overwrite guard | 主控用 qualified C1 检查两个 tracked runner，对各自已有输出路径尝试写入 | PASS_NO_FE；两个 runner 都拒绝现存目标，旧文件字节不变 | 收据 `controller_v18_research_entrypoint_guard_checks.json` SHA `385f7484ae4b9bd439bdb29c4ad92bbc705381294f8affdcec2c60b171b6d3c6`；无 PDE/operator/factor/KSP |
| Ny4/Ny8 完整 E/H common-subcell artifact | 复用已有 v18_ny4_ny8_saved_field_common_subcells.json | 沿用已保存 PASS_WITHIN_SMALL_MODEL_ENGINEERING_OBSERVATION | 本轮不重算 field integration、不覆盖原结果；artifact SHA 4e5e6d9a643c38afabda6350fb6573885e9244e0a855a3d98d9e0de102f6296c |
| 文档合同测试（早于最终 compact/index 更新） | qualified Task40 C1 activation；`python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py src/test/test_183_development_model_registry_markdown.py` | 29 passed、134 subtests passed in 0.24 s；日志 SHA `385d889685e7f766b5cc81a77f2cd922f562b7c5217ed748c279c44f42eb8f35` | 日志 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/v18_doc_closeout_pytest_attempt01.log`；没有在最后 compact/run-index edits 后重跑，因此不称最终文档复测；不涉及 FE/PDE |
| 主控最终文档与计数器定向检查 | C1 activation；上述四份文档合同测试加 `src/test/test_task40_p6_support_bounds.py` | 36 passed、134 subtests passed；0.47 s | 源码冻结 `ff8251dbcede1f736a0827fab8ffa8fb58daa9bd`；日志 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/controller_v18_final_docs_and_counter_tests.log`，SHA `f9425bada13234e51394abbcdb4f5e4ed26f49c7169430a983a73941e81627b1`；无 FE/PDE |
| JSON 与 whitespace | `jq empty` 四份 V18 compact 与 run index；`git diff --check`，并扫描两个 untracked entrypoint 的 trailing whitespace | 收口检查 PASS；结构与空白检查不代表 scientific qualification | 最终记录见 [run index](records/run_index.json) |
| full repository pytest / MPI4 / Ruff / CI | 未运行 | not_run | 不外推，不声称 CI 通过 |

V18 最后文档收口阶段没有新增 PDE 或 heavy case。六次 Ny8 worker failure、后续 Ny8 success、E1 resource controlled stop、Ny4 original worker failure 与离线 recovery PASS 均作为不同 evidence entries 保留，见 [run index](records/run_index.json) 与四份 [compact records](records/review_v18_component_closure.json)。

---

# Task40extra Review V17 测试与文档检查摘要

| 阶段 / source | 收据与身份 | 结果 | 证据边界 |
|---|---|---|---|
| V17 launcher/run_case 定向测试 | `controller_launcher_fix_targeted_tests.log`，SHA-256 `96dab9f740872a28a33c77003b581f80e67774e93344bafafb58bf2302d2e0da`；针对精确 V17 launcher route 修复，之后冻结于 `cbdcc12812b439f5252949ad1279331b86a2dbb6` | 24 passed、18 deselected，0.16 s | 只测 launcher/run_case 路由；不是 solver 或完整 V17 suite |
| Ny=8 ABI/import preflight | 资格化 Task40 C1 activation；PETSc complex128/int32、MPI1；receipt `executor_v17_p2_final_targeted_preflight.json` | `IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION` | 只检查 import/scalar/MPI API；无 FE 构造或 action |
| P1 S2 independent saved-vector checker | checker source SHA `1962cc96810c8838467b9d883240234e5781e7bd5217df1234f2ac65c012dfd6`；原 S2 arrays SHA `d656ff94510836a0592ff36f3579c2c46cbfbd5ae77695228488b5cc25024273`；replay SHA `2a0d74d9ffb1ef93bc1a5d3ee9011e427fca8feff3bac59473bf0e635771b0c4` | direct LU top/bottom forward `2.2029e-11/2.4244e-11` 超过 `1e-11`；top 2 次尝试/1 次接受，bottom 3/3；refined `5.3525e-14/5.1433e-14` 通过 | 只重算保存 S2 数组并对原 complex128 `Vii` 重算残差；保留直接 LU 负结果，不是新 PDE |
| P4 D / plane readback checker | raw D receipt SHA `9003be06d24c4f38afa010abd73d83cd33b2d961b174e2e09b589c9a7a628439`；plane receipt SHA `edd1257598526da8e697ab3b18797688ce62bfedcb6e09c8a0dcbdc34642d9b8` | top/bottom 各 16,030 ordered modes、每面 882 原生行（32,060 face-mode pairs）；两面 D/端口门与逐 key plane gate PASS | 保存数据组件；不是目标全局矩阵或 operator-norm 证明 |
| Ny=8 FE RHS 独立 readback | `controller_saved_vector_recheck.json` SHA `8b01c7280161a4084100a838a886fe0c42421a7ed9dfe5988b1078fc2918b306` | FE q=0…7 均覆盖一次，q=4 端口数为 0 但 FE sector 存在；RHS readback 26 项通过 | 只验证一个固定向量 witness；no FE/operator replay，不代表 full C columns |
| B0 row-tile 四块组件 | B0 source `ca913307d3cdd5a455c2718138bf2089151b3887`；component receipt SHA `c97673c446648bd7492c7c9e4ba10ed8dbbd465f88293ac9cdd6a70b21223a26` | 两 sector 的 00/01/10/11 candidate/legacy 数值比较通过；worker `720.832 s`，watchdog `722.823 s`；最大 simultaneous staging `53,684,424 B` / contract `268,435,456 B` | `PASS_COMPONENT`；没有因子、KSP 或 target solve；组件结果不计入 pytest 数量 |
| 50,000-row row-tile boundary fixture | receipt `controller_50k_boundary_fixture_v17.json` SHA `39a8d324fd58b37ea4c0d2486eb0b8d8ca19cc8e0bac5052e115103ba0346737`；log SHA `4f6fee855d10b7336ea784561e8ef9a5be55a0fb52e4a7fe8685f76aa7eb010c`；HEAD `23626f44243d19d58af41d15a8ccafcba41ee54b`；test/builder SHA 分别 `881c9b92d145dac538db2cd1f3395bc53db5f44df6e833b5d635e9bd4465f44a` / `563ee409a3e4064bf4fd7d4b0a420d6b3d7731021ab74adb7d1d54598d7171aa` | `1 passed in 0.48 s`；wrapper `0.623586 s`；四块 00/01/10/11 比较通过 | 软件 fixture 跨过旧 43,344 行形状限制；无 FE 或全局因子，不代表目标容量 |
| Gx560 V17 formal run and checkers | solver source `cbdcc12812b439f5252949ad1279331b86a2dbb6`；current attempt04 checker SHA `3131b1618ac5a6c788e490bd435d126c411c9c3f65907fdba79cea5243637492` | full A6、physical output、同离散 comparison、row-tile assembly 与 allocation-ledger guards PASS；KSP.solve-only `71.630558198 s`；q numeric factorization `4.063932/3.953524/4.011221/4.408180 s` | 数值运行/独立 readback，不计入软件测试数；checker 从保存 CSR 复算 guard，未重放 operator；不能外推到 E1/目标 |
| V17 doc-closeout ABI preflight | qualified Task40 C1 activation；receipt `review_v17_doc_closeout_abi_preflight_final.json` SHA `ecf98e40c1adfb3e14bbf7f87ff837f480f5e082b6a8ef8bbe9ec4566d5d373e`；log SHA `a658137fd5c3d320dcfa8a984e21dda52e050e3be955271c0593f10751a6bb15` | `IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION`；PETSc complex128/int32，MPICH 5.0.1 rank 1；C1 not_run | imports/scalar/MPI API only；no FE action |
| V17 文档合同套件 | qualified Task40 C1 activation；source HEAD `23626f44243d19d58af41d15a8ccafcba41ee54b`；log SHA `5f0c619eed932c73d3a7549d674b3fbcb707e633a566cd324a79e02d1454c218` | `29 passed, 134 subtests passed in 0.22 s` | 文档、模型登记、回顾与 Markdown 合同测试；不含 FE/PDE |
| V17 初次文档合同尝试（修复前） | preserved log `review_v17_doc_closeout_pytest_attempt01_failed.log` SHA `8bb872439ef9d4486ebf82da5ea80e848318132879a11b5502949d6812e665bb` | `27 passed, 2 failed in 0.27 s` | 两项 Markdown 历史文本合同在临时文档编辑后失败；恢复历史反引号后同一套件最终通过；失败日志保留 |
| full repository pytest / MPI4 / Ruff / CI | 本轮 | not_run | 不声称全仓或 CI 通过 |

旧基础 output checker SHA `9e3f64e0bd12d54492269bd280bdd0a7a5621538543014c9967e5e225df3f1b1` 的 V17 guard 槽为空，只作为历史 saved-output check；当前 guard 结论来自 attempt04。各测试和组件分别按源码、输入及范围记账，不累加成覆盖率。数值运行、输出 checker 与 document-contract pytest 是不同证据类别。
# Task40extra Review V16 历史测试摘要（原文保留）

| 阶段 / source | 收据与身份 | 结果 | 证据边界 |
|---|---|---|---|
| P1 初始候选（基线） | source `7ac204557080019fa0e3788a351e618b96a3411b`；候选收据 SHA-256 `fc004f50c31cad6d9982d5f27c7e5dd58f9b7dc3c6fee98652c0c66b28d6330b` | 69 targeted tests，0.94 s | 修复前基线，不是最终修复验证 |
| P1 projection 修复 | source `a09f887b46ea01e89ac8ffb316caf798a4443ae7`；[receipt](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/local_w16_wsl/controller_source_repair_v16_projection.json) SHA-256 `d81d215abc102fdc48eca3c4fd85476c9707f3dfcc35e454627a917d70a32c57` | 71 targeted tests，1.23 s | 命令和源文件哈希由 receipt 绑定；不含 PDE |
| runtime registration：真实当前窗口 | source `54b98a871632a1eef1c34e3542788f5859ee255c`；[receipt](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/local_w16_wsl/controller_runtime_registration_repair_v16.json) SHA-256 `1010ad6407d3c032424e754760289ab97805131e847064a732a0e256b443ba6c` | real_runtime_with_current_window：1 passed | 独立 1 项范围；wrong-stage/scope/profile 负例保留 |
| runtime registration：V16 routes | 同一 source 与 receipt | v16_routes：11 passed | 独立 11 项范围；不拼成 12 项 suite |
| P4 Hhat helper | helper source HEAD `3fffbddc3ebdf597cf25eed5600095d09f24d918`，helper SHA `7e2fa0629ab350ad0bf5e976c63c09363c96d2fd718bae11eb1044461283d21d`；test SHA `d60ef7e7a2cb33085a76eaba70b243d6fb2f07548cb61ddcac5fa923ce7e05b9` | 3 targeted tests passed | helper 单测；实际组件为 COMPONENT_GATE_FAIL |
| P4 launcher / driver | qualified runtime；`py_compile` 与两个 launcher 的 `bash -n` | PASS | 静态检查，不是数值门 |
| P5 ABI preflight | activation + `qualify_imports_only.py --runtime-profile local_wsl2_authorized`；[receipt](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/local_w16_wsl/executor_v16_p5_abi_preflight_final.json) | PASS；以 receipt 为准 | 仅 runtime/API 检查 |
| P5 文档合同 suite | `python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py src/test/test_183_development_model_registry_markdown.py`；source HEAD `3fffbddc3ebdf597cf25eed5600095d09f24d918` | 最终实测 29 passed / 134 subtests passed in 0.24 s（pytest 报告值；wrapper wall 0.357446 s） | 文档、登记和回顾合同；不含 FE/PDE |
| full repository pytest / MPI4 / Ruff / CI | 未运行 | not_run | 不外推为全仓或 CI 通过 |

所有阶段按各自源码 SHA、收据和覆盖范围记录；不把各阶段计数相加。Gx560 是独立科学运行，P4 两次 attempt 是组件运行，不计入 pytest 通过数。P5 不改数值源码。

# Task40extra Review V15 测试与文档检查摘要

## P0–P5 按冻结源码分列的测试

| 阶段 / source | 命令或 hash-bound 收据 | 结果 | 边界 |
|---|---|---|---|
| P1 初始合同/路由实现，source `3a737f3e57fc5eda6119fada77e734d656483d98` | [source freeze receipt](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/local_w15_wsl/controller_source_freeze_v15.json) | 初始 targeted 103 passed；最后一项 owner fix 另有 29 targeted passed；compileall、git diff check 和三份 dat validate-only PASS；Ruff 未安装/未运行 | 不把两个不同 targeted 阶段并成一次测试；validate-only 不是 PDE |
| P1 runtime profile repair，source `e77575f7df27154196a79819d7d9ed3044d4b62a` | [runtime repair receipt](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/local_w15_wsl/controller_source_freeze_v15_runtime_repair.json) | 41 targeted tests passed | 工程 runtime profile 注册修复；无 FE/PDE |
| P1 ABI profile repair，source `0201815c6b13f8456e9717ab93cc5023d4c946d1` | [ABI repair receipt](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/local_w15_wsl/controller_source_freeze_v15_abi_repair.json)；[failure/repair compact](records/review_v15_failure_witness_and_repairs.json) | real ABI helper three profiles 7 passed；相关套件 49 passed, 1 skipped | 修复启动/ABI profile 注册；不算 PDE 数值通过。失败尝试 20261007T102226.442467Z 的 workflow 1.706062557 s 仍按工程失败记录 |
| P5 文档合同最终复测 | 资格化激活；`python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py src/test/test_183_development_model_registry_markdown.py`；PETSc complex128/int32 | 29 passed, 134 subtests passed (final run) | 仅文档、模型登记和回顾合同；无 FE/PDE |
| P2–P4 冻结 source `40dbe138f53b9a2ee39399eac66dc4b0867a2d50` | [final source freeze receipt](../../../benchmarks/artifacts/task40extra_0p7nm_engineering/local_w15_wsl/controller_source_freeze_v15_b0_recovery.json)；`python -m pytest -q src/test/test_task40_v15_routes.py src/test/test_task40_v10_saved_output_recovery.py src/test/test_task40_augmented_reference_correction.py` | 61 passed in 0.49 s；compileall、git diff check PASS；Ruff unavailable | 这是路由、saved-output recovery 和增广修正 targeted tests；不是 full repository pytest、MPI suite 或新 PDE 的替代 |

冻结 source 之间按运行阶段记录，不将 103、29、41、49、61 相加成一组覆盖率。B0 原运行、B0 saved-field recovery、Gx560 完整 target 和 E1 symbolic resource stop 是科学/资源证据，不是 pytest 计数。

## 未运行范围

本轮没有 full repository pytest、MPI4、Ruff 或 GitHub Actions/CI；没有运行 bounded-staging CSR 候选。E1 在数值 factor 前受控资源停止，numeric factor、KSP、field 和官方输出均 `NOT_RUN`。不声称 CI 通过。

---

# Task40extra V14 历史测试与文档检查摘要

| 检查 | 身份 / 回执 | 覆盖范围 | 结果与边界 |
|---|---|---|---|
| E1 路由与装配策略 source-ready | benchmarks/artifacts/task40extra_0p7nm_engineering/local_w14_wsl/review_v14_source_ready_receipt.json SHA256 535786efc4d5a7b8003f516c1ab554d45857059a22da3a375a1eb0e120a58dd8；pre-repair frozen source 5ac368b168b5e9cdc89889154bf78f25535e3d85 | route/window gates、shared strategy allowlist、dispatcher/worker、witness guard、strict/inexact fixtures | 46 passed；独立 source-ready 收据 |
| 6ac is_v13 NameError repair | benchmarks/artifacts/task40extra_0p7nm_engineering/local_w14_wsl/controller_source_freeze_v14_repair01.json SHA256 c0db577f5d98ba118e43c75890e7874eca89650fe14b1e2ee0798c1f0133fd69; repaired source 6ac8cf7fd4697e575a4bf47a862c560ae290076b | worker-local predicate repair | 4 focused tests passed in 0.40 s; separate receipt, not combined with 46 |
| V14 文档合同测试 | Task40 qualified activation; python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py; PETSc complex128/int32 and common runtime prefix | 文档、模型注册与回顾合同；不含 FE/MPI/PDE | 24 passed, 134 subtests passed in 0.17 s |
| Gx560 attempt 2 数值运行 | V14 formal run，source 6ac8cf7fd4697e575a4bf47a862c560ae290076b | 四个 q 通道的严格真残差与物理 RHS action identity Gate | 数值运行不是软件测试；q 残差通过但 action identity 失败，未产生 target R/T/A |
| full repository pytest / MPI4 / Ruff / CI | 本轮 | full repository pytest、MPI4、Ruff、CI | NOT_RUN；不声称 CI 通过 |

---

# Task40extra V12 测试与文档检查摘要

## Review V12 已有资格与收口验证

| 检查 | source / 输入 / 回执身份 | 结果与边界 |
|---|---|---|
| p6 transform bank 和 algebra qualification | `src/test/test_task40_v12_p6_transform_bank.py`、`src/test/test_task40_v12_transform_bank_algebra.py`、`src/test/test_task40_v11_p6_grid_contract.py`；source-freeze audit `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w12_wsl/main_v12_pre_b0_source_freeze_audit.json` SHA256 `b52c64aeb84a492cfc771732f1fabe089b1ab9edf31abb573409cdf5bd86eff6`；通过 `source_ready_v12.json.verification` 绑定 | `15 passed, 1 skipped`；组件/代数资格，不是 Gx560 solver 或 PDE pass；原始收据不重跑 |
| V12 formal wrapper readiness | `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w12_wsl/source_ready_v12.json` SHA256 `7fb32e68dadefeba4ab71cf35dfedae8893f70026cc1abad54baebffd882593f` | `PASS`；只证明 wrapper identity/preflight readiness，不证明完整求解 |
| B0 worker NameError repair | `src/test/test_task40_v10_worker_arrays.py`；repair receipt `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w12_wsl/repair_ready_v12_b0_nameerror.json` SHA256 `6a2895f976a36d7a0c5fa556cd3101a846690b55b1ddc249d6002577b4551415` | `8 passed in 0.43 s`；R0 修复回归；Ruff 在 qualified environment 中不可用 |
| B0 saved-output output-scope repair | `src/test/test_task40_v10_output_gate.py`、`src/test/test_task40_v10_output_checker.py`、`src/test/test_task40_v10_saved_output_recovery.py`；source `6d2c54389fe885ecf24d474a8782166ff31f9154`；audit `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w12_wsl/main_v12_b0_output_count_repair_audit.json` SHA256 `55f65c2379140f7211ea899fa40b0366daf38f7fc22c235794a0e7546694b097` | `26 passed in 0.65 s`，其中6项独立回归在0.07 s；覆盖通道计数/保存输出，不是 fresh PDE |
| Gx560 saved-witness raw-array recomputation | `gx560_saved_witness_independent_recheck_v12.json` SHA256 `a0f3c986c348e26a7171d2fe9692396647b7be55a286dcf4c6df81a019cd1264`；输入 NPZ SHA256 `99bcd1010b9fbea28cf759217f5dec4dea50422beb47a83b6940056785f0358c` | 三个原 inverse Gate 失败值重现；无 FE assembly、factor、KSP、PDE 或单一根因归因 |
| 历史 V10 closeout-reserve SKIP | 既有 V10 测试记录 | `SKIP`；不可变 V10 campaign 窗口已达到 closeout reserve，与 V12 qualification 的 `15 passed, 1 skipped` 分开，不计作 V12 pass/fail |
| V12 final doc/model-registry contracts | `python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py`；qualified Task40 activation；冻结 source `6d2c54389fe885ecf24d474a8782166ff31f9154` | `24 passed, 134 subtests passed`；仅文档/模型注册/回顾合同，不含 FE/MPI/PDE |

本轮不重跑已绑定 source/input/artifact 的资格测试、B0/Gx560 worker、独立 checker或原始数组。Full repository pytest、MPI4、Ruff与CI均未运行。

---

# Task40extra V11 测试摘要

| 检查 | source / 命令 | 结果与边界 |
|---|---|---|
| S2 局部恢复定向测试 | `src/solvers/task40_w1_local_probe.py` SHA-256 `3c8bd3bef250a590e433247ac287cc43b9e134dfa48d7a09183cc98ad90b4ff6`；`src/test/test_task40_w1_local_recovery.py` SHA-256 `be4575083a17df3af6f1bd51e35e49ba0d70be4eaf8a0ab44641a89c9baeb21e`；执行父 HEAD `9977284c47c8028751de4dbecd12b95d1912a580`；随后实现冻结 `a1c5c6040cc3674418bbebd877790b1882ac010f` | `26 passed`；执行时身份与随后冻结提交分开记录，不声称在冻结提交运行；仅对应局部恢复，不是全局 PDE |
| S1 早期扩展/旧 ABI fixture | source `5dbcc653913cf050395d23e38dc59fed00b977a4`；root `results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_b0_p6_y_orbit_candidate_v10__full3d_iterative__mpi1__Mna/20261006T024823.886317Z` | 旧 ABI fixture `FAIL`、worker `WORKER_FAILED`，保留历史结果；后续 qualified ABI preflight 与独立输出 checker PASS，不回写或覆盖旧失败 |
| S1 qualified ABI 与恢复检查 | WSL Linux、PETSc complex128/int32、MPI1、线程1；source-bound V11 recovery receipt | ABI preflight PASS；保存场独立物理 checker PASS；不是 FE/PDE 重新求解 |
| V11 implementation/no-FE targeted suite | `implementation_no_fe_qualification/targeted_pytest.xml`；42 tests | 初次 `37 passed / 5 failed`；失败保留为历史入口，不冒称全通过 |
| V11 implementation/no-FE diagnostic suite | `implementation_no_fe_qualification/diagnostic_pytest.xml`；7 tests | 初次 `4 passed / 3 failed`；失败保留为历史诊断结果 |
| V11 implementation/no-FE final suite | `implementation_no_fe_qualification/targeted_pytest_final.xml`；42 tests | 最终 `41 passed / 1 skipped`；与早期失败记录分列 |
| S5 helper 定向测试 | frozen HEAD `223f602b84761eb99631e7a61a784c3d6c857c04`；现有回执 | `5 passed`；只验证组件 helper，不替代32,060模式双面结果checker |
| S5 helper 首次 targeted run | `s5_full882_v11/s5_targeted.xml`；5 tests | 初次 `1 passed / 4 failed`；保留为修复前历史结果 |
| S5 conjugation 修复后 / timing-qualified | `s5_targeted_after_conjfix.xml`、`s5_timing_qualified.xml`、`s5_targeted_final.xml` | 各 `5 passed`；完整行动作、共轭方向修复后的定向检查通过；不把修复前失败覆盖为通过 |
| S5 artifact-local runner 编译 | runner SHA-256 `b5438f74fb2434fcbb85e8acd4035a2a2c67a84dce9b44ec9d98cf3e16edba1c` | `py_compile`通过；不是数值测试 |
| S1 / S5 independent checkers | V11 hash-bound gauge-power 与 full-882 compact | PASS；S1为保存场物理复核，S5为两个代表面的边界动作；均非新 PDE |
| V11 文档合同测试 | qualified Task40 WSL activation；`python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_183_development_model_registry_markdown.py` | `21 passed, 82 subtests passed`；本地文档合同检查，不含 FE/PDE |
| 全仓 pytest / MPI4 / Ruff / CI | 本轮 | `NOT_RUN`；不声称 CI 通过 |

不同 source、回执和 fixture 范围不可相加成一个覆盖总数。Gx560 资源停止不是测试失败或求解器数值失败：符号阶段后数值因子、KSP、场均未运行。文档测试也不能证明目标规模容量或 PDE 精度。

---
# Task40extra 当前测试摘要：Review V10文档收口与版本分列测试（V9及更早记录保留）

## Review V10 证据、工程修复与文档收口

| 检查集合 / source | 命令或证据 | 结果与边界 |
|---|---|---|
| 原始 A 定向测试，Git source `45a388fa12afb69a29afaa0240a72018a0069967` | V10 原 A 测试记录 | 44 passed，按该次原A源回执；保留为旧源测试结果 |
| A checker相关测试，Git source `b2c5ae94ebec1394e4b659dd6b8aef26866b5b38` | Task40 qualified activation下既有记录 | 30 passed in 2.96 s；不与其他source的fixtures合并 |
| A V2输出目录守卫fixtures，冻结source `a4ac46a8d796f9c101a0b4b9364bf01e9101dd50` | V2 runner fixture既有记录 | 3 passed in 0.52 s；与前两组分开，不求和宣称统一覆盖 |
| V10 ABI preflight（最终文档收口） | V10 `4.2 qualified activation；解析`runtime_prefix`下解释器与petsc4py/slepc4py/dolfinx/mpi4py | PASS；Linux；PETSc complex128/int32；全部模块来自同一runtime_prefix。较早一次探针错误地要求root/.venv，断言失败只反映路径条件不适用于Task40，不是ABI环境失败；随后按真实runtime_prefix resolve重跑通过 |
| V10文档合同测试 | `python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py` | 24 passed，134 subtests passed in 0.17 s；文档/registry/retrospective contracts only，无PDE |
| V10数值 / 全仓范围 | 本次收口 | 本次未追加FE/PDE或数值测试；此前V10的A边界与B0运行及负结果按Response/records登记。全仓pytest、MPI4、Ruff、CI未运行 |

上述测试属于不同源与fixture集合，不能相加为一个“通过总数”。定向测试不证明official R/T/A或目标尺度能力。
| 检查 | 命令 / 记录 | 结果与边界 |
|---|---|---|
| W1解析矩helper定向测试（V9 source `50f29a285d25b20ba0c4d34e6d6b9e2d8ce46de8`） | Task40资格化本机activation后运行`python -m pytest -q src/test/test_task40_w1_moment_reference.py` | `6 passed in 4.29 s`；只测独立高精度矩helper；不含FE/PDE。此为已有回执，V9文档收尾未重跑 |
| 收尾文档/记录检查 | 最终修改后`git diff --check`、JSON解析、原样快照SHA核对 | PASS：git diff --check、JSON解析、hash-bound证据、原样快照cmp及旧run-index字段保持核对；不是pytest或科学Gate |
| V2 raw持久性/ZIP/NPY头部目录 | qualified ABI下只读fsync、重开SHA、10成员CRC和shape/dtype目录 | PASS；无数组值、积分、残差、FE或PDE读取/计算 |
| helper静态检查 | qualified ABI preflight；对已提交helper与test执行compileall；检测ruff可用性 | ABI preflight及compileall PASS；Ruff `NOT_AVAILABLE`，未安装；未重跑6项数值测试 |
| 全仓pytest / MPI4 / Ruff / CI / 新PDE | 本轮无此类执行 | `NOT_RUN`；不声称CI通过 |

V9所列负实轴球Bessel分支、分析脚本维度修正、依赖安装和命令修复不混称为测试通过；耗时不完整的阶段保留`UNKNOWN`。clock-only RSS/swap不能作为测试或归因阶段资源结果。

---

## Review V6 closeout（V9之前历史测试记录）

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

原生 W0 handoff packet 已从 `/tmp/task40_native_handoff_4c98a859.b64` 解码并在本地逐项复核：packet 为 113,898 B、SHA256 `4c98a859a265bb942cc2eb3e37cead21f0fafd2251574bbe742f1cef61cf4d3d`；19 个 UTF-8 成员的字节长度和 SHA256 在写入前及 ignored artifact 回读后均通过。整包及全部成员保存在 `benchmarks/artifacts/task40extra_0p7nm_engineering/native_w0_handoff_4c98a859/`；13 份轻量 raw ABI/audit/import/resource/host 身份收据按原字节复制进 tracked receipt 目录，另外记录持久副本 stdout（明确标注为控制端回读 stdout，不是 packet member）。路径、全部成员 SHA、tracked receipt SHA 与复核边界见[原生 W0 handoff index](records/native_w0_handoff_4c98a859/handoff_index.json)。长安装日志、包清单与辅助脚本仍只留在 ignored artifacts，由 artifact manifest hash-index。

收据中的状态和边界如下：三项浅导入预检通过；真实命令 `python -c 'import src.solvers.dtn_port_3d'` 在 source `5be1210aa79f25c13a7677cc291a4a766a548650` 上于 `2026-10-04T03:24:37Z–03:24:38Z` 因 `ModuleNotFoundError: No module named 'pyvista'` 以 exit 1 停止，调用链为 `dtn_port_3d → common_3d_utils → solve_vector_maxwell → postprocess → pyvista`。FE start event `NOT_REACHED`，W0 component、dry admission、worker、checker、official physics、raw archive 均 `NOT_RUN`；这属于 FE 前入口 blocker，不是数值测试或 PDE 失败。ABI receipt SHA256 `4ef26bf3d4ea0b3c16170b030694e7de7a303108e5fd78b3309835d0c4aa5102`、closure JSON SHA256 `64f65b92b8379c432cf87c6f6d97b62108236e67512eade1699b22cdde9c20b7`、stderr trace SHA256 `343939c7bec310f03c05134763e4aef504d9997abb40f06956bdb08dcf2af01a` 已在 tracked receipt 中原字节保存。

03:35:29Z 宿主快照 `MemAvailable=2,089,370,224 KiB`（约 `2.1395e12 B`）；Task42 进程组在 03:34:11Z 前后已不见，Metrology 仍活动。本轮资源/空闲窗口为 `HELD/NOT_ATTEMPTED`，不是容量失败：宿主 SwapUsed 基线及末次观测均 21,600 KiB，但基线时间缺失；相等读数只得到 derived 0 KiB 差值，不能归因给 Task40；pswpin/out 的初始计数未采集，增量为 `null`。整体准备起点、monotonic/boottime 与 W0 预算消耗都未知；packet 中的 34.489 s 和 771 s 是 UTC-derived 局部区间，不是安装耗时、FE 耗时或预算扣款。

保留的辅助诊断也按实际类型分类：两次 readback 误报分别是 lexical venv Python 与 resolved symlink 被错误要求相同路径，以及假设 `dolfinx_mpc.__version__` 存在但模块未提供该属性；分别改用 prefix 同源核对和 conda-meta/dist-info 版本证据后通过，均未重建环境。只读 `micromamba list` 与 `micromamba --version` 查询曾以 `tl::bad_expected_access` 失败；包事实由 conda-meta 读取，版本查询未生成 core dump（`ulimit -c=0`），canonical repo 状态复查未变。这些是读取/断言诊断，不等于 ABI 或 package 环境失败。

原生 packet 文档收尾后，资格化 activation 轻量 preflight 再次通过；相同的三文件文档/模型注册/回顾合同 suite **24 passed in 0.05 s**。最小交叉 hash/index 检查通过：run index 的 response、增量账、四角父接口、V4/V6 历史引用和 handoff index 指针一致；packet 为 113,898 B、SHA256 匹配，19 个 artifact 成员及 14 个 tracked receipts 的长度/哈希匹配；W0/W1/W2 与 V6 settled debit 状态一致；`git diff --check` 通过。首个检查脚本自身曾把仓库相对路径再交给 `Path.relative_to(root)`，在文件校验开始前因 `ValueError` 退出；没有改写文件或触及证据。修正为根目录路径拼接后，上述检查通过。该脚本处理错误不是项目、packet 或数值失败。

## Review V7 W0 实际运行与离线收口（2026-10-04）

| 检查 | 命令/来源 | 结果 | 范围与边界 |
|---|---|---|---|
| Native 16-module import closure | earlier native startup preflight at source `74bfcddf52cc97b518e71154dc47d59654fd4a8e`; formal W0 run source `4b89d7f922bda3859048d20714557ac0cf07ffc6` used its own fresh ABI receipt; metadata-only identity fix `5f74e15fae6e01e4361325db162806a7319ba3f4` did not rerun the 16-module closure | 16-module closure passed at the earlier preflight; the 4b89 W0 startup ABI receipt passed independently; 5f74 explicitly reran the saved-receipt public validator in list and tuple forms | Import closure is historical startup evidence, not a new 5f74 test or FE/solver pass |
| Runner scope / degree gate | Read-only inspection of `benchmarks/run_fresh_c1_p6_component.py` at SHA `7290d392a9ac4c00b1bc1a3f070da947b62414865b29faac8f07814315a3ef36` | degree tuple `(6,)`; asserts `spaces == {6}` and `floquets == {6}` | Confirms p6-only setup; filename/config `q4` label was not run as four q branches; no p4 or q factors |
| W0 frozen budget manifest | `benchmarks/fresh_c1_p6_w0_budget.json`, SHA256 `533930676db07f7a145e0e6b71eacd198288bea92717bf7a8ba91fe9d16a9b81` | raw-member disk cap `8,589,934,592 B`; derived worst-case `6,900,030,936 B`; margin `1,689,903,656 B`; separate process-tree cap `3,221,225,472 B` | Derived admission contract; not measured output/RSS/capacity; legacy checker assertion still expects 512 MiB and was not changed |
| Native focused component suite | `python -m pytest -q -p no:cacheprovider src/test/test_fresh_c1_p6_component_contract.py src/test/test_fresh_c1_p6_native_tensor_checker.py` | `40 passed, 10 skipped in 0.39 s` | 10 项因 archive fixtures unavailable 而 skip；未对原始 tensor/CSR 数据执行 checker，且该 raw 未生成 |
| Actual W0 worker | native run `w0_20261004T0638Z_4b89d7f` | `WORKER_FAILED`, exit 1，tuple/list mode identity guard；196.762108860 s，RSS peak 1,408,434,176 B，task swap 0 | fresh setup 与 same-live component receipt 已生成；full p6 worker/raw export 前退出，不是 time/resource stop |
| Saved-receipt public validator: list | 捕获 native stdout `/tmp/task40_w0_fix5f74_list_tuple_stdout.json` | PASS；1.411307457 s 内部 / 1.58 s outer，46,796 KiB max RSS | JSON list 身份；FE/JIT/mesh/form/matrix/factor/PDE 均 NOT_RUN |
| Saved-receipt public validator: tuple | 同一 stdout 与同一 receipt SHA | PASS；1.404511847 s 内部 / 1.58 s outer，47,108 KiB max RSS | Python tuple 身份；离线验证，不是 worker 重放或 scientific raw checker |
| Captured validator stdout identity | root readback of native public validator stdout `/tmp/task40_w0_fix5f74_list_tuple_stdout.json` | `1,951 B`; SHA256 `b563cbce296c0740b707aa48394bc3fd15cb8cdbc5a89dbb6f473db5e01a8c89` | validator SHA `aec3ae90634ce8ef0f18d3490097e331f863dc56cc4d978c0e2244a22af4673d`; qualification SHA `fb572d7f1ab6f0e5bc2b94cc14bbb3d9a3bd9d1c6b637aa59a7926121c5ddfdb` |
| 本地文档合同 suite | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_26_documentation_contract.py src/test/test_development_model_registry_contract.py src/test/test_29_task_retrospective_contract.py` | `24 passed in 0.05 s` | 使用本地旧 PETSc 3.19/Open MPI 4.1.6 activation，仅测文档合同；不代表 native W0 ABI 或 PDE |
| Snapshot, packet 与 compact hash | qualification activation 下的单次 Python hash/index 合同检查 | PASS | 5f74 ledger snapshot byte-equal 到 commit blob；small packet archive 与 3 JSON members 的长度/SHA 匹配；native 36-file copy/readback 由本地 manifest 逐项报告，但原 member bytes/tensor arrays 不在主线 |
| `git diff --check` | 仓库根目录 | PASS after final content edits | 纯文本空白检查；不提供 Markdown GitHub rendered-view 证明 |

Native component-only receipt 的重算 Gate 数值、worker 失败位置、4 小时 policy cutoff 与 10:07:14Z launch deadline 的区别、scientific raw 不存在的原因见 [Response V7](../response_v7.md) 与 [actual-run record](records/native_w0_actual_run_v1.json)。



早期 native worker attempts 的 measured elapsed 子计时和 6bbc shell blocker 的 unknown cost 见 [Response V7](../response_v7.md) 与 [incremental ledger](records/review_v7_incremental_workflow_ledger.json)。三次 worker 仅小计 worker elapsed，不折算完整 W0 准备或收费。

本轮离线证据身份进一步确认：原 35-member 包（47,078 B，SHA256 `d5f934e09e034b1349c2860948e1dc91ec24c9670ba6dd5939a01bc8e6379f62`）是运行日志/ABI/资源/测试收据，不是 tensor/场数据；native 侧 36 份支持文件共 5,757,491 B，逐文件 SHA 和 copy/fsync/readback 通过。worker 在 scientific raw export 前失败，原始 p6 tensor/field 数组根本不存在；另一次支持收据跨窗传输被 auto-review 拒绝后，没有尝试替代通道。JIT 64 files / 1,220,807,231 B 留在 native 原路径，未复制。


## Review V23 定向验证与未运行范围

定向验证针对最终 patch 内容，随后主控冻结同一内容为 43588de8275a1014375ab8d5fdd1d835b0bcee55。测试只覆盖服务 selector、stage/checker 接线和 fixture 原始贡献重算，不代表真实 Ny=8 q tile 或 PDE 通过。

| 验证 | 结果 | 范围 |
|---|---|---|
| route/probe selector | 19 passed, 39 deselected in 3.06 s | 定向命令选择的 route/probe tests |
| numeric-stage | 3 passed in 0.09 s | stage 状态和 route shape，不运行 FE |
| q contribution/projection readback fixtures | 2 passed in 0.18 s | 从 fixture raw data 重算 C、-D、H 与身份 |
| 真实旧 checkpoint binding helper | PASS | 校验 32,060-mode metadata/payload/source/input/window identity；不是 q FE |
| py_compile / git diff --check | PASS | 语法和 whitespace 检查 |

测试输出保存在执行 transcript；未另存 pytest log，因此没有独立 log SHA。full repository pytest、MPI2/MPI4、Ruff、CI、documentation contract suite、q-only service、FE/q tile、q CSR/factor/KSP/PDE 均 NOT_RUN。控制器在固定数值 cutoff 后要求停止数值运行，不从未运行项推断通过。

## Review V27 / V29 final closeout (no replay)

| 验证 | 实际结果 | 范围与边界 |
|---|---|---|
| source-focused regression | **79 passed, 1 skipped in 29.74 s** | 覆盖 `test_362_partial_assembly.py`、`test_task39extra_v24_p4_repair.py`、`test_task39extra_v25_dynamic_checker.py`、`test_task39extra_v28_profile.py`、`test_task39extra_v29_p6_raw_tensor.py`；唯一 skip 是 `test_362_partial_assembly.py:712` 的显式 tiny MPI2 qualification。 |
| documentation contracts | **21 passed (<1 s)** | `test_26_documentation_contract.py`、`test_183_development_model_registry_markdown.py`、`test_development_model_registry_contract.py`；覆盖 p4/p6 归属、setup峰值口径、CPU/wall-time unknown 及 V29 selective manifest 的最终本地复核。 |
| JSON parse / `git diff --check` | **PASS / PASS** | 7份本轮 compact/component/checker/decision/selection/refinement/run-index JSON均为对象；所有变更通过 whitespace/error 检查。 |
| formal PDE / R1 | **1 formal V29 run / R1 not replayed** | 用户选择保留 R1 部分证据并停止重跑；本轮为文档和记录收口，没有额外数值运行。 |
| full repository pytest / Ruff / CI / MPI2/4 | **not_run / not_run / not_claimed / not_run** | 仅报告以上本地 targeted suites。 |

## Review V26 / V28：修复后正式验证追加

修复后按明确授权完成一场正式 V28 运行：126步、独立最终显式真残差 `9.283164917015627e-7`、dynamic checker `DYNAMIC_PASS`。现成离线全 FE 指标 `L2/scaled-curl=2.38e-14/8.92e-14`，80模态功率、通道和 E/H/curl 导出检查通过。旧 V24 `old_b_regression` 返回 `PARTIAL_PASS_POINT_SAMPLES_AND_MODAL_ONLY`，原因是它还查找本次不适用的 V24 专用 metric/watchdog 文件；不改写这个 raw 状态，完整 V28 FE PASS 由独立报告提供。Checker 输出、哈希和细节见 [post-repair compact](records/fused_operator_speed_v28_post_repair_compact.json)。最终文档合同测试 `21 passed in 0.09 s`，四份权威 JSON 解析与 `git diff --check` 通过。本轮只用现成工具做离线证据核验；未运行组件试验或第二场 PDE。

## Review V26 / V28：库存与融合预算 bug 修复（修复前测试记录，保留）

| 验证 | 实际结果 | 范围与边界 |
|---|---|---|
| ABI preflight | **PASS** | qualified WSL activation；Python `.venv`；PETSc complex128/int32；同一 Linux MPI/DOLFINx ABI |
| fused owner inventory / workspace budget / V28 profile focused tests | **15 passed in 1.44 s** | 三文件：`test_task39extra_v28_fused_kernel.py`、`test_task39extra_v28_profile.py`、`test_physical_schur_v14_budget.py`；small fixture 实走 packed factory 的 split/fused inventory 与预算字段；正式开关 `shared_contractions=False` |
| compileall / `git diff --check` | **PASS / PASS** | 覆盖本次两处 production 文件和回归测试 |
| 文档合同 / compact JSON parse | **21 passed in 0.06 s / PASS** | `test_26_documentation_contract.py`、`test_183_development_model_registry_markdown.py`、`test_development_model_registry_contract.py`；compact、decision、run index 可解析 |
| source fix fresh PDE | **not_run** | 一次 replay 已消费，保留用户“停止重跑”选择；不可把 unit tests 写成 PDE qualification |
| full repository pytest / Ruff / CI | **not_run / not_run / not_claimed** | 仅报告本地 focused suite；未安装 Ruff |

修复前 V28 run 在 KSP 前以真实 `KeyError` 退出；上述历史 focused tests 只验证最小接口修复，不改变原 raw run 的 `WORKER_FAILED` 分类。此后另一次获准 post-repair run 的状态见本文件顶部；详见 [V28 outcome](fused_operator_speed_v28.md) 与 [Response V29](../response_v29.md)。

## Review V25 / V27 engineering closeout (no formal solve)

| 验证 | 实际结果 | 范围与边界 |
|---|---|---|
| R0 V27 profile/launcher/worker/watchdog mock route | PASS | original-only guard、observe-only time/swap policy、V23 physical-memory-pressure policy；无 PDE |
| focused suite | **47 passed in 8.29 s** | ABI preflight PASS (qualified WSL, PETSc complex128/int32); five files: V27 setup, V25 checker, V20 lifecycle, V22 capacity, V22 launcher |
| R1 engineering probe | **NO_REPRODUCED_IMPLEMENTATION_REGRESSION** | attempt03 adapter failure preserved; one later authorized probe-only replay completed i=16 BAL_H and i=112 A6/H6/BAL_H; all six groups pass equivalence gates; no formal PDE |
| R2 selection / R4 | `NO_ADOPTED_CHANGE` / `NOT_RUN` | 不把未配对工程 setup 时间差当因果收益；未启动正式 PDE |
| full repository pytest / Ruff / CI | not_run / not_run / not_claimed | 仅报告本地 targeted suite |
| final documentation contracts | **21 passed in 0.07 s** | `test_26_documentation_contract.py`, `test_183_development_model_registry_markdown.py`, `test_development_model_registry_contract.py`；针对最终记录改动复核 |

测试结果与工程 factor、正式 PDE 分开报告；本批没有新的求解残差或物理输出。

---

## V26 setup-efficiency 收口检查

| 验证 | 实际结果 | 范围与边界 |
|---|---|---|
| V26 formal result | **PASS, one formal run** | 本轮正式运行 126 步，显式真残差 `9.283164976754267e-7`；执行端另一次启动在 worker 前 gate rejection，没有第二场 PDE |
| saved field / channel / power regression | **PASS** | 只读取已有 V26 与 r2 输出；FE field、80/80 channels、saved-output、modal/power/closure checker 通过；不创建 solver |
| V26 every-16 checkpoint report | **AVAILABLE** | 读取已有 worker snapshots；16/32/48/64/80/96/112/120/126，未把 gate rejection伪造为新 checkpoint |
| policy / parameterization targeted suite | **23 passed in 5.54s** | `test_task39extra_v25_parameterization.py` + `test_physical_schur_v14_q4_mock.py`；source `32bf03e0ab50ea67487ecb1ca06f5da468800482`；没有用修复 source 重跑 PDE |
| V26 route replay evidence | **22 passed** | replay record 中的 Q4 route、summary dispatch、Q3/Q2 boundary focused suite；不是第二场 PDE |
| component operator pair | **QUALIFIED_OPERATOR_EQUIVALENCE** | 990-cell raw/rechecked pair；A6/H6/diagonal checks pass，no p4 factor/no formal PDE；optional projection reuse disabled |
| dynamic raw p4 accounting | **derived PASS for BAL_H/p4/residual/Aq/Arnoldi** | 131 boundaries、262 logical units、267 MatSolve、5 repairs；max final p4 relative `7.243731544969288e-11`; generic backend string gate is separately recorded because V26 has its own frozen backend identity |
| replay gate rejection | **PASS as negative classification evidence** | systemd/service 约束在 worker 前拒绝；无 factor/KSP/iteration；ledger 未修改 |
| T5 numeric cache reuse | **DEFERRED** | 无 qualified packet loader/schema；numeric cache load=0；没有第二场 |
| targeted tests / compileall | **to rerun after final docs** | 使用 qualified activation；只报告本地 targeted 结果，不声称 full repository pytest/CI |
| Ruff / full repository pytest / CI | **not_run / not_run / not_claimed** | 不安装工具、不扩大范围 |

测试集合与正式 PDE 证据分开，不相加冒充覆盖率。

---

# Review V23 / Response V26：V25 coarse-degree closeout checks

| 验证 | 实际结果 | 范围与边界 |
|---|---|---|
| V25 common source / focused suite | 92 passed，1 skipped | S1/S2 implementation, parameterization, runner/schema and checker contracts；skip 为未用 MPI fixture；不是 PDE 重跑 |
| Q4/Q3/Q2 formal runs | Q4/Q3 existing PASS；Q2 existing RESOURCE_CONTROLLED_STOP | source cad282e25ed53cad1f9e4a5a70c14f3dd40e6d32；本次 S6 只整理 raw evidence，不重跑 PDE |
| Q4/Q3 dynamic checker | DYNAMIC_PASS | checker 从原始字段重算；Q2 terminal checker not_run |
| FE audit glue promotion | tracked utility added; FE audit not rerun | 只修正 repository-root parents 层级；旧 ignored tool SHA 与 audit-recorded SHA 保留；当前 promoted tool SHA=`507fe2b7de074dc5482b4f8343e6920a23618c11d05efb1a41ad6c86c5896099` |
| JSON / link / syntax / diff closeout | **PASS** | qualified activation 下解析 7 个 V25 JSON；核对 promoted tool SHA=`507fe2b7de074dc5482b4f8343e6920a23618c11d05efb1a41ad6c86c5896099`、本地链接和 Q3 condensed rows=`45440`；`python -m py_compile benchmarks/fe_metric_v25_q4_glue.py`、`git diff --check` 通过；不等同 full repository pytest |
| Ruff / full repository pytest / CI | not_run / not_run / not_claimed | 没有安装新工具或虚构 CI 结果 |

测试集合不相加冒充单一覆盖率；正式 PDE 资源、残差和官方结果与工程测试分开登记。

# Review V22 / Response V25：V24 formal B 测试与边界

| 验证 | 实际结果 | 证据/边界 |
|---|---|---|
| V24 formal service | **exit 0 / watchdog COMPLETED** | MPI1、single-core；systemd inactive/dead；descendants cleared；swap peak 0 |
| V24 solver gate | **PASS** | 126 iterations；explicit final/post-release residual=`9.283164961979326e-7`；门槛 `1e-6` |
| V24 physical checks | **PASS** | field/channel/power/energy/modal/identity/post-release checks all true；官方功率来自 DtN port modal amplitudes |
| V24 authority | **LIMITED** | 没有匹配 h7.5 reference；不作 continuum-convergence claim |
| V24 formal resources | **AVAILABLE** | formal watchdog RSS/PSS=`7339319296/7307023360 B`；zero process-tree swap；16998 samples；resources SHA=`0b220a16d4cb096ea6a00a808e1a76b547bee42867b5152044f04e1e5e6a4e79`；worker `1142` samples仅非权威旁证 |
| V24 offline checker / audit | **PASS** | checker targeted pure-data suite=`8 passed in 0.19s`；独立 raw-field audit `passed=true`，SHA=`58ca321b21a01ac60a57beaf1699c9f76f17f0b92a8f2af7a565fbc96c0b32ef`；py_compile通过；不启动 solver/PDE |
| V24 saved-field FE metrics | **AVAILABLE / PASS** | L2=`1.8744734231920724e-14`、scaled-curl=`1.351616670038343e-13`，限值 `1e-4`；artifact SHA=`37dcc93c5747cb31db49c8e858ba2cc8c139fbe7e42ebe9db3d95d46b29fe782`；由 absolute/reference 重算，不是新 PDE |
| V24 FE metric wrapper boundary | **COMPLETED with strategy deviation** | 成功 wrapper `24.127236970991362 s`、RSS=`559112192 B`；首次 wrapper `TIMEBASE_INCONSISTENCY`=`49.30150357799721 s`、RSS=`1280192512 B`、swap0；两者均清场；成功记录使用 legacy static memory envelope + `time_policy=enforce`，不是 formal resource authority |
| V24 solver/factor/timing evidence | **PASS / measured** | KSP true monotonic=`3716.1522563079925 s`；factor INFOG19/22=`4687/4326 MB`；JIT=`11 hit/0 miss`；correction boundary=`2.602906637999695 s`，bare interface=`0.9039880140044261 s`；无精确 KSP-end resource timestamp，不伪造 pure-KSP RSS window |
| V24 component boundary | **QUALIFIED BUT NOT FORMAL SPEED CLAIM** | owner 首次 P/PH baseline=`4.10675620699476/0.7427930510020815 s`、candidate=`0.3230319220019737/0.3155690860003233 s`；三次 warm 中位 baseline=`4.218087512999773/0.7719355450026342 s`、candidate=`0.32633427099790424/0.2924728030047845 s`；full-PC 是 owner+packed-A6+packed-power10 组合而非 owner-only 直接配对，setup/apply=`206.372522398/53.11041180999018 s` vs baseline=`136.53963406301045/52.3144450539985 s`；soft/hard `25/30 s` 是 `observe_only` 历史 metadata；组件结果不替代正式 PDE |
| V24 relevant pre-formal focused suite | **104 passed, 1 skipped** | source route/owner/profile/solver contracts；qualified activation；skip 为未用 MPI fixture |
| V24 timing/release suite | **50 passed** | timing marker、旧 release 生命周期与 V24 接线；不含新 PDE |
| compile / diff check | **PASS / PASS** | Python compileall 与 `git diff --check`；Ruff 未安装，未声称 Ruff/CI |
| docs-only 收口合同 | **21 passed in 0.14s** | `test_26_documentation_contract.py`、`test_183_development_model_registry_markdown.py`、`test_development_model_registry_contract.py` |
| PETSc/MPI post-doc rerun probe | **not_repeated_environment_blocker** | 当前受限 shell 的直接 MPI import 命中已知 PMIx socket restriction；没有启动 PDE，也不改判同 source 的既有 qualified code tests 或正式 service |
| 2/4-thread qualification | **not_run** | 没有 memory-neutral 正证据，正式保持 single-core |
| full repository pytest / CI | **not_run / not_run** | 只陈述本地 targeted tests，不声称 CI |

测试集合不相加冒充单一覆盖率；正式 PDE 证据与工程测试分开记录。旧 V23 `58/59`、旧失败和 authority limitation 保持原样。

# Review V21 / Response V22：Z5 证据、测试与 formal 边界

Z5 汇总阶段只读取已保存原始记录，没有额外 PDE；本批 Z2/Z3 已分别启动 A、B，C 未运行。测试集合保持分离：Z1 preformal engineering qualification=`99 passed`；A 更正 repair path=`49 passed`；A checker/recheck=`65/65` checks；不能把三者相加。B checker=`not_run`，因为 B 没有终态 residual 或 physical fields。

| 验证 | 实际结果 | 证据/边界 |
|---|---|---|
| A formal residual/physical | PASS | worker explicit residual=`9.756517234801763e-7`；independent A6=`9.756517234802322e-7`；80 modes、R/T/A/`A_volume`、closure、field/curl gates 通过 |
| A checker | **65/65** | current/recheck hash=`149747de773e9cded62898195cc4b1e58d0714cf691e5b7b7c20316619590bce`；original failed copy 保留，原失败仅 `release_timeline`、`summary_schema` |
| A corrected repair path | **49 passed** | `benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z2_root_fix_targeted_tests_corrected_path.log`；不含 PDE 重跑 |
| Z1 preformal engineering qualification | **99 passed** | `benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z1_final_targeted_tests.log`；与 49/65 分开统计 |
| B resource stop audit | PASS as classification evidence | p4 CSR identity、symbolic stats、capacity arithmetic、parent/worker/systemd terminal fields 均保存；B checker 不运行、不伪造通过 |
| Z5 frozen authority | **passed** | `50` frozen files、`26` old profiles、`changed=0`；SHA256=`880534b2c2bb72939669ef098cb809510b666930101a74a0a1312905e0b3a5b3` |
| Z5 文档合同 | **15 passed** | `benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z5_root_documentation_tests.log`；仅文档检查，无 PDE |
| Z5 saved cost comparison | read-only verified | SHA256=`87975d656484936f6b3ca1ca067bd539fd6a752a91a98acb8816fd2e6fe1d577`；O10/A 单步及 setup measured fields 分开记录 |
| prepared-form cache audit | consistent | O10 `10 hit/1 miss`（`p6_condensation`）；A/B 各 `11 hit/0 miss`；A/B 无 compiler descendant samples；不声称 warm-cache RSS 收益 |
| 未运行/未声称 | not_run | C、B outer solve、numeric factor allocation、Ruff、full repository pytest、CI、MPI2/4 新资格、任何新 PC 或新 heavy PDE |

几何审计也已冻结：notch union=`x=[16.5,33.5] nm, y=[0,8.333333333333334] nm, z=[40,80] nm`，8 个实体；h7.5 每轴 `[9,5,22]`、owned cells=`990`，含 neutral alignment planes，不写成 720 cells 或 uniform multiplier。Z1 base=`f9e16c21b936673b5a2dadcf52d2c344e61aabe8`；当前 pre-Z5 HEAD=`f8d0fbf3da48fd3cbe5cc3a226dbff3feb1d9b48`。没有声称 GitHub Actions/CI 通过，也没有把资源控制停止当作数值失败。

证据入口：[V21 compact](records/dual_condensed_robustness_v21_compact.json)、[V21 decision](records/dual_condensed_robustness_v21_decision.json)、[Z5 frozen authority](../../../benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z5_root_frozen_authority_check.json)、[Z5 saved cost](../../../benchmarks/artifacts/task39extra/dual_condensed_robustness_v21/root_engineering/z5_root_saved_cost_comparison.json)。

---

# Review V20 / Response V21：V20 low-memory lifecycle 的测试与 formal 边界

| 验证 | 实际结果 | 证据/边界 |
|---|---|---|
| ABI/Y1 admission | PASS | qualification 为 Python `.venv`、PETSc 3.19.6 `complex128/int32`、DOLFINx 0.10.0.post2、Basix 0.10.0、SLEPc 3.19.6、Open MPI 4.1.6 |
| 最终 focused suite | **116 passed / 1 skipped** | skip 是 MPI2/4 专用 fixture；不是 V20 formal failure |
| compileall / diff / frozen contract | PASS / PASS / PASS | `changed_files=0`、`changed_profiles=0`；formal source 为 `b337d215c3d278d0c1e715f53e28b69f7f0ee3fe` |
| Y3 independent checker | PASS | 57 independent checks、24 physical subchecks；保存 checkpoint 由 worker 每8步写入，checker 读取并重算 |
| Y4 文档合同 | **21 passed** | `test_26_documentation_contract.py`、`test_183_development_model_registry_markdown.py`、`test_development_model_registry_contract.py`；仅本地合同检查，未声称 GitHub 网页视觉核验 |
| 正式 original | PASS | 112 步，independent A6=`9.730817853580463e-7`，完整 field/80 modes/RTA/守恒/资源检查通过；formal run 1，PDE replay 0 |
| 服务与资源安全 | PASS | exit0、后代清场、zero swap、连续 parent-process-tree 资源记录；full RSS=`2831749120 B` |
| 后端 fixture 初次错误 | 保留工程失败，已修正 | 初次 NumPy `int64` 与 PETSc `IntType=int32` 不匹配；未启动 PDE，修正后 fixture 通过 |
| sandbox PMIx 现象 | 保留工程记录 | sandbox-only `errno=1`；实际宿主 qualified ABI/MPI1 通过，不计作数值失败 |
| 未运行/未声称 | not_run | notch、5 nm/0.7 nm、MPI2/4 新资格、Ruff、full repository pytest、CI、detach restart |

轻量证据 SHA：focused `f87cfccd8f5f512dd83d3b6f08268d3146449d16f2bfb6e316850a7d021751bb`；compileall `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；ABI `2524f8c8a3ee4d625cd8b091de1f89213ad20a66bf8c03b5569640855e6acfb4`；frozen contract `53c79154b678ce48d23e8b5a0f3185e896a1471c37ed25a34a8b3398a83f7b42`；independent `8224cf22ff7143315ae911c0011633f8554e596c2532e7a2789428eb17fbdef1`。

Y3 原始 field/matrix/factor/cache/timeline 仍在 ignored artifact root；本页只陈述本地测试与正式 evidence，不声称 CI 或全仓测试通过。

---

# Review V19 / Response V20：新p6保留空间原始模型完成

| 验证 | 实际结果 | 证据/边界 |
|---|---|---|
| 最终focused | 82 passed / 1 skipped，pytest 1.67 s | MPI2/MPI4专用fixture跳过；正式profile MPI1；代码与8eff提交相同 |
| 数学/FE覆盖 | PASS | 非Hermitian、非零Bi/Di/内部和端口RHS、MPC/方向、恢复恒等式、J增广逆、非交换反例、输入不改/重复/线性/清理、tiny非零RHS不误判 |
| 接线/旧路径 | PASS | retained FGMRES/public dispatch/ledger/checker、V18旧dispatcher/ledger/checker/core/ports及action-only回归 |
| compileall / public dat | PASS / valid | 最终实现后验证，未升级ABI |
| 非PDE服务 | PASS_AFTER_PROBE_FIX | 1个测试、2次工程尝试：第一次漏phase_path失败清场，修正后脱离调用shell正常完成；不是2次PDE |
| 正式同根X1 | PASS | 3个固定向量+1PC；恒等式≤5.97668e-14，PC计数1BAL_H/1H6/2p4，全部对象复用X2 |
| 正式X2与独立checker | PASS | 112步、A6=9.730817853580687e-7，完整原生E/H/80端口/功率/守恒/资源；一场、正式重放0 |
| 服务完整生存/退出 | PASS | user service inactive/dead、exit0、完整后代清场、zero swap；正式source_after clean |
| 交付静态检查 | PASS | 132份raw hash、43项独立checker条件、36条旧运行、45个冻结文件、24个旧profile、JSON/表格/公式围栏/相对链接；图表已目视检查。本地HTML已生成，Codex预览排队；浏览器/GitHub公式渲染未目视核验 |
| 独立checker入口纠正 | 保留工程失败 | 直接文件调用模块搜索路径失败，改用python -m从原数组通过；无源码修补/计算重跑 |
| 未运行 | Ruff（未安装）、full repository pytest、MPI2/4、CI | 不声称其通过；旧U2/U3/BLR/参考没有重复计算 |

测试日志`benchmarks/artifacts/task39extra/dual_cell_condensed_v19/root_engineering/x0_precommit_focused.log`，SHA256 `db6c054ef70a6f0fa4b298267148321c41336f104ea6698cf65e67f7d977cb28`。source `8eff068b06f4713cc6d1281c92ed82d370060403`，base `3c7b6ecfd7aede2651dd973052a097dbed601d03`。同shell先资格化activation/ABI；后续只有文档和证据变化，不触发重型回归。

```bash
source scripts/activate_myfenics_wsl.sh
python -m pytest -q -rs src/test/test_task39extra_v19_p6_cell_condensed_action.py src/test/test_task39extra_v19_adapter_identity.py src/test/test_task39extra_v19_retained_fgmres.py src/test/test_task39extra_v19_outer_dispatch.py src/test/test_task39extra_v19_profile_ledger.py src/test/test_task39extra_v19_checker.py src/test/test_task39extra_v18_outer_dispatch.py src/test/test_task39extra_v18_launcher_ledger.py src/test/test_task39extra_v18_cell_condensed_checker.py src/test/test_physical_schur_v14_q4_mock.py src/test/test_task39extra_v18_cell_condensed_core.py src/test/test_task39extra_v18_cell_condensed_ports.py src/test/test_229_task037_action_only_condensation.py
```

[完整结果](dual_cell_condensed_v19.md)与[compact](records/dual_cell_condensed_v19_compact.json)保存小测试、formal和原始hash。旧失败/未知记录在下方保留。

---

# Response V19 / Review V18 最终验证

| 检查 | 结果与实际范围 |
|---|---|
| 最终相关测试 | **106 passed in2.74s**，`root_engineering/final_delivery_tests.log`；真实单元/两单元、内部RHS/左右端口/MPC、CSR、重复/线性、清理、入口、ledger、旧BLR/profile/budget、KSP与计时 |
| original独立checker | 从保存数组/范数/计数/资源重算，完整p6A6/场/模式/近场/功率/守恒PASS；相关只读checker/ledger28 passed，未重跑PDE |
| 共享helper旧路径 | 最后相关改动后串行4 passed，MPI2三个fixture各rank3 passed；不是新MPI2正式大模型 |
| 非数值修复 | 两个计时bug已在第三次original完整计算中验证；notch父级寿命修复只做用户systemd ABI探针与新wrapper `--help`，退出0、bash语法通过 |
| 最新用户停止后的动作 | 新正式PDE为0；宿主原三PID不存在；未结算43200预留只作政策占用，重复行政收口无变更 |
| 文档/身份最终检查 | **21 passed in0.06s**；历史证据链接补齐records/，无数据改动，初次20pass/1fail日志保留。结果见`root_engineering/user_closeout_static_checks.json`与`user_closeout_documentation_tests.log`；不将静态校验冒充模型PASS |
| 未运行 | Ruff未安装；full repository pytest、MPI4新资格和CI未运行；服务方式完整PDE未运行（用户禁止恢复） |

最终相关测试命令（qualified activation后）：`python -m pytest -q src/test/test_physical_schur_v14_runtime_clock.py src/test/test_physical_schur_v14_fgmres.py src/test/test_task39extra_v18_*.py src/test/test_task39extra_v16_blr.py src/test/test_task39extra_v17_blr.py src/test/test_260_task038_input_schema.py src/test/test_physical_schur_v14_budget.py`。文档检查覆盖documentation contract与model registry contract/Markdown；另做JSON解析/hash、旧41文件和30-run前缀、compileall与diff检查。

原始成功source为`8a2d5cbba6ed834a6d731a30dd3735c8824fa762`；notch中断source为`c56437271a4e3c34c984e4c3dee111b61dc5130e`；后续只做运行方式和证据修正。开发期失败、两次original失败、BLR收益负结果、notch未知字段永久保留。[完整边界](../response_v19.md)。

---

# 当前验证：Response V18 / Review V17 的有限 BLR 试验

| 检查 | 本轮结果 | 证据范围 |
|---|---|---|
| 最终直接相关测试 | **137 passed in 1.23s** | V17、旧V16、控制/代数/接口、schema/launcher/dispatch；真实资格化WSL complex128/int32栈 |
| 小型 MUMPS API 检查 | 1e-3和1e-4各3×3通过 | 控制读回、一次symbolic/numeric、每动作一次MatSolve且无refinement；不是正式p4试验 |
| 输入 / 编译 / diff | 两个新输入validate通过；compileall与diff通过 | 没有另行声称dry-run；默认profile与旧证据保持不变 |
| 正式 T1 | `NUMERICAL_GATE_REJECTED` | 三RHS全部保存；Q=false、M=false；包装exit4/WORKER_FAILED来自数值拒绝 |
| 独立原始数据复算 | `T5_CLOSE` | 原A4恒等式和计数核验，保存矩阵hash缺失及strict slave-zero失败，未将checker正常退出当作PC通过 |
| 正式资源 | 通过 | 树RSS2672054272 B、PSS2641505280 B；zero swap、reserve/库存/工作区、清场成立；时间observe_only |
| 文档/Markdown最终检查 | **20 passed** | [本地日志](../../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/final_documentation_tests_v17.log)，最终新增文档与登记结构检查 |
| T2 / original / notch | not_run | T1内存准入失败，不额外启动计算 |
| Ruff / 全仓pytest / CI | unavailable / not_run / not_claimed | 沿用既有工具可用性，不安装额外工具 |

[最终相关测试日志](../../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/final_evidence_tests_v17.log)、[tiny MUMPS日志](../../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/tiny_mumps_v17_fixed.log)、[最终checker](../../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_checker_final_v2.json)和[独立主控复算](../../../benchmarks/artifacts/task39extra/p4_blr_tradeoff_v17/root_engineering/t1_root_audit.json)均为本地证据。正式source为 `a1bc6b54e613ebf91c5c97ecddcc14555b084ee0`；后续checker修改只补单位和证据口径，未重跑PDE。最初日志控制小测试错误及sandbox MPI限制保留为工程记录，正式fresh=1、replay=0。

前期工程只有UTC窗口4093.641020536 s，含root/Luna重叠工作和等待；更早准备及后期文档审核独立耗时unknown，不混入正式571.461267577 s或626.199033101 s保守结算。完整费用见[response_v18](../response_v18.md)。下方旧测试历史保持原样。

---

# 当前验证：V16 p4 BLR S2 与历史 V14/V15 证据分层

| 检查 | 已完成结果 | 来源与限制 |
|---|---|---|
| S0 qualified ABI / source gate | `PASS` | source `24bd767e6b0d158ac20deb360a135f10c0611ede`；complex128/int32、MPI1、线程1；formal input 启动前 clean |
| V16 directly-related targeted tests | **128 passed** | V16 BLR、controls/algebra/interface/schema/launcher/dispatch、real tiny MUMPS 和 saved Q1；不是 full repository pytest |
| 最终文档与 Markdown 合同 | **20 passed** | `test_26_documentation_contract.py` 与 `test_183_development_model_registry_markdown.py`；根控最终修订后验证，stdout 为 `p4_blr_v16/root_engineering/s5_doc_tests.log` |
| formal input validate / dry-run | `PASS / PASS` | `input/task39extra/v16_s2_blr_control.dat`；只验证配置路由，不是 PDE 结果 |
| S2 formal worker | `worker_exit0` / `S2_BLR_CONTROL_PASS` | 三 RHS、one factor、one MatSolve/RHS、native identity、field metrics和资源清场均有 raw evidence |
| independent checker | `quality_pass=true`; decision `STRONG_BUT_INSUFFICIENT_MEMORY_GAIN` | raw-vector/resource/factor/control fields 独立重算；Rpeak/Rlive未达S3线，因此S3/S4 not_run |
| formal resource | `PASS` | RSS/PSS readable、tree/inventory/workspace/host reserve、zero job swap、descendants cleared；full RSS peak `2741243904 B` |
| sandbox MPI permission / process-view record | engineering-only false negative，已由实际宿主复核纠正 | OpenMPI/PMIx singleton 权限和 sandbox PID 视图不计为 PDE failure 或 bug replay；本轮没有因此重跑 PDE 或增加 route |
| compileall / diff-check | `PASS` | parent formal source commit 后完成；本轮文档不改数值源码 |
| Ruff / full repository pytest / CI | unavailable / not_run / not_claimed | 不补装 Ruff、不把局部测试改写为全仓或 CI 通过 |

原始 V16 工程证据：[S0 preflight](../../../benchmarks/artifacts/task39extra/p4_blr_v16/root_engineering/s0_final_preflight.json)、[independent checker](../../../benchmarks/artifacts/task39extra/p4_blr_v16/root_engineering/s2_independent_check.json)、[phase audit](../../../benchmarks/artifacts/task39extra/p4_blr_v16/root_engineering/s2_phase_time_audit.json)。S0 app-reported `1761.112 s` 与最终 preflight engineering elapsed `5235.60104560852 s` 是重叠工程窗口，不相加；formal ledger 只计 S2 worker workflow。

[response_v17](../response_v17.md)、[p4 BLR outcome](p4_blr_v16.md)、[V17 compact](records/p4_blr_v16_compact.json)、[run index](records/run_index.json)提供当前 source、raw hash、三 RHS 和资源口径；下方 V14/V15 均为历史测试状态，不被 V16 S2 误并为完整 p6 资格。

# 历史快照（HEAD 原始当前段）

# 当前验证：V14/V15 续算、生命周期修复与 Q6 负结果读取

| 检查 | 已完成结果 | 来源与限制 |
|---|---|---|
| 同一 qualified ABI | complex128/int32、MPI1、线程1；新正式入口 clean | 沿用相同 Linux PETSc/SLEPc/DOLFINx 栈，未重新调查 ABI/MUMPS/metric。 |
| 时间策略 targeted 主批 | 77 passed in 10.99s | 对应实现随后提交 `6a8b273c383d5bd9da37d6630a48bd24d6a90cce`；纯 FGMRES policy 另9项，真实PETSc两策略另4项（0.40s）。这是此前已完成测试，非本次文档阶段重跑。 |
| owned active volume 生命周期修复 | 10 passed in 0.87s；控制测试另3 passed in 0.38s | `test_390_physical_interface_schur.py`、`test_physical_schur_v14_fint.py`、`test_physical_schur_v14_q4_mock.py` 等；释放owned句柄后作用/伴随/恢复不变，borrowed对象仍可用。实现提交 `188224ad5fc81b34156a0ae3678bd2121b1206da`。 |
| Q6 保存负结果读取 | 17 passed in 0.10s | `test_physical_schur_v14_q6_evidence.py` 与 `test_physical_schur_v14_evidence.py`；覆盖真实累计计数1/2/3、错误计数、非有限/零参考范数拒绝、全通过但BAL未完成不误判negative。 |
| Q6 reader 编译与差异检查 | compileall / diff-check 通过 | 17项测试在188 HEAD+未提交reader改动上运行，随后相同代码提交 `d9530636ab2f043a84235b515846b410a8deb4b3`；不混作188 clean源码的测试。 |
| 新正式数值 | Q0核心与Q1/Q2准确配对通过；Q3三输入全部未准入 | 第一次Q3资源停止保留，唯一重放完成三输入后BAL map guard异常；全部具体数值与门槛见详细结果表。 |
| Q6真实保存包 | MEASURED_NEGATIVE_CANDIDATE；Q6_FINALIZED | 主控已从三份NPZ残差向量重算rho并核对hash；Q6在d953 clean source上零PDE收口。不是p6或物理PASS。 |
| 最终文档合同检查 | **20 passed in 0.08s** | qualified actual-host preflight后运行 `test_26_documentation_contract.py` + `test_183_development_model_registry_markdown.py`；原始stdout/ABI记录见run_index当前组。未重复PDE或未受影响工程测试。 |
| full repository pytest / Ruff / CI | 本轮未运行 | 既有Task038 registry缺件仍保留；不安装工具或升级ABI为绿表补测。 |

原始工程证据：[生命周期修复记录](../../../benchmarks/artifacts/task39extra/p4_schur_v14/root_engineering/active_volume_release_fix_20260913.json)（SHA `c88528572d18227d0b670ae7f8bc81c7a515e6c587ec3bad94f9ad4d2b02e70d`）；[主控读包与17项stdout](../../../benchmarks/artifacts/task39extra/p4_schur_v14/root_engineering/q0_q3_time_observe_review_20260913.json)（SHA `f98926d4ed661b45156805a2a04be833124413eb487b1f01f7aef63c803d78a8`）。前者保留测试时未提交身份，最终实现SHA如表。工程完整总时长unknown；可核验单项计时与formal ledger分开，不双重计费。

[response_v16](../response_v16.md)、[详细数值/资源表](p4_schur_v14.md)、[run index](records/run_index.json)提供阶段source和原始hash。下方均为原时点历史测试/停止状态，不覆盖当前三输入负结论。

---

# 历史实施快照：V16 时间观察策略测试（正式续算前）

| 检查 | 最终结果 | 口径/限制 |
|---|---|---|
| qualified ABI / actual-host preflight | `PASS` | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`；PETSc `complex128/int32`；MPI1；实际宿主与正式入口一致 |
| V16 相关主套 targeted regression | **77 passed in 10.99s** | 覆盖 time-policy、budget/recovery、runtime clock、watchdog、evidence、Q6 和 Q4 mock；不替代 PDE qualification |
| 纯 Python FGMRES policy screen | **9 passed, 2 test functions deselected** | 覆盖 observe-only 的 step-64 数值 Gate 与时间观察语义；被 deselect 的两个 PETSc/KSP 测试随后在实际宿主参数化为下行 4 个 case |
| 实际 PETSc/KSP policy matrix | **4 passed, 9 deselected in 0.40s** | `enforce`/`observe_only` 两种策略均在单位算子测试保持 1 步 `TRUE_RESIDUAL_PASS`，在链式算子测试保持 64 步 `V14_PROGRESS_SCREEN_STOP`，KSP 数量断言通过 |
| current documentation contract | **15 passed in 0.08s** | `test_26_documentation_contract.py`；当前 response/compact 修改后复核 |
| JSON / py_compile / diff-check | `PASS` | compact 可解析，修改后的 Python 可编译，`git diff --check` 无错误 |
| PDE / formal physical qualification | `not_run` | observe-only Q0 尚未启动；无新的 R/T/A、residual 或物理 Gate 结论 |

此前默认 sandbox 的 OpenMPI/PMIx singleton socket `errno=1` 只表示执行环境受限；实际宿主复核已通过，不能计为数值失败或 implementation-bug replay。早期 fixture 期望错误保持其原有测试语义，不改写为 PDE 失败。

当前新增测试与策略边界见 [Q0/Q6 compact](records/p4_schur_v14_compact.json) 和 [response_v16](../response_v16.md)；正式运行仍须保留资源、存储、zero-swap、清场和数值停止证据。

---

# Review V15 最终测试与证据收口

| 检查 | 最终结果 | 口径/限制 |
|---|---|---|
| qualified ABI preflight | `PASS` | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1`；Python 位于 `.venv`；PETSc `complex128/int32`；Linux WSL2、MPI1、线程1；未混用 Windows 栈 |
| V15 recovery/runtime targeted tests | `24 passed` | 绑定实现 source `ea5ed4cd511a9f169cd5bbf63c06f33bfed85d9e`；覆盖 budget、runtime clock、Q6 evidence、recovery synthetic contracts；不替代 PDE qualification |
| compileall | `PASS` | `python -m compileall -q src scripts`；源码与脚本可编译 |
| final Q0 | `PERFORMANCE_CONTROLLED_STOP` | 一次正式 worker；assembly 后达到 600 s Gate；RSS/PSS 资源与清理证据已 hash-bound；没有 residual/field/official result |
| final Q6 | `Q6_EVIDENCE_INCOMPLETE` | packet 生成；外层 exit4 为既有 stage-pass 语义，`error=null`，new PDE actions 0 |
| documentation/model-registry Markdown checks | **20 passed in 0.05s** | `test_26_documentation_contract.py` + `test_183_development_model_registry_markdown.py`；本轮最终文档可通过这组检查 |
| historical registry contract audit | **1 failed in 0.01s** | 既有缺件 `docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_small_v2_checker.json`；未为本任务伪造或修复旧 Task038 证据 |
| Ruff / full repository pytest / CI | `not_run` | 当前 qualified venv 无 Ruff；没有全仓或 CI 通过声明 |

Q0 watchdog 2152 行中 2151 行 PSS 可读；可读样本峰值 `1734977536 B`，完整树 RSS 峰值 `1769385984 B`，另有 1 行 PSS 不完整。24 项 targeted tests 的实际命令、源码 SHA 和原始 stdout 文本登记在 [recovery compact](records/v14_io_recovery_v15.json) 的 `continuation.engineering_validation`；测试与运行状态入口为 [response_v16](../response_v16.md)、[Q0/Q6 compact](records/p4_schur_v14_compact.json) 和 [run index](records/run_index.json)。最终仍无 Q1–Q5；三类数值结论不因测试通过而改变。

---

# 历史快照：Review V15 宿主存储 Gate 测试与核验边界（后续已解除）

以下段落保留 R0 阻断时点的旧测试结论。

| 检查 | 结果 | 口径/限制 |
|---|---|---|
| R0 原子 I/O 探针 | `all_probe_checks_passed` | ledger/results 各两轮、每轮 `4194304 B`，共 `16777216 B`；独占创建、文件/目录 fsync、重开 hash、rename 和自身清理均通过；这是受限 sandbox 视图，不是宿主存储资格 |
| 宿主范围补充核验 | `INFRASTRUCTURE_BLOCKED` | 只读确认 Ubuntu-24.04 的 C: 承载卷余量 `827174912 B`；没有新增 probe payload 或 PDE action，但写入了本核验 JSON；`old_q0_matches=[]` 不等于历史清场已证明 |
| 旧 ledger / snapshot | `unchanged` | 原 ledger 与 `old_ledger_snapshot.json` SHA 均为 `b3ef68488207af8130cf906222f8699183881645ddbaa7e9cc5081b02eecf8f0`；snapshot mode `0444`；没有正式 policy debit 或 R1 migration |
| 本轮文档 ABI preflight | `PASS` | 沿用既有 qualified activation，complex128/int32、MPI1、线程 1；日志 `documentation_abi.log`，不重新资格化 MUMPS/metric |
| 本轮文档合同测试 | **20 passed** | `test_26_documentation_contract.py` 和 `test_183_development_model_registry_markdown.py`；原始输出 `documentation_tests.log`，不包含新 PDE |
| JSON / 证据 hash / diff | `PASS` | 旧数值字段、原账本和源码保持原样；新增记录只保存本轮基础设施停止及未执行范围 |
| GitHub rendered view | `not_verified` | 不宣称远端公式/表格渲染已通过；JSON、Markdown 合同和本地路径核对不替代这项检查 |
| V15 R1 / 新 Q0 / Q1–Q6 | `not_run_by_infrastructure_gate` | 没有新 worker、PDE、MPI2/4 或 official result；V14 partial Q0 和 parent EIO 历史保留 |
| V14 已通过 104/30 工程测试 | `not_rerun` | 复用既有 source-bound evidence；本轮为文档/compact 增量，不把旧测试重写成新测试 |
| full repository pytest / Ruff / CI | `not_run` | 没有 CI 或全仓通过声明 |

R0 的原始报告、宿主范围 JSON、时间口径、C:/D: 卷身份、历史 UTC journal 覆盖缺口和完整负结果见 [V15 I/O compact](records/v14_io_recovery_v15.json) 与 [response_v16](../response_v16.md)。旧窗口命令没有明确 UTC 基准，不能用其有限输出证明覆盖 `2026-09-12T12:35Z` 故障窗口；orphan/recovery/journal 行也不证明 EIO 根因。R0 已知收集时间 `2.387310507 s` 是应纳入原 43200 秒总预算的基础设施采集费用，本轮尚未写入 ledger；不代表 solver/PDE pass。

本轮文档测试日志与 ABI 日志位于 ignored `benchmarks/artifacts/task39extra/p4_schur_v14/review_v15/r0_io_recovery_20260913T140500Z/`，其 hash 和紧凑结果随 V15 compact 保存。上表检查针对最终文档；未执行的恢复草稿不计为测试通过代码。

# Review V14 工程测试（正式数值任务尚未完成）

| 检查 | 实际结果 | 边界 |
|---|---|---|
| 最终 qualified ABI | complex128/int32，PETSc 3.19.6、SLEPc 3.19.2、DOLFINx 0.10.0.post2、MPI1/线程1 | 同一 Linux activation；本地 MPI socket 需获准在默认沙箱外初始化，不升级 ABI |
| 最终 V14 与相关旧策略联合测试 | **104 passed in 9.71s** | 小型 Schur/P/Q/Fint/BAL_H、有限 KSP、watchdog、Q4 mock、Q6/前置证据检查；代码字节绑定 `5d239140d3931364bc16d35c45458189cd957808` |
| 最终输入 schema、旧 watchdog 和文档登记检查 | **30 passed in 12.69s** | `test_260`、`test_354`、`test_26`、`test_183`；当前实测通过，旧轮次失败记录仍保留 |
| compileall / diff-check | 通过 | 最终源码修改后执行；无正式 PDE |
| 实际账本的只读 Q6 smoke | `Q6_EVIDENCE_INCOMPLETE` | Q0 保留未结算；缺 Q1/Q2 不变成方法失败；账本 SHA 不变 |
| Ruff / full repository pytest / CI | `not_run` | 当前资格化环境未安装 Ruff；不声明全仓或 CI 通过 |
| 正式 Q0–Q6 | Q0 partial，其余完整结果不可用 | 工程测试不能填充三 RHS 精度、全过程资源或 p6 物理结果 |

[工程证据 JSON](records/p4_schur_v14_engineering.json)保留 27 份原始日志、hash、代码文件身份和早期失败；各阶段测试集合重叠，不相加当作新的测试总数。完整工程编辑/监督耗时未单独计量，不能写成零。正式中断边界见 [response_v15](../response_v15.md)。

---

# V13 512 MiB 续算测试与独立审核（当前）

| 检查 | 结果 | 口径/限制 |
|---|---|---|
| qualified activation preflight | complex128/int32，PETSc3.19.6，MPI1/线程1 | 复用已资格化 ABI/MUMPS；MPI socket 受默认沙箱限制，测试与正式运行在获准的同一Linux栈完成 |
| test_410 | 10 passed | pytest1.03s，外层wall1.34s；局部算子与观察接口 |
| 相关组件测试 | 14 passed | test_412、packet lifetime、schema和profile；不是另14个互不重叠的新测试 |
| 最后局部清理后的 targeted tests | 7 passed | test_412 + packet lifetime；代码源 `3457b5e2f54dec690fcb70deb1f387fe7f6d57cd` |
| 源码 compileall / diff-check | 通过 | 无新增PC方法实现；后续文档改动不重跑昂贵PDE |
| 源码 Ruff 0.11.13 | 12个变更Python文件：历史82条，当前82条，新增0 | 不声称全仓Ruff通过；新research审计脚本保留实际执行字节，不能套用此12文件的结论 |
| 真实三输入续算 | COMPLETED | 1次fresh42构建，新增2次I4与2次bare；连旧账累计3/3 I4、3/3 bare、B4总15 |
| 独立向量审计 | 219/219 PASS，wall1.09s | 重算21候选rho与saved weighted-R eta、块恒等式/PoU/旧bare一致性/hash和阶段发布顺序；curl仅复核保存范数，不再施加FE动作 |
| 块外项归纳 | 完成，wall0.17s | 只从保存的126块操作项取范数，不解释成全局能量百分比 |
| 全过程资源复核 | 4252样本、34016项PASS，wall0.12s | 同时树RSS/PSS为采样峰值，非连续或cgroup峰值；swap增量0 |
| 最终文档合同检查 | 20 passed、1 failed（既有缺件） | 旧Task038缺 `memory_first_small_v2_checker.json`；修改前登记表复核完全相同，新增错误0，未伪造旧证据 |
| full repository pytest / MPI2或4新增资格 / CI | NOT_RUN | 无全仓或CI通过声明；本批正式配置为MPI1 |

[最终文档测试日志](records/p4_direction_diagnosis_v13_documentation_tests.log)与[修改前/后失败对照](records/p4_direction_diagnosis_v13_documentation_baseline.json)保留这一限制。

[工程测试和源码准入的轻量原始证据](records/p4_direction_diagnosis_v13_engineering_evidence.json)包含各条日志原文、hash、ABI preflight与Ruff基线对照。新三份research审计脚本的F821/F822/F823检查通过；保留原样执行版本，不声称其全部格式lint通过。

三个原样执行的轻量复算脚本、JSON和日志在 [records](records/)，由 [续算provenance](records/p4_direction_diagnosis_v13_continuation_provenance.json)绑定。其费用只计外层wall，core包含其中。正式累积为2160.401528466149 s，剩余5039.598471533851 s；后续文档检查属于工程验证，不混入新FE/PC费用。工程修复观察窗口4677s包含实现、测试、监督和等待，完整细分仍unknown。raw tests位于 ignored `continuation_engineering/`，正式模型身份及旧停止见 [response_v14](../response_v14.md)。

---

> 以下保留续算之前各版本的历史时点；旧文中的“当前/本轮/最新”仅指当时，不覆盖上面的续算结果。

# V13 P0–P4诊断测试、raw记录与只读审计

本节是当前测试边界；V12及更早测试表保留为历史。V13 本轮实际包含两次构建和一次 I4；受控停止后没有再重跑科学计算，也没有执行新的完整 p6 original/notch 求解。

| 检查 | 结果与边界 |
|---|---|
| targeted diagnosis algebra/capture | `src/test/test_412_physical_p4_direction_diagnosis.py` 与 `src/test/test_410_physical_macro_dd4.py` 合计 **16 passed**；覆盖复数 QR/SVD、rank/zero/dependent columns、right-PC observer、PoU/非零 `r_ref` synthetic identity 和历史捕获关闭 |
| input contract | `python scripts/run_case.py input/task39extra/p4_direction_diagnosis_v13.dat --validate-only` 通过，`run_id=p4_direction_diagnosis_v13` |
| 新 tracked checker 格式 | Ruff 通过；导入拆分规范化后的 AST 与格式化前相同，数学代码未变；未重复执行已通过的数值审计 |
| source hygiene | qualified activation 下 `python -m compileall -q src scripts` 通过；split-git `diff --check` 通过；监督 Ruff 发现的 3 个 F841 与新 lambda lint 已修复 |
| independent raw checker | 两次只读 checker 各 16 项通过；第一次 wall `1.70 s`，第二次 wall `4.70 s`；不调用 PDE、PC、factor、A4、M0 或 curl |
| resource provenance | checker second MaxRSS `198344704 B`、swap 0；正式 replay 的 process-tree RSS/PSS 与 derived liveness 分开记录 |
| full repository pytest / CI | `not_run`；无 CI 通过声明 |

测试和 raw 索引见 [V13 response](../response_v14.md)、[P4 compact](records/p4_direction_diagnosis_v13.json)、[checker provenance](records/p4_direction_diagnosis_v13_checker_provenance.json)。

---

# V12 supplement 最新测试、raw 记录与只读审计

本节是 bounded supplement 的最新测试/evidence closeout；下一节起的原 V12 O0–O4 测试表保留为历史。此轮不重新启动 PDE、MPI、factor 或任何 O2/O3 workflow。

| 检查 | 最新结果与边界 |
|---|---|
| repaired-source focused regression | `51 passed`，绑定修复 source `d39261bb17e8d9042c03d4d4990258da5043b621`；raw stdout/stderr 为 [focused stdout](records/v12_supplement/logs/task39extra-v12-supplement-root-repaired-focused.stdout.log) / [focused stderr](records/v12_supplement/logs/task39extra-v12-supplement-root-repaired-focused.stderr.log) |
| field-metric smoke | 2 个 smoke tests `PASS`；绑定 [stdout](records/v12_supplement/logs/task39extra-v12-supplement-root-repaired-field.stdout.log) / [stderr](records/v12_supplement/logs/task39extra-v12-supplement-root-repaired-field.stderr.log)；只验证保存 field metric 的诊断路径，不构成 PDE rerun 或 official field pass |
| ABI preflight | qualified Linux activation；PETSc scalar `complex128`、integer `int32`、MPI1、线程1；[ABI stdout](records/v12_supplement/logs/task39extra-v12-supplement-root-abi.stdout.log) / [stderr](records/v12_supplement/logs/task39extra-v12-supplement-root-abi.stderr.log) |
| read-only budget audit | 最终 continuation ledger `74a863666e4b299002306f505d070ff248847c9e7c91d1bc97494beec2b6c329`；`errors=[]`，total `4361.388890249411 s`，remaining `6438.611109750589 s`；`/tmp` 与 tracked audit SHA `838193b6094548405ea74264723f5bca55d638c51018d784fc792628a3ac9d0a` |
| record audits | O1 inventory `759/0`、O1 p4 `132/0`、O1 shared `96/0`、repaired R32 outer `1187/0`、repaired R32 inventory `759/0`、R64 prefix/resource audits `errors=[]` |
| raw evidence archive | 六条 O1 p4 calibration JSON 已 byte-identical 归档到 `records/v12_supplement/core/p4_controls/`；首次 R32 与 R64 的 8/16/24 residual prefix 由现有 audit/hash 绑定，未改 raw JSON |
| docs/JSON/hash checks | 本轮只做 JSON parse、相对链接、tracked-vs-`/tmp` hash 对照和差异检查；不把它们写成 solver test 或 CI pass |
| full repository pytest / CI | `not_run`；没有 CI 通过声明 |

测试日志只保存轻量 stdout/stderr；大型 matrix/factor/field/cache/timeline 仍在 ignored artifact root。O1 fresh source 为 `7d9df5e19d324776588aaa9efc4996cc3fe36d8e`，修复 R32/R64 focused source 为 `d39261bb17e8d9042c03d4d4990258da5043b621`；不能用 closeout HEAD 替换 run identity。

---

# 历史：V12 O0–O4 测试、raw 记录与静态收口

本节是 V12 source/evidence closeout；不重新启动 PDE、MPI、factor 或 O2/O3。正式 source SHA 为 `e8c3c82bab2687a811a11f0798a2879c725532b5`，review base SHA 为 `96e5d5fcfc3e801ef33d4a2d241ea7571937f734`。测试使用仓库规定的 qualified activation；没有 full repository pytest 或 CI 通过声明。

| 检查 | 结果与边界 |
|---|---|
| changed-source focused regression | `27 passed in 0.72 s`；覆盖 `test_260_task038_input_schema.py`、`test_365_light_pc_monitor.py`、`test_410_physical_macro_dd4.py`；[stdout](records/v12_final_root_focused.stdout.log) SHA `06fb627be4f8eb56eda298be72080c1a3e41a61c9046274bcd8b6b9bd0c666dc`；[stderr](records/v12_final_root_focused.stderr.log) SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| supervisor stop smoke | 3 个 `PASS`：monitor-at-10 保留 safe iteration10；external-at-50 保留 iteration48；真实 `FloatingPointError` 原样传播；[stdout](records/v12_stop_smoke.stdout.log) SHA `de2906176ec9a4a43537dff33021072d4edb1ad4a50b0a6b19d354bf38230b29`；[stderr](records/v12_stop_smoke.stderr.log) SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| V12 dat dry-run | 9/9 public dry-run exit `0`，PDE 未启动，old profile caps unchanged；[stdout](records/v12_dat_dry_run.stdout.log) SHA `ac6ea60956a6830a867c246cdfe00e62d8a0f8f433c907d81e041647fbcc6772`；[stderr](records/v12_dat_dry_run.stderr.log) SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| ABI preflight | qualified Linux stack；PETSc scalar `complex128`、integer `int32`、MPI1/线程1；V12 formal identity 与 preflight 文档绑定；没有 Windows ABI 污染 |
| Python/static | qualified `compileall` exit 0；源码/文档/JSON 的 whitespace 检查通过；完整 `git diff HEAD --check` 只剩 byte-preserved docs-contract raw stdout 第7行原始尾空格，不能为保持原始 SHA 而改写 |
| changed-file Ruff | parent 保存的 Ruff 0.11.13 changed-file F821/F822/F823 检查通过；这不是 full-repository Ruff pass，历史 diagnostics 未改写 |
| additional registry audit | `test_development_model_registry_contract.py` 批次为 `20 passed / 1 failed in 0.09 s`；唯一失败是历史缺失 `docs/task038_extra_full3d_iterative_0p7nm/outcomes/memory_first_small_v2_checker.json`，该路径在 review base 的既有 registry 引用中已缺失，本轮不修旧 Task038、不伪造 checker；[stdout](records/v12_final_root_docs.stdout.log) SHA `a32d9b6d463456db04c45d997fa2b4d8dc58ff446cf14d1be316caa32309db1c`；[stderr](records/v12_final_root_docs.stderr.log) SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；[baseline audit](records/v12_final_root_doc_audit.json) SHA `464bae144d1058295f4d16a620d807aa19f3f74e6a05f3e066c7123410d1efd2` |
| V12 JSON/evidence | compact、terminal/budget、inventory、p4/resource audit、lossless raw JSON evidence 可解析；原始 raw JSON SHA `0ff0246b6c1212b5d1c2706cd1954884626b828192697d1a7d0c9e99d06e6710`，tracked normalized copy SHA `329ed513c351896c3db09ea5899389a060b71ff36805daf456132e304fdd1580`；两者解析后的 JSON 值相同 |
| formal stage audit | O0/O1/O4 terminal hashes、42-block inventory、88-check p4 arithmetic audit、resource audit 均已写入 [V12 compact](records/physical_macro_v12_compact.json) 及其 records |
| full repository pytest / CI | `not_run`；没有 CI 通过声明 |

V12 的 `p4` 数值记录只说明有限 4-step I4/B4 控制及其真实 residual/field error；O1 shared budget stop 后没有新 PDE。大型 raw/matrix/factor/field/cache/timeline 保持 ignored，tracked raw 只保存轻量可审阅日志和 hash-bound JSON evidence。

---

# 历史：V11 N5 compact、文档合同与静态检查

本节登记 Review V11 的 docs/evidence closeout，不重新启动 PDE、MPI、factor 或 N3/N4。37 项 source-focused regression 已绑定正式 source SHA 并保持不变；本轮只验证新增 compact、逐块汇编、Markdown 链接/登记合同和源码语法。

形式 N1/N2 仍绑定 source `7c936958451bc196f784ecc30db9278c4e5b402f`。随后仅为新 N1 helper 修复一处 Ruff E731（`save=lambda` 改为等价 `def`），不改变数值语义、策略或 formal artifact identity；因此不重跑 PDE。

| 检查 | 结果与边界 |
|---|---|
| formal source-focused regression | `37 passed in 0.57 s` on formal source `7c936958...`；raw stdout/stderr 已复制到 [stdout](records/v11_focused_tests_supervisor.stdout.log) / [stderr](records/v11_focused_tests_supervisor.stderr.log)，SHA `cd8d0d4e20acef2c052a88cb70631a96cf93d4a5e3e701b2835ab51a54bb8455` / `ccb5f758e2b7c490417fb1ecef34a3227cb64cbcbacfcd6d6f4cf92c24db24c4` |
| final callback-only regression | E731 等价格式修复后 `37 passed in 0.71 s`；raw stdout/stderr 已复制到 [stdout](records/v11_final_focused_tests.stdout.log) / [stderr](records/v11_final_focused_tests.stderr.log)，SHA `70f7b5369ab6599352433826bd9eb3c162011d199701b60923565d6a480e81f0` / `c1c1c3e72eb6feb8cada736d2101da1094b27f850d26e2064c1a8407818a719b`；ABI 摘要见 [ABI](records/v11_final_abi.stdout.log)，SHA `31d16f39e8363f4c5555de06139d80c166ff8e6adb77f345faa17f5fbbec9f6a` |
| real MUMPS probes | `test_355 -k actual_mumps`: 2 passed；`test_373 -k real_mumps`: 1 passed；另有 backend snapshot 成功；不等于 N2 full inventory |
| V11 macro contract | `test_410`: 9 passed；`test_260`: 3 passed；`test_355` non-real subset: 13 passed, 2 deselected |
| documentation/model-registry contract | `test_26_documentation_contract.py` + `test_183_development_model_registry_markdown.py`: `20 passed in 0.05 s`; raw stdout/stderr 已复制到 [stdout](records/v11_n5_docchecks.stdout.log) / [stderr](records/v11_n5_docchecks.stderr.log)，SHA `88d00f8cc25efd895f76b07d9fb811f1782b4872206c18eea2a70638637b1c0a` / `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Python syntax | qualified activation 下针对 V11 changed runners、input validation 和 focused tests 执行 `python -m py_compile`，通过 |
| Ruff | 使用官方 Ruff 0.11.13 archive（SHA `01aa32d29d00876b8d1429c617ed63a00b1fc81abfa4183bb05c9cb647fbc3d0`）；13 文件 baseline `85`、current `84`、new `0`，移除的唯一新增诊断是 N1 helper 的 E731；全文件命令仍因历史 diagnostics exit 1，不能写成 Ruff 全通过。raw [delta](records/v11_ruff_delta.json) SHA `7713164d593b24a70dfc4de49cc074adc4bb91f155f44766b58e37e6b2ae82c3`、[baseline](records/v11_ruff_baseline.json) SHA `31c072312e88808ab4d59f3a783b15660e3ea1ddffdfdedfa54f785e39871f62`、[current](records/v11_ruff_current.json) SHA `bddb1fe4a2c543330c67594517adaa5ef41e8a218e7fa7eec5fba98648d6db93`、[check output](records/v11_ruff_check.stdout.log) SHA `c8bb7fad3c1f7bc5c4e13f941cc21142532115f54d1567f0cce1ab155bd4f487`；[before-fix](records/v11_ruff_before_fix.json) SHA `dff3d03e8ff26391eeee839438d04807cd0131c6d66314c33eb790f963de2264` |
| JSON/static | compact、per-block compact、copied audit、ledger 可 `jq empty`；`git diff --check` 在显式 Git dir/worktree 下执行 |
| full repository pytest / CI | `not_run`；没有 CI 通过声明 |

证据中心见 [V11 lifecycle](macro_memory_lifecycle_v11.md)、[compact](records/macro_memory_lifecycle_v11.json) 和 [per-block compact](records/macro_memory_lifecycle_v11_blocks.json)。N2 的资源负结果仍为 `LOCAL_INVENTORY_RESOURCE_BLOCKED`，N3/N4 和 official outputs 不因本节静态检查而改变。

---

# V10 M4 compact evidence与文档检查

本节是当前 V10 文档/证据收口。V10 不再启动 PDE、MPI、factor 或 M2/M3；静态检查只验证 compact、run index、链接、哈希和文档合同，不把局部小测试冒作 M1 controls 或 physics PASS。

| 检查 | 结果与边界 |
|---|---|
| V10 compact JSON | `jq empty` 通过；14 个 persisted local backsolve checks 和 6 个 native witness checks 可从 `difference_norm/rhs_norm` 或 `difference_norm/operation_scale` 独立重算；block 7 pre-factor/numeric INFOG raw fields 已保存；compact SHA=`1615eda5143a351a694b45b180e39a4fa1b728a03d882c513b87864fa7a334cc` |
| V10 run index | `jq empty` 通过；V5–V9 历史条目保留，V10 source/input/physical/ledger/compact hash 与 `not_run` 边界已登记 |
| V10 focused regression | test361/test379/test410 合计 `55 passed in 1.81 s`；这是 task-focused regression，不是 full repository pytest |
| V10 macro suite | `9 passed in 0.52 s`；覆盖局部 macro witness/selection/contract，不等于 M1 controls 完成 |
| 静态代码检查 | macro solver/test Ruff 通过；changed macro modules `py_compile` 通过 |
| 测试日志 | [v10_m4_test_run.log](records/v10_m4_test_run.log)，SHA `f484c96d8231de6b56052f162457010d8a2bba8d1af6b3992dfc8d950090cc97`；source `b0df7457c0c4b33c66abda16862926da3426bb7d`；手工编译摘录，不是 raw stdout；轻量 task-focused/static only |
| 文档链接/哈希 | 当前 V10 sections 的 8 份文档、26 个本地 Markdown 链接 resolve 通过；`jq empty`、hash 对照和 `git diff --check` 通过；大型 raw/matrix/factor/cache 仍在 ignored artifact |
| full repository pytest | `not_run` |
| CI | `not_run`；没有 CI 通过声明 |

本节不改变第二次 M1 的 `RESOURCE_BLOCKED` 结论：system RSS peak=`1107648512 B`、job swap=`0 B`，停止原因是保守 allocated policy 超过 2 GiB，而不是系统 OOM。完整边界见 [V10 中心结果](physical_macro_inverse_v10.md) 和 [V10 compact](records/physical_macro_inverse_v10.json)。

---

# 历史：V9 compact evidence与文档检查

本节是当前 V9 的 L4 收口记录。V9 的 L0 prototype 与 L2 正式 PDE 已在此前完成；本节只补充 compact evidence 和文档索引，不再改代码、不再运行 PDE、MPI、factor、正式 checker 或 full repository pytest。旧 V8/V7/V6/V5 测试记录继续保留在下文，不能被本节的 docs-only 检查冒作新的数值资格。

| 检查 | 结果与边界 |
|---|---|
| L1 compact schema/字段 | 12 个 sequence I4 + 4 个 complete-control I4 分开登记；`total_i4_calls=16`、`total_B4_applies=256`，RESET/CARRY residual、q、累计时间和 raw SHA 已写入 [V9 compact](records/equal_work_recycled_p4_v9.json) |
| L2 compact schema/字段 | `A4_matvec=1292`、`explicit_A4=168`、最大 I4 elapsed、native exit relative spot、pool/closure audit、monitor residual curve 和 76 行逐 I4 标量表已写入 [V9 compact](records/equal_work_recycled_p4_v9.json) |
| L0 clean-SHA prototype tests | source `55b7325cae8477ded7b04cfab42181f18e035a0f`；test391 的 `v8_k1_fake_runner`/`v8_k1_real_engine`/`v9` 合计 `10 passed / 0.22 s`；test386 指定 4 项 `4 passed / 0.21 s` |
| historical prototype/checker tests | V8 focused/checker-only 测试在下方历史段保留；本轮 L4 不重跑 |
| JSON/static validation | qualified activation 下解析 V9 compact/run index，核对计数、绝对/相对路径、raw SHA 与 L1/L2 scalar；结果为通过 |
| hash/link/diff | 核对 V9 compact 声明的 raw SHA、中心报告链接和 `git diff --check`；结果为通过 |
| PDE/solver regression | 未运行；不声称新的 pytest、MPI、formal checker、CI 或 full repository 通过 |

L2 的 `TIME_PROGRESS_SCREEN_STOP`、full explicit residual `0.1292009191903606`、资源峰值和 preparation partial ledger 语义见 [V9 中心结果](equal_work_recycled_p4_v9.md)。这些文档检查不改变 `EQUAL_WORK_RECYCLE_BOUNDED_NEGATIVE`，也不把固定新工作量或内部计数改写为完整求解 speedup。

---

# 历史：V8 K4 compact evidence与文档检查

本节是历史 K4 收口记录。K4 只补充可审阅的 compact evidence 和文档索引；没有新建或重跑 PDE、MPI、factor、正式 checker 或 full repository pytest。旧 V7/V6/V5 测试记录继续保留在下文，不能被本节的 docs-only 检查冒作新数值资格。

| 检查 | 结果与边界 |
|---|---|
| K1 compact schema/字段 | RESET/CARRY per-input native residual、`eps`、pool、B4/A4，以及两次完整 control 的 PC 秒数、g2 recompute 和 eps closure 已写入 [V8 outer compact](records/recycled_p4_outer_v8.json) |
| K2 compact schema/字段 | `A4_matvec=1098`、`explicit_A4=260`、最大 I4 elapsed、native spot、pool closure/orthogonality、terminal eps audit 和 118 行逐 I4 标量表已写入 [V8 outer compact](records/recycled_p4_outer_v8.json) 与 [per-I4 rows](records/recycled_p4_i4_rows_v8.json) |
| K1 prototype focused tests | 已完成 `31` 项 focused tests，绑定 prototype/run source `09c1b3a6f3c21d4d0e99feb36a97972819971fb3`；当时 K4 不重跑 |
| K1 checker-only tests | checker-only 新增 `1` 项、旧项复核 `4` 项均已完成，绑定 checker-fix source `49ddad7f4b196e45e449c1044d90b17d6ee6300c`；当时 K4 不重跑，pre-fix 与 post-fix checker hash 均保留在 compact |
| JSON/static validation | qualified activation 下解析新增/更新 JSON，核对 118 行、关键计数、相对路径和逐 I4 compact SHA；结果为通过 |
| hash/link/diff | 核对 compact record 声明的逐 I4 SHA、相对文档链接和 `git diff --check`；结果为通过 |
| PDE/solver regression | 当时未运行；不声称新的 pytest、MPI、formal checker、CI 或 full repository 通过 |

K2 的 `NORMAL_SCREEN_STOP`、full explicit residual `0.09114277170870674`、资源峰值和 reserve/actual ledger 语义见 [K4 中心结果](recycled_p4_outer_v8.md)。这些历史文档检查不改变 `RECYCLE_BOUNDED_NEGATIVE`，也不把内部 B4 减少改写为完整求解 speedup。

---

# V7 J5本地测试与文档检查

本节是当前 J5 收口记录。以下 V6、V5 及更早验证均为历史批次，原测试结果和失败原因保留，不冒作本轮重跑。

| 检查 | 结果与边界 |
|---|---|
| source targeted regression | `8 passed in 0.22 s`，覆盖 `test_390_projected_seq2.py` 与 `test_388_bounded_checker.py` 的相关排除项；source `355322e8be0716cdc3dd70df2665b8c74ff76583` |
| B finite raw recheck | `recompute_bounded_i4` 通过；4 I4、2 complete PC、实际 H6 2；`recompute_projected_trace_costs` 通过 |
| finite checker distinction | generic `bounded_costs` 对旧的 2-row audit expectation 返回 false；实际合法 audit lifecycle 为 4，原因和 `checker_recheck.json` 已 hash-bound 记录 |
| B formal outer checker | 原始 checker 的 bounded I4、screen、cost、projected trace 通过；fine residual 和 official-output gates 未通过 |
| compact/document contract | 本轮只做 JSON、raw hash、相对链接、历史保留和 diff 检查；不运行 PDE、MPI、factor、正式 checker 或 full pytest |
| CI/full repository | 未运行；不声称 CI 或 full repository pytest 通过 |

J5 追加命令费用按共享账本的实际记录计入，不把模型等待时间重复收费。A compact [bounded_inexact_outer_a_original_v7.json](records/bounded_inexact_outer_a_original_v7.json) 保持原字节不变；新增 [B finite compact](records/bounded_inexact_outer_b_controls_v7.json) 与 [B original compact](records/bounded_inexact_outer_b_original_v7.json) 分别绑定 source、input、raw root 和关键 artifact SHA。

---

# 历史：V6本地测试与文档检查

G1/G2已完成，旧新C真实负结果保留；用户补充授权继续有依据的p4/p2诊断，G5与response_v8尚未最终收口。该授权超出V6原停止分流，不改变物理、精度或安全线；不复跑G1/G2。

| 批次 | 结果 / 失败原因 |
|---|---|
| focused_v1 | 6failed/18passed/2deselected；PETSc3.19枚举DIVERGED_ITS不可用，改为DIVERGED_MAX_IT；原失败保留 |
| focused_v2 | 8passed/4deselected；有界I4、finite cap/饱和、tiny6/4/2通过 |
| focused_v3 | 2failed/5passed/8deselected；稀疏fixture向1NNZ矩阵插入密集行导致分配错误，非PDE方法失败 |
| focused_v4 | 2failed/5passed/11deselected；替身接口缺apply_into，局部fixture修正 |
| focused_v5 | 2passed/16deselected；精化fixture通过 |
| focused_v6 | 9passed/9deselected；input unchanged/slave-zero和失败成本证据补齐 |
| focused_v7 | 1passed/17deselected；非有限attempted/completed计数局部检查 |
| g2_focused_v1 | 16passed/0.94s；无FE组装，含旧V5 launcher兼容 |
| g2_focused_v2 | 最终17passed/3.79s；新增冻结RHS/映射桥fixture；parent收费5.265852279s |
| G1正式 | 首次JIT遗留cache失败0I4/0PC，唯一冷cache重试完成六+三；0/6 LO target，非数值通过 |
| G2正式 | screen数值负结果；独立checker通过账本/闭合验证，未通过fine残差与official输出 |
| 当前阶段文档 | compact JSON、相对链接及diff局部检查；G5未最终收口，记录见ignored p4_stage_docs_check.json |

初始新测试18种通过分布于各focused批次，不能写成一次30passed；未重跑昂贵G1/tiny/完整pytest，未声称CI。全部监督测试树swap0/globalΔ0且清场；所有失败计费和raw日志均由[compact](records/coarse_inverse_replacement_v6.json)绑定。没有新增测试框架。


以下完整保留历史正文；“当前/下一步”仅指当时阶段，以本节为最新状态。

---

# V5完整链与E5文档检查

| 验证 | 结果与口径 |
|---|---|
| 已提交恢复实现 | 本地47 passed /1.62s；source094204b7281fe867744fe334e8753d2faebaf89b；本E5未重跑数值测试 |
| 完整求解 | 原始564/notch576步，完整残差≤1e-6，匹配参考及物理Gate通过 |
| 资源 | sampled tree swap0；条件参考global out448页归因UNRESOLVED，不能视为全系统swap0 |
| raw证据 | 主线程独立637文件hash通过；本E5不重复全面校验 |
| E5最小检查 | 结果写入ignored e5_docs_check.json；仅JSON/绑定hash/链接/历史保留/diff，不运行PDE |

详细结果见[balanced_coupling_v5.md](balanced_coupling_v5.md)。以下为保留的历史验证记录。

---

# 补充授权真实误差定位：分阶段验证与最终文档检查

| 检查 | 结果 |
|---|---|
| 参考实现最小批 | 32 passed /1.47s；历史日志保留，未冒作本次重跑 |
| incident quadrature窄修 | 9 passed /1.57s；普通默认不变，匹配native degree25 |
| actual-error接线最小批 | 10 passed、1 FE项deselected /0.40s；含真实3snapshot/reference/9PC纯读load smoke，无FE |
| 独立ABI/静态 | qualified Linux complex128/int32、MPI1/线程1；ABI子进程退出后启parent；compileall/diff通过 |
| matched reference | 原A6≤1e-10、canonical/map/RHS/audit93hash资格；旧reference failure保留 |
| actual-errors saved-only | 224 raw/cache哈希；3投影、6平滑、0new fullPC、4p4 RHS/4MatSolve/0refinement；原A4残差独立重算≤1e-10 |
| 补充代数审计 | Gram相位无关相关、g两部分cross/相消、MR alpha、能量分解及owned-cell材料/高度归一化通过；M0仍是正式runtime实测，不称重装配FE验证 |
| 资源/清场 | 全5302样本违规0、swap0、global delta0，所有观测PID清场；双时钟原值保留并保守计费 |
| docs-only收口 | 仅JSON/hash/link/历史保护/diff检查；报告benchmarks/artifacts/task39extra/fine_reference_followup/docs_v5_static_checks.json |

中心JSON索引日志、源码及两份可审阅saved-only脚本。最终文档没有重跑FE/PDE/factor/PC/pytest/full suite，没有Ruff安装或CI通过声明。

## 历史V4及此前验证（原文当前仅指当时）

# Review V4 / C5验证：诊断完成，未新增完整PDE资格

| 验证 | 结果与证据 |
|---|---|
| 一批C0 focused | 23通过、5失败、2 deselected；5失败同因decision packet重复policy字段，属于写包bug |
| 定向修复复测 | 7通过、8 deselected；覆盖全部5失败及拆分的atomic/旧artifact审计，旧artifact缺失时该审计明确skip |
| 其他静态/ABI | compileall、git diff --check通过；独立ABI子进程完全退出后启动child-free watchdog；complex128/int32/同Linux ABI/线程1 |
| 正式C1–C3 | 8PC/4互补/10逻辑p4/12MatSolve；C2先于C3；投影110步残差9.27038e-11，原p4重建门槛未放宽，2个真实输入各精化一次 |
| raw checker | 保存的g/A4y重算r4、增广残差差向量及范数；最后10个p4输入≤1e-10；2新真实PC的q/Az残差比重算；哈希绑定全部raw |
| 资源/清场 | 3936样本无违规，RSS峰3540959232 B、swap0；parent987127/MPI987185/worker987188均清场 |
| C5最终检查 | 只做JSON/hash/文档链接/历史保护/diff检查；不重复FE/PDE或pytest，不安装Ruff，不声称CI/full repository通过 |

C0原始失败与修复日志位于`benchmarks/artifacts/task39extra/v4_c0/`；正式独立审计位于`benchmarks/artifacts/task39extra/v4_completion/b127546f172e46d0b217680338b4e0ea7aa39f12/completion_audit.json`。完整命令、哈希和新批时间账见[中心JSON](records/diagnostic_completion_v4.json)。诊断成功只证明这些控制与记录通过，不生成official R/T/A或真实散射参考。

## 历史V3验证（原文当前仅指当时）

# D5最终验证：工程政策通过，正式诊断发生数值拒绝

| 对象 | 最终证据与边界 |
|---|---|
| conservative_realtime接线 | 19 passed / 5.50 s；ABI与编译通过；source bf8e0c1d16c9c86677e866cdf29fd5491f076e32 |
| 日志 | benchmarks/artifacts/task39extra/v3_clock_policy/focused_tests.log；SHA256 14e7553168ff8fdb3a0a171b2b947df16151f4c9f378c18ddf32bdc9f32d3c73 |
| Windows独立对照 | Interop socket失败，未启动35秒对照；没有安装/系统修改，不冒作计时资格PASS |
| 正式数据复核 | 3 identities从b/x/Ax/r/分项/Gram复算，7 PC从q/Az复算；8 started/7 completed；失败p4向量未保存，只有代码/标量核对 |
| 数值拒绝 | JOINT448→LIGHT原A4残差1.0086968840613509e-10>1e-10；不因19测试通过提升为formal PASS |
| 资源/时间 | 3324样本RSS峰3777171456 B、swap0、资源违规0；watchdog保守945.519547 s、outer952.495115 s独立核对，清场完成 |
| D5最后一批 | 仅JSON/证据hash/链接/表格/历史保护及diff检查；报告benchmarks/artifacts/task39extra/v3_d5_numerical_closeout/static_checks.json；无新pytest/代码/PDE/CI声明 |

详见[最新中心记录](records/nonconvergence_diagnosis_v3.json)。原TIMEBASE停止和MPI预检导致的launch false-start均保留；旧V2的181测试不冒作本轮数学资格。

## 历史验证（以下当前均指当时）

# Task39extra：Review V3 / D5 验证边界

| 验证 | 实际结果 |
|---|---|
| V3小批次 | tiny 6 passed；诊断7→8→8 passed；后续bridge/mode窄修1 passed、raw能量字段2 passed；各日志/命令/hash见中心JSON |
| ABI/编译 | 资格化activation，仓库.venv，complex128/int32、Linux统一栈、MPI1/线程1；源码24b3dbb的compile/diff已通过 |
| 唯一原尺寸诊断 | TIMEBASE_INCONSISTENCY受控停止；完整PC/互补/投影均0；不是数学测试通过 |
| D5 | 仅JSON解析、相对链接、关键artifact/hash、文档与git diff检查；不新增pytest、PDE、环境调查或系统改动 |
| 未声明 | 无full repository/MPI sweep、无新Ruff或CI通过；旧181批次只属V2，不冒作V3原尺寸资格 |

短检查累计预算13.183744896 s，正式前准备/失败一并按保守外部4936 s扣账，不能只扣pytest。D5静态检查结果保存于`benchmarks/artifacts/task39extra/v3_d5_closeout/static_checks.json`。详见[中心JSON](records/nonconvergence_diagnosis_v3.json)。

## 历史V2及此前验证

# Task39extra：F5 最终验证

F3正式只读审计通过：476PC/476原p4检查、14完整周期+28尾段、checkpoint/hash/零初值、reported/explicit差、资源/清场核对。属于证据一致性通过，原A6残差0.10535820013809101>1e-6，solver未通过。双时钟差异单列，不以测试通过掩盖UTC solve超7200。

最终一次task-focused回归：**181 passed、1 skipped**（test362的MPI2专用fixture）；覆盖test352/354/355/356/358/359/360/361/362/363/365/366/367/368。ABI preflight和compileall通过，源码仍为60b8df2a24cbcd96e49e018be22fb64f06eeae3f，只改文档。不跑full repository/PDE，不安装Ruff，无CI通过声明。F1最终85 passed、F3实现63 passed及失败fixture均保留，见[中心记录](records/packed_and_joint_mr_v2.json)。

| F5最终测试口径 | 记录 |
|---|---|
| pytest报告 | 117.19 s |
| 外层monotonic / UTC-derived | 109.88929661700968 / 118.71753764152527 s；双时钟原值保留，不混为一个wall |
| 日志 | `benchmarks/artifacts/task39extra/v2_f5_closeout/checks_15.log`；SHA256 `5ad4ca130192568295f721b1730212302f6fdcbbcfeac0964126d6418b9566d1` |
| 完整命令及身份 | `benchmarks/artifacts/task39extra/v2_f5_closeout/test_record.json`；SHA256 `c0b7fbc682ccafb37801006c27411c40bf22d2673e7d57faaf1c03e2f0ae3243` |
| 预算 | V2原monotonic账本16项，累计8820.53636143892 s，余27179.46363856108 s；余额不授权新PDE |

最终静态核对JSON、相对链接、Markdown表格列数、关键artifact/hash及旧task/review/response不变；结果保存在`benchmarks/artifacts/task39extra/v2_f5_closeout/static_checks.json`。不宣称GitHub网页渲染通过。

## 历史 Review V1 / R6及此前测试


## Review v1 / R6 验证（当前）

| 对象 | 结果与源码边界 |
|---|---|
| R3接线、packed原作用、safe monitor | 104 passed、1 skipped；MPI2专用项未运行；日志 `benchmarks/artifacts/task39extra/r3_checks/checks_26.log`，正式source `cbf56e87e515ab0c3fc5756cb6cf52feb047f610` |
| LIGHT停止路由修复 | 23 passed、0 deselected，26.60 s pytest；日志 `benchmarks/artifacts/task39extra/r3_stop_lifecycle/checks_39.log`，SHA256 `35abeaa4014e4a14bff12233963997fde030426ddbd6ca22ae36c621263ac7ee`；代码 `597546311feea60d61acb2a9999b706dd895dcf0` |
| MPI1停止五路径 | 旧整树SIGTERM复现、只请求应用一次并安全退出、不合作到宽限整树硬停、资源立即硬停、陈旧start ticks拒绝；各fixture结束清场 |
| 监控数值不变 | 真实PETSc3.19零初值None及非零初值FGMRES轨迹逐位一致、64次PC不增调用；安全点保留当前cycle初值，不重复加解 |
| 停止fixture隔离 | `checks_32.log`的5 failed/15 passed/3 deselected保留；C层继承OMPI/PMIX环境导致子MPI过早失败，测试改为显式传递环境后通过；生产未清洗环境 |
| R3正式结果 | 原A6 last_safe576残差0.0791360407785889>1e-6；p4最大7.058163970105702e-11≤1e-10；资源安全、数值未资格化；normal checker not_run |
| 最终R6 task-focused | **153 passed、1 skipped**（MPI2专用）；源码HEAD `597546311feea60d61acb2a9999b706dd895dcf0`，仅文档dirty；pytest报告120.69 s，外层monotonic实测107.97184431797359 s，分别保留；ABI preflight与compileall通过 |
| R6日志 | `benchmarks/artifacts/task39extra/r6_closeout/checks_41.log`；SHA256 `8d258ba4c8e5f487cf84e50a9078d6ca9ed47e9f0f5aef66340d4e36a93bd522`；完整命令及预算绑定见[紧凑JSON](records/cost_and_contribution_v1.json) |

fixture宽限为3 s便于验证，生产LIGHT宽限仍为60 s。停止修复没有改变原A6/PC数学作用，没有重跑R3；小fixture通过不等于正式R3安全收口通过。此前局部失败、负运行与旧计数证据均保留。Ruff未安装，不安装或声称通过；不运行full repository，无CI通过声明。旧章节均作为历史快照解释。

最终回归覆盖test352/354/355/356/358/359/360/361/362/363/365/366，在同一shell资格化activation并先执行ABI preflight；显式MPI1小fixture是测试的一部分，未运行新的MPI2或原尺寸PDE。JSON解析、相对链接、四份audit及20份关键raw的hash、完整PC计数、残差阈值、历史task/review/response_v1不变和diff-check均独立核验；静态报告在 `benchmarks/artifacts/task39extra/r6_closeout/static_checks.json`，不声称网页可视渲染或CI通过。

## 历史 A5 与此前实现验证

最终交付的计数窄修提交为 `adc448814c3022fdf6d1a688da69a28238e7db9c`，正式 A2R 运行源码仍为 `54ab46cf4c8378a9b27650ca6963cadb34013a2f`。窄修只把 S6/S3 生命周期序号按实际调用计一次，并提供旧 raw 的独立只读重算；未修改方程、PC 作用或求解过程。

| 最终补充检查 | 结果 |
|---|---|
| public 登记遗漏修复 test359 | 3 passed / 0.07 s；真实两份 dat 的 plan/public dry-run/worker 路由可用，ordinary/未知 profile 仍不可用 |
| 计数独立重算及未来 ledger test360 | 3 passed / 0.07 s；跨两个周期、生命周期序号不中断、逐次计数字段保留、输入不改；缺失序号拒绝 |
| 最后相关轻量回归 test356 + test359 + test360 | 19 passed / 0.85 s；ABI preflight、compileall、diff-check 通过 |
| 正式 A2R 审计 | 5 周期 reported/explicit 对照通过；163 个原 A4 残差均 ≤1e-10；外层 160 步残差 0.18250767622880507 >1e-6，性能停止，不是 solver PASS |

最后回归使用同一 shell activation/ABI preflight 后执行 `python -m pytest -q src/test/test_356_physical_intermediate_wiring.py src/test/test_359_physical_reference_public_entry.py src/test/test_360_physical_cost_recount.py`。没有因计数或文档变更重跑已绑定 FE/正式 PDE，也未运行 full repository pytest；无 CI 通过声明。对应源码 hash、完整命令、28 份正式 raw hash 由 [运行索引](records/run_index.json) 绑定。

以下为此前实现阶段记录，保留原测试快照边界；原尺寸最终结果以上述正式性能停止记录为准。

| 验证对象 | 实际结果 | 证据与边界 |
|---|---|---|
| S6 精确对角 | 三个原 p6 单元与旧 dense oracle 相对误差约 2.2–2.6e-15；p3 serial/MPI2 约 2.3e-15；最终 callback 回归 17 passed | [既有组件记录](records/setup_diagonal_optimization.json)；曾发生的 MPI2 reference 布局测试错误及修复日志保留 |
| A2R focused_v1 | 15 passed；覆盖 tiny p4、旧 A2 FE、接线及 real p3 h50 oracle | 此前实现快照，不冒称最终源码重新运行 |
| A2R focused_v2 | 17 passed；reference/原 profile 接线、ledger、释放、负路径 | 此前实现快照 |
| 最终 focused_v3 | 38 passed：test358、test352、test355 | 同 RHS repeat 相对差 0.0 ≤1e-12；增广/native action 1.8225937969296386e-15；原 A4 残差每次 ≤1e-10；错误 action 拒绝 |
| 最终组件资源 | RSS peak 640000000 B，swap 0，清场通过 | watchdog 原始 elapsed 61.57664551300695 s；pytest 原始 67.21 s，分别保留 |
| 静态检查 | compileall、git diff --check 通过 | 未运行 full repository pytest；不声称 CI 通过 |

A2R 代码提交为 `920cf08eedf99610e5eee90ec1fe8ce317e14591`。测试运行时为基于 `2bed3d4248a465a9cf2224c575fc8b64357fd020` 的 development worktree；经逐文件核验，最终 14 文件内容集合 hash 为 `2f61cf5c65a18dfcb71e700ac3a21ca1280e76d2516687627ccd7f05a44b5177`，与代码提交内容一致。较早回归没有因无关文档变更重跑。

全部 Python 测试先在同一 WSL shell 中 `source scripts/activate_myfenics_wsl.sh`，ABI preflight 确认 marker=1、链接的仓库 venv、PETSc complex128/int32、Linux OpenMPI、同 Linux ABI 库、线程数 1。实际命令：

```bash
python -m benchmarks.subreaper_watchdog --directory benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/focused_v3 --wall-seconds 180 -- python -m pytest -q -s src/test/test_358_physical_p4_reference.py src/test/test_352_task039_extra_physical_multilevel.py src/test/test_355_bounded_p1_factor.py
```

180 秒仅为该组件测试预算，正式 workflow/solve 仍为 7200/3600 秒。完整命令、源码 hash 和 9 份 raw 测试文件 hash 见 [implementation_manifest](../../../benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/implementation_manifest.json) 与 [实现报告](../../../benchmarks/artifacts/task39extra/a2r_implementation_2bed3d4/implementation_report.md)。这些小型测试当时不构成原尺寸 A2R 或主候选资格；后续正式结果见本文件开头及总账。

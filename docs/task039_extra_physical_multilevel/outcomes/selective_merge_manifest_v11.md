# Task39extra Review V13 p4 direction diagnosis selective merge manifest（最新）

本节登记 V13 的依赖边界，不是 `master` merge approval。V13 是一次 bounded, opt-in 的 p4 方向诊断；正式 replay 在 source `e46fec48dc073a745e9b7e6c9186a147aefbc0a0` 上受控停止，不能把 partial packet、derived operator residual 或 source-liveness lower bound 提升为 solver qualification。普通默认路径保持不变，original/notch、完整 p6 物理求解和 official R/T/A 均为 `not_run`。

| 依赖组 | 文件/内容 | 数值行为是否改变 | 测试与 fresh evidence | 建议合入顺序/结论 |
|---|---|---|---|---|
| production numerical/core | V13 opt-in 的 right-PC observer、P0 matrix-free/reference-free probe、P1 local direction capture、P2/P3 response-column capture 及相关 `physical_macro_dd4`/runner wiring | 仅显式诊断路径改变；ordinary default unchanged；尚无 production candidate | 16 个 targeted tests passed；formal replay 完成 P0 直接/pullback 度量检查、1 个 I4、4 个实际 right-PC 输出和部分 P3 原始算子列；最终细分 action 计数未持久化；无 full PDE pass | 保持 research-only；不得按 production numerical/core 合入，须经新 review 重新资格化 |
| reusable runner/watchdog | V13 opt-in CLI、42-block fresh-process lifecycle、terminal/resource provenance 和 split-git/source identity 记录 | 改善诊断生命周期与受控停止记录；不把 controlled stop 改成数值失败或通过 | 首次失败与一次 user-authorized repair replay 均保留；replay `USER_CONTROLLED_STOP`、descendants cleared；无 OOM 或 RSS-cap violation | 仅作为 research runner/evidence 依赖审阅；与 core 原子评估 |
| checker/benchmark | V13 compact、offline partial audit、tracked partial-audit script、checker provenance、run-index registration、memory-liveness record | checker 只从原始字段重算结论，不重新实现求解器 | 主控和执行窗口各一次离线 checker 均 16/16；wall `1.70 s + 4.70 s`；未运行新的 PDE | 可作为轻量证据组审阅；不把 derived original-operator rho 当作 physical eta/curl 或 official result |
| compact evidence/docs | `response_v14.md`、`outcomes/p4_direction_diagnosis_v13.md`、next-method blueprint/decision、summary/test/progress/registry 及本 manifest | 无数值行为改变 | source/input/model/map/raw artifact hashes、terminal/stages/resources hashes 和 provenance 已登记 | 在 code/runner 边界确定后最后审阅；只合 compact/hash-bound evidence，不合大型 arrays/factors/cache/timeline |
| research-only | P0 metric-equivalence、P1 direction-reconstruction、P2 未闭合、P3 42 个 p-column/A-image 诊断和下一方法设计 | 研究路径；尚不能证明 production PC efficiency、物理误差或 workstation qualification | P0 pass；P1/P3 partial；完整 L 的 derived rho=`0.9358770172082744`、selected response rho=`0.9678905201139729`；eta/curl unavailable；formal resource status `DERIVED_UNCERTIFIED` | 整体保持 research-only；不得升级为 production capability |
| do-not-merge | ignored matrix/factor/field/cache/timeline/raw tree；未运行的 original/notch/official outputs；未经资格化的 proposed next method | 不适用 | 大型 artifact 仅由 hash-bound records 指向；source-liveness 为 lower bound，不是 RSS 结论 | 不合入；重新打开必须新 review、预算、source 和 artifact identity |

## V13 固定边界

- 正式 replay 绑定 source `e46fec48dc073a745e9b7e6c9186a147aefbc0a0`；此前 source `80d2fb35145ac4770040ec9bb4627dfbe8cc7e67` 的同一诊断首次失败记录必须保留，不能改写为通过。
- 两次正式尝试的 conservative realtime 合计为 `948.1497426901994 s`；两次离线 checker wall 合计 `6.40 s`；当前可核算总计为 `954.5497426901994 s`。首次失败发生在完成一次 direct mass action 后的同网格 owner-row 一致性检查；不得将该阶段写成 P0 probe 已运行。
- replay 的 derived lower bounds 为：direct mass action `1`、I4 `1`、实际 right-PC 输出 `4`、bare-B4 `1`、local block replays `210`、A-image `47`（P1 的 4 个加 P3 的 43 个）以及 M0/curl `2`；完整阶段时钟未知，因 `current_counts` 未在受控停止前持久化。
- replay 在写出 P3 response packet 后受控停止；没有 P2 complete packet、02/09 direction records 或最终 p4 summary。资源记录的 sampled process-tree RSS peak 为 `3125956608 B`、swap `0`；`2.5 GiB` 是 local inventory policy，不是 process-tree RSS cap。停止原因是 diagnostic additional-array/live-object accounting 未闭合，状态为 `DERIVED_UNCERTIFIED`。
- source liveness lower bound 为 `273571328 B`，相对 `256 MiB` local diagnostic budget 超出 `5135872 B`；该值排除了 Python allocator、maps、local records 和 metric internals，不能替代 process-tree RSS。下一方法的更低 workspace 上界仍是 proposed/unverified。
- 当前没有可合入的 production candidate；ordinary default unchanged；official p6/original/notch solve、physical eta/curl gate、E/H/R/T/A、`A_volume`、modal/diffraction 和 conservation 均为 `not_run`。当前状态为 `NOT_APPROVED_FOR_MASTER_MERGE`。

# Task39extra Review V12 supplement selective merge manifest（最新）

本节是 bounded supplement 的最新依赖分组，不是 `master` merge approval。O1 fresh 与首次 R32 工程失败绑定 source `7d9df5e19d324776588aaa9efc4996cc3fe36d8e`；修复 R32/R64 绑定 `d39261bb17e8d9042c03d4d4990258da5043b621`。最终结论必须同时保留：local construction/inventory/transfer/I4 coupling 已审计；完整 PC efficiency 仍为 negative/unqualified；R64 为 user-controlled stop；official Maxwell outputs `not_run`。

| 依赖组 | 文件/内容 | 数值行为是否改变 | 测试与 fresh evidence | 建议合入顺序/结论 |
|---|---|---|---|---|
| production numerical/core | 既有 V12 opt-in core/profile/runner wiring；修复 field metadata fallback 和严格 restart dependency | 显式 research path 的实现/诊断行为改变；ordinary default 不变 | O1 42/42、C_U/transfer；repaired R32 64 outer residual `0.7666389832389989`；无 official fresh PDE pass | 仅作为 research-only core group 审阅；不得升级 ordinary default |
| reusable runner/watchdog | 既有 `--macro-v12 --macro-v12-supplement --profile-budget-ledger`、whole-tree stop、checkpoint/terminal semantics | 改善工程诊断和 stop provenance；不把 user stop 改成 numeric result | R32 terminal/resource、R64 `USER_CONTROLLED_STOP`、descendants cleared；51 focused tests + 2 field smoke | 与 core 原子审阅；保留 source 分段和 stop classification |
| checker/benchmark | supplement ledger、O1/R32/R64 summaries、inventory/P4/shared/outer/prefix/resource/budget audits、run index/compact | checker 只重算原始字段，不重新实现求解器 | budget audit `errors=[]`；R32 outer `1187/0`；R64 no selection | 与 raw evidence 绑定审阅；不能把 residual negative 或 R64 stop 改成 pass |
| compact evidence/docs | response_v13、physical_macro_v12、summary/test/progress/registry/handoff、README、轻量 logs | 无数值行为改变 | source/input/physical/ledger/artifact hashes；history SVG/PNG；tracked-vs-`/tmp` log/audit hashes | 最后合入 docs/evidence；只合轻量 raw，不合 matrix/factor/field/cache/timeline |
| research-only | 42-block macro factors、C_U classes、BAL_H selection、R32/R64 restart probes | 当前 complete PC 被 fresh evidence 排除为 production candidate | O1 已完成；`gate_pass=false` 只表示 ONE_C 切换条件失败（L2/residual 超阈值），不是 O1 workflow failure；R32 residual/field 均 `measured_not_met`；R64 controlled stop | 整体保持 research-only；不声称 workstation/continuum资格 |
| do-not-merge | ignored matrix/factor/field/cache/timeline/checkpoint tree；原始/notch/official output的未运行项 | 不适用 | 大型 artifact 只由 hash-bound JSON 指向 | 不合入；重新打开必须新 review、预算和 identity |

## 最新固定边界

- supplement formal cap 为 `10800 s`；四笔 formal charge 为 `4361.38889024941 s`，remaining `6438.61110975059 s`。最终 continuation ledger SHA 为 `74a863666e4b299002306f505d070ff248847c9e7c91d1bc97494beec2b6c329`。
- O1 的 6 条 p4 records 每条只做 4-step I4/B4；3 个 shared-q matched comparisons 选择 `BAL_H`。ONE_C switching gate 的 L2 geometric=`1.000603999343256 > 0.8`、residual geometric=`1.0240463212446451 > 1.0`，而 curl、最大 field 和累计 time 条件通过；`gate_pass=false` 不表示 O1 workflow 失败。
- O1 42/42 block、C_U/transfer、84 witness 和 local residual 只能证明构造/接线记录一致；修复 R32 的 64-step residual `0.7666389832389989`、node32/64 field L2 `0.9384007607744688/0.9488237463600627` 和 scaled curl `0.9382432819659642/0.9486448577201997` 均已实测但未达 gate，是 complete PC efficiency 的 fresh negative evidence；其 `0/128` I4 calls 达到内部 `1e-4` target。
- 首次 R32 工程失败与 R64 都保存了 8/16/24 residual checkpoints=`0.8283760020203784/0.8172376273064963/0.811621467511064`；二者均为 `partial_checkpoint_evidence`，最终 candidate unavailable、restart comparison incomplete。R64 的停止分类仍是 `USER_CONTROLLED_STOP`，不是 numeric failure。
- R32 的 full explicit residual gate 已为 `measured_not_met`，而 official field/power recovery、O3 original/notch、E/H、R/T/A、`A_volume`、modal/diffraction 和 conservation 仍为 `not_run`；ordinary default unchanged，当前 `NOT_APPROVED_FOR_MASTER_MERGE`。

---

# 历史：Task39extra Review V12 selective merge manifest

本 manifest 只登记 V12 的依赖边界，不是 master merge approval。V12 取得了真实 42 块物理宏块 inventory 和 4 条有限 bare B4/I4 控制记录，但 O1 共享预算停止；没有完整 p6 outer 或 official output。因此以下内容整体只能按 research-only / evidence closeout 审阅，不能提升 ordinary default。

| 依赖组 | 文件/内容 | 数值行为是否改变 | 测试与 fresh evidence | 建议合入顺序/结论 |
|---|---|---|---|---|
| production numerical/core | src/io/input_schema.py、src/io/input_validation.py、src/io/physical_intermediate_profile.py、src/io/physical_recursive_profile.py、src/solvers/physical_macro_dd4.py、src/solvers/fullspace_memory_first_krylov.py、src/runners/physical_recursive_controls.py、src/runners/physical_macro_v12.py、9份 input/task39extra/v12_*.dat；src/solvers/fullspace_bounded_mumps.py 是复用依赖，本轮未改 | 仅显式 physical_macro_dd4_v12 改变；V10/V11/ordinary default不变 | V12 27 focused tests；42块 inventory；4条 p4 records；无p6 official fresh evidence | 与 runner/contract 一起审阅；不得单独合入 production default |
| reusable runner/watchdog | scripts/run_case.py、src/runners/physical_macro_controls.py、src/runners/physical_recursive_entry.py、src/runners/physical_recursive_controls.py、src/runners/physical_macro_v12.py、Krylov stop/snapshot safety | 改变生命周期/受控停止记录；不改变 ordinary numerical path | 3-stop smoke PASS；O0/O1/O4 terminal/resource audits；O1 controlled stop | core后作为同一 research-only group 审阅；保留 stop semantics |
| checker/benchmark | V12 compact、raw JSON evidence、inventory/p4/resource audits、run index V12 registration、相关 tests | checker只重算原始字段，不重新实现求解器 | 759 inventory checks；88 p4 arithmetic checks；JSON/hash/diff validation | 与core/runner证据绑定审阅；不得把 controlled stop 改成 pass |
| compact evidence/docs | response_v13.md、outcomes/physical_macro_v12.md、summary/test/progress/registry/handoff、raw logs | 无数值行为改变 | raw stdout/stderr、source/input/physical/artifact SHA、p2 stage SHA | 数值/runner审阅后最后合入；只合compact和轻量raw，不合大型artifact |
| research-only | physical_macro_dd4_v12 显式分支、2.5 GiB local inventory policy、42块 MUMPS factors、C_U class factors、bare B4/I4 controls | 研究路径；局部质量未证明 full p6 solver | O1 PERFORMANCE_CONTROLLED_STOP；p4 true residual与field errors未达目标；O2/O3未运行 | 整体保持 research-only；禁止升级为 production capability |
| do-not-merge | ignored matrix/factor/field/cache/timeline/checkpoint/raw tree；任何绕过 inventory/Q/cap 的修改 | 不适用 | 大型artifact只由 raw SHA 指向；不把RSS/used替换保守inventory | 不合入；若重开需新review、预算和identity |

## 固定边界

- V12 的 42 个宏块各自是独立 numeric factor records；18 个 C_U 内部响应类因子不替代这 42 块，也不属于 DtN block factor count。
- S/p2 rows=7326、NNZ=818100、allocated/used padded=270000000/65000000 B、derived matrix+reported-factor=341069688 B < 536870912 B；这是一条与 local inventory 分开的、同时存在的 derived policy budget，原始 stages SHA 已登记。
- 4 条 record stem 的 BAL_H 是历史 packet 标签；本轮只做 bare B4/I4，没有完整 BAL_H/ONE_C outer comparison。A2R160_01/LIGHT448_09 的 residual improvement伴随 field error worsening，不能把 residual improvement写成PC强。
- p6 原方程 1e-6、restart32/64、original/notch、E/H/R/T/A、A_volume、modes、diffraction和守恒均 not_run。V5 original/notch成功与448页global swap attribution UNRESOLVED 保持历史。
- build/JIT/其他检查没有独立终态时钟，记为 unknown/included；不从O1阶段费用扣p4小计伪造build成本。
- 当前状态 NOT_APPROVED_FOR_MASTER_MERGE；ordinary default unchanged。继续必须重新绑定 source/input/artifact 和新预算，不要求修改冻结 input 本身。

---
# 历史：Task39extra Review V11 selective merge manifest

本 manifest 只登记 Review V11 的依赖边界，不是 `master` merge approval。V11 N1 证明了显式新 policy 在两个代表块上的局部等价性；N2 在完整 retained inventory 的第 42 块前置 Gate 受控停止，因此没有 production solver 或 workstation heavy-case 资格。

| 依赖组 | 文件/内容 | 数值行为是否改变 | 测试与 fresh evidence | 建议合入顺序/结论 |
|---|---|---|---|---|
| production numerical/core | `src/io/input_schema.py`、`src/io/input_validation.py`、`src/io/physical_intermediate_profile.py`、`src/io/physical_recursive_profile.py`、`src/solvers/fullspace_bounded_mumps.py`、`src/solvers/fullspace_v17_p3_oracle.py`、`src/solvers/physical_macro_dd4.py`；以及 V11 input contracts | 改变仅发生在显式 `physical_macro_dd4_v11`；old default/V10 policy 不变 | V11 N1 equivalence pass；N2 `LOCAL_INVENTORY_RESOURCE_BLOCKED`；无完整 PDE fresh evidence | 研究审阅后才可与依赖 runner 原子评估；不得作为 ordinary default 合入 |
| reusable runner/watchdog | `scripts/run_case.py`、`src/runners/physical_macro_controls.py`、`src/runners/physical_recursive_entry.py`；调用上列 core/profile/solver | 增加可复现的 opt-in 控制、fresh-process lifecycle、inventory gate 和受控停止分类 | 37 focused tests；actual MUMPS 2 + real MUMPS 1；N1/N2 raw manifests and watchdog summaries | 不能脱离依赖 core 独立合入；若审阅允许，必须与 core 同一 research-only change group 原子处理 |
| checker/benchmark | V11 compact schema、per-block compact、`src/test/test_260_task038_input_schema.py`、`src/test/test_355_bounded_p1_factor.py`、`src/test/test_373_condensed_fine_reference.py`、`src/test/test_410_physical_macro_dd4.py`、run-index V11 registration | 不改变求解方程；checker 只重算记录字段 | compact JSON/hash、82 backsolve audit、N2 no-double-count audit | 与依赖 core/runner 一起作为 research-only group 评估；不得把 controlled negative 变成 pass |
| compact evidence/docs | `macro_memory_lifecycle_v11.md`、`macro_memory_lifecycle_v11.json`、`response_v12.md`、summary/test/handoff/progress/registry 更新 | 无数值行为改变 | JSON parse、hash/link/diff checks；完整 pytest/CI 未运行 | 可在审阅后作为 evidence/docs 合入 |
| research-only | 全部 V11 code/profile/runner wiring、N1 symbolic-sized policy comparison、N2 41-block partial inventory、`COMPACTION_UNSUPPORTED` observation | 仅研究测量；不能推出完整 outer 或 RAM 定理 | source/input/physical/ledger/raw hash-bound | 整体保持 research-only；不升格为 production capability |
| do-not-merge | ignored matrix/factor/field/cache/timeline/raw tree；任何绕过 retained inventory 的 cap/Q 修改 | 不适用 | 大型 artifact 不入 Git；N3/N4 未运行 | 不合入；若重新打开需新 review、预算和 identity |

## 固定边界

- V11 N2 的 `2,178,209,948 B > 2,147,483,648 B` 是 retained inventory + 当前 block matrix + 一次 symbolic-sized Q 的保守 Gate；不能用 measured RSS、MUMPS used 或最小值替代。
- block 41 没有 numeric factorization；`MemoryError` 是 runner 的 local/workflow gate 分类，不是 MUMPS `-9/-19` 或数学失败。
- N3 restart、N4 original/notch、p4 true error、BAL_H/ONE_C、E/H/R/T/A 和 workstation 0.7 nm 均 `not_run`。
- 当前状态为 `NOT_APPROVED_FOR_MASTER_MERGE`；source run SHA `7c936958451bc196f784ecc30db9278c4e5b402f`。V11 代码与依赖 runner 只能作为一个 research-only change group 提交审阅，不能先行拆合。

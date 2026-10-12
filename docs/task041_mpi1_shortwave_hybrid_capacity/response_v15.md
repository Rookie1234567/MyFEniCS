# Task041 Review V13 执行回应：V12负结果与V13分批资格边界

## 当前状态

V12的W0.7 warm运行仍是未通过的历史负结果：模态子求解达到32步上限，原方程残差和近似预条件器接纳线均未通过。后续V13合同测试通过，不改变V12的consumer/finalizer结论，也没有把该次运行补成成功。

V13实现及A/B/C合同测试现已完成分批验证。A、B各由多个已批准attempt组成；C的同一个registered entity-closure tiny真实FE selector在serial与MPI2分别通过。结果适用于各attempt所绑定的源码与环境，不是一个最终SHA上的整组一次性通过。随后又完成30个serial清场/服务合同节点，以及一次MPI8 native ABI-only预资格（8个rank检查通过）；该ABI没有启动pytest或数值worker。尚未执行W0.7 p6/h0.70/M400 MPI8正式warm、QEP、完整外场/五残差、physics或R/T/A计算。

用户后来明确要求取消内存节点绑定。最新C MPI2及此后测试采用操作系统默认内存策略，不强制node0或node1，也不把页分布当资格门；CPU14/18小测试映射、80/72/8 GiB cap/warning/W和384 GiB双节点合计reserve保持。node1至少80 GiB只作资源可用性检查，不表示页必须位于node1。A/B及较早C serial仍按各自attempt记录旧内存策略；不能倒改旧attempt的membind身份或历史ABI失败。

C MPI2 attempt收口时V5历史快照由261项增至262项，SHA为`64fd8d5ffc3a62aa4e49a8058e81e5701aa0a1107269c35bcae50cf1d2396ec4`；该值不是当前账目。本次文档收口前的live V5为264项，SHA `17376a6343ac65f359f059ad632e9a305ce28a60c683164f6a16539ee6e767ce`。C MPI2 pytest父wall `153.515994687099 s`只记一次；ABI和资源门不收费。

## A/B/C合同测试汇总

| 组 | 冻结范围与实测 | 环境/源码边界 | 证据入口 |
|---|---|---|---|
| A | 23个selector、45个参数；分批合计43 passed，另2个仅限MPI2的参数在serial中skip。skip不是pass，后续MPI2组覆盖了其中对应节点 | 多个attempt和源码快照；每项以其`source_hashes_before_after.json`为准，不表示最终19路径同SHA的一次全组运行 | [冻结serial清单](../../results/task041_v13_bounded_static_validation_20261011T072210Z/run_serial_gate.py)、[071636Z封存的A覆盖表](../../results/task041_v13_A_B_mpi2_review_prep_20261012T071636Z/A_serial_selector_coverage.md)、[覆盖表JSON](../../results/task041_v13_A_B_mpi2_review_prep_20261012T071636Z/A_serial_selector_coverage.json)、[A剩余selector记录](../../results/task041_v13_numa1_A_remaining_serial_20261012T044347Z/serial_selectors.json)、[最终8项attempt](../../results/task041_v13_A_serial_final8_20261012T064555Z/serial/pytest.attempt.json)、[finalizer 17参数attempt](../../results/task041_v13_A_test352_finalizer_17_service_fix_serial_20261012T070500Z/serial/pytest.attempt.json)；覆盖表只描述其封存时的A分批覆盖，后续B/C及源码变化按各自证据核对，不改写旧表 |
| B | 8个selector、14个参数定义；MPI2两rank执行，合计覆盖28个rank-case（不是28个独立selector）。由audit-counter单项及余下7-selector批次分段通过 | 分段attempt；B汇总不把早期ABI拒绝或失败attempt改写为通过。merged stdout缺rank-to-summary映射的记录继续标为`not_persisted` | [audit-counter serial/MPI2回归](../../results/task041_v13_q_counter_mismatch_retest_20261012T081735Z/)、[B其余7项MPI2批次](../../results/task041_v13_B_mpi2_retry_20261012T093637Z/mpi2/pytest.attempt.json)、[该批manifest](../../results/task041_v13_B_mpi2_retry_20261012T093637Z/manifest.json) |
| C | 1个registered entity-closure tiny真实FE selector；serial一次通过，MPI2一次通过。最新MPI2为1 selector/2 rank-cases，pytest `rc=0`，父wall `153.515994687099 s`；合并输出不能归属到具体rank，故不称“每rank各1 passed” | serial C旧attempt使用显式membind=1；最新MPI2使用用户批准的default/unbound内存策略。两者分列，均不是M400/MPI8 pilot资格 | [最终MPI2执行摘要](../../results/task041_v13_C_cpu_wait_retry_mpi2_attempt_20261012T142650Z/execution_result_summary.json)、[pytest attempt](../../results/task041_v13_C_cpu_wait_retry_mpi2_attempt_20261012T142650Z/mpi2_c/pytest.attempt.json)、[完整输出SHA清单](../../results/task041_v13_C_cpu_wait_retry_mpi2_attempt_20261012T142650Z/OUTPUT_SHA256SUMS.json)（SHA `f9bcdc0045418fd60f21b938493a5c12bb5828375fefe851b881e61f1b1ba779`） |

## 后续serial合同与MPI8 ABI-only预资格（2026-10-12/13）

| 项目 | 结果与费用 | 证据及边界 |
|---|---|---|
| owned-session与setup边界serial合同 | 先3项清场合同通过；首attempt随后在test351 setup-boundary fixture因缺`include_blis`关键字失败，保留该失败，父wall `6.377355428179726 s`。修复仅让fixture显式接收该关键字；新attempt的27项全部通过，父wall `10.62438608892262 s`。跨两attempt为30个合同节点通过，wall各唯一入账；mock节点不构成真实OS/MPI8清场资格 | [首attempt](../../results/task041_v13_owned_session_serial_contract_attempt_20261012T195835Z/serial/pytest.attempt.json)、[首stdout](../../results/task041_v13_owned_session_serial_contract_attempt_20261012T195835Z/serial/pytest.stdout.log)、[修复后27项attempt](../../results/task041_v13_owned_session_serial_remaining_attempt_20261012T200713Z/serial/pytest.attempt.json)、[输出SHA清单](../../results/task041_v13_owned_session_serial_remaining_attempt_20261012T200713Z/OUTPUT_SHA256SUMS.json) |
| MPI8 native ABI-only | 8/8 rank通过production rank qualification；固定CPU `[10,11,14,15,16,17,18,19]`，内存策略default/unbound，允许节点集合`[0,1]`；六线程变量、complex128、Int32与原生桥检查通过。parent wall `2.1766278869472444 s`；不计V5 | [native ABI attempt](../../results/task041_v13_mpi8_abi_rank_qualification_attempt_20261012T215842Z/native_abi.attempt.json)、[33项输出SHA清单](../../results/task041_v13_mpi8_abi_rank_qualification_attempt_20261012T215842Z/OUTPUT_SHA256SUMS.txt)、[post-shell identity rescan](../../results/task041_v13_mpi8_abi_rank_qualification_post_shell_identity_20261012T232030Z/post_shell_identity_rescan.json)。无pytest、FE、QEP或numerical worker；这是dirty 21路径map下的预资格，不是clean HEAD或warm资格 |

两次serial合同attempt把V5从262项增至264项；ABI-only不增加V5。当前live ledger与本次文档更新前21路径身份见[待clean-source重绑的warm候选包](../../results/task041_v13_final_docs_warm_candidate_review_20261012T232650Z/README.md)。本阶段四份文档更新不改数值源码；正式warm仍需clean HEAD重绑与新的fresh host/resource/ABI审核。

### 源码身份沿革

相对044347Z的19路径冻结map，最终C attempt执行时的map有6个经批准的代码delta、其余13项当时未变。A/B在不同批次之间也经历过获批的fixture与service修订，不能把各批结果合并成一个同SHA全组通过。以下hash说明该执行时点的代码演进末端；每个测试仍以其本地attempt的逐文件source map为准。本文四份文档在这次计算之后更新，因此其当前文档hash不再冒充C attempt的运行前hash。

| 文件 | 最终C map SHA256 | 已批准变化 |
|---|---|---|
| `src/runners/task041_service.py` | `c7670e4030c92ff98a2302d1725736e2141f283e374bf4facac3f3aaab31985d` | strict V13 finalizer要求沿supervisor实际证据检查outer-control结果 |
| `src/test/test_347_task041_balh_physical_operator.py` | `2c77d6d0e058723e54182ce7affc1cc19061e7a70e05c9c8a0ad6023d72c82a1` | 对齐registered `entity_closure` support并读取cell-condensed producer真实`relative_residual`键 |
| `src/test/test_349_task041_balh_side_inverse.py` | `c298046ec4165c4c23505384cd945d4e1158a590b1b12da048f01dd238e5585a` | MPI2 owner-local RHS fixture覆盖实际full-row布局 |
| `src/test/test_350_task041_balh_block_ldu.py` | `070db620498aae86c9373ce3a25350141084c6aa9eaaa061df37455c88d07cca` | V13 tiny solver/builder、workspace和生命周期fixture的经审修订 |
| `src/test/test_351_task041_balh_public_workflow.py` | `6654c10200a67d52d4a92a905b3b6d4d9c5eacc5e6ca75c6ad038b2e31771973` | 普通V12 policy实际route字段fixture |
| `src/test/test_352_task041_service_boundary.py` | `9f87a77c487fc33e715d81a6bdd6498a5765c1d960dc865af34fbf5839667bdb` | registered V13 qualification名称与生产字段一致 |

当前C attempt还把19路径before/after map及对应producer/source identity封存在[来源回执](../../results/task041_v13_C_cpu_wait_retry_mpi2_attempt_20261012T142650Z/mpi2_c/source_hashes_before_after.json)。本次四份文档的后续修订发生在该运行之后，只改变文档字节；数值源码和测试源码没有随文档收口改变。不得把这些文档新hash写回旧attempt或当成新的数值source资格。

## 需要保留的失败与纠正

| 历史观察 | 已确认内容 | 结论边界 |
|---|---|---|
| V12正式warm运行 | modal reason `-3`，32步，relative residual `0.47290220837766356`；目标`1e-3`和PC拒绝线`0.1`均未通过；outer末四项残差仍高于`5e-9`；没有完整场/physics/RTA | 继续记负结果。目标miss本身不等于拒绝，本次实际eta也超过0.1；V13组件测试不改写该事实 |
| C早期legacy fixture | 测试省略`support_policy`，使用默认legacy；registered W0.7路径要求`entity_closure`。后续单行残差字段读取也与cell-condensed producer的`relative_residual` schema不符 | 两个test-only修订后，registered entity-closure C serial和MPI2合同通过；不能说legacy生产数值bug已修复 |
| 旧NUMA触页探针 | `numa_maps`在观测中找不到目标mapping | 缺少映射证据不能证明页落在错误NUMA节点；后续用户取消绑定，当前default-policy ABI不以页节点分布作门 |
| default-policy ABI前置拒绝 | 叶cgroup缺少`cpuset.mems.effective`；后续按controller未启用的继承关系解析祖先effective集合 | 本次fresh双rank ABI记录default策略、允许内存节点匹配和cgroup身份稳定并通过；不能倒推旧probe失败时的实际页放置 |
| CPU14忙碌及等待 | 一次resource gate因CPU14超过`<20%`门拒绝；后续独立只读样本满足条件后才生成新OUT并重走fresh链 | resource refusal是启动资格问题，不是数值失败；未降低阈值、未迁移CPU、未干预邻任务 |

V12费用和其他历史账目以对应时期的V5 receipt为准；当前最新ledger只在本节开头列出。snapshot tiny阶段曾发生2 GiB授权偏离，原授权偏离receipt仍保留；不把那两次pass写成80 GiB资源资格。细节见[历史snapshot记录](outcomes/test_summary.md)。

## V12正式场负结果

Invocation `62c3763e266345e0b094a4f3ba3ae19c`，运行source `132e3b321f336916d55459b50be95729520ff0f4`，W0.7 reduced、p6/h0.70/M400/MPI8、QEP=0。终态为consumer `IMPLEMENTATION_FAILURE`、public rc3、finalizer `failed/service_boundary_failure`、`controlled_stop.active=false`。

末次modal solve达到`max_it=32`仍未收敛：reason `-3`、RHS norm `0.2594808945363501`、residual norm `0.12270908805805157`、relative residual `0.47290220837766356`。该值高于目标`rtol=1e-3`，也高于近似PC接纳线`eta=0.1`，因此本次确实被拒绝；target miss本身并不普遍等同于拒绝。记录为`pc_usable=false`、`raw_residual_pass=false`、`budget_exhausted=false`。没有outer收敛、最终五残差、恢复、完整E/H、R/T/A、A_volume或physics资格。`first_exception`精确时间戳`not_persisted`。详细成本、46条side审计、历史node0运行门及V12终态见[summary](outcomes/summary.md)和[terminal compact](../../results/task041_v12_w0p7_bounded_modal_backup_policy_only_run_20261010T085320Z/terminal_compact_v12.json)。

V12当时的资源记录按当时授权写明node0 floor；后续用户授权将测试floor改为node0+node1合计384 GiB并取消强制内存绑定。历史资源字段保持原样，不适用于推断当前default-policy测试的页放置。

## V13实现与资格边界

策略`task041_v13_consistent_fixed_balh_modal_surrogate`已实现。它让同一固定B作用贯穿LDU各块；模态矩阵的8个预定列直接保留在最终矩阵，其余列逐列构造一次；owner LU后的`S_B a-g`检查与完整PC输出后由原全局A modal row进行的`L z_side+C a-r_modal`检查是两道独立门。测试还覆盖单次restart/有限停止控制合同和public→worker→service/finalizer实际证据绑定。首次出现的两个C fixture错误分别是registered support policy不匹配、以及残差键名不匹配；已修复的只是对应测试fixture，生产阈值和算法门没有放宽。

| 已证明 | 尚未证明 |
|---|---|
| A/B合同与tiny solver/service路径的分批selector覆盖；C的degree-6、`2×2×2` cell-condensed FE、每侧6个解析模式组成12模态、固定B/LDU、原modal row、P4残差及借用生命周期的registered `entity_closure` serial/MPI2回归 | W0.7 M400 MPI8正式执行；完整800列生产S_B/其内存和wall；生产outer连续求解、最终五残差、恢复与完整场；R/T/A、A_volume、衍射、energy/physics/finalizer资格；cold/QEP/full pilot |

V13正式实施触点及后续独立pilot资格差额见[阶段记录](outcomes/w0p7_consistent_block_pc_v13.md)；selector级attempt、资源/ABI与账目见[test summary](outcomes/test_summary.md)。不启动任何后续计算或dispatch；需先对目标pilot的封存配置、producer/consumer链、MPI8 rank map、default memory policy、资源与数值门作独立审核。

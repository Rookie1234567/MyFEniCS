# Task041 V16/V17 补充统一回应：M400 首次 PC 行门拒绝与离线证据收口

## 结论

V16 唯一正式 W0.7/M400/MPI8 Invocation 已结束。它完成了本次构造中的 800 模态行 `S_B` 与 owner LU，随后在第一次 PC apply 的 V13 原始 modal-row 门拒绝；没有完成任何 outer iteration，也没有最终五项原方程残差、恢复场或物理结果。`IMPLEMENTATION_FAILURE` 是 consumer 的分类字符串，不足以证明 PC 或实现代码有缺陷。V14 旧 M400 的未查明根因仍为 `UNCONFIRMED`。

本次对 800 行冻结 binary64 数组作了 90 位 Decimal 离线复算。没有重新执行原 A、B/P4、求解器或谱计算。复算确认 732 行超过原 `1e-10` 门，最大值在零基行 259；因此本次首因是实际数值门拒绝，不是资源拒绝、finalizer 标签或日志问题。

| 项目 | 结果 | 判定边界 |
|---|---|---|
| 唯一运行 | unit `task041-v16-m400-20261015t141300z.service`；Invocation `6344a904b8df435a88a7466dd739da76`；runtime HEAD `c662a70b4af4d742f7a8305d0efd63342423c775`；W0.7、10×5 nm、p6/h0.70、M400、MPI8；CPU `[1,2,3,5,6,7,8,15]` | V16 `MemAvailable` 资源合同通过并进入 worker；来源身份见 launch manifest。不是数值通过 |
| `S_B` 与 `C` | `S_B`、`C` 均为有限 `complex128 (800,800)`；数组内容 SHA 分别为 `d4b25b…d3bfc`、`b720ee…fc1286`；`S_B` 在本 Invocation 构造，没有复用旧缓存 | owner rank 7，LU factor count 1；factor 已随 cleanup 销毁，归档矩阵身份不表示有可复用 live factor |
| 首次 PC 行门 | attempt 1；attempted apply 1；stored `eta_terms_inf=1.7996403128522177e-2`，限制 `1e-10`；owner LU backward error `1.9821704747745833e-16` 且同次输入未变 | owner 解通过；全局 modal-row 检查拒绝。没有完成 outer iteration |
| 800 行独立复算 | 最大行零基索引259（第260行，全局模态索引302659）；732/800 行 `eta_inf>1e-10`；`d=w_modal-r_modal` 对所有行与归档 binary64 完全一致 | 这是已归档 PC apply 的分量后向误差复算，不是新原 A action，也不是最终解全局残差 |
| 服务终态 | consumer `IMPLEMENTATION_FAILURE`，首错 `FloatingPointError`；service public result `task041_public_command_nonzero`、exit 3；finalizer `service_boundary_failure` | consumer 分类是宽泛外层标签。真实首因仍以行门拒绝为准；finalizer false 是次级证据完整性检查 |
| 资源与清场 | process-tree RSS / memory-authority peak `49,616,527,360 B`；专属 job cgroup peak `47,208,488,960 B`；job swap peak 0；原生 host PID1 `systemd`，MainPID 0、NRestarts 0、ControlGroup 空、登记组与 ranks 已退出 | RSS、dedicated cgroup 与 swap 是不同口径；不可相加。资源门通过，作业正常完成清场后失败于数值门 |
| V5 账目 | 306项前缀逐条不变；本场只追加 service entry `13,489.261149145 s`；现307项、top `651,274.1059664167 s`、SHA `4fe39d105e32e2601172116a300bedac61f6e4458fa0b780cbbcd8ff11b0edc8` | 只记一次 service wall，不按rank乘8。parent summary另记 `13,488.424919819 s`，两个收据字段分列，不重复相加 |
| 大型构造额度 | V14原两场额度现为2/2已用尽 | 不把额度重置；本记录不包含也不授权下一场大型构造 |

## 本场生产 MemAvailable 合同的贯通证据

本场实际使用资源策略 `task041_v16_memavailable_phase_v1`、schema `task041.kernel_memavailable.v1`。启动门要求内核 `MemAvailable >= 498,216,206,336 B`（464 GiB，即384 GiB reserve加80 GiB cap）；正常RAM节点范围是 `system_default_unbound_all_normal_memory_nodes`，即 system default/unbound 覆盖全部正常RAM节点。运行阶段令 `J=max(process-tree RSS, dedicated cgroup memory.current)`，并要求 `J+Delta+8 GiB<=80 GiB`、`MemAvailable>=384 GiB+Delta+8 GiB`，以及每个有限祖先cgroup的headroom至少为 `Delta+8 GiB`。72 GiB为warning，80 GiB为hard cap；MemFree、node1 MemFree与swap为观察项，不替换MemAvailable门。这里的阶段增量合同不同于测试runner的remaining-cap监测公式。

同一策略由[public入口](../../scripts/run_case.py)选择并由[公共launcher](../../src/runners/task038_launcher.py)绑定到manifest，经[service resolver/worker/finalizer](../../src/runners/task041_service.py)传递；[workflow资源策略绑定](../../benchmarks/task041_balh_workflow.py)、[supervisor初始门与阶段采样](../../src/runners/task041_supervisor.py)、[exact-side阶段采样](../../benchmarks/task041_exact_side_workflow.py)和[LDU outer receipt验证](../../src/solvers/hybrid_fem_modal_block_ldu.py)使用同一版本与schema。[策略定义及pure gate](../../src/io/input_validation.py)给出上述公式。运行证据见[launch manifest](../../results/task041_v16_m400_supervision_20261015T141300Z/launch_manifest.json)、[stage memory samples](../../results/task041_v16_m400_supervision_20261015T141300Z/memory_stages.jsonl)、[service summary](../../results/task041_v16_m400_supervision_20261015T141300Z/summary.json)和[finalizer summary](../../results/task041_v16_m400_supervision_20261015T141300Z/finalizer/finalizer_summary.json)：最终收据记录了同一policy binding/schema与阶段公式，运行资源门通过。finalizer 的 `modal_solver_policy_matches_request=false` 是首次PC门拒绝后V13 candidate/solve/outer-control回执缺失所致的次级检查；它不表示MemAvailable合同不匹配。

## row 259：冻结分量与门限复算

合同为 `task041.v15.original_modal_row.terms_backward.v1`：每行用原 A 同次捕获的 `d=w_modal-r_modal`，相对于未相消组成项的模长和核对。以下复数是归档 `complex128` binary64 的原值；`r_modal=0`，因此该行 `w_modal=d`。

| 归档分量 | row 259 复数值 |
|---|---:|
| `t_bottom` | `-3.2887837938824806e-18 - 3.185324603020592e-17j` |
| `t_top` | `0 + 0j` |
| `t_constraint` | `2.1553346202144075e-18 + 3.1673468771682553e-17j` |
| `r_modal` | `0 + 0j` |
| `w_modal` | `-1.1334491736680731e-18 - 1.797772585233666e-19j` |
| `d` | `-1.1334491736680731e-18 - 1.797772585233666e-19j` |

存档 numerator norm 为 `1.1476179207258029e-18`。存档 denominator 由 `row_scale × row_denominator_scaled` 得到 `3.2022576122225604e-17 × 1.991385505128775 = 6.376929392668288e-17`，row 259 的 `eta_terms_inf` 为 `0.017996403128522177`。`eta_terms_2=3.257659348665526e-14` 则是同次800项模态向量的二范数后向误差，公式为 `||d||2/(||t_bottom||2+||t_top||2+||t_constraint||2+||r_modal||2)`，不是row 259的单行指标。分解差精确为零且 decomposition 门通过。从同一 binary64 分量用 90 位 Decimal 独立求模长后，row 259 分子为 `1.1476179207258028121780057258688193703348496054820806972929214094739043264868101e-18`，分母为 `6.3769293926682879221382688257671357484678336332063205039850346836305207834304296e-17`，比值为 `0.0179964031285221265572196694898458783818526110890330917142803924124390369746215449179077034`。与稳定 binary64 指标差 `5.007708775839947960299196412e-17`；两者都远高于 `1e-10`，拒绝结论不依赖末位舍入。

732 个超门行使用零基闭区间表示为：

```text
[1,41], [44,54], [56,97], [99,104], [106,169], [172,191], [194,249],
[251,263], [265,314], [316,331], [333,333], [336,336], [340,342],
[344,344], [349,355], [357,357], [360,375], [377,377], [380,397],
[401,410], [412,425], [427,442], [444,454], [456,483], [485,497],
[499,504], [506,569], [572,592], [594,649], [651,663], [666,714],
[716,731], [733,733], [736,736], [740,744], [750,755], [757,757],
[760,763], [765,775], [777,777], [780,796]
```

这条记录属于 attempt 1；同次 owner LU solve count 增量为1并通过；identity/capture errors 为空。原 A handle 为 `2134638864`，布局 SHA `db70fd5ee69f64337780912877872fc61ce3809f87e66fe3ccd4de8d9a39c5f8`，8个 rank 的 MatMult/action IDs、context identity、输入/输出范围及 alias/hash 检查都绑定在 machine record 与原 index 中。PC 源与目标不 alias，原 A 输入未变。row record 自身的 Invocation 字段是占位文本；实际 Invocation 由同一 runroot 的 `launch_manifest.json` 绑定，不能把占位字段说成记录内的直接身份。

NPZ 中唯一非有限数组为 `decomposition_row_relative_log_error` 的800个 `-inf`；对应线性分解误差与 `decomposition_error` 全为精确零，其他数值数组有限。这符合合同对精确零误差的 log 编码，不是漏采数据。8个 rank 的 source/target 冻结向量共16个文件，逐项核对 SHA、shape、dtype 与 finite 均通过。

## 首因、次级 finalizer 结果与旧失败边界

本次 primary 是第一次 PC apply 保存的原 modal-row 数值记录超出 `1e-10`。consumer 将异常标作 `IMPLEMENTATION_FAILURE`，首阶段为 `v13_original_modal_row_gate`；`observed_stage=top_construction_cleanup` 是清理路径观察，不能覆盖首因。outer 尚未形成最终解，因此没有本场完整方程残差可报告。

finalizer 的 `modal_solver_policy_matches_request`、`public_result_completed`、`service_terminal_normal` 三项为 false。代码路径是 `task041_service._modal_solver_policy_matches_request` 对 service/worker/launch identity、请求资源绑定和完整 V13 实际候选/求解路线做终检；supervisor 的 `fixed_h6_method_validation` 要求实际 candidate inventory、solve inventory、side action 与 V13 outer-control evidence。首个 modal-row gate 在 outer 证据写全之前拒绝，实际 V13 route/control 留为 not persisted，因而该 policy-match 检查失败。它是数值首错后的次级终检结果，不证明 request policy 或资源 binding 错误。旧 V14 Invocation 的 M400 根因继续标为 `UNCONFIRMED`；V14 iteration 1 的全局 modal true residual `7.6e-14` 与本次 PC 行 `eta_inf=1.7996e-2` 是不同量，不能互换。

## 已取得的资格及未完成范围

| 范围 | 已保存证据 | 限定 |
|---|---|---|
| Registered tiny FE serial R30 | KSP reason 2、389步；原 A 相对残差 `4.97654121633487e-9 <= 5e-9`；销毁后冻结证据经独立审核通过 | 该次 pytest 因旧 fixture/schema 断言 rc1，不能称 pytest 整项通过。R60因R30数值通过而未运行 |
| Registered tiny FE MPI2 | 两 rank 均 reason 2、441步；原 A 相对残差 `4.83780279602371e-9 <= 5e-9`；冻结快照/lifecycle断言通过 | 这是 tiny FE 与 analytic modes 的代数资格，不是 M400 实际物理场；MPI2 R60 未获执行授权且 not_run |
| Owner-writer MPI2 | 最终相关helper版本的真实tiny builder/PC owner写失败传播回归通过，pytest `rc=0`；父wall `3.2586057849694043 s` | [034737Z attempt](../../results/task041_v16_owner_writer_failure_mpi2_attempt_20261015T034737Z/mpi2/pytest.attempt.json)，SHA `5c4c1880f7015bfe3363f3c7590d51cf8105ee07702fa943d2994febbc2331f2`、[source map](../../results/task041_v16_owner_writer_failure_mpi2_attempt_20261015T034737Z/mpi2/source_hashes_before_after.json)，SHA `dcdde83cf8fe6c40eac2f527115f5af3c13767218b64bfc58431f942896aa780`。较早的[112820Z attempt](../../results/task041_v15_real_tiny_builder_owner_writer_failure_mpi2_attempt_20261014T112820Z/mpi2/pytest.attempt.json)仅作历史记录；rank OS exit codes未单独持久化。协议证据，不是数值求解通过 |
| V16/V8 producer reuse | 两个 test351 节点通过；V16 穿过真实 producer validator 与真实 `_run_phase` | consumer 由测试替身截获，不是 FE/PDE 结果 |
| P1 MemAvailable 资源合同 | 21个唯一节点经4个serial批次完成有效覆盖，分组为4+1+8+8 | 分批且 source map 不同，不是一条21项全绿 attempt；中间失败/未运行 raw 均保留 |
| 本次 M400 | 完成 producer/QEP 复用链之后进入 consumer；本次构造 `S_B` 800/800并建 owner LU，首次 PC 行门拒绝 | 无 outer 收敛、五项最终真残差、recovery、E/H、official R/T/A、`A_volume`、衍射或 physics |

资格证据索引：registered tiny FE serial 的[pytest attempt](../../results/task041_v16_registered_fe_serial_attempt_20261014T162356Z/serial/pytest.attempt.json)（SHA `cf2187d04095ac69d338f376a4a55df1d9811ef6db978221e70c61e6b2b67599`，rc1）、[R30 completion](../../results/task041_v16_registered_fe_serial_attempt_20261014T162356Z/serial/pytest_basetemp/test_task041_v13_real_fe_conde0/v15-modal-evidence/tiny_fgmres_R30_completion.json)（SHA `71d0de7d1404f8941415bf47e8a9773bda7a559a467f15fb1e3403195c487831`）和[post-destroy lifecycle record](../../results/task041_v16_registered_fe_serial_attempt_20261014T162356Z/serial/pytest_basetemp/test_task041_v13_real_fe_conde0/v15-modal-evidence/tiny_fgmres_post_destroy_lifecycle.json)（SHA `83a33dbe0214a5d03de1f620039cbe3dcf882cac5c9f6d44e5380bf2daa6721e`）。R30 completion记录reason 2/389与原A残差达标；pytest的最终fixture断言仍rc1。冻结行记录显示rank0 arrays readable且`ldu_destroyed=true`，当时的snapshot validator因exact-zero log字段`-inf`拒绝`first_success_control`；后续仅对已存记录作schema-aware离线核验，没有重跑serial FE或改写旧attempt。registered FE MPI2的[pytest attempt](../../results/task041_v16_registered_fe_mpi2_rank_private_basetemp_attempt_20261015T000139Z/mpi2/pytest.attempt.json)（SHA `7899a05a48d4f117656d2f4fb0983244a9dea0be86bf141c94daefdd7d8593a7`）；owner-writer MPI2的[attempt](../../results/task041_v15_real_tiny_builder_owner_writer_failure_mpi2_attempt_20261014T112820Z/mpi2/pytest.attempt.json)（SHA `01d1715adc1af74ed10d3ee475380bceac90a583e5a76b6bfca2f20c739714c7`）；producer reuse V16/V8的[serial attempt](../../results/task041_v16_producer_reuse_serial_session_v8_owned_policy_dynamic_cpu_attempt_20261015T091551Z/serial/pytest.attempt.json)（SHA `96ba6ce6034e755648b1ecdc8ba9aa3917a6abbc3c3990c08161f637db99890e`）。P1四批的attempt与source-map入口集中列于[test summary](outcomes/test_summary.md)。

“`S_B` ready”表示两侧模态耦合矩阵已经建立并保存；其 owner LU 随本次 cleanup 销毁。当前档案不能用来恢复 live factor，也不能把 ready 状态说成完成求解。

## 账目、证据与文档范围

V5 旧306项逐条不变；唯一新 service entry 将账目推进到307项、`651274.1059664167 s`、SHA `4fe39d105e32e2601172116a300bedac61f6e4458fa0b780cbbcd8ff11b0edc8`。执行中没有新增 pytest。memory authority/process-tree RSS 与 dedicated cgroup peaks 分列，不能加总成单一峰值。大型构造额度2/2已用尽。

- [离线800行复算 receipt](../../results/task041_v16_m400_offline_closeout_20261016/terminal_recompute.json)，SHA `027b60f4dad3251f0caa25b3e5f141983379bdddabb92fd9d0f9244636cd1161`；[receipt SHA 清单](../../results/task041_v16_m400_offline_closeout_20261016/SHA256SUMS.txt)，[自封摘要](../../results/task041_v16_m400_offline_closeout_20261016/SHA256SUMS.sha256)。
- [Machine record](outcomes/records/task041_v16_m400_terminal_20261016.json)；[M400 supervision summary](../../results/task041_v16_m400_supervision_20261015T141300Z/summary.json)，SHA `c56cc14c8170b1844cfee5802506bbaf5d4f08069b8b485bc43193744f4969e0`；[launch manifest](../../results/task041_v16_m400_supervision_20261015T141300Z/launch_manifest.json)，SHA `4d36167b092a8c47c9dfecc8a55e865a291eab070135016142f88f699c6d3283`；[finalizer summary](../../results/task041_v16_m400_supervision_20261015T141300Z/finalizer/finalizer_summary.json)，SHA `3b3df4b37f3dd2a02ef7d99a71b36dd31bf3fac8bcdd2d2bc4488a879ce6fcba`。
- [800行 evidence index](../../results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261015T143400.129213Z/consumer/numerical_output/v13_modal_row_evidence/index.json)，SHA `775c453b8c60699fd3f64ef4e4a3c1a1934c8616784d0777652adc3d9aaedfd9`；[consumer summary](../../results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261015T143400.129213Z/consumer/consumer_summary.json)，SHA `532b1cb8edde9c59cc8d50bde3e1042e8aafdd02f73ca3f4d38bd830f1739520`。

## 待 ChatGPT 技术裁决

请审阅row 259中组成项接近抵消后留下的非零 `d=w-r` 与 `eta_terms_inf` 拒绝：现有存档能确认复数分量、binary64分解关系和Decimal复算一致，但没有重放原A或B/P4，尚不能判定该弱行误差的来源。请裁决下一步应先对冻结分量做数学/误差预算分析，还是另行提出一个受限诊断方案；本次没有获准的新计算、门限调整、PC变更或大型重跑。

本次仅做原生 host 终态只读确认、存档数组和 ledger 前缀独立复核及文档/record 收口；没有测试、ABI、MPI、FE、生产代码或数值门改动。本回应统一交ChatGPT审阅；提交身份见执行交接，runtime SHA与文档提交分开；监督timer由主控在推送核验后停用。

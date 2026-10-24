# Task43 执行回应 V2：有限诊断因工程前置失败而收口

**本轮结论仍是 `PARTIAL / CONTROLLED_NEGATIVE`，最后接受状态为 R9。** V1 中九次已接受更新、R10拒绝、原场后验比较和历史负证据全部保留。Stage1 的 Q01–Q08 已按 review 补证，但生产/全仓测试门仍有明确限制。之后启动的三次完整诊断尝试都没有形成合格的新端点：A1_q 在结果广播时遇到 observer 序列化异常；两次 A2_q 都在网格构造前因运行接口或冻结元数据检查失败。它们属于工程执行失败，不能说明 h/p 方法数值失败或通过，也不能回答这轮 q/R 扰动的完整数值影响。

V2 的范围是按计划判断积分阶次和端口截断是否影响结果，并在条件满足时推进一个局部 h 见证。其前置要求是每个端点都保留原求解校正策略、完整独立残差、端口向量和公共场样本；只有部分模态行或某个 residual 数字不足以判断。A1/A2额度与所有停止条件在揭盲前已冻结。最终机器索引为[正式尝试与profile修复记录](outcomes/records/v2_formal_attempts_and_profile_fix_v1.json)。

这里的`q`是单元和端口积分时使用的数值采样精度；提高它会让积分近似更细，用来检查原有积分误差，但增加组装工作。`R`表示保留多少边界波分量；增加它可检查端口截断误差，也会扩展方程规模。同因子额外回代复用已分解的矩阵，测试求解误差对场和物理输出的影响，代价是延长因子驻留内存时间并多做一次回代/输出。这些诊断都不能替代网格精度验收；本轮三个正式尝试均未完成所需端点证据。

## 三次正式诊断尝试

表中墙钟为各次 watchdog 的完整 wall，RSS 是受监管进程树同时采样峰值。所有三次的 task-tree swap 峰值为0并清理了后代；这不把提前退出变成数值资格。A2失败时没有建网格，因此计划中的576个Y6_1 cells、FE 380,160、121,572行不能记成这两次的实际装配测量；两次的R/T/A、残差、NNZ和场结果都是`not_run`/null。

| 阶段/尝试 | 实际终态与成本 | 可用证据 | 缺失及结论 |
|---|---|---|---|
| A1_q / 1 | `WORKER_FAILED`；4,882.447373806033 s；采样峰9,708,847,104 B；worker exit 1、launcher exit 2；3,930个资源样本；source前后hash一致 | 求解流程已到结果收集。Root从已保存的612个R13模态及原有体吸收值复算：旧R10→primary最大通道功率差`8.1846196487e−12`、幅值组差`8.2694173937e−12`；primary→extra分别`2.5368596113e−14`、`3.457149372e−14`。primary/extra能量闭合绝对差为`4.1038283882e−12`/`4.0496495046e−12`。 | 广播时mpi4py无法pickle嵌套`MappingProxyType`。primary q8/q10场样本、primary与extra的持久化独立A6报告、完整endpoint record缺失；这组部分模态差不代表q资格或endpoint PASS。root terminal/partial audit见compact。 |
| A2_q / 1 | `WORKER_FAILED`；18.740401392802596 s；采样峰190,795,776 B；worker exit 1、launcher exit 2；15个资源样本；60个选定源码与34个输入前后hash一致 | watchdog/worker日志记录了本次实际启动。 | wrapper未把`PHYSICAL_WATCHDOG_PHASE_PATH`传给native runner，退出发生在网格/方程工作前；没有数值输出。 |
| A2_q / 2 | `WORKER_FAILED`；13.984614439308643 s；采样峰190,918,656 B；worker、watchdog、launcher分别exit 1/2/2；12个资源样本；60个源码与42个输入前后hash一致 | 原Y6_1配置的原生validator重放发现仅一个差异：旧resolved profile缺少`component_options.directional_mesh_comparison.display_label`，当前派生值为`D15-Y6-1`。 | 原生profile检查在网格构造前拒绝；没有数值输出。冻结计划的576-cell/380,160-FE等Y6参考值不能填成此次装配测量。profile差异和真实phase/ABI记录由root审计。 |

上表中“A2计划FE等”只指冻结Y6参考的现有身份；A2两次未构造网格。V2三次formal watchdog wall合计`4,915.1723896381445 s`，仅合计这三条完整watchdog wall；测试、真实配置预检、旧场恢复和root审计等支持成本另行保存，没有把未监控时间拼入正式运行总数。56份V1 summary的`63,340.73598930752 s`历史小计及R8的`3,109.3891972089186 s`不完整观察窗仍按原Q04账本独立报告，不覆盖为全campaign成本。

### 配额与停止决定

实际正式dispatch为3/6：A1_q 1次、A2_q 2次。A2配额2/2已用尽；A1_q未获得完整endpoint/A6证据，所以A1_R的冻结前置不成立；A2_R相位未运行，其中一个原A2_R名额按前瞻授权仅重分配一次给A2_q attempt2。A1不合格且没有可用B候选，因此B和依赖B的C继续锁定；没有跨组或进一步配额重分配。新profile修复后的只读预检通过，不构成额外PDE或重新打开已耗尽的A2配额。

## Q01–Q08 工程证据回应

| 问题 | 本轮结果 | 限制与证据入口 |
|---|---|---|
| Q01 原场和残差复核 | **核心精度目标仍未达到**：R9的两个零级s功率通道仍超过限值，R10仍有一个超限通道且整体更新未越过冻结噪声。另从历史存储样本重新审计E/H/G、612通道Poynting和原有R/T字段，并对已保存残差标量做算术复核。 | 未从系数重新采样；未重新体积分`A_volume`；未重新施加完整算子或做fresh A6。旧数据复核不改变未达精度结论，见[post-selection replay](outcomes/records/post_selection_old_field_replay_v2.json)。 |
| Q02 全仓收集与核心回归 | 原full collection的8个collection errors保留。干净tracked collection收集3,121项后仍有1个SLEPc ABI/注册阻塞。补做SLEPc-free的空间、装配/恢复、采样MPI2、independent action和same-LU微型fixture。 | 原full pytest在collection中止，测试体0执行；不能写成full suite pass。focused中的3个MPI2-only skip另有MPI2实测；[Q02 compact](outcomes/records/q02_collection_and_abi_v2.json)。 |
| Q03 选择性依赖闭包 | 从base405建立的隔离overlay逐项核对66个文件hash；实际代表模块从overlay导入；25个明确测试路径收集157个节点。 | 这是hash/import/collection闭包证明，测试体执行0项，不是运行或数值资格。新的native A2 adapter不在该66文件闭包证明中，不能借其获得production资格；[依赖闭包记录](outcomes/records/selective_merge_dependency_closure_v2.json)。 |
| Q04 实际workflow成本 | 逐项索引56份有终态summary的历史workflow，原分类和whole-wall合计`63,340.73598930752 s`；root独立审计成本账通过。`post_selection_restore_attempt1`覆盖Y5_1/Y3/Y3_2的完整恢复workflow，原summary实测`166.96172243729234 s`，不是倒算。 | 56项包含失败、停止、恢复等，不代表56次数值成功。R8只保存`3,109.3891972089186 s`采样观察窗下界，不是完整wall。原件为[`watchdog/summary.json`](../../benchmarks/artifacts/task43/post_selection_restore_attempt1/watchdog/summary.json)，SHA256 `075c2d9dbc19a0d45dd069288723d6af1806fcc43256d18118c02c41bb05d8b6`；root总账核验见Q04机器记录。三个本轮formal wall另列于V2 compact。 |
| Q05 冻结时序 | 冻结contract的hash存在pre-run snapshot且匹配。 | 原日志没有足够的时间戳/调用顺序证据证明冻结严格早于第一个候选；此边界保留，不作更强声明。 |
| Q06 p3完整D4和方向子单元 | 两个p3测试节点覆盖8个D4变换及256个oriented-child组合。 | 只支持这些明确fixture，不扩张为所有level2/cross-h组合资格；[Q06/Q07 component record](outcomes/records/q06_q07_component_validation_v2.json)。 |
| Q07 R8 partial特例 | 仅精确R8 run路径可读取原partial资源审计字段；其他路径缺summary时拒绝。V1 attempt inventory不改写，V2输出独立。 | R8 PDE终态及sender仍未知；保留partial窗和字段，不伪造完整wall或exit；同见Q06/Q07记录。 |
| Q08 registry Markdown合同 | 两次既有回归均保留，最新结果为5 passed/0.11 s；本轮对registry文档做最终更新后另跑同一现有Markdown回归。 | 当前最终回归stdout、exit和hash见最终closeout validation compact；不替代full-suite。 |

Root对Q04原summary身份、56条总账、58份原件hash、18条旧R3行及64份V1不可变文件做过独立检查。Q05的结论仍只到hash匹配，不升格为严格时序证明。Q02的real-SLEPc与当前complex128/int64 PETSc ABI不匹配继续作为Hybrid/SLEPc阻塞，未重装环境或更改全仓collection配置。

## 五项能力和科学结论

| 任务能力 | 最终判断 | 本轮证据边界 |
|---|---|---|
| 空间能力 | `PARTIAL` | p3–p6 mixed-p和600叶p3真实h1已有组件/实解证据；h1数值资格与空间精度分开。level2、跨h转移及一般联合分布未资格化。 |
| 选择能力 | `PARTIAL` | V1实际候选支持R1–R9九次p更新；R10因改善未超过冻结噪声拒绝。它是受控人工编排实验，不是已验证的通用自动selector。V2没有可用的新q/R完整数值结论。 |
| 精度能力 | `NOT_PASSED` | R9仍有两个零级s功率通道超限；R10仍有top `(0,0,s)`超限。尚未证明最终目标精度，也未建立独立更高精度参考。 |
| 成本能力 | `NOT_ESTABLISHED` | 尚未在同等精度下证明更少FE；也没有可比的同精度全过程成本结论。任务要求比较成本，但不要求成本必须获胜。 |
| 迭代能力 | `NOT_RUN / NOT_QUALIFIED` | 没有相同自适应空间上的direct/iterative完整观测资格，不把Task41或固定空间结果转移成证明。 |

单独说明：`0.7 nm` pilot为`NOT_RUN`，因为精度及自适应空间迭代的前置资格均未满足；这不是上述五项能力之外的已获能力。

R9仍是最后接受状态：110,472 FE（35,352 trace + 75,120 interior）；相对Y6_1参考，top和bottom零级s通道的功率绝对差分别为`4.065061945e−6`和`2.148245071e−6`，均高于`1e−6`限值。R10为180格全p6、118,800 FE，G改善`8.412900702e−6`小于冻结噪声`9.088158797e−6`，没有transition10；它相对Y6_1的top零级s通道功率绝对差为`2.837172688e−6`，高于同一限值。用户要求的同精度更少FE尚未证明。任务书要求比较同精度全过程成本，但成本优势不是必须获胜条件；本轮没有同精度成本数据。

## 修复、验证与限制

A2 attempt2的profile错误只改为V2 adapter中的局部兼容：对hash绑定的Y6_1配置做内存副本；若且仅若缺少`display_label`，填入派生值`D15-Y6-1`；逐字段确认其它profile值一致后调用既有native `_validate_resolved_profile`。旧配置原字节与native默认validator没有改写。clean fixtures覆盖原validator对缺标签的拒绝、V2缺标签接受以及错误标签/资源字段/数值字段差异拒绝。这个修改证明的是组件检查与配置preflight兼容，不是新PDE资格；实际冻结输入的read-only preflight调用retry loader和完整冻结输入helper，未调用runner、未建网格。

| 最终局部检查 | 命令与结果 | 证据范围 |
|---|---|---|
| profile helper fixtures | `source scripts/activate_task40_phi90_pord64.sh && python -m pytest -q src/test/test_task43_v2_native_p6_diagnostic_helpers.py`；26 passed/0.96 s | pure/helper fixtures；不是旧attempt1/Y6原件重放，真实原件预检另列。 |
| Ruff/format/compile | 对adapter与对应helper test运行默认`ruff check`、`ruff format --check`和`python -m compileall -q`；exit 0 | 两个文件Ruff通过、format已符合、compileall通过；日志`benchmarks/artifacts/task43/v2_diagnostics/v2_closeout_validation_attempt1/a2_profile_fix_static.log` SHA256 `a3b39e82c315b070b1332e0daff197afe07136fa93d56379179c01d61c55b4ec`。仅静态检查，不包含测试或PDE。 |
| 工作站冻结输入预检 | retry authorization loader + `_validate_frozen_inputs('A2_q')`；exit 0，native原生profile validator通过，除缺标签的内存归一外数值/资源profile一致 | 实际resolved config SHA `57ad47a4…baeedc`；日志及SHA见V2 compact。没有runner、网格或PDE。早期辅助预检错误、PMIx sandbox阻塞和纯fixture首轮失败均另按支持成本索引，不合并到formal wall。 |
| 原全仓pytest | `python -m pytest -q` | 使用V1最终记录：collection中止，1 skip、8 errors、测试体0执行。未因本轮文档或profile兼容补丁重跑，也不称通过。 |
| Registry Markdown合同 | `source scripts/activate_task40_phi90_pord64.sh && python -m pytest -q src/test/test_183_development_model_registry_markdown.py`；5 passed/0.06 s，exit 0 | 日志`benchmarks/artifacts/task43/v2_diagnostics/v2_closeout_validation_attempt1/registry_markdown_pytest.log`，SHA256 `d8723ee001feaaf2086b9ce1b811b05cd7fcaa5a6810308b70293e0529ba97f7`；只验证总账Markdown合同，不是full suite或CI。 |
| 文档、链接、JSON与提交身份合同 | 最终结构/引用检查结果见[V2 closeout compact](outcomes/records/v2_closeout_validation_v1.json) | 若保留的历史总账中有未随本轮引入的外部临时路径，compact会标为继承项；不将其误报为本轮新增缺链。 |

### 其他支持工作与费用入口

下列工作服务于原场恢复、证据核查或前置排错，不是正式模型尝试；其watchdog wall单独保留，不能与正式模型wall混称。三次legacy R10场恢复/采样尝试合计`152.32824470987543 s`，不执行PDE，见[legacy R10采样账](outcomes/records/v2_legacy_r10_resampling_attempts_v1.json)（SHA256 `22346bc8426213ed81aa17647da224d38e4648742b16a5aa33ba532bed090d46`）。旧保存场联合复核另用watchdog `46.21374210854992 s`，见[stored-field replay watchdog summary](../../benchmarks/artifacts/task43/v2_root_audit/old_field_replay/watchdog/summary.json)（SHA256 `2a28af1c13fc8423a15ba123c883ab5eb0fa6dd8ce7b41cbafb1136a7b02f95b`）；它复算旧样本，不是新PDE或fresh A6。Q02 collection/ABI与Q06/Q07组件工作分别见[Q02记录](outcomes/records/q02_collection_and_abi_v2.json)（SHA256 `0bf9cd88cf08a185d17489cc99eb98e376d1783dc577ab36fc39bb5bad40330e`）、[Q06/Q07记录](outcomes/records/q06_q07_component_validation_v2.json)（SHA256 `c7339611a127971f274954878baecd60f289031f970e6b9e4c958f75d2fc01e8`）和[Stage1门索引](outcomes/records/stage1_gate_v2.json)。

支持性失败也保留：早期冻结输入辅助预检错误见[原件索引](../../benchmarks/artifacts/task43/v2_diagnostics/A2_prelaunch_review_only/failed_frozen_input_identity_preflight.json)（SHA256 `730be5bf0a09985866ebf82c2bca9366e3bcccafbc225abdb0e7ca38e614d8fb`）及[捕获输出](../../benchmarks/artifacts/task43/v2_diagnostics/A2_prelaunch_review_only/failed_frozen_input_identity_preflight_captured_output.txt)（SHA256 `31548489de9120d46c6c1490298f4000d29ced749017b585f9f3843c5c783800`）；sandbox PMIx预检未能初始化见[日志](../../benchmarks/artifacts/task43/v2_diagnostics/A2_q_attempt2_prelaunch_review_only/final_path_fix_preflight_20261024T053841Z_final.stdout.log)（SHA256 `595c6a72618d90ab232509a1c18237f67823ba9ef20911d5f7bdac41701f19dd`），后续合格host只读预检通过。早期retry fixture有一次`35 passed, 1 failed in 51.54 s`（`NameError: identity_path`），保留在[retry wiring验证记录](outcomes/records/diagnostic_plan_v2_a2_retry_wiring_validation.json)（SHA256 `2e8fc4e905554b92225df6403b7e5424f905b8e574e394dd3c1e154d5f0b737a`）；当时console输出未保存为原始日志。上述辅助失败没有formal模型PDE；没有watchdog的辅助检查wall记为`not_measured`，不估算或加入任何总额。profile兼容修复的最终fixture与真实只读preflight日志已分别在V2 compact中按路径和SHA记录。

当前修复没有对应fresh PDE。三次正式尝试和所有历史负结果继续按原artifact保留；V2不能给出完整积分/端口扰动、独立q/R资格或局部h见证结果。没有CI声明。

## 分支与提交身份

仓库为`/home/fenics/Projects/NN-Lab-V2`，分支`task43_hp_adaptivity`，base为`405e3aff42ac421a4c99315df1ed9b96941ecbe4`。从外部review提交`7458fadccde01d37ed93187ebe4c39177783d60b`到本回应提交之前，本轮已推送提交如下；最终文档提交的完整SHA由同分支最终交付状态报告，避免在本文件中形成自引用。

| 完整提交SHA | 说明 |
|---|---|
| `fad2df0fb5c15ab1e14fabddf262a772c126cda5` | Q06/Q07及R8范围接线 |
| `822ebcf12f9277d1e5b4d88b1e8a1112b80dee3f` | Stage1证据首版 |
| `ed39637fd56976d91353640ad5c984baefff2850` | 删除summary重复副本 |
| `5d056b28ff61e5f3a2bac58431ea0b31531bdb2d` | V2端点比较器 |
| `e7c12e03cb32cb4ab183186bd153b47c79807faf` | 物理/空间比较身份 |
| `5f466d69b777539b42d1e35f2777936d88c19d78` | 同空间比较与R10场恢复 |
| `7590d7ea8945700ee684481fe2f201237142c682` | R10恢复设置记录 |
| `68ed596bc354ce3e4d33e3a2f55c808c91100865` | V2诊断计划冻结 |
| `ed95df3370973c2f06168ed938666250587ece6d` | A1诊断入口 |
| `2d775c9c00847f80eda7d09bd120be218603691e` | V2 observer transport修复与回归 |
| `647a85afeff121248cdbeecb3700fad93b8ee11d` | native P6 A2诊断入口 |
| `a3657ca1f82fbac0b18aead39ad78285b0887c38` | A2恢复bundle身份绑定 |
| `5b23aabe839effc1cb18f8a31820ea83219ec8d4` | 一次性A2_q retry前瞻授权与接线 |
| `a879554d7149bef1187b31bd731b09629f33fef3` | Y6_1 native profile缺字段的局部preflight兼容修复 |

所有工作限定在同一Task43执行分支；没有master操作、V1权威文件重写、旧失败覆盖或额外模型启动。外部审阅仍待进行；没有merge approval，也没有合入master。

# Response V28：新身份输入、全模式代表面与实际消费者交付

本轮按 [Review V27](review_report_v27.md) 完成了三项真实验收：新清单独立科学合格；原尺寸两代表面的全部32060模式边界组件通过原门；另一个新目录里的独立进程实际重开同一数值包并再次通过。交主线状态为 **READY_FOR_MAIN_OPT_IN_NOT_INGESTED**，主线尚未接入。旧原件没有找回，新清单与旧数值清单的等价性仍为UNKNOWN。

这里的边界组件把有限元面上的电场转换成各出射模式，并把模式牵引返回有限元方程。它是完整求解器的一个接入环节；本轮检查模式定义、两切向分量、B/D/H、方向约束、作用、伴随和入射载荷，没有求解原尺寸体内电磁场，也没有训练网络。

## 1. 三项验收与范围

| 对象 / 实际检查 | measured结果、原门与证据 |
| --- | --- |
| 新输入 | 32060有序key，top/bottom×s/p各8015；416780项独立物理字段检查，失败0；最大普通相对误差1.0747787677074433e-15，门1e-10；[输入身份](outcomes/records/input_identity_v28.json)、[科学核验](outcomes/records/mode_validation_v28.json) |
| 出射分支、H与物理背景 | 从原配置独立重算k/beta、极化、h_code、牵引、参考面H、功率和真实入射；8个固定高精度角色核验通过。实际选中32060条均classified propagating，不能冒称实测覆盖了不存在的倏逝模式 |
| 原生B0 | 实际Basix p4/p6的300/882全部局部列；两条非单位Floquet缝和角点，p4/p6方向正交误差9.5991e-14/3.7664e-13，MPC相对7.3030e-17，伴随绝对1.3878e-16；[实际运行](outcomes/records/run_index_v28.json) |
| 原q60全模式B1 | 两代表面(top,100,1)/(bottom,100,1)，p4/p6各32060模式，1004完整chunk；357个实际去重频率、ell0..6；一维矩最坏绝对9.082805012334877e-14≤1e-12 |
| 独立保存checker | 1218328项数值检查、失败0；最坏原分母相对9.595725209727146e-11≤1e-10；B/D/H、两分量、逐key投影及回散布、完整作用/伴随、坐标桥、真实入射RHS均通过；[原分子/分母](outcomes/records/boundary_metrics_v28.csv)、[完整数组入口](outcomes/records/independent_checker_v28.json) |
| 独立新目录消费者 | 实际重开1043文件、1625383207B的数据，重算模式物理和全部保存数值门；package_manifest SHA664e4ad412e818553c0172060b9e158f7edb06a1a90539a40370985b1aa8a5a9在两目录完全相同；[消费者收据](outcomes/records/consumer_receipt_v28.json)、[可消费说明](outcomes/main_handoff_v28.md) |

最坏项是p6、top(-64,-35,p)、mode_index9001的`original_recover_key`：分子4.307908906196561e-15，实际分母4.489404200351269e-5，相对9.595725209727146e-11。它接近1e-10门，约4.04%裕量；没有增大分母、丢微小内部迹或只报告平均值。此资格是两代表面和固定见证的经验通过，不是所有面、所有向量的统一误差界。

新身份为`W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28`，schema2显式开启。复用的V27文件36263033B/SHA7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e，没有重新生成。历史schema1仍要求原36244923B/SHA52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d，原常量、严格拒绝和旧FAIL没有改。声明保持`historical_bitwise_reproduction=false`、`equivalent_to_historical_numeric_manifest=UNKNOWN`、`historical_ledger_recovered=false`。

## 2. 有限修复与独立检查

没有因普通接线错误停止整包。实际修复了冻结Floquet函数返回值解包、冻结源码namespace看不到新增积分模块、过长Unix socket地址，以及第24份有效资源样本被读账误拒绝。最后一处恢复先完成36项定向测试与真实60s PSI观察；第二次接线因函数局部import未使用替换provider而失败。修正实际import来源并通过单独受监督回归后，沿用**同一未启动数值消费者的第24份准入、同一dat/hash/阶段时钟和已完成压力窗口**继续。没有第25份采样，没有声称新鲜重准入，没有改资源阈值。

两次消费准备失败均完整保留；最后消费者1289.617945s的阶段计时包含修复/等待，223.740910s的watchdog子段嵌套其中。健康清单和唯一完整边界producer均没有因封存或checker错误重跑。[有限修复及原记录](outcomes/records/repair_log_v28.json)明确区分软件拒绝、CPU前置拒绝与科学结果。

流程限定：最终消费worker前复用了先前同一准备阶段的CPU准入样本，修复期间没有重新采集CPU样本；PSI、内存、磁盘、自身swap及邻任务余量由实际watchdog持续保护。不能称最终启动瞬间重新通过CPU门。此窄范围续接及样本时效交审阅确认，数值数组PASS不替代该流程判断。

最终36项schema/字段/材料/H/符号/用途/损坏数组/失败监督/写出封存重开测试通过，另外1项局部import回归通过。原92A与39项V27按实际依赖绑定复用，没有full pytest、环境重装或新CI声明。纯fixture中的Basix替身不算原生证据；原生B0与全模式数组另有实际FE环境结果。[测试来源和所有先前失败](outcomes/records/targeted_tests_v28.json)。

## 3. 源码、费用与资源

| 阶段 / 实际clean source | 全链s / 同时进程树采样峰B |
| --- | --- |
| input_contract_checks / 9b1a9ec28cdd74510f8fd1ec0f40731c53d401de | 67.714709 / 124870656 |
| manifest_qualify / 9b1a9ec28cdd74510f8fd1ec0f40731c53d401de | 79.043941 / 290721792 |
| native control / 84e2c44cc0f94c82b89fcd045015835c4b5dc7bc | 73.584087 / 255557632 |
| 唯一完整boundary / 31b5ff639e4389c4c3bccd6605907a1b5b7be0e8 | 319.007977 / 810545152 |
| 独立saved checker / 12809c50011ca7013c441704b424569b8b11c2f6 | 595.392221 / 483381248 |
| 实际consumer / 82b74b2e7b2afa9660595cea37730c77b591e877 | 1289.617945 / 421486592 |

执行分支`task42extra_feinn_5nm`，冻结base`fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`，权威发布`ec05cb2ece095d54073563b02ab0da30f2795310`。数学源`c354afa449fb80cfb5012e7d2ff66a3e3e64e088`的43文件/1054179B闭包只读复用；各运行另绑定35份接收源码及实际输入、环境、阶段时钟、原数组。后续文档HEAD不替代上述run source；[run index](outcomes/records/run_index_v28.json)保存准确绑定。

连续28800s窗口从03:04:15.212063Z起算，含120s明确保守开场allowance，不重写旧窗口。记录快照截至04:50附近约6368.936111s，含开发、等待、所有失败及数值，发布尾段另入本机`tmp/task42extra/w1_receiver/v28/delivery_receipt.json`。实际24份内外准入，前台等待873.628663s≤900s；不同阶段各从现场合格核选择，单阶段只有一核，CPU-only/MPI1/数学线程1。所有已保存监督自身swap0并清场；最大采样树峰810545152B，watchdog之前的峰NOT_RETAINED，不把采样峰冒称精确峰。

轻/模式/控制/checker为2GiB，局部boundary上限16GiB；原PSI、max(128GiB,10%)系统＋384GiB邻增长余量不改，无OOC、无邻任务变更。新artifact快照5249268071B＜16GiB，启动磁盘余量通过。重复准备记录共用原consumer时钟，费用按区间并集而非简单相加；全部nested/失败记录保留。[完整资源账](outcomes/records/resource_costs_v28.json)区分实测快照与未完成发布尾段。旧A/V25/V26/V27、失联3284s、外部日历等待和未知尾段均保留，项目精确累计仍UNKNOWN。

## 4. 交付与未验证项

交付是相对路径数值包和独立pure消费者，已经在本任务另一个新目录实际读取，成功监督/清场后才写ready标记。它不是仅指向旧绝对路径的索引，也不授跨机/断电存储资格。主线必须显式opt-in同一instance，不能混用旧manifest的B/D/H或旧端口因子；本支没有修改主线或dot。[接入包](outcomes/main_handoff_v28.md)、[专题](outcomes/versioned_manifest_and_boundary_v28.md)、[Gate](outcomes/records/gate_decisions_v28.json)、[分组边界](outcomes/records/selective_merge_manifest_v28.json)。

原q60通过，条件`q60_phase_subdivision_v28`未触发、未运行；没有q80/q100、全局/局部Maxwell factor或solve、Gram、NN。原尺寸完整总/散射E/H/curl、六样本、复散射通道、R/T/A/A_volume和全场原残差均NOT_RUN，不能把模式边界数组当成这些物理结果。

保持 **FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED**。保留M3600中期较好、Mfinal退化、D0成本否决/D1未运行、全部旧FAIL/UNKNOWN及费用。最终原50×25×140nm、Si17/120nm、λ0.7完整三维FE、decimal2e12B整机、ownswap/OOC0和172800s完整冷流程的原门尚未达成；本轮增量是确定性输入与端口组件接入资格，不是NN收益。

GitHub有限抓取新review返回服务错误/Cache miss，没有实际浏览器视觉PASS；资源采样额度已用尽，没有额外浏览器树。[呈现记录](outcomes/records/render_check_v28.json)保留阻塞及本地结构检查范围。网页问题没有停止数值工作。提交推送本分支、精确fetch核对和自身清场后仅发一次正式完成通知，随后停止等待审阅；不merge master、不自动扩大计算。

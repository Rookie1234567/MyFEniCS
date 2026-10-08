# Response V64：准备包已保存，两个新完整场均未取得

本批没有完成P6或L4的完整物理解。P6真实组装了全四面体p6体弱式和两套完整828边界，随后独立原式核对过慢，在单例18000秒配额必须留下3000秒审核/输出的边界受控停止，尚未做symbolic、numeric分解或求解。L4固定标记的相容网格实际为25576tet、1043792行，超过19200tet/800000行，两项形状门拒绝正式PDE。没有放宽精度或资源门，也没有将准备包、小测试或边界通过写成场通过。

这里p6是在原网格的每个四面体内增加场形状；L4则把前两份场差异大的区域细分，周期与相容要求会连带细化周围单元。本批保留全部内部未知量，只压缩周期重复项，没有静态凝聚。实际有限全局LU没有产生；标准完整tetra直接参考仍不是目标规模生产方案。

## 唯一身份与实际执行

canonical `/home/fenics/Projects/NN-Lab`、分支`task42_neural_coarse_inverse`、base `ccd357885f7f9be84efe3be07868cc94f13d93fc`。被审V63 `17e953f12502b0dfded7778e751d2274d12e5295`；Review `b2cf084ee0269b87acfacef314475a70702f4266`，blob `875eeacad19c9cc4c1862242e040a3e0ac98f37c`，正文SHA256 `b68ed6e8338ae3ed62707b72270a7071ea996ab1a3c47f3031c681e63ac60184`。未重导入旧3eff附件，报告正文不改。完整身份见[记录](outcomes/records/report_identity_v64.json)。

正式preflight/P6实际source `e28ce30b47797581176f2d5fa752b1f3539387c8`；保存消费者/最终targeted资格source `687663e2f7210c62808dfc54b7951369469ba520`，与最终文档HEAD分开。真实`.venv`资格activation、complex128/int64、MPI1/math1/CPU1、GPU/Loader0；原ABI不变。本批四个dat已实际实现、clean提交并validate；L4因形状不准入没有盲跑。

首次工作UTC `2026-10-08T13:13:11.457752329Z`、monotonic1390186.31、boot绑定；heavy-stop `2026-10-09T00:13:11.457752329Z`、总截止01:13:11.457752329Z，未刷新。P6单例配额独立有效，不能因全批尚有剩余就重新开一遍。研究总时钟包含读合同、实现、失败、等待、比较、IO和交付。

保持s=7/135有限真实三维NOTCH、λ0.7nm、canonical Si n=0.999885140474+4.32477054e−6i、epsilon=n*n、mu=1；入射1°/5°/s、原κ=(8.94046081729244,0.7821889682108057,0)，完整Cκ、双周期、m±11/n±4的828模式。材料hash `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。不是原尺寸完整问题，不移用邻支资格。

## 实测结果与未运行项

| 对象 | 实际空间或存储 | 已完成 | 未完成与原因 |
|---|---|---|---|
| S/L4冻结网格 | 1267/7680标记；25576tet；FE1042964；含828为1043792行 | θ=.5最小前缀、周期配对、父材料/体积审核 | 超19200tet/800000行，L4 PDE NOT_RUN |
| P6 | 7680tet/p6；FE980352；native1005528；981180行 | mesh/MPC、完整UFL体组装、q47/q63边界 | 独立原式gate未完成；symbolic/factor/solve NOT_RUN |
| 独立VERIFY | 4个新NPZ/25成员；828边界库存 | 保存mesh及边界重算，无新body作用或因子 | 没有系数，所有新场/功率/完整方程资格NOT_RUN |

实际没有新的total/scattered E/H/curl、240点、解的828复振幅/逐mode功率、R/T/A/A_volume或能量。B/P6、A/L4、B/L4、P6/L4和固定P6误差—费用表均未运行；不从旧summary造场，不补零通道。formal1e−6、direct1e−10、恢复1e−10、全场/复通道1e−4及功率原门保持，缺解不能称PASS或数值FAIL。[冻结与分类](outcomes/records/decision_and_not_run_v64.json)给出所有缺项。

标记使用原DE/NE+DH/NH；NE=.8042647476533107、NH=.8040966375803122，总指标4.98246786552436e−7。选16.4974%的单元覆盖50.018973%，最高10%覆盖35.567263%。同值用原几何键，未加curl或改局部分母。mate-only(False)实际周期门通过，仅多2条周期mate边；没有True同步后备或调整θ。相容闭合使cell增长3.3302倍，独立父体积操作差2.75111e−15、材料继承相同。该固定L4配置否决，并不否定所有局部细化。

P6实际superdegree6/local216、完整MPC一行最多10master。397744956项是实际支撑推得的保守图上界，不是实测nnz；装配规划40.475910GiB在192GiB许可内。numeric仍要求可靠symbolic两倍+liveRSS+2GiB，尚未到达此Gate，不能声称numeric容量通过。实际nnz/fill/numeric峰和完整成功T_N1未知。

## 完整费用与停止证据

| measured P6阶段 | 秒 | 计费边界 |
|---|---|---|
| mesh/MPC | 17.924943 | case内阶段 |
| q47 / q63 | 60.583201 / 63.998702 | 两套各真实生成一次 |
| 标准UFL/FFCx完整体组装 | 12203.710183 | 含本次实际准备，不是新求解 |
| 独立原式未完成段 | 至少2490.803052 | 嵌套在失败进程内，不能再相加 |
| 失败完整入口 | 15056.335016 | 启动到run_case返回及后代清场 |

P6完整入口13:50:44.044349Z至18:01:40.379346Z，15056.335016s是真实失败费用；成功T_N1不可取得，不能把这段全部写unknown。预留阈值约18:00:43Z，18:00:59.850159Z执行自身已核实PGID的SIGTERM，检测/控制延迟约16.17秒，剩2983.827秒，未开始numeric。原supervisor保存`WORKER_FAILED/-15`，新增语义记录为`CONTROLLED_STOP/P6_COMPLETE_CASE_ORIGINAL_AUDIT_OUTPUT_RESERVE`，不改旧失败。最近保存事件为两列标准UFL/PUBLIC_BASIX作用配对开始；原作用启动计数保留[1,2]、生产[0,2]区间，不伪造完整次数。

P6采样整树峰35811266560B（33.351GiB），ownswap观察峰0，20556样本最大gap2.008412s；名义0.5s不是连续硬峰。可见numpy unique-owner载荷14530397344B，PETSc/MPI不透明对象另为unknown但包含在RSS，二者不能相加。没有OOM、OOC、资源重入、排序/shift/PC替换，邻任务未修改。

q47/q63每包804624140B，成员与文件hash在保存消费者首次完整记录；不是冒称旧producer已有同一hash收据。全部828边界最大相对差3.47853e−15、操作尺度3.53175e−15、入射牵引2.75929e−15。它证明积分包一致，不证明离散解存在或场准确。[实际数组](outcomes/records/array_inventory_v64.json)和[独立检查](outcomes/records/independent_saved_pair_checks_v64.json)保留来源。

独立VERIFY重建一次解释mesh/space，139.873466s完整入口、峰2.951GiB；没有新body作用/factor/solve。preflight完整入口188.016511s。全部前后辅助、拒绝入场、定点修复、文档及尾部费用最终汇入[最终费用](outcomes/records/resource_costs_final_v64.json)，嵌套launch/supervised不重复相加。历史已知下界229211.7403489353s和unknown延续；V63父A/B必需生成链8016.232864s已在历史内，不免费也不再加一次。最终原始版本/储存/闭合见[交付索引](outcomes/records/delivery_index_v64.json)。

## 有用归因与唯一下一pilot

保存mesh上的精确未舍入cache键有1118类；q17的729点、216基函数使每类变换后basis/curl表为11337408B。现有512MiB LRU只能放47类，按原cell顺序重算得到5932 miss、4814重复重建；全存约11.81GiB超过额外2GiB空间。这是确定性cache库存推演，不是原运行逐类计时，不能断言它是唯一耗时根因或预报速度比。

唯一下一pilot建议先资格化“系数先变换”的独立PUBLIC_BASIX向量积分：直接变换单元系数和输出复对偶，避免为每个精确几何方向构造整张变换basis表；与现有正确p6保存见证配对后，在新完整合同下只做同一P6完整场。它只针对本次实际原式消费者瓶颈，不改变空间/物理，不缓存全部11.81GiB、不自动p7、第二轮θ或更多模式。本轮没有实现或运行这项建议。

V63 A/B散射E/H差4.89487e−4/5.08576e−4、240点2.32882e−3仍超1e−4，direct内部目标FAIL也保留。本轮没有新正确性基线，不能授同精度资源比、连续真解、原尺寸0.7nm、2TB/48h或NN20。历史低存储局部装配/凝聚收益保留；完整tetra LU不可直接放大到目标，准确相位空间以后仍需可扩展trace作用及分块内部恢复。本批训练0，确定性工作不归NN收益。

六个新增数学/接线targeted测试、相关Ruff/compile及4dat validate通过；失败fixture/API/祖先映射/计费、部分保存consumer按同轮最小修复保留，不重跑旧PDE。无full pytest/CI/历史hash扫描。一次紧凑文档检查及最终字节收据封存，GitHub视觉NOT_VERIFIED。

[专题](outcomes/p6_reference_local_h_v64.md) · [科学](outcomes/records/scientific_checks_v64.json) · [容量/标记](outcomes/records/capacity_and_marking_v64.json) · [失败部署](outcomes/records/deployment_failure_v64.json) · [修复](outcomes/records/repair_journal_v64.json) · [真实source](outcomes/records/source_bindings_v64.json)。当前批次结算、closed/active null、后代清场和自有锁释放、同分支push及remote/clean/upstream核实后用户暂停，不通知邻窗，不merge或自动开下一窗口。

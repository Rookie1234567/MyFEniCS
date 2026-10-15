# V79：真实误差预算尚未运行，资源拒绝及只读交接

**本轮科学消费者未运行：两次正式CPU/SMT准入均拒绝。** 已实现保存场诊断接线并完成静态检查，但没有取得新的E/H/curl误差、区域分账、χ或γ；不能把NOT_RUN写成0或方法失败。本轮遵守Review第6节“现场有冲突则完成纯文档部分”，未绕过heavy锁或CPU规则。

这次计划直接比较同一离散中的正确参考和128步失败场，量出实际场错误，再看curl、质量和精确开放边界三项如何抵消。它不改变方程、不求新解，也不产生新的PC。已有0.284是闭合物理FE残差，不等于28.4%的电场误差；源码中q=rE−C H^-1 rp已消去辅助端口不平衡，不能把它仅归咎于端口坐标。

| V79获准项目 | 实际状态 | 证据/原因 |
|---|---|---|
| V70/V78同离散身份 | SAVED_METADATA_MATCH_ONLY | 物理、p5、25576tet、828模式、κ、MPC/编号/几何及RHS成员hash一致；未在本轮解压大数组或重建live空间 |
| 128步真实场误差与固定区域 | NOT_RUN_CPU_GATE | 无经审计空闲物理核，不给伪数值 |
| q15闭合误差恒等式、curl/mass/q63 DtN分解 | NOT_RUN_CPU_GATE | 新body作用0列，上限8；没有新Γ/χ测量 |
| 可选32步 | AVAILABLE_NOT_CONSUMED | 完整full系数快照收据已定位，不重建轨迹 |
| 两个one-run入口 | STATIC_SCHEMA_PASS / 正式未运行 | clean-source资格化辅助在CPU准入时被阻止；EXPORT不能捏造前置结果 |
| 新PDE/KSP/numeric/global K/S | 0 / 0 / 0 / 0 | 未重跑旧解、建PC、训练或操作邻任务 |

[主证据与CPU逐核排除表](records/known_error_budget_v79.json) · [只读参照契约](records/reference_consumer_contract_v79.json)

两次允许CPU均为48个，eligible=0；第一次排除理由计数为sample busy>0.05的33项、active wide thread的53项、narrow affinity的38项（同核可多理由，不能相加成核数）。两次原始admission、stderr和wrapper费用均保留，第二次遵守至少120s间隔。CPU门先拒绝，MEMORY/DISK/PSI/CGROUP_GPU后续正式门是NOT_CHECKED，不冒称通过；独立早期宿主快照内存压力为0也不能替代准入。没有修改邻任务亲和性、线程、系统或任何保护阈值。

新增opt-in原式回调在已经恢复的完整FE误差上分别积curl和mass，保留真实Piola、T^T系数变换、test共轭及MPC复对偶；production默认返回数值不变。q13差分分子可同一次cell遍历批128/32两列，差分先在独立FE系数中相减再经P到native，不重复内部特解。现有per-cell积分按材料和四个预先固定等高几何z区间的cell中心唯一归属；实际cell体积分账单列，不冒称边界跨cell时已经作平面精确裁切。**这些是待消费实现，不是本轮实测物理资格。**

初始5项合成回归通过（0.327s，非PDE）。零分母合成例曾产生RuntimeWarning，C1前改为显式None；最终clean-source两次focused辅助都未越过CPU准入，因此最终数值资格NOT_RUN，不能把初始测试替代它。最终源码compile、相关Ruff与两个dat元数据validate通过；后续只做一次紧凑文档检查，不full pytest/CI/旧FLAT或历史数组重放。GitHub视觉NOT_VERIFIED。

| 费用；measured，独立区间不重叠相加 | 秒/边界 |
|---|---|
| 第一次 / 第二次准入wrapper | 54.000720 / 51.715501 s；无科学worker |
| 已计时命令及元数据归档已知下界（结算快照） | 106.761952 s；未包裹编辑/Git等区间unknown |
| 既有V78失败对照 | KSP534.859523 / 完整尝试875.795297 s，不改旧账 |
| 既有V70正确同离散参考 | 必要BUILD+prepared solve22313.374088 / prepared solve12666.547605 s |
| V79完整科学消费/成功N=1/RSS峰/χ/γ | NOT_RUN / unknown / unknown / unknown / unknown |

历史已知费用下界400183.831621s原样承接，本批不重复加父前缀。packet-only fresh份额unknown；没有同正确性新解，不能从875s失败尝试与正确直接参照相除宣称速度收益。2TB/48h和历史连续空间精度FAIL、NN20资格均不升级。本轮从2026-10-15T05:40:31.497035581UTC/monotonic1967826.36/原boot冻结2h，所有实现、失败、观察、静态检查和交付均计入，不刷新旧窗。

下一方法准入卡为**INSUFFICIENT_CAUSAL_EVIDENCE**：尚未测得真实误差、χ/γ和区域份额，不能选择新PC或申请其重型预算。可证伪问题是“剩余错误是否具有可重复的curl尺度、抵消和空间分布，某候选能否在新独立方向及完整成本下真正消除它”；一组名字、局部代数或单一比值不够。唯一下一行动是待审计物理核可用并有有效冻结窗口后，先完成本保存数据消费者，不自动搭建或运行下一PC、不自动V80。

worktree=/home/fenics/Projects/NN-Lab；分支task42_neural_coarse_inverse；base=ccd357885f7f9be84efe3be07868cc94f13d93fc。Review=1c355cf7bb8a856f5987e4b0b459f85cf8d657b2，blob=41b3eaf87e5750db37ae2e7dc6372459386d2f58，正文SHA699d383344b3660a7ca19f5612ae595ef4d2716bc3f5f8bc0af08747908a4fd4均核实。实现/准入source=3cd630b676729faf6766b54fb6415d71e9950ce4；**本轮数值运行source不存在**，文档HEAD另列最终Git收据。原qualified native complex128/int64 ABI已只读核对，未升级环境。

旧task/review/response/raw不变。只推送本分支，closed/active null、清场与锁释放后暂停；不merge、不改master/邻工作树、不通知隔壁。

结算快照（2026-10-15T06:03:53.899699Z）：本批已计时命令/元数据费用下界106.761952s，历史已知下界400290.593573s；截至该快照研发实钟1402.402664s不与前者相加，后续Git与交付实钟另记最终收据。新增ignored快照16253885B、free2469222977536B；未为文档重扫全部历史存储，当前Task总量unknown，最后既有快照214759898797B。15项纯文档检查通过，最终数值focused和两个正式数据入口仍NOT_RUN。ledger closed/active null，自有锁取得释放，科学actor从未启动；最终remote/文档SHA与交付时刻见Git收据。

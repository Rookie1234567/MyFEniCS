# V40：真实有限体积与非零载荷恢复闭环通过，原尺寸解仍未完成

| 本轮对象／目的 | 实际结果 | 资格边界／证据 |
|---|---|---|
| 0.7nm／8hex xy_corner／两种材料／p6 | storage7056、独立trace2796、内部3600、slave660、12冻结端口 | 真实FE MPI1／数学1，非384-cell旧pilot；[身份](records/run_index_v40.json) |
| 先验证接口、再构造昂贵数据 | 公共carrier在任何kernel/LU前通过；4类882张量与450内部LU及时保存 | 实际8hex/4LU，无完整重建；[checkpoint](records/checkpoint_inventory_v40.json) |
| 原native体积 vs 独立Basix q15/q17 | 两tag四项最大4.13409338553e-15<1e-10 | 实际原数组全部保存；旧Fourier边界q15FAIL不改 |
| 完整作用／伴随、非零f_i/g与恢复 | 独立66项全部通过，最差内部平衡4.06091386035e-12<1e-10 | `COUPLED_ACTION_AND_AFFINE_RECOVERY_QUALIFIED_ON_WITNESSES`；[checker](records/component_checker_v40.json) |
| 新进程真实volume消费 | 加载10.88413s；两完整作用0.170528s；恢复0.061963s；原矩阵审核0.094775s | `REAL_VOLUME_RECOVERY_CONSUMER_QUALIFIED`；不是零callback；[消费包](records/deployment_package_v40.json) |
| 原尺寸接入 | 原宽度／tag精确270类；E单实体工作区上界86880B；完整native方向／owner未知 | [容量合同](records/original_size_integration_capacity_v40.json)，仅derived／conditional |
| 全目标PDE／场／功率／2TB48h／NN20% | NOT_RUN／NOT_QUALIFIED／NOT_DEMONSTRATED | 本轮无训练、无新official结果，不授micro或原尺寸解资格 |

原来的程序只在最后保存体积数据，一次接线错误就会丢掉昂贵构造。本轮把几何、张量与内部LU、原小矩阵、求积对照、恢复和消费结果分阶段保存并核对hash。这样后续小错误只需补做未完成阶段。内部LU仅求每个单元450个内部未知量；它不提供全局p4逆，也不使本轮成为factor-free。

边界系数现在按完整边／面实体的少量master条目生成，最大实体6／60行；共轭散布进入调用者已有的合法向量。删掉的是构建时整张“边界行×全体积行”临时数组，而非原方程、端口或高阶矩。消费合同绑定几何、basis、周期MPC、物理、材料、离散、源依赖；同shape不同相位／材料／编号会拒绝。有限片段的行号不冒充原尺寸DOLFINx行号。

## 真实恢复与独立审核

使用未缩放的一般复输入、固定seed非零内部载荷和port载荷，`norm(f)=112.7807031283`、`norm(g)=5.47891418907`。原Hp是I，D只归一化一次，增广块为`[V,B;-D,I]`。因此非零g的原生有效右端是`f-Bg`。恢复除trace诱导场外，还加入内部载荷的特解；误差场去掉该特解。

| 原数组比较／门均1e-10 | 相对差 | 意义 |
|---|---:|---|
| 一般a输入体积／伴随 vs 独立原小CSR | 1.82757032779e-14／1.82955389138e-14 | 正向与共轭转置均一致 |
| MPC物理展开 | 0 | 计算slave精确0，物理展开保留周期系数 |
| 仿射恢复差F(a)-F(b)=F(a-b)-F(0) | 4.63203030563e-16 | 非零特解没有被当成误差场 |
| 原native／增广恒等式 | 5.48586872447e-17 | r_native=r_FE-B*r_port，未强置残差0 |
| 压缩RHS／凝聚作用 | 2.66051930632e-17／4.22687826858e-17 | 原内部负载投影与trace/port同坐标 |
| 压缩残差注入原trace | 3.96077373003e-14 | 与原完整方程残差一致 |
| 最大局部内部平衡 | 4.06091386035e-12 | 分子2.40980311198e-10、运算尺度59.341399371；无需精化 |

独立checker只使用保存的原小CSR、C/D、完整原张量／已存LU、RHS和MPC数组重算，不调用生产action或recover。零输入要求严格0，复缩放另查；缺q17、缺f_i/g、漏slave、错class/identity或破坏恢复项均有拒绝回归。原C/D内部浮点残项未裁剪。一般输入的原方程残差很大是正常的：这些向量没有被求解，不是PDE通过。

## 费用、失败与继续消费

| 步骤（shared-workstation） | 实测秒 | 计费／重叠说明 |
|---|---:|---|
| PREFLIGHT，复用旧四类literal/E数组 | 17.908204972 | 48检查；不建新mesh |
| BUILD首次，失败仍收费 | 860.362899838 | 张量/LU/小CSR已保存，随后Basix实数接口拒绝复数数组 |
| BUILD修复后只补求积 | 34.735824945 | 不重建kernel/LU/CSR；源92052770 |
| RECOVER／CHECK／DEPLOY／CAPACITY | 21.324593／12.832949／14.798618／4.491730 | 各one-run真实执行 |
| 原class构造含原子保存 | 282.005639117 | 内含kernel275.595345427及LU/恢复0.777338275，不重复累加 |
| 原小CSR装配／其hash保存 | 550.145130343／7.032965543 | 原oracle未分解；不得声称全流程无装配 |
| 独立q15/q17构造比较／保存 | 19.802860854／3.866693908 | 两材料原数组保留 |

所有辅助、失败、编译、测试、准入、归档和交付列于[最终费用](records/resource_costs_v40.json)。native/慢oracle934.331522755s<2400，组件966.454819266s<5400（二者是总额内子集）。历史下界78517.88650908363s和V39监督1249.459315514192s另外接续；未监督实现／一般读写及完整旧端到端费用保留unknown。

第一轮pre04测试fixture累计存储越新2GiB上限，watchdog受控停止，原日志保留。仅将本轮394份合成fixture共2165357441B无损压成56347102B，逐件校验解压hash后收回自己的重复原文件；旧科学数组与失败记录不变。pre05的fixture缺name已定点修复。真实BUILD唯一错误是Basix `T_apply(float64)`不接受complex128；对实虚部分别沿两轴施加同一真实方向变换，非Hermitian实接口小回归通过，再读取原checkpoint补做。没有静默改变精度、输入尺度、门限或材料。

全本轮同时整树采样峰1265823744B、ownswap0；FE warn6GiB/hard8GiB，辅助hard2GiB，0.5s完整后代监督。独立cgroup写权限不可用，未伪称内核cgroup硬峰。CPU按现场tick/亲和性/SMT每次选择；shared-workstation观察没有持续PSI压力，但缺少可比邻任务阶段指标，干扰INCONCLUSIVE，不宣称零影响。[资源重算](records/resource_samples_audit_v40.json)。

## 原尺寸容量合同与下一步

| 对象／来源 | 字节或库存 | 尚缺的资格 |
|---|---:|---|
| 实测本轮LU/恢复/Schur等class cache | 56274336B<256MiB | 只属于4个实际class；全目标方向类未知 |
| 11个原子数组包／138逻辑成员 | 压缩文件158696482B | 压缩字节、唯一payload与RSS分开；[数组库存](records/array_inventory_v40.json) |
| 原尺寸E/EH条件稀疏载荷 | 各≤547969544B；workspace86880B | 假设每实体row一master，通用MPC多master需给出倍数 |
| 冻结短轴精确宽度／材料库存 | 270键，共530856cell | 不四舍五入合类；native方向／全局MPC类unknown |
| 原尺寸complex128单向量 | 5532337056B | 345771066 storage行尚未构造 |
| 逐cell LU/恢复/Schur同时载荷条件 | 4956275464704B>2e12B | 必须有可证明的精确class共享及生命周期 |
| 每cell882个int64映射条件载荷 | 3745719936B | owner-local分区/索引协议待真实native身份资格 |
| 不构造的32060² Hp稠密块 | 避免16445497600B | Hp=I保持隐式，不能藏进setup |

完整成本应为`T_setup+K*(T_volume+T_boundary+T_adapter+T_PC)+T_recovery+T_audit+T_IO`。V38边界首次forward/adjoint约0.077134419/0.076004680s仅是边界组件；本轮10.88413s加载也仅是有限包。目标K、全体积/PC、活跃向量、完整恢复/审核/IO均未测，不能外推48h。原尺寸material仍使用canonical用户表，source0.699999988显式alias nominal0.7，n=0.999885140474+4.32477054e-6i，epsilon=n²。

原尺寸full true residual≤1e-6、完整场／复振幅≤1e-4、R/T/A/A_volume≤1e-5、逐通道功率≤1e-6和能量≤1e-5：全部NOT_RUN。本轮没有合格物理解，也没有新R00_s/p/total或official R/T/A，h/p与模式截断未授资格。旧native q60／q15及V39体积失败继续保留；不训练NN，无NN20%实证。dot旧包材料/编号等缺口按Review保留，本轮未执行它的solver或读取factor。

唯一下一建议：资格化同物理全体积引擎的native owner/MPC映射及精确class缓存容量，以本轮有限非零RHS包作接口anchor；先证容量与同原方程作用，不自动启动完整求解或再开独立边界测速。

[Review V37](../review_report_v37.md) · [response](../response_v40.md) · [原始证据](records/raw_evidence_index_v40.json) · [run/source](records/run_index_v40.json) · [可消费包](records/deployment_package_v40.json) · [集成就绪](records/integration_readiness_v40.json) · [测试](records/tests_v40.json)。GitHub精确页无视觉证据，NOT_VERIFIED；本地表格／公式检查不等于网页或CI。

最终结算：19次监督共1260.375694643939s，准入24.514265201171s，加bootstrap3s及交付收尾保守5s，共1292.889959845110s。ledger closed、active为空，自有后代逐次清除；实际结算UTC 2026-10-04T09:11:09.192651+00:00。监督配置间隔0.5s，首次BUILD实际样本中位0.878012s、最大1.078099s（包含健康检查调度），没有伪称连续cgroup硬峰。新增含文档482946231B，新JIT196161322B，Task artifacts15589782476B；证据余量256MiB与free50GiB门满足。历史监督研究下界接续为81027.721519241764s，其余unknown不猜造。

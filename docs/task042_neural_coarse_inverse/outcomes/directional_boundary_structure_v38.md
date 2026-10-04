# V38：完整原尺寸边界作用与周期native桥接

端口先将边界有限元场分解为衍射振幅，再把对应牵引返回边界方程。此前每个通道都逐面片重算，完整库存会重复访问上亿次面片。V38把同一q离散积分按x/y方向组织为矩阵收缩，共享几何及波数表；体积内三维传播方程没有降维。付出的代价是原生Nédélec基与边界布局之间的局部坐标转换及额外缓存，必须逐项通过原生装配和独立积分检查。

**取得 `NATIVE_P6_PERIODIC_PATCH_BRIDGE_QUALIFIED` 与 `TARGET_BOUNDARY_ACTION_QUALIFIED_AT_FROZEN_Q`（q30，真实MPI1）。这是边界组件资格，无原尺寸PDE解、场／功率、2TB／48h或神经20%资格。**

## 固定身份与范围

| 项目／身份 | 实际值 | 数据口径／边界 |
|---|---|---|
| 合同／首次接手 | Review V35 `cf0896e57f9f16970e5af6b55ad14920ab4c7815`；2026-10-04T04:41:55.638633870Z | UTC、monotonic1013910.50、boot fd8f4b00-1e17-46af-a6fa-da3a32dbeba3不可刷新 |
| 原尺寸与材料 | 周期50×25nm，z=−10..130nm；Si x=16.5..33.5、y=0..25、z=0..120 | λ=0.7；canonical用户表 n=0.999885140474+4.32477054e-6i，epsilon=n²；source标签0.699999988显式alias，未插值 |
| 原库／边界 | 32060有序端口，16030每侧，双Floquet，layered background，无PML | 历史mode／材料hash复用；[身份与run](records/run_index_v38.json) |
| 四类native见证 | min/max普通、x周期缝、xy角点；完整882基、12固定mode、唯一20hex | 新构造累计28/32，含失败重建；q30原生装配与MPC，未裁剪 |
| 全表面 | 每侧73×36=2628面，p6高阶完整边／面矩 | 紧凑边界189216行／侧、两侧378432行；不是目标体积canonical编号 |
| 输入与规则 | 两组一般复系数seed423801/423803；q30、独立更高阶q60 | FP64/complex128，保留全部mode、方向、Piola及周期复相位；无FFT、低秩或NN拟合 |
| 新规模没有构造 | 530856cell体积mesh、345771066维体积向量、全局体积A/SH/LU/QR、训练 | 全部NOT_RUN；6.05MB边界向量不能冒充5.53GB体积向量 |

材料表hash `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`；物理合同hash `7da1f5b5f1ef0345c499c656965cb3c9820c3f8beec850ef2889efd605b8eaa8`。底端口、基底、光栅和背景使用同一Si值。规则原尺寸边界可服务三维体积模型，但本轮未建立notch或全体积内部求解，不能以边界计算证明非可分三维最终解。

## 独立数值验收

非零完整向量差为两结果差的范数除以两结果范数较大者，门1e-10；逐通道同理。全零另验精确零。H使用相对门，单位通道参考面功率使用绝对门；保留分子、分母和最差原index，不校幅相或删除小条目。

| 比较／为什么需要 | measured结果 | 原门／分类 |
|---|---:|---|
| min普通：新同q／native与独立2D q60全部C/D | 最差1.47457343214e-12 | PASS，原native q30普通数组只读复用 |
| max普通／x缝／xy角点 | 最差1.47609408351e-12／1.48686036402e-12／1.48685259295e-12 | PASS；literal cell permutations、T_apply、MPC主从／corner链均保存 |
| 小面片与紧凑行坐标桥 | primal差max3.37543233931e-15；原点／x缝／角点rank324/324/624 | PASS，仅小片行双射；全目标体积row adapter未构造 |
| 全32060端口q30/q60振幅向量 | a1.17780841167e-14；b1.25458242550e-14 | PASS，两输入都覆盖全部通道 |
| 最差逐通道q30/q60 | a1.47954943851e-12 index22336；b1.60663242361e-12 index29663 | 分子8.02075e-16／6.00550e-15；分母5.42108e-4／3.73795e-3，PASS |
| 全边界forward／adjoint／modal RHS | 最大1.65302229731e-14／1.65163795364e-14／8.51739703187e-15 | PASS，完整378432输出保存，不只比较总功率 |
| 复线性／dual | 最大1.14568625654e-15／2.49146944139e-14 | q30/q60及两输入全部PASS，零输入精确零 |
| 独立12mode显式全表面求和 | 最大作用差2.39972325681e-14；31536实际facet访问 | PASS；直接2D Basix q60全882tabulation，未使用分方向多项式系数路径 |
| 完整库存H／单位参考面功率独立重算 | 5.46028927946e-16／3.41060513165e-13 | PASS；最差index28957／5659；不是求解后的R/T/A |
| 真实MPI／合成MPI | native与完整作用MPI1；MPI2/4仅合成fixture | 不授真实目标MPI2/4资格 |
| V37 q15、native q60 | q15差1.32594720615e-5 FAIL；native q60 NOT_RUN_STORAGE_GATE | 原结果不改写；本轮不启动巨型q60 UFL JIT |

[全部原指标与literal数组身份](records/boundary_metrics_v38.json) · [独立checker](records/component_checker_v38.json) · [Gate分类](records/gate_decisions_v38.json)。三条路径共享Basix原基定义；原生q30装配锚定FE/MPC，直接2D q60锚定积分，新方向收缩锚定执行等价。它们不是三套独立物理求解器；全部q30/q60通过也不是h/p或连续极限收敛。

## 软件修复、真实失败及费用保护

完整checker现在强制四类预登记身份、q集合和action库存，缺整q、缺action、重复替代、错误身份均拒绝；从保存数组重建分类，不能沿用上游status或空集合通过。旧checker的V37 partial结果保持。每mode不再复制全部面片tuple，而绑定共享表身份；MPI单rank坏H、坏hash共同传播，有界退出。新计算核共享两侧几何与row表，没有mode×face元数据展开。

| 保留失败／缺口 | 最小修复与同轮分流 | measured失败费用 |
|---|---|---:|
| Basix原生创建缺variant | 通过现场basix.ufl的真实p6 Legendre定义读取 | 4.001501996s |
| BRIDGE重复预留所有已生成JIT文件 | 增量预留并hash复用已完成min/max前缀 | 79.488342440s；未越实际存储门 |
| FFCx缓存依赖C文件存在，归档后重编译撞cached标记 | 精确hash恢复原C字节，复用原.so；不修改安装栈 | 24.846572670s |
| 前64端口只有一侧，空侧reshape失败 | 显式空表维度与单侧真实workflow回归 | 8.438553591s |
| 当前worker查询预算被当作重复启动 | 只读active身份及已消费时间，launch准入规则保持 | 11.864887528s |
| 全量输出144MiB预留被拒绝 | actor退出后归档5个生成.so，先解压核hash再释放相同副本 | 12.850935348s；164650360B原库→22596015B无损归档 |
| action.stats第一输入快照被第二输入原地更新 | 新代码复制快照；旧数组不重跑，旧计数明确为两输入累计10project/10scatter | 数值结果不变；修复／测试费保留 |

旧失败与prefix结果均不覆盖。归档只回收本任务生成的JIT或合成fixture副本，科学数组、stderr和旧closed账本只读保留。压缩NPZ保持complex128，alias仅允许字节完全相同的dtype/shape/content，逐成员hash仍验；未降低精度或移出任务目录绕存储门。数值停滞没有被当作bug重调。

首实现提交误用普通git commit，出现“Auto packing ...”提示；之后所有提交显式禁用gc.auto与maintenance.auto，现场未见活跃gc/repack或gc.log，是否后台maintenance曾完成UNKNOWN。未执行主动gc/prune/repack、修改共享Git配置或其他worktree；此记录不能被包装为已证明全程无自动maintenance。

## 执行成本、内存与容量

| measured或derived对象／阶段 | 实际值 | 口径与边界 |
|---|---:|---|
| 64→1024→32060成本前缀六类作用 | 0.111844729／0.166127181／0.441056754s | 最后值是一个输入的6类作用集合，非完整solver |
| q30完整首次setup | 4.016996373s | 前64/1024各3.415371456/2.728261280s也计费；q60独立setup未单独打钟，包含于stage wall |
| q30完整投影／forward／adjoint／modal | 0.033394624／0.077134419／0.076004680／0.042669471s | shared-workstation；第二输入及q60全部值保留，非无争用正式加速 |
| 同样两输入×q30/q60六类作用 | 四组wall0.441056754/0.520020542/0.481246559/0.593285238s | 计入同stage，不能另加嵌套project/scatter到总wall |
| 成功COMPONENT／独立ORACLE整stage | 30.084113727／20.550954598s | 含加载、数组保存及审核；ORACLE内部数值集合11.564905505s包含于20.55s |
| 包含失败的全部BRIDGE／LAYOUT／COMPONENT／ORACLE | 154.093470076／10.809338664／63.238490194／20.550954598s | 组件合计248.692253532s；历史与aux另列 |
| 同时整树0.5s采样峰／own swap | 1047965696B／0 | warn6/hard8GiB保护；非独立cgroup连续硬峰，无GPU |
| 数值缓存／共享layout | 7628096B／10596096B | 缓存门64MiB，所有Python／workspace另计RSS；geometry/map共享一次 |
| 一个紧凑边界向量／原目标体积向量 | 6054912B／5532337056B | 后者历史derived，不在本轮构造；不能互相替代 |
| 全部实际费用、最终存储和日历耗时 | 见最终费用记录与response | 所有失败、probe、测试、归档、checker、打包累计；bootstrap3s单列；未监督实现／一般读写UNKNOWN |

[完整费用／资源](records/resource_costs_v38.json) · [生命周期](records/capacity_lifecycle_v38.json) · [原始日志与gzip](records/raw_evidence_index_v38.json)。单次完整边界作用均小于600s；全量前实际按 `4×32060/1024×prefix六作用wall+120` 保守准入，包含checker／清场余量。native及慢oracle按更保守的包含失败BRIDGE累计收费，未刷新旧时间戳。数学／BLAS getter1、MPI1、CPU/SMT每阶段现场准入、自有锁和0.5s整树监督；只降低自己的CPU/I/O优先级。Task042extra邻负载存在且未操作，自己的准入／运行未触PSI、swap或RSS停机；缺可比阶段指标，性能干扰INCONCLUSIVE，不能声称绝对零干扰。

完整预算式仍为：

```math
T_{N=1}=T_{setup}+K T_{boundary}+T_{volume/PC/recovery/IO}.
```

K和体积求解、内部恢复、MPI、IO成本UNKNOWN。小边界作用降时不是迭代收敛改善。历史费用保留已知下界与unknown，暖结果上游成本不消失；没有匹配合格完整N=1非神经基线，NN20% NOT_DEMONSTRATED。

## 消费包、未运行项与唯一下一步

[机器可读消费合同](records/deployment_package_v38.json)保存物理／材料／mode／layout／source与C/D符号、dtype、primal-dual及归一化。这里投影分母H是参考面切向模态E平方积分；物理振幅未知量的原增广约定H=I，由除投影分母转换，不能混同Hp/Hhat。输出只含上下紧凑边界未知量；未来体积solver必须提供显式native抽取／散布row adapter，验MPC/slave和复dual，再校验同一内部仿射恢复及原方程。小片双射不是整个目标体积row资格。

无匹配dot solver包，保持SOLVER_PACKAGE_NOT_QUALIFIED；本批没有fetch或运行dot，不消费其逆。完整体积PDE、原Schur/native残差、E/H/curl、R00_s/p/total、R/T/A/A_volume、逐通道物理解功率／能量、h/p／外部截断、2TB／48h和NN20%均NOT_RUN/NOT_QUALIFIED。没有新teacher、dataset、model训练或global p4 factor。

最终已结算监督 654.956926790s＋probe 41.348239223s＋bootstrap3s＝预算收费 699.305166013s；另保守预留5s标量close费用。组件 248.692253532s／5400s，慢oracle含失败BRIDGE保守收费 174.644424674s／1200s。已知新库存含compact交付 433468326B，另1MiB源码／导航余量后仍低于512MiB；历史实测下界续记 78517.886509084s，完整历史和未监督实现／一般读写仍UNKNOWN。日历截至费用收口 3644.119s，自首次接手计算，窗口未刷新。

唯一下一建议：对一份同物理／同离散的体积solver包实施native边界row抽取／散布及内部恢复接口资格检查。这里只交付需求，不自动实施或扩大模型。新核心保持opt-in；[依赖分组](records/selective_merge_manifest_v38.json)未授merge approval。GitHub精确页没有视觉证据，NOT_VERIFIED；本地公式／表格检查单列，不声称CI。

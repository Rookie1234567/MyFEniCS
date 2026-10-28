# Task43 正式审阅 V19：接受固定保存场诊断，下一步分解已有 R10 响应

审阅形成日期：2026-10-28；授权中断后续行发布：2026-10-29。唯一执行分支：`task43_hp_adaptivity`。

## 1. 正式裁决

**V19 的固定保存场科学诊断接受，工程整改部分接受；不授予整体精度、生产或合并资格。下一轮直接执行第9节：R9→R10 全 p6 动作响应与 R10 剩余离散场差分解。新增正式 PDE 为0，新增支持最多4次、whole累计3000秒。**

下一任务必须读取已存在的两阶三场数组，给出此前没有的逐单元响应、剩余差异分布和一个有明确规则的位置提案。通过前门后连续完成，不逐阶段等待另一份review，不以再写一轮归档回应代替科学分析。

| 裁决对象 | 结论 | 实际含义 |
|---|---|---|
| D1索引修复及D2固定入口 | 有限接受 | 实际owner/几何重排路径正确；D2同worker受影响验证后完成诊断 |
| 整轮执行与合同一致性 | 部分接受 | 两次槽外数组操作、一次shell127及三处合同冲突是真实监督缺陷，不因D2完成而消失 |
| 两阶180单元/612通道科学结果 | 接受固定数据范围的解释 | P8局部响应强但覆盖小；H8局部改善被域外恶化超过；不是DWR或独立空间精度证明 |
| 测试、资源和运行身份 | 有限接受 | 接受各自实际字节与可见时间窗；不是一次最终全套、全仓CI或生产ABI通过 |
| V18-02小原件补证 | 关闭本轮要求的提交可见性缺口 | 退出原行窗口和原42数组审计报告已补交；原NPZ及完整资源流仍未亲验 |
| 下一轮运行 | 明确批准第9节 | 新支持T1/T2/D1/D2有条件使用；不借用旧T2，不恢复历史封存正式槽 |
| 合并 | 未批准 | 任何依赖组及整分支均无实际merge approval；本次只提交本报告 |

原科学状态保持：空间 **PARTIAL**；选择 **PARTIAL**；精度 **NOT_PASSED**；同精度全过程成本 **NOT_ESTABLISHED**；迭代 **NOT_RUN / NOT_QUALIFIED**。accepted9/R9、R10拒绝、H8/P8的明确收益失败及历史正式失败均不改。

这里的“场差分解”，是把两份已经保存的有限元解之间的差异，按原网格单元拆开，并检查一次升阶造成的变化是否朝参考解靠近。它只改变后处理分析，不重新求解；收益是避免重复计算并为下一次局部改网格提供依据，代价是仍依赖既有离散参考，不能据此证明连续真解精度。

## 2. 固定身份、差异与本审实际证据范围

### 2.1 提交身份

| 身份 | 完整SHA |
|---|---|
| 固定被审交付 | `56a2a41d0b0cd7b034dab6f434d61c83b250e9e1` |
| 本轮执行权威，V18 review | `5586112bf5bee924cc603253a5cbf7dd6c4a0863` |
| T1/D1实际运行HEAD | `8898f7e5fab82234786c51ffbd0cdeb167b379fe` |
| D2实际运行HEAD | `f066305d7e95b438a5ef8b223f2d5928bc6d79d9` |
| 长期数值基线 | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |

审阅开始及本次续行发布前核对的远端分支均指向固定交付；相对V18 review为3个线性提交、ahead/behind=3/0，88个文件变化（83新增、5修改）。新增源码是保存数组checker及测试；其余是V19合同、脚本/证据归档和当前文档。没有共享数值核心、三个旧求解/比较runner、watchdog、activation/ABI或历史review变更。[固定差异](https://github.com/Rookie1234567/MyFEniCS/compare/5586112bf5bee924cc603253a5cbf7dd6c4a0863...56a2a41d0b0cd7b034dab6f434d61c83b250e9e1)

交付HEAD不追认为T1/D1或D2运行HEAD。本审通过远端API核分支和固定文件，没有进入工作站canonical worktree，不能独立证明其现场工作树干净或本地ahead/behind=0/0。本次使用指定分支的新文件创建操作，不覆盖既有文件；发布后核对提交parent、changed files和远端回读。若远端出现并发后续提交，必须保留并明确说明，不能强推覆盖。

### 2.2 阅读及复核方法

前一轮审阅已阅读三层AGENTS、任务书、V11科学补充任务书、V18 review（重点完整第9节）、本轮回应、合同、机器结果、代码、测试、启动/快照脚本、当前结果与依赖清单，并追溯R9/R10身份和旧共同数组写出路径。本次为恢复未发布的完整审阅草稿并继续写入，重新核对了远端分支和文档规则，没有另开科学实验。历史规则以最新明确授权覆盖的范围为准，不把旧补充任务书中的已耗槽重新打开。

本审及前一轮并行子审阅只读取固定源码和Git证据，用另写的标准库程序核CSV/JSON/XML、字节身份及标量算术；**没有执行项目模块、交付checker、pytest、旧审计器、native导入、支持driver或PDE**。审阅计算不是工作站新实验，不计作新的项目支持通过。

| 证据层级 | 本审确实检查的内容 | 不能外推的内容 |
|---|---|---|
| Git直接可读 | 两阶完整180行cells表、612行modes表、逐项diagnostic；7份完整raw trace；两个原XML；实际launch、manifest、runtime/terminal；42项交付副本大小/hash | 副本一致不证明本审访问了工作站原路径 |
| Git中的派生记录 | 三槽共168条紧凑资源行、现场主控source/posthash结果、NPZ目录/内层身份/finite声明 | 紧凑行不含完整每PID资源/affinity原流；hash声明不等于本审读取原数组 |
| 新补交的历史原文/摘录 | V18 F/C连续退出资源窗口、历史host检查、原42数组复核报告 | 没有重新读取42个原数组或施加A6；没有重新现场检查旧PID |
| 未访问的工作站ignored原件 | 四份原NPZ、全部点/权/owner原数组、modal/Av原JSON、完整resources.jsonl及现场快照原目录 | 不写为本审亲验、重采样或独立算子核验通过 |
| 下一任务输入 | Git已绑定的旧R10共同包路径/hash及写出源码 | 当前工作站是否仍可读、实际成员/数组正确性须由第9节受监控worker验证 |

本审重新从完整CSV求和、核复数差值、符号和所有超限通道，而非只读response或PASS。CSV是派生数值，因此这证明表级一致性及源码路径可解释性；没有冒称重新计算原NPZ。

## 3. 按严重程度排列的问题与验收要求

本轮未发现足以推翻D2固定诊断的确定性科学公式错误。以下工程问题与已知精度负结果分开裁决。

| 编号/严重性 | 固定提交定位 | 问题与影响 | 最小整改及可执行验收 |
|---|---|---|---|
| **V19-01／中** | `response_v19.md:82`；`sources/unmonitored_operations_self_report.md:7–60`；`sources/d2_recovery_decision.json:29–36` | D1后两次实际NPZ数组读取超出V18允许的槽外文本/hash准备；另一次shell127。未保存完整计时/身份，不能称所有执行合规 | 历史原字节与NOT_MEASURED保留。第9节所有实际NPZ数值读取进入编号driver；代理槽外只读源码、已提交JSON/CSV及文件hash。下一合同和主控分工明确此边界，不为补归档重跑V19 |
| **V19-02／中** | `v19_saved_hp_response_contract.json:24,50–54,72–84,132–151`；checker `642–737`；`sources/launch/snapshot.py.txt:38–52` | 合同仍写无动态授权/D2未启用，另一处却armed=true；旧launch hash与实际绑定不一致。现有validator未否决这些重复字段冲突 | 不改消费过的合同/快照。下一合同只保留一个槽授权状态和一个规范化launch身份；所有重复引用静态逐项核对，并在第9.6授权T槽内以负例验证冲突拒绝。主控在首次调用前亲审完整差异 |
| **V19-03／低，范围限制** | `src/test/test_task43_saved_hp_response.py:326–364`；checker `1554–1608` | “q10写失败”fixture实际是预建目录触发FileExistsError，不是写入途中/fsync/终态故障注入；通用resume只在fixture使用，D2未走resume | 本报告限定覆盖范围即可，旧测试不用重跑。第9节只使用已完成阶次的窄绑定复用，若实现新的写入/恢复行为，只验证该新增风险；不授通用恢复资格 |
| **V19-04／低，导航** | `README.md:57`及其后旧阶段“当前”文字 | 顶部V19正确，但旧表仍可被误读成当前V18/V11权限 | 下一轮文档收口将旧段标题标为历史，当前权限只指最新review；不改历史review/回应正文，不单独开支持运行 |

上表`sources/`均指`docs/task43_hp_adaptivity/outcomes/records/v19_saved_hp_response_sources/`，checker指`benchmarks/task43_hp_adaptivity/analyze_saved_hp_response.py`。

**V19-01责任包括执行代理越过只读源码/JSON指令，以及主控没有在操作发生前落实边界。** 两次读取确实参与了索引故障定位，不能称毫无信息作用；但D2在授权worker里从固定输入重新完成owner和全部数值计算，额外输出没有成为最终科学验收数据。未知wall、PID、解释器和成功操作的准确退出码继续UNKNOWN，不补造为0或已合规。

**V19-02不等于实际D2没有可追溯身份。** T1/D1的旧launch为`87b60b…26aa52d`；D2实际launch、tracked归档、`launch_files`与运行manifest一致为`fc9db4…57e2b8f2`。V18 §9.8允许本类D2恢复；主控决策与同worker三节点实测也存在。因此裁决是“合同整体不一致、实际执行链仍可限定接受”，不是后验删掉失败或凭元数据冲突推断换了输入。

## 4. 实现、失败恢复及测试覆盖

### 4.1 D1原因与D2修复

D1把几何plan列表顺序误当mesh global ID；请求box位于plan row66，闭包位于row67，实际global ID分别是8、14。失败为`root target requested global cell ID/box mismatch`，在两阶诊断完成前拒绝；不涉及新PDE或科学Gate失败。

D2新增`order_plan_boxes_from_saved_owners`（checker 885–910），先核local-slot/global-ID对应，再由各owner点组包围范围匹配唯一冻结box，并要求180项双射；913–935逐点核几何归属；实际`_one_order`在1387–1403调用这些函数。请求仍为global8/root4，闭包仍为global14/root34，没有改模型或选择位置。

新增测试367–380有意打乱plan行序，并直接调用真实映射与点检查函数，另核错误owner拒绝；没有mock掉受验函数。它修复了最初测试和主控预审遗漏的真实数据结构风险。[固定checker][checker]；[固定测试][tests]

### 4.2 测试证据按字节归属

| 运行 | 实际测试结果 | 允许复用的范围 |
|---|---|---|
| T1，8898f7e5… | XML 12 passed，time=1.040s；console约1.05s | 原数学、加和、612集合、混包/反向reference、只读及窄持久化fixture |
| D1，同HEAD | checker拒绝，退出2；无新增pytest结果 | 保留失败，不算科学负实验或测试通过 |
| D2，f066305d… | 同worker3 passed，XML time=.674s；console约.69s | owner重排新增节点、错误owner节点、多单元加和节点；随后真实两阶诊断 |
| 最终交付 | 文档及证据提交 | 不追认为一次最终13节点或15次节点执行的全套pytest，更不是全仓CI |

D2绑定的checker SHA256为`f1191f223e087a4d8d589e7a11a056e06e2c831a37ae2c5aa862c2da55868ca8`，测试为`aa0f292d2be57454ec0c847b44fef34fdbd5bd40494fc80c22340db483907a45`；本审核其固定字节与记录一致。新fixture和session的D2同worker分支不由旧T1自动覆盖，实际D2提供对应证据。未变节点按函数及依赖差异复用，不能将两个批次拼接为最终同字节全套。

### 4.3 输入与输出路径的实际边界

checker 185–284核外层NPZ、精确member集、内嵌record及每数组dtype/shape/hash，禁止object/pickle；287–309核四场共同点/权及q绑定；807–819将数组标只读。源文件及输入前后hash、实际HEAD、runtime终态与退出记录共同决定资格，单个早写出的diagnostic标签不够。

独立阶次落盘和排他目录有实际实现，但多文件原子事务没有被证明；本次也没有这类生产声明。新增checker共1768行，包含大量固定路径、输入身份和生命周期代码，适合作为这次研究读取器保留。后续只能复用必要纯函数，不据此次成功扩成通用consumer、controller或新的恢复平台。共享数值核心、默认行为和旧runner未改，不为本轮研究checker补发这些组件的生产资格。

## 5. 科学结果的直接复核

### 5.1 恒等式、方向和归一化

代码实际使用e=Y6_1−R9、d=动作−R9，复内积含共轭；E与curl/k0分别累积，k0=2π/13.5。逐单元独立计算：

```math
B_K=\langle e,e\rangle_{G,K},\quad D_K=\langle d,d\rangle_{G,K},\quad X_K=2\Re\langle e,d\rangle_{G,K},
\qquad I_K=X_K-D_K=B_K-\langle e-d,e-d\rangle_{G,K}.
```

第二条I使用直接形成的e−d数组范数，未以第一条结果赋值自证。完整表中E+curl/k0=G，两动作B相同，180项加和与全域相符。共同归一分母为`max(reference_G_norm, incident_floor)^2=700000`；参考范数约554.563，入射floor约836.660。没有把单元开方范数直接相加。[checker 332–369、938–1041][checker]

两阶180盒构成完整3×10×6分区、体积350000nm³。Git表的box/行号双射与已保存owner诊断一致；本审没有亲读110万点原数组，不能声称在本机重新做了原点owner检验。

### 5.2 请求区、闭包与其余域

以下为q10未归一化G平方内积，直接由完整表求和：

| 区域 | 原B占全域 | H8净改善I | P8净改善I |
|---|---:|---:|---:|
| 请求global8/root4 | 1.243361895% | +1.0013599456388371e−5 | +1.3719067924065197e−5 |
| H8必要闭包global14/root34 | 0.212150546% | −3.397776995376554e−5 | +1.1753099505539893e−6 |
| 其余178单元 | 98.544487558% | −3.0594387947085664e−4 | +5.389711173405981e−7 |
| 全域 | 100% | −3.299080499682338e−4 | +1.5433348991959785e−5 |

原全域B=`0.0011175840214348934`。P8请求区B减少98.72948%，其动作增量平方D的92.0517%在该区；全域B只减少1.380956%。P8全部180单元I为正，但域外量很小。不能将“全域改善小”说成“请求区没有响应”。

H8请求区G平方减少72.0630%，但闭包和其余域的负I合计约为请求正I的33.95倍，全域B增加29.519754%；只有请求单元I为正。请求区E分量I本身为负，改善来自更大的正curl分量，不是每一场分量都变好。这里的“恶化”只指与固定离散Y6_1的距离增加，不自动证明h约束、方程或材料实现有bug。[q10完整单元表][cells10]；[q10逐项诊断][diag10]

global8本来就是最大单元，却只占1.24%；前十最大单元合占12.398394%，分布于x=[16.5,33.5]、z=[−10,0]的十个y带。因此不能据本结果说“最大seed选错了”，也不能期待一个单元消除广泛分布的全部差异。全局耦合响应仍需实际测量，局部覆盖率不是所有h/p动作的收益上界。

### 5.3 q8/q10、完整通道及J

| 动作 | q8 G | q10 G | J | 冻结结论 |
|---|---:|---:|---:|---|
| R9 | 3.995683423458671e−5 | 3.9956834234581814e−5 | 4.065061945224269 | 原接受态不具最终精度 |
| H8 | 4.547357272406128e−5 | 4.547357272405789e−5 | 3.9745473239816143 | ΔJ小于εJ，G恶化 |
| P8 | 3.967998186281262e−5 | 3.967998186280788e−5 | 4.020864574738603 | ΔJ及ΔG均未越冻结可辨识尺度 |

完整通道键是top/bottom×m=−4…4×n=−8…8×s/p，四组各153，合612；没有仅检查最差项。两阶modal表同字节符合其复用同一原端口输出的用途，不是两次独立模态测量。每个候选超逐通道功率门1e−6的键恰有两个：

| 候选减Y6_1 | R00_s／top(0,0,s) | T00_s／bottom(0,0,s) |
|---|---:|---:|
| R9 | +4.065061945224269e−6 | −2.1482450713386503e−6 |
| H8 | +3.974547323981614e−6 | −2.1129819847975906e−6 |
| P8 | +4.020864574738603e−6 | −2.083962419685559e−6 |

其余610项在各候选上未超该门。不能只提R00而遗漏T00，也不能用大量小通道稀释最大通道失败。[完整612表第154/460行及其余全部行][modes10]

J重现包含6项聚合功率、最大单通道、4项复幅组、5项场量，共16项。其最大witness为`power.R00_s`。总/散射差使用共同背景相消；散射reference norm/floor及Av为明确绑定的历史复用，没有新背景或体吸收积分。模态复幅平方恒等式与保存物理功率分开，未反除极小幅度构造物理权重；独立物理功率重装配仍NOT_PERFORMED。代码985–1151、1231–1289的角色与归一化成立。

εJ=`0.12716416232413652`、εG=`9.088158796603444e−6`不变。P8点估计ΔJ/250优于H8的ΔJ/6268，但两者冻结区间均跨零，P8下界未超过H8上界；不授p优于h或transition10。

### 5.4 能接受的解释及仍不能确定的原因

接受：P8在请求处有效、全域覆盖有限；H8的域外响应超过局部收益；G与R00/T00变化不同步；两阶保存数据支持同一解释。

不能接受：把局部G贡献叫局部R00误差、DWR、可靠连续误差估计或已资格化选择器；把低于237600 FE叫同精度；把两阶稳定叫operator q/R、参考本身或独立holdout已通过；由H8变差否定所有h/p方案。

DWR（dual-weighted residual，对偶加权残差）是在“哪里对指定输出最重要”的意义上给残差加权，通常需要目标量对应的对偶信息；本轮只分解已有解的场差，没有这类对偶权重。因此它能解释已发生的响应，却不能直接把局部场差解释为局部R00误差贡献，也没有授权新的对偶PDE。

当前仍不能唯一归因为参考离散、q/R、空间表达或不同路线误差。任务书本来就将G定义为正定比较量，而非Maxwell双线性形式的能量误差。目标量方法也需要额外结构：Ingelström的[作者机构论文记录](https://research.chalmers.se/en/publication/1747)从对偶解构造散射参数误差；[Demkowicz的Maxwell hp论文](https://doi.org/10.1016/j.cma.2004.05.023)用参考解投影收益/新增自由度选择。这里只沿用前一轮审阅核对的机构/出版方摘要所述方法区别，不将论文的可靠性保证套给本仓库，也不据此授权对偶PDE。

## 6. 资源、退出、费用及历史补证

### 6.1 三次授权调用

| 槽 | whole含清理/s | watchdog内部/s | 紧凑资源行 | 同时树RSS采样峰/B | worker/watchdog/supervisor |
|---|---:|---:|---:|---:|---|
| T1 | 4.016669398 | 3.284586710855365 | 8 | 107126784 | 0/0/0 |
| D1 | 13.085514464 | 12.415548613294959 | 28 | 349720576 | 2/2/2 |
| D2 | 88.164291237 | 86.53078653058037 | 132 | 892551168 | 0/0/0 |
| 合计 | **105.266475099** | 不另加内层时间 | 168 | 不跨运行相加 | D1失败保留 |

两次未监控数组操作、一次shell127、静态及人工时间另列NOT_MEASURED，105.266475099秒不是全轮所有活动的总wall。pytest和内层读取/运算已经包含在whole中，不重复加。T2未启用，不得挪作其他任务或抵扣越界操作。

7份Git raw trace共340/177/232行，每槽5个getter均[1]，没有setter；正常SIGCHLD分别关联已知退出子进程，D1主worker尾为2，其他已记录尾为0。不是“无任何signal”。D2 worker PID/start=`3615316/312156949`，直接watchdog=`3615313/312156873`，tracer=`3615320/312156954`，runtime始末及host历史不存在记录对应。末行资源exit0、无后代。

全部已提交紧凑行task swap=0，峰值及终态可复算；CPU1、线程变量和父链有runtime/trace支持。本次没有MPI并行或完整ABI探针，记录`NOT_USED_NOT_ABI_QUALIFICATION`正确。trace从taskset后开始，部分短命子进程缺start_ticks；RSS/VmSwap为采样量，PSS未启用；空cache metadata不证明实际JIT/global cache稳定。完整原资源流未亲验，资源结论限于上述证据，不授通用监控资格。[D2 root原值及索引][d2close]

### 6.2 V18-02补证的具体裁决

F窗口原1-based 5574–5581行：先有同PID/start活worker，5576/5577为vanished，随后连续4行exit0且children空。C窗口原673–678行：674为vanished，675–678连续exit0且children空。对应历史trace退出时刻和host消失记录支持“退出期间采样竞态”，没有显示活worker脱离监控后继续求解。这个判断来自连续原行时序，不是忽略所有vanished标签。[F窗口](outcomes/records/v19_saved_hp_response_sources/v18_F_resource_window.jsonl)；[C窗口](outcomes/records/v19_saved_hp_response_sources/v18_C_resource_window.jsonl)

原42数组审计JSON现已提交，1,628,364字节，SHA256为`7190e2831ddc18382921e5529f08de5b643b943a57205681b1fa49005b617f41`。42个name唯一，dtype/shape/hash/finite及原绑定可见；由其保存范数相除能重现A6、full-active、condensed标量。**这不是42个原数组本身，本审没有重施加A6。** 因此关闭“报告和连续小窗口未交Git”的缺口，保留原件可见性与生产资格限制，不要求重复F/C或旧数组复核。[原审计报告](outcomes/records/v19_saved_hp_response_sources/v18/v18_root_primary_array_recomputation.json)

## 7. 下一科学任务的选择依据

**先用已有R10回答“广域升p实际消除了什么、剩余场差在哪里”，比立即换另一个seed或再求一个p子集更有判别力。**

旧R10并非未做的设想：原180叶上，28个剩余p5升p6，另外152个p6不变；实际118800 FE，比R9增8328。其G约3.154393353284729e−5、J=2.837172688008316，ΔG=8.41290070174027e−6仍小于冻结εG，因而旧拒绝正确保留。[R10实际空间准备第9–27行](outcomes/records/round10_p_only_plan_preparation_v1.json)；[R10拒绝记录第28–102行](outcomes/records/round10_rejected_candidate_v1.json)

现在确认旧`post_selection_shared_q8/q10.npz`保存了R9/R10/Y6_1，且两阶在各自共同点有完整E/curl。写出源码是`compare_round1_candidate.py:2864–3036`，其中2950–2972保存points、weights及逐场数组；不需要重新恢复或采样。[原包固定索引第1582–1594行](outcomes/records/post_selection_existing_fields_validation_v1.json)

本轮前十B单元仅覆盖12.3984%。若假设只消除这十格差异、域外完全不变，理想G减少约2.56e−6，仍小于冻结εG。这是附带明确局部假设的算术判断，不是实际耦合解的上界。它说明此时立即做十格p批次，若目的只是越过原G门，依据不足；已有更广R10响应应先利用。R10也不是所有p子集的严格最优上界，后续任务不能据此证明p普遍无效。

新任务的收益在于把“28个低阶位置被提升”与“实际改善/恶化发生的位置”分开，并观察全p6后剩余差异是否集中。它不会解决所有q/R/参考不确定性，但能为下一次有限h假设提供比再次选最大R9单元更具体的证据。**只有第9节是执行授权，本文讨论的其他可能动作均未授权。**

## 8. 依赖组及合并资格

| 依赖组 | 具体文件与依赖 | 本次资格 |
|---|---|---|
| 文档/轻量证据 | response_v19、contract/results、sources、当前README/summary/registry/progress及本报告 | 研究档案可保留、可进入选择性审查；须带监督偏差和合同冲突，无实际merge approval |
| test-only | `src/test/test_task43_saved_hp_response.py`；依赖checker、冻结输入、工作站运行约束 | 指定节点/字节有限接受，不能作为无依赖独立生产测试包合入 |
| checker/benchmark | `analyze_saved_hp_response.py`、合同、固定源目录及NumPy | 固定研究用途接受；缺通用输入、失败恢复和生产消费者资格 |
| 研究启动与快照 | sources下`launch/stage_launch.sh.txt`、`snapshot.py.txt`及其实际ignored同字节脚本 | 具体T1/D1/D2链有效；不提升为共享运行器或新的默认策略 |
| 共享watchdog/环境 | 本轮无更改 | 旧使用证据不等于新生产merge批准 |
| 数值核心及整分支 | 本轮无核心变更；历史多层、精度、完整成本和迭代缺口存在 | 不借本轮后处理补发资格；禁止整分支合并及提交大原件 |

本次**没有任何具体依赖组的merge approval**。保留档案、工程接受、科学解释接受与实际合并许可分别裁决；实际合并仍需明确逐组批准和用户授权，本次不执行。

## 9. 下一轮唯一执行授权：R9→R10响应与R10剩余场差分解

### 9.1 批准范围、科学问题与固定角色

**批准立即实施并连续完成本节。新增正式PDE、FE场恢复、新采样、背景重建、矩阵/算子作用、对偶求解均为0。新增支持最多4次、whole累计3000秒，具体槽见9.7。**

唯一科学问题：**已执行的28处p5→p6动作，改善主要发生在原升阶区还是原p6区；全p6后的剩余离散场差是否有稳定集中位置，足以提出下一次有限h诊断的位置？**

固定物理为50×50×140nm、新phi90、13.5nm，原operator q15、incident/port q28、R13/612通道；只分析已存R9、R10和Y6_1。动作是历史R9→R10的28处p5→p6、无h、保留原闭包事实，本轮不施加任何新h/p动作。R9仍为accepted父态；R10只是被拒诊断状态，不能成为新accepted父态；Y6_1为原选择参考，不换参考。

前瞻允许消费旧六场共同包中这三场的数值及既有几何。**禁止消费Y5_1、Y3、Y3_2数组、模态或比较结果来归一化、排名或挑参考。** 旧post-selection记录的`selection_eligible=false`及“不反馈旧选择”仍保留，本授权不回写旧R10的角色；新产物仍是诊断和提案，不是自动选择transition。

### 9.2 先完成的静态准备与输入锁定

安全fetch/fast-forward本review，核canonical worktree、分支、upstream和后续差异，不覆盖已有工作。canonical固定为`/home/fenics/Projects/NN-Lab-V2`。

先仅用源码、原JSON/已提交CSV和文件hash完成以下准备，**不在槽外打开NPZ数值**：

1. 将V19-01/02最小纠正落实到新任务：唯一权限状态、launch规范化路径/hash一致；主控给代理明确文本/数组边界；保持V19已消费文件不变。
2. 从原件JSON锁定R9/R10 plan、modal、Av、原comparison及Y6_1身份。核R9的28p5/152p6和R10的180p6，180个box不变，无新增h；逐box关联global ID、forest root和父p，不能由plan行号推global ID。
3. 原R9 plan SHA为`9f8bbc8f90ae609822ac934311986f75d1648eba5b26b6a488647e9b94fd4947`；R10 plan为`7e8305e0d6117ceeb37e88eb715d98ab5212505a2410161f0b38aff5c7ed1826`。R9 global→box映射用V19两阶一致且已绑定的完整表/诊断，加原plan/forest JSON交叉核；不猜十个root或重新做native搜索。
4. 两原包目录唯一为`benchmarks/artifacts/task43/round1_candidates/comparisons/post_selection_joint_attempt1/`，身份如下。

| 原件 | SHA256 |
|---|---|
| `post_selection_shared_q8.npz` | `ce3707052419ada5a8e55574a826772bcb1e37cf1f764fc115eb8bf8a52306e5` |
| `post_selection_shared_q10.npz` | `895b65ffbf63176ac20008e6488c1c1318141f877eb5814496fcc945c049514d` |
| 同目录`post_selection_comparison.json` | `347195b3e29e23a2907e16264385346e208a2a7d2d48fb8b2d8c0b00ede3b6aa` |
| 原R10 `candidate_comparison_v2.json` | `3db50c67e871520398eee3c05219d4ef3090c360f5f2b4495e5fe31f3c70b3e0` |
| 原R10 modal rows | `f7048a9ecad65db39faa688d9d4f0041099f2719e64e5ea2898e3dc793003450` |

原R10后两路径从`round10_rejected_candidate_v1.json:evidence`读取；R9/Y6_1沿V19对应角色及原资产，不目录扫描挑替代版本。原post-selection的pairs没有Y6_1→R9/R10这两对，不能误取其中Y5方向的J/G当复现锚点。读取该JSON仅限输入身份、共同几何规则与来源；J/G锚点用原R9/R10 comparison、拒绝记录，R9可另与V19同定义积分标量核对。

这些NPZ为旧写出格式，没有V19那套内嵌record/owner。不能要求不存在的历史内层hash，也不能伪造它。新worker在核外层原SHA后，对允许成员记录本次dtype/shape/数据hash/finite，明确这是新派生目录，来源锚仍是旧外层SHA。

任何原件缺失、hash冲突、p分布/box身份不符，停止受影响动态消费，交具体缺项；不得为补原件恢复FE场、重采样或另解R10。

### 9.3 最小实现范围与精确数据allowlist

允许：

- 新增`benchmarks/task43_hp_adaptivity/analyze_saved_r10_response.py`，只读标准库/NumPy；
- 新增`src/test/test_task43_saved_r10_response.py`，小型合成fixture；
- 新增`outcomes/records/v20_saved_r10_response_contract.json`及对应response/results/sources；
- 第9.7节新前缀中的短launch与快照，tracked保存脚本文本；
- 当前README、summary、manifest、模型总账和开发进展的必要更新。

复用V19纯数组恒等式、模态inventory及原子文件函数，不复制其整套1768行绑定/runner。默认保持V19源码不变；若确需将被复用纯函数作窄参数化，只允许该checker及受影响fixture，并在T中验证实际改变。不得修改旧求解runner、共享数值核心、watchdog、activation、ABI、旧合同或历史记录；不建controller。

新工作入口固定为：

```text
python -u -m benchmarks.task43_hp_adaptivity.analyze_saved_r10_response
  --manifest <canonical>/docs/task43_hp_adaptivity/outcomes/records/v20_saved_r10_response_contract.json
  --output-root <本槽唯一root>/data
```

这是本节授权实现的入口，不声称已经存在。无任意模型/参考/seed选项。

旧写出源码的允许数值成员精确为：

```text
points_nm, weights_nm3,
round9_p_up_E, round9_p_up_curl_E,
round10_p_up_E, round10_p_up_curl_E,
Y6_1_E, Y6_1_curl_E
```

按ZIP实际`.npy`名精确匹配。完整目录应为六场E/curl加点权的14项；另6项Y5_1/Y3/Y3_2数值成员仅核ZIP目录存在，不解压、不加载、不计算。外层文件整体hash可读取；不得使用`dict(np.load(...))`等把全包顺手展开。测试用“打开保留成员即抛错”的真实访问监视证明隔离，而不是只断言最终输出不出现这些名字。

一次只展开一个q包的允许三场，分块计算；禁止object/pickle、重复ZIP键、非有限数据、错dtype/shape。实际允许数组的dtype/shape/数据hash落盘，不把未打开的控制数组标为finite通过。

### 9.4 共同点、映射与数学产物

q8应有516096点，q10应有1008000点，旧共同分区为1008盒；**不是V19的1104盒、565248/1104000点**。各三场只在其自身q包内相减。两包不得拼接，V19数组不读取/重采样；只能对完成积分后的同定义标量作历史比较。

原包无owner：使用冻结180个box及global/root映射对已有点作纯数组分桶，不构网、不调用FE几何搜索。每点恰归一盒、所有180盒有点；权为有限正数，全域权和350000nm³误差≤1e−8，逐盒权和与几何体积误差≤max(1e−8nm³,1e−12×该盒体积)。事前采用半开区间、全域最外边界闭合的唯一规则；不得通过膨胀重叠box把多归属变成通过。若原Gauss点没有边界命中，如实记录0。

令e9=Y6_1−R9，d10=R10−R9，e10=Y6_1−R10。两阶分别完整交付180行：

```math
B_{9,K}=\|e_9\|_{G,K}^2,\quad D_{10,K}=\|d_{10}\|_{G,K}^2,\quad
X_{10,K}=2\Re\langle e_9,d_{10}\rangle_{G,K},
```

```math
I_{10,K}=X_{10,K}-D_{10,K}=B_{9,K}-B_{10,K},\qquad
B_{10,K}=\|e_{10}\|_{G,K}^2.
```

每项拆E、curl/k0和G，记录未归一化值、公共G分母归一值、正负I及方向相关；B或D=0时相关度N/A。第二条I直接从e10范数独立积累，不由第一条回填。交付：

1. global ID、box、forest root、R9 p、R10 p、28个实际升阶与152个原p6身份；
2. 原升阶区、原p6区、六个z层的B9/D/X/I/B10、正负项和完整加和；不得把域外响应归因为当地独立被升阶；
3. B10完整降序、top1/5/10/20及达到50%剩余B10的最小前缀，q8/q10排序及累积分布差异；
4. 原V19请求global8、闭包global14、原十大B9位置在R10后剩余多少；只读已提交几何名单，不新读H8/P8数组；
5. 全域G、原16项J、全部612通道/复幅及全部超限，明确Av、散射reference分母历史复用，没有新积分/背景或物理功率重装配；
6. ΔJ/8328、ΔG/8328及原ε区间；8328是历史实际FE增量，不声称新空间审计。

复现容差沿V19的relative 3e−11、absolute 1e−15（允许误差取两者较大）；逐单元和全域恒等式误差≤1e−10×max(B9,B10,abs(X),D,1e−30)。不同旧共同分区引起的积分差应单列，不能删数据或修改旧标量；若不能在已冻结尺度复现，报告差异并按9.8处理，不改参考、ε或采样阶次。

### 9.5 必须形成的科学判断与一个位置提案

诊断应回答：广域p动作消除了多少原场差与J；改善发生在28个升阶区还是152个原p6区；剩余是否集中于某一层/区域；相对单点P8，广域响应是否表现显著非局部改善或抵消。

同时只形成一个**下一h假设的位置提案**，不生成h计划、不求解、不授选择资格。规则事前固定：

- 主序为q10的B10降序，数值完全相等时global ID较小优先；
- 两阶总B10均须大于0。分别定义空间份额 `p_K(q)=B10_K(q)/sum_j B10_j(q)`，要求 `sum_K abs(p_K(8)−p_K(10))≤1e−6`，且q8/q10的最大单元相同，才标为`STABLE_REMAINDER_LOCATION_PROPOSAL`；否则交两阶实际排名并标`LOCATION_UNRESOLVED_AT_SAVED_Q`，不改规则挑重合项。两阶总B10均为0时标`ZERO_REMAINDER_NO_LOCATION`，不任意选最小ID；仅一阶为0时保留实际值并标位置未决；
- 提案记录实际global/root/box、R9/R10 p、B10份额、与原global8是否相同、域内/界面/端口的既有几何关系；
- 计算“只消除此盒B10、域外不变”的条件G收益，明确不是全局耦合收益预测；不称该处为R00误差最大或DWR标记。

上述1e−6只限制本次位置提案的分布稳健性，不是精度门，不改变εG；这里按总B10归一，不能用第9.4节的公共G平方分母代替。提案只是下一次有限h实验的定位假设，**不使R10成为接受态，也不证明剩余全由h不足导致、p已真正饱和或所有p子集无效**。位置不稳、剩余不集中、或R00仍主导，都是合格的诊断结论，不触发额外计算。不得借50%前缀重新运行旧Dörfler选择器或生成transition10。

### 9.6 前置验证、冻结和主控独立复核

T1只运行本轮新增/真正受影响的节点，展开后最多12项；selectors在首次launch前冻结，禁止collect-only和旧整套复跑。至少覆盖：

1. 旧无内嵌record的14成员格式、精确8成员读取、控制成员访问即拒绝；
2. 非均匀权、乱序box/global ID、点唯一归属、边界/重复/漏盒/错权拒绝；
3. p-map 28/152及180全p6正确关联，错box或把行号当ID拒绝；
4. R9/R10/reference方向及两条独立恒等式；q包错配即使外层重新绑定也拒绝；
5. 真实新main到输出的微型三场fixture，16项J/612键、旧归一化来源完整；
6. q8完整落盘后q10真实写入异常保留q8/输入hash；终态非零/不完整时不得成为完整诊断；下一合同冲突的launch hash/槽状态必须在运行前拒绝。

微型main fixture允许仅在测试函数调用时显式注入test-only输入规范，绑定合成小数组、小尺寸和本槽排他的`fixtures/`目录；该上下文只用于授权T槽或D2前置pytest内部，D1/D2实际分析CLI不能接受测试schema或任意输入。真实原SHA、固定点数/盒数和路径门不得为fixture放宽。fixture仍须调用实际成员读取、身份校验、分桶、数学计算、写入和失败终态处理；可以在写入边界注入异常，不能把受验函数mock为通过，也不需要新controller。

可以复用V19未改纯函数及历史有效测试，但实际新增loader/映射/绑定/main不能用mock绕过。T1通过后不再为同字节重复测试；T1普通bug仅用T2补相关节点。

静态实现、输入JSON/hash、launch归档、合同完成后提交冻结。每槽manifest记录实际HEAD、最小依赖字节、合同SHA、实际argv/env、NumPy版本、绝对输入和输出。合同不自包含自身commit或自身hash；实际launch与tracked归档逐字节一致。各槽的条件授权、状态和唯一路径只有一个权威值，不能再保留“未启用”与“已armed”两个相反声明。

主控在放行D1前亲审上述完整映射和测试实值；完成后亲读完整180/612表、两个q的关键范数/恒等式/超限清单、全部trace和逐行资源/终态。可在槽外用标准库复核已落盘CSV/JSON算术，不重新打开NPZ或运行项目checker。这样获得独立表级复核，不伪称第二次原数组复算。

### 9.7 唯一launch/root、次数与预算

唯一新前缀：

`/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v20_saved_r10_response/`。

外层唯一命令形状为`bash <绝对前缀>/launch/stage_launch.sh <stage>`，其中`<stage>`只能是`T1`、`T2`、`D1`、`D2`中的一个；不接受任意root/模型，也不是shell管道。脚本是本节最小实现范围，先冻结再调用。每个运行root排他创建，非空或symlink拒绝；不得删除、改名或追加attempt3。

| 新槽 | 前缀下唯一root | 次数与准入 | 工作停止/whole含清理 | RSS |
|---|---|---|---:|---:|
| T1 | `support/targeted_attempt1/` | 1，新增小fixture首次验证 | 270/300秒 | 8GiB |
| T2 | `support/targeted_recovery1/` | 至多1，仅T1已定位普通bug受影响节点 | 270/300秒 | 8GiB |
| D1 | `support/decomposition_attempt1/` | 1，T门通过，三场两阶实际保存数组诊断 | 1140/1200秒 | 8GiB |
| D2 | `support/decomposition_recovery1/` | 至多1，仅D1普通工程失败，同worker先验受影响节点再续接 | 1140/1200秒 | 8GiB |

**支持最多4次，whole累计3000秒；新增正式0次，正式账保持9/10、历史末槽封存。** 本次是新增的明确支持额度，不恢复V19未用T2或任何旧槽。T2/D2互不转换，剩余时间不授予额外调用。外层shell被调用即计数，包括watchdog前失败；失败不退款。whole从调用到清理/终态结束，内层测试与读取不另加；未测项如实NOT_MEASURED。

预算锚是V19 D2两阶whole88.164秒、采样峰约0.83GiB。此处1200秒是包含首次读取旧格式、身份检查及记录的保守上限，不是预计必须耗满，也不构成加速或全过程成本结论。

CPU1、单worker、无mpiexec/native导入，六线程变量均1；使用原资格化activation所绑定的解释器/NumPy及worker局部既有设置，`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，不改共享环境或跑完整ABI。RSS取8GiB与现有动态available/reserve门较严者，保留64GiB/15%系统余量规则；task VmSwap=0，全局swap另记。单次运行顺序执行，不并跑。

复用既有watchdog与strace-D组织，核实际直接父PID/start_ticks、TracerPid归属、每个可见TID affinity、开始/结束身份；保存raw trace、原resources.jsonl、末行、退出码及host清除。完整资源解析失败、任一成功的非CPU1 setter、活worker或可见TID非CPU1、未分类setter/信号均否决；已分类的CPU1 setter和正常SIGCHLD不自动失败。whole尾部余量仅用于TERM/KILL/reap与保存终态，不延长数值工作。异步bootstrap返回0不代替worker/watchdog/supervisor最终退出与清理。

### 9.8 连续执行、普通bug恢复与硬停止

**静态准备完成→T1/T2门通过→D1→必要且有条件的D2→主控复核与交付，可连续实施，无需每成功一步再等review。** 不要求先写另一份任务书来获得这里已经给出的授权。

T1若是已定位的fixture/字段/索引/容器普通错误，局部修复、冻结新字节后，T2只验证受影响节点；未变证据逐项复用，不拼为最终全套。T2仍不通过则不启动D1。

D1若明确发生新checker的路径/字段/索引/序列化bug，且输入身份、资源及清理完整，可用唯一D2。D2同一受监控Python worker先用`pytest.main`执行最多6个受影响小节点，再执行同输入诊断，不额外开未计数验证driver。D1已完成阶次只有在checker算法字节/输入绑定仍适用且原件hash完整时才显式只读引用；算法改变则从同一旧数组重算受影响派生值，保留D1，不叫旧产物自动通过。不用通用resume框架。

下列真实违例没有自动重试权：原件缺失/身份漂移、禁止成员被读取、物理/reference或box绑定不符、非有限原数据、无法解释的恒等式/复现失败、CPU/RSS/swap/时限、父链/tracer异常、必需证据持久化不可信或清理失败。立即停止受影响消费并静态定位；不能以“可能是普通bug”绕硬门。只有现有日志/源码已明确定位为新增checker的普通实现错误、实际输入绑定正确且未触及上述身份/禁读/资源/清理硬门，才可占用尚未使用的对应恢复槽。小fixture仅在该恢复槽内运行，先通过再分析；真实硬门违例不因找到软件原因自动获得重试权。

可识别的派生CSV/JSON序列化异常属于普通工程bug的前提是输入与已完成阶次原件仍可信、失败非零及终态/资源留证完整；无法证明原件保留的持久化故障是硬停止。科学上无改善、原p6区仍主导、位置不稳或q两阶解释不同都不是bug，不得因此启动D2、增加q或换参考。

### 9.9 必须交付与继续锁定项

交付`response_v20.md`、`outcomes/records/v20_saved_r10_response_results_v1.json`、sources索引、两阶完整180/612表、p/box映射、响应与剩余分布、单一位置提案或未决原因、原J/G复现、全部超限、实际源/输入/输出/资源/费用与失败记录。每阶完成立即保存，全部科学结果不能只放摘要。当前导航、summary、manifest、模型总账和进展同步，历史负证据不变。

即使全任务完成，仍不自动允许新PDE、R10成为父态、新h计划、其他seed、p7、h+p、fresh baseline、q/R扫描、参考/holdout/control重算、A1/A2及R/B/C路线、成本campaign、迭代、0.7nm、NN/FTT、环境重建或合并。此次交付的实际科学产物用于决定下一次有限动作，而不是回写accepted9或独立精度。

## 10. 提交声明

本次只新增`docs/task43_hp_adaptivity/review_report_v19.md`，不修改历史review、合同、失败记录或原件；不提交master、不执行合并。本审没有启动新项目测试、支持driver或PDE。完整review提交SHA在提交产生后由交付消息给出，不制造文件自包含自身SHA。

本报告恢复了前一轮已完成但未发布的审阅草稿；续行调整仅包括发布日期、实际发布方式及必要的通俗解释，不改变第9节科学任务、槽数、资源预算或历史裁决。远端写入、回读和页面渲染检查分别记录，不把API写入成功冒称GitHub rendered view已检查。

[checker]: https://github.com/Rookie1234567/MyFEniCS/blob/56a2a41d0b0cd7b034dab6f434d61c83b250e9e1/benchmarks/task43_hp_adaptivity/analyze_saved_hp_response.py
[tests]: https://github.com/Rookie1234567/MyFEniCS/blob/56a2a41d0b0cd7b034dab6f434d61c83b250e9e1/src/test/test_task43_saved_hp_response.py
[cells10]: https://github.com/Rookie1234567/MyFEniCS/blob/56a2a41d0b0cd7b034dab6f434d61c83b250e9e1/docs/task43_hp_adaptivity/outcomes/records/v19_saved_hp_response_sources/decomposition_recovery1/data/q10/cells.csv
[diag10]: https://github.com/Rookie1234567/MyFEniCS/blob/56a2a41d0b0cd7b034dab6f434d61c83b250e9e1/docs/task43_hp_adaptivity/outcomes/records/v19_saved_hp_response_sources/decomposition_recovery1/data/q10/diagnostic.json
[modes10]: https://github.com/Rookie1234567/MyFEniCS/blob/56a2a41d0b0cd7b034dab6f434d61c83b250e9e1/docs/task43_hp_adaptivity/outcomes/records/v19_saved_hp_response_sources/decomposition_recovery1/data/q10/modes_612.csv
[d2close]: https://github.com/Rookie1234567/MyFEniCS/blob/56a2a41d0b0cd7b034dab6f434d61c83b250e9e1/docs/task43_hp_adaptivity/outcomes/records/v19_saved_hp_response_sources/decomposition_recovery1/root_closeout.json

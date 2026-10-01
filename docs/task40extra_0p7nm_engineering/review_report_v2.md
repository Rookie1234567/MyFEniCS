# Review V2：保留0.7 nm成功基线，完成边界精度、精确几何提速与电尺寸增长验证

## 0. 决策、目标与执行身份

**本轮要消除的blocker：已经能够解出缩小的0.7 nm非可分三维模型，但尚未验证传播模式之外的DtN截断误差，跨网格比较还主要是固定平面采样；精确几何缓存的成本增长没有完整分解，也没有固定波长下增大电尺寸的实测。因此，本轮将精度补强、一个明确的局部矩阵加速候选、两档电尺寸增长和容量分账串成连续工作，而不是再修一个字段就停审。**

最终目标仍为单节点约2 TB物理内存内的0.7 nm、complex128、Nédélec H(curl)、x/y双Floquet、z开放Fourier-DtN、任意非可分三维周期单胞工程计算。现有准确p4双凝聚是可靠基线和过渡路线，不是已经解决全域因子增长的最终架构。

用户本轮明确要求：读取最新结果、针对性写review，并允许本轮工作多一些、遇到问题自行尝试修复，不轻易中止。该要求落实为第9节的连续执行与定向自修复授权；不解释为绕过真实物理、数值、资源或工作站权限。

```text
repository                  = Rookie1234567/MyFEniCS
execution_branch            = task40extra_0p7nm_engineering
review_base_SHA             = 6bef3fdb8d7d70ac70db444086a2efd15c7cd80d
accepted_G0_G1_source_SHA    = b8a20bd24848a83f2f4fa50b1ccaaa4ec9be9672
accepted_G0_direct_source   = 393e5c0dddb933848945ab2e18edb73cf69cc224
review_file                 = docs/task40extra_0p7nm_engineering/review_report_v2.md
response_required           = response_v3.md
execution                   = P0 -> P1/P2 -> P3 -> P4 -> P5 -> P6 -> P7
machine                     = 笔记本已资格化WSL/Linux，MPI1/数学线程1
workstation_change          = NOT_AUTHORIZED
ordinary_default_change     = NOT_APPROVED
master_merge                = NOT_APPROVED
```

先读取根与目录AGENTS、仓库工作原则、[task.md](task.md)、[Review V1](review_report_v1.md)、[Response V2](response_v2.md)、[summary](outcomes/summary.md)、[identity结果](outcomes/records/identity_recovery_v1_results.json)、[h比较](outcomes/records/h_agreement_v1.json)。保留既有B线分支与所有祖先，不重新建分支、reset、rebase或合并master。HEAD有新合法提交时先核对差异，不回退它们。

本review新增的许可是：边界截断验证、精确几何参考积分复用、有限电尺寸增长、相应输入参数化及自修复续作。旧正常运行和旧重放账本不清零；本轮采用独立campaign身份。严格identity已恢复，本轮不启用V1的条件误差预算B，不降低原A6或A4检查要求。

## 1. 对最新结果的正式审阅

### 1.1 接受的结果与证据范围

以下均为已归档测量，不是本review新运行。时间单位为秒，内存为十进制GB；不同计时边界保持原定义。

| 对象 | 离散与求解 | 数值与物理结果 | 时间与资源 | 裁决 |
|---|---|---|---|---|
| G0 iterative | 336 cells；p6完整229680、外层trace+port 68336；q4因子29072行、10912592 NNZ；152步 | 原A6=9.798664008005796e-7；strict identity=1.520588963522625e-11；R/T/A_volume=0.07565196449717393/0.9062068564432124/0.01814125705170932 | workflow=1204.0178907530499；setup=373.0963321989984；KSP=787.135280114；同时树RSS=3776098304 B；任务swap=0 | 当前离散求解通过 |
| G1 iterative | 880 cells；p6完整595512、外层177200；q4因子75280行、28705330 NNZ；127步 | 原A6=9.901397191660007e-7；strict identity=3.2542694546811876e-11；R/T/A_volume=0.07612406206792088/0.905769220572286/0.018106712729780598 | workflow=4097.993754097028；setup=908.008740989957；KSP=3135.912814103；同时树RSS=6855741440 B；任务swap=0 | 当前离散求解通过 |
| G0同离散direct | p6 trace+port因子68336行；1 symbolic、1 numeric、2 solve；不是229680行全场全局因子 | 原A6=5.055376131651821e-11；与G0 FE L2/scaled-curl相对差1.0644e-7/1.0590e-7；模式与功率比较通过 | watchdog=1647.5270624320256；charged=1801.4672110320269；同时树RSS=11505573888 B；任务swap=0 | 同离散参考通过，启动纪律偏差另记 |

G0/G1全场及释放后原A6均满足1e-6；原strict identity限值1e-10未改。G0/G1能量闭合分别约7.7992e-8与-4.6300e-9。G0对direct的同坐标E/H与界面迹最大相对差4.9590e-7、80-mode振幅整体差1.3374e-7、逐模式功率最大绝对差7.5071e-8，满足原任务门槛。

几何缓存修复提交为33b773d161b5e5dc218a29b122cdb4044ca01800。旧代码将实际宽度舍入到12位后生成/索引局部算子，造成原A6与凝聚路径的几何不一致；Task40现在保留精确几何。第8步保存向量重算identity降至1.33697e-11，随后两场fresh PDE也通过strict Gate。旧attempt4仍保留失败分类，不能改写为当时已经通过。

本轮审阅状态：`PASS_WITH_QUALIFICATIONS_FOR_REDUCED_FIXED_DISCRETIZATIONS`。不是目标尺寸通过、不是通道收敛或连续极限证明，也不是master merge approval。

### 1.2 仍需处理的边界

1. G0–G1当前h比较使用4000个共同点。E/H总场相对变化约0.374%/0.393%，散射场约0.291%/0.306%，功率最大绝对变化约4.721e-4，确实通过原工程目标；但它不是体积FE L2积分，scaled-curl由H推得，不是独立curl(E)评估。保留原PASS及其限定，不将其改写成尚未做过的体积误差资格。
2. 当前输入为`auto_propagating`，80个模式覆盖当前筛选的传播通道，尚未包含一组经验证的倏逝截断。原A6残差小只能证明所选截断系统解得准，不能证明截断误差小。
3. G1比G0单元数约2.619倍、KSP平均每步约4.768倍，总workflow约3.404倍；G1步数反而更少。不能直接归因为PC退化、精确key或某一内核，必须读取同一作用的分项和实际局部类型数量。
4. R1 full operator diagnosis累计14039.107 s，约3.90小时；不要重复这种全域诊断。已有成功解和保存向量优先复用，局部oracle应有明确代表对象及成本。
5. direct在`/init.scope`由shell启动而非规定user-service；独立watchdog、身份、零swap和清场证据仍有数值价值。保留纪律偏差，不为洗掉历史重跑该direct；以后启动前纠正。
6. physical hash目前包含部分离散/assembly标签；跨网格或direct对照应分别列物理实体、离散与执行身份，不能仅靠字符串hash相同或不同作判断，更不能静默改旧hash。

## 2. 本轮工作矩阵：连续完成，不逐项停审

| 阶段 | 工作 | 主要交付 | 条件与继续规则 |
|---|---|---|---|
| P0 | 冻结已通过结果、核对入口、读取已有分项 | baseline与campaign清单、服务/线程/缓存接线、现有成本分账 | 不重新跑旧G0/direct |
| P1 | 现有场的跨网格体积/独立curl检查及有限局部回归 | 体积与采样分开、材料区域/界面/散射量、非零内部与端口RHS检查 | 无新PDE；缺一项证据不阻止独立候选 |
| P2 | 精确几何下参考积分与几何系数分离 | 一个p6局部矩阵生成候选；真实类型配对；合格时G1 M0整合 | 失败只回退该候选，不阻断边界/增长验证 |
| P3 | G0固定网格的DtN模式阶梯 | M0对M1/M2、条件M3；确定已测M*及边界 | 不只改输出阶数；不删除传播模式 |
| P4 | G1采用相同M* | 新截断下G0–G1体积/采样/模式/功率比较 | 未获得截断资格时仍可作明确标记的离散诊断 |
| P5 | 固定0.7nm与解析能力，几何扩大1.25、条件1.5倍 | 两档电尺寸的完整离散解、总时间/内存/纠错效率 | 单场不安全则跳过该场，继续独立工作；不伪造成功 |
| P6 | 真实局部尺寸的端口库存与2TB组成模型 | 450内部/432trace的小规模组件库存、局部/全局因子和复制账 | 不建立目标规模全局因子，不重做旧流式PC全套 |
| P7 | 综合裁决及下一架构选择 | response_v3、summary、两级总账、一个具体无全局大因子后续方案 | 完成后统一推送审阅 |

本轮可以有多场有不同科学目的的计算，但不允许用反复运行同一模型挑最快样本代替研究。所有候选都失败时也要完成可独立执行的精度和容量任务；不要只新增计时器后结束。

## 3. P0/P1：稳定复用成功基线，补足真正缺失的精度信息

### 3.1 运行前绑定与已有成本

绑定两份iterative input、实际source、ordered modes及field packet；G0/G1路径见[run index](outcomes/records/run_index.json)。保留原canonical worktree、upstream、输入及历史目录。正式启动从clean committed source进行。

从已有raw读取setup、numeric、A6/A4/H6、C中的限制/缩减/MatSolve/恢复/检查/延拓、Krylov、终检和输出。缺少某分项标unknown，在下一场必需运行补计时，不能为补表再建一份因子。统计actual raw/oriented几何类型、reference模板数量、唯一backing字节、每步各类solve次数。父子计时分开。

检查新`.dat`到profile、run identity、材料、mesh/ordered keys、精确几何开关和输出路径贯通。JIT原路径失效时先寻找签名匹配的合法缓存；无法复用就正常在本场监督内编译，不把可重新编译的缓存缺失变成整个任务长期blocker。不得强行复用不相容二进制或把预热成本移出账本。

原KSP首次停止原因、实际PETSc reason和KSP-only计时已经有新实现，直接复用；不再建第二套事件框架。所有未来formal包括reference都先验证user-service与subreaper后代关系；不能临时从裸shell启动后声称同一合同。

### 3.2 跨网格体积与场量

复用G0/G1已有FE系数，在相同解析材料分区内构造共同积分分块。对非嵌套网格可用两网格轴分点的交集分区组织积分，不需要创建第三张求解网格，也不需要组装/分解新的PDE。

分别输出体积加权总E/H、散射E/H和直接从FE基函数计算的curl(E)。不能再次由H代替独立curl结果。所有相减使用同一单位、坐标、时间谐波、Floquet相位和背景场定义，禁止整体相位拟合。记录总场与入射/背景尺度，弱分母同时给绝对或入射归一化差。

按air、Si、缺口邻域及界面单列；界面迹明确真实物理界面、单侧极限与法向，避免把普通水平采样面称为材料界面。不要在棱角奇异点用单一最大值否定或证明整体误差。采样场与体积积分保留为两个证据层。

工程h目标仍为场/独立scaled-curl变化1%、R/T/A/A_volume绝对变化1e-3。两网格只能授予已测h一致性，不授予连续极限。若体积检查未达标，保留离散解与明确区域信息；继续P2/P3等独立工作，P5只能带离散精度未资格标签运行，不冒称准确扩展。不得自动无限增加第三、第四张h网格。

### 3.3 局部回归补缺口

原定位中三处spot check的内部RHS和B alpha为零；本轮用少量真实边界/材料/缺口单元，加入非零内部及端口RHS、复Floquet与真实方向的独立raw块检查。覆盖两个在旧12位舍入下碰撞但实际宽度不同的局部几何。默认逐类型流式取数，用后释放；不复制全网格稠密矩阵，不再进行小时级完整operator诊断。

## 4. P2：唯一新增计算内核——精确metric的参考积分复用

### 4.1 它解决什么，不解决什么

精确几何是正确性要求，不能为了速度恢复12位舍入。但即使不同单元宽度必须分别保留，也可以共享参考单元上的基函数积分；每个单元只使用自己的真实几何系数组合物理矩阵。候选减少的是重复积分，不是把不同几何当相同，也不是可分离三维物理近似。

它只改p6完整局部矩阵的生成，随后仍按原方法单元凝聚、内部LU和恢复。优先不改p4构造、不改在线A6/A4/H6作用、不改MUMPS。它不能消除全局p4 factor，也不能保证所有曲面网格的缓存恒定。

### 4.2 固定数学定义

首个支持范围是当前真实轴对齐仿射六面体、单元内常数各向同性材料。令正向轴宽为h_x、h_y、h_z，体积Jacobian为d=h_x h_y h_z。curl与mass分别用各自原FFCx积分点/权重，不强行合并规则。

```math
(\widehat K_a)_{ij}=\sum_q w_q(\widehat\nabla\times\widehat N_j)_a(\xi_q)\overline{(\widehat\nabla\times\widehat N_i)_a(\xi_q)},
\qquad
(\widehat M_a)_{ij}=\sum_q \widetilde w_q(\widehat N_j)_a(\widetilde\xi_q)\overline{(\widehat N_i)_a(\widetilde\xi_q)}.
```

```math
V_K=\mu_{r,K}^{-1}\sum_{a=x,y,z}\frac{h_a^2}{d}\widehat K_a
-k_0^2\epsilon_{r,K}\sum_{a=x,y,z}\frac{d}{h_a^2}\widehat M_a.
```

此式来自H(curl)协变Piola映射。实际局部编号、Basix方向和约束变换必须沿原相容路径处理；原核已包含的变换不能再施加一次。非对角Jacobian、非仿射几何、单元内变化或各向异性材料，使用经过检查的旧正确fallback，不能硬套上式。共享参考积分不等于共享局部LU。

先形成完整V_K，再形成Schur：

```math
S_K=V_{tt}-V_{ti}V_{ii}^{-1}V_{it}.
```

不得分别凝聚curl/mass后相加。复材料系数不能被额外共轭。所有坐标单位与k0匹配。p6/p4的几何、材料和物理身份不得因cache key优化而移动。

### 4.3 缓存、验证和采用规则

参考模板按单元族、阶次、Basix/FFCx ABI、精确积分规则、基函数编号和必要方向身份缓存；每个物理单元使用实际double几何metric。完整局部factor/Schur缓存继续按准确身份。不得靠round、放大几何容差、共用近似Jacobian减少类型。

六张实数882×882模板的原始载荷约35.61 MiB，这是按形状派生的模板量，不是总RSS；物理输出与求解仍complex128。避免为每个类型重复一套模板、为每个单元保存新旧两份矩阵，固定批次与scratch。若模板必须complex，报告实际两倍载荷，不隐瞒。

先核对已有实现，确实已有同等算法时不重新命名作为新成果；应给出路径和实测，再聚焦其尚未共享的参考计算。与当前blocked Gram和原FFCx比较实际局部矩阵、实际向量作用、局部Schur及非零RHS恢复，作用相对目标1e-11，原严格identity仍1e-10。近零量同时给绝对差，不能靠除以小值挑选结论。

组件配对最多三轮交错运行，计入模板准备、组合、方向转换及临时分配。选取真实G0/G1类型分布，并有界验证更多真实metric类型的增长。不得只测试一个微核而不计初始化。已有正确候选无收益时回退，仅记录负结果，继续其他任务。

候选有可重复整体收益且内存合格后，在新source下完成一次G1、原M0=80通道的完整回归，与已成功G1比较。场/模式同离散相对1e-4、总功率绝对1e-5、逐模式功率1e-6，原A6与strict identity要求不变。以当前Task40 G1 4097.993754 s为历史同case参照，不能改用13.5 nm的Task39成绩放大收益；运行条件差异须披露。若候选未采用，不运行这场仅为凑数。

## 5. P3：固定G0网格的DtN截断验证

### 5.1 必须改变真实边界模式，不只是输出清单

当前[模式源码](../../src/common/modes_3d.py)在`auto_propagating`下只选零级或传播阶；`manual`选择枚举范围内全部阶。优先复用这一已存在能力，不另写一个DtN求解器。

传播模式决定远场能量的重要部分，但端口附近一般还含倏逝成分；解出当前80通道系统、能量闭合和两网格相近，都不能单独确认截断。新增模式应贯穿p6/p4 carrier、外层端口、RHS、独立A6、恢复和功率路径。只改输出的diffraction_order_max字段而边界仍auto_propagating不算完成。

固定G0全部几何、网格、材料、入射与p6/q4，只改变边界模式集合。模式数以下是由矩形索引范围和两端两极化推导的计划值，最终以实际ordered keys、合法切向极化与生成器审计为准。

| 集合 | 边界policy与索引范围 | 计划模式数 | 执行 |
|---|---|---:|---|
| M0 | 已成功auto_propagating，原m上限7、n上限1 | 80实测 | 复用旧G0，不重跑 |
| M1 | manual；-7≤m≤7，-1≤n≤1 | 180 derived | 新G0一场 |
| M2 | manual；-8≤m≤8，-2≤n≤2 | 340 derived | 新G0一场 |
| M3 | manual；-9≤m≤9，-3≤n≤3 | 532 derived | 仅M1/M2不稳定时增加一场 |

所有当前传播模式必须保留。按(side,m,n,polarization)匹配，不按数组位置截断相减。非零Bloch、出射平方根、近cutoff、切向极化归一化及损耗符号按原定义核对。manual增加了新物理边界离散，所以新的operator/discretization identity必须不同；连续物理实体仍相同。

端口与模式投影积分要能解析新加入的横向振荡。先用少量真实端口单元/模式做必要积分对照；若原规则不足，先记录固定模式下的积分变化资格，再比较模式截断，不能把两者混成纯M差。新增通道不应因旧80维硬编码而被静默丢弃。

lossy下不能按名称将全部倏逝/复beta模式功率一律置零；保留既有Poynting与边界归一化，核对R/T求和的定义和字段。发现真正符号或选择错误时做最小修复并重新资格化受影响结果，不用手工改能量账补齐。

### 5.2 比较和条件选择

每场保留完整p6场、原A6/恢复检查、全部新旧模式振幅及物理功率。在相邻集合之间比较体积/共同样本总场、散射场、独立scaled-curl、界面邻域及所有共同传播模式。

本轮预先规定的截断工程观察目标：相邻最细两集合的场/独立scaled-curl相对变化≤0.3%，总R/T/A/A_volume绝对变化≤1e-4，显著共同传播模式复振幅变化≤1%；近零模式同时报告绝对或入射归一化变化，不通过不稳定相对分母作判断。显著模式的筛选规则在比较前固定并保留全部模式原值，不允许结果出来后丢掉未通过项。它们是有限序列工程目标，不是严格截断误差上界。

M1与M2符合时选M*=M2作为保守的已测集合。否则运行M3；M2与M3符合则选M*=M3。仍不符合时不自动继续M4/M5；保留最大安全完成集合，明确`CHANNEL_TRUNCATION_UNQUALIFIED`及主要变化区域。

重要区分：截断变化超工程目标不等于某场原方程没有解出。只要算子实现、残差和资源合格，可继续P4/P5取得明确标记的离散成本/增长结果，但不得称为已满足边界精度的生产解。某集合出现真实operator/identity错误时，先修该错误，不以“只作diagnostic”为由绕过。

## 6. P4：在同一新截断下完成G1及h比较

对P3选定M*在G1运行一场，使用相同解析实体、材料、入射和ordered keys。P2候选通过则采用；未通过则使用原准确路径。不要为了维持统一宣传强行采用慢候选。

G0 M*与G1 M*进行P1规定的体积和采样比较；旧G0/G1 M0保留作为原截断结果，不能跨模式数比较后称纯h误差。若P3已经判定截断未资格，P4仍可完成该有限截断下的h研究，两个限制分开。

保留旧G0 direct M0，不能把它当M*的同离散reference。此轮不新增G1 direct，不重跑旧G0 direct，不为每次模式扩展建一个高内存p6直接参考。新路径用独立原A6、局部相容性及原严格identity保证所选离散问题求解；没有M*独立reference就明确范围。

原始数学与Gate保持：

```math
A_6u=b_6,\qquad
C_4=P_{64}F_4P_{64}^{H},\qquad
M_6=C_4+(I-C_4A_6)H_6(I-A_6C_4).
```

最终与释放后原A6≤1e-6，native/internal/Schur-port identity≤1e-10，port closure≤1e-8；能量绝对闭合≤1e-5。每8步原A6、每32步场/解checkpoint和终态输出保持。每次完整原A4检查及额外精化后检查不减少；目标1e-10，最多两次额外同因子精化，耗尽但有限完整时按既有最佳同一FE/alpha/A4c/e状态继续外层。不得将该粗层策略套成p6错误算子也允许继续。

## 7. P5：固定波长、扩大真实电尺寸

### 7.1 明确改变的量

这一步不是继续缩小波长和几何、保持同一电尺寸。真空波长与Si材料固定0.7 nm；以原解析单胞为母体，将所有几何长度、缺口、材料界面、端口与采样位置乘以q。网格最大目标长度固定为G0的10s nm，s=7/135，约0.5185185185 nm。各解析区间独立稳健ceil细分，不能移动材料面或改变缺口体积分数。

```math
k_0L\longrightarrow qk_0L,\qquad \lambda_0=0.7\,\mathrm{nm},\qquad h_{\max}\le 10s\,\mathrm{nm}.
```

| 电尺寸模型 | q | 计划轴段数 | 计划单元数 | 执行 |
|---|---:|---|---:|---|
| E1 | 5/4=1.25 | 10×4×19 | 760 derived | P3/P4可用且现场安全时完整一场 |
| E2 | 3/2=1.5 | 10×4×22 | 880 derived | E1完成且容量安全后再一场 |

这些计划值由原解析平面区间长度与固定h计算；实际网格必须读回核验。E2虽然与G1同为880单元，但物理尺寸、h与模式集合不同，不能称为G1复跑或同物理解对照。

模式清单按各自周期重新枚举。若母体采用M2，则对该新电尺寸的自动包络在m/n各增加1；若M3，各增加2，manual保留包络内全部合法模式。不能复用母体80/340/532这个数字作为新模型上限。若采用其他最大安全集合，将其包络余量规则明确冻结。母体截断资格不自动转移到新电尺寸，E1/E2首先是离散求解与成本增长点；未再做h/M序列时不授予新模型连续精度。

### 7.2 资源与继续规则

每个模型先用实际网格计数、局部类型、模式与已有同范围测量做容量预检，允许唯一必需p4 symbolic后按真实余量判断numeric。symbolic不是RSS预测；不恢复旧固定2倍估计普遍否决线，也不能忽略实际系统压力。

成功进入numeric后只保留该场唯一因子，直接完成求解与输出。E2不安全时保留E1并标注具体阻碍，继续P6/P7；不自动缩小E2、降阶或删模式冒称E2通过。P3/P4的离散误差目标未过但实际方程与实现正确时，可明确标为`DIAGNOSTIC_ELECTRICAL_SIZE_GROWTH`执行安全E1；这不是允许忽略原A6或identity。

每个成功场比较总成本，不仅是外层步数。保存相同原A6定义下、残差确实下降区间的“每下降一数量级所需时间”：

```math
\tau_{10}=\frac{t_b-t_a}{\log_{10}(\rho_a/\rho_b)}.
```

不要用不同类型的reported/true residual拟合预计完成时间；不要求E1/E2仍是127或152步。没有下降时如实记录，不赋予负的效率值或制造预计收敛。

## 8. P6：真实局部尺寸和约2TB的组成模型

本阶段利用前面必需运行的实测补充成本与容量，不再启动目标规模PDE。至少分开：mesh/MPC、精确几何类型、p6/p4局部LU/Schur/恢复、p4矩阵与MUMPS原生统计、原始/派生端口块、FGMRES与其他工作向量、JIT及后处理生命周期。去重view的实际backing；对象库存、后端used/allocated和树RSS不混加。

允许固定少量真实p6局部块，在450个内部、432个trace的真实维数上，比较80、已测M*和最多3904模式的诊断库存/作用增长。后者属于合成/重采样通道维度stress，不能冒充完整2nm或0.7nm物理模型。固定batch和工作区，先计算大小，禁止为每个cell生成模式平方oracle或为此建立全局factor。近零/稀疏支撑按实际记录，不能用2×2玩具作为扩展性证明。

本轮不重新实现旧已更慢的端口流式PC，不扫描另一批batch参数；这一步只让下一架构决策面对真实局部维数和存储增长。

```math
M_{\mathrm{peak}}=\max_t\bigl(M_{\mathrm{mesh}}+M_{\mathrm{local}}+M_{\mathrm{coarse}}+M_{\mathrm{ports}}+M_{\mathrm{Krylov}}+M_{\mathrm{other}}\bigr)(t),
\qquad M_{\mathrm{FGMRES,main}}\simeq16N_\Gamma(2m+1).
```

公式只是组成与形状推导，不能由G0/G1两点拟合一个精确的TB预测。2TB是整机物理内存，要保留系统余量；此轮不改变工作站cap、不SSH迁移、不调整其正在运行任务。不得把本机10GB或旧8GiB当最终资源政策。

最终应清楚指出：无论本轮局部积分快多少，全域p4稀疏因子仍可能成为最终目标的主要blocker；端口和每cell稠密缓存也有独立风险。不得用小模型缓存共享优势承诺任意曲面网格容量。

## 9. 执行许可、自修复与停止规则

### 9.1 正常正式运行清单

| 编号 | 新正式场 | 条件 |
|---|---|---|
| F1 | G1 M0、采用新reference-metric矩阵生成 | 仅P2候选合格并实际采用；否则NOT_RUN |
| F2 | G0 M1 | 正常执行 |
| F3 | G0 M2 | 正常执行 |
| F4 | G0 M3 | 仅相邻M1/M2未稳定且安全 |
| F5 | G1 M* | M*选择后执行；截断未资格时明确限定 |
| F6 | E1 | 物理/实现完整且安全 |
| F7 | E2 | E1完成、容量安全且已批准条件满足 |

最多七个不同目的的新正常正式场；不是允许七次反复运行同一配置。已有G0/G1/direct不为补表重跑。P1与P6组件成本照实记录但不额外建全局工程factor；P2唯一整合回归已在F1内。

每个`.dat`对应一次明确计算，唯一run_id/结果目录。新增mode/mesh扩展用数据与小型通用接口实现，不复制巨型runner，也不因旧allowlist只接受G0/G1就把E1改名G1。扩展schema需保留旧输入行为和必要反向测试。

### 9.2 自修复授权：不再用旧一次replay阻断有依据的续作

本轮明确允许Codex在上述固定研究范围内自行定位真实实现错误，做最小修复、对应测试、提交clean source后，重放受影响case或续做独立阶段。**旧Task39/Task40一次replay次数不限制这轮新许可；不需要每个字段/JIT/serialization修复后再请求批准。**

每次修复必须记录失败source、first cause、artifact与已用成本、修复diff、测试、影响范围和新attempt。历史错误不删除，未改源码或条件的同一失败不反复重跑。遇到缓存路径、run identity、metadata、合法profile参数化、结果持久化等问题应先修接口；不能修改材料、几何实体、模式定义或阈值伪装为工程修复。

同一根因连续两次修复后仍不能通过针对性检查时，应暂停受影响完整PDE，转入有界局部定位或回退未合格候选；独立的其他工作继续。出现新的、不同的明确实现问题可以继续本轮修复流程，不把累计attempt数当唯一停止理由。诊断没有形成新信息时及时收口，不无限消耗时间重复全域检查。

数值未收敛、模式/h变化超工程目标、资源不足和速度没有提升，不属于实现bug。max2048仍不收敛时保留该配置负结果，不自动换p/PC/restart/MUMPS；准确的有限截断离散解可以保留，即使截断资格未通过。真实NaN/Inf、矩阵/约束/identity错误、factor失败或任务资源危险仍然停止受影响运行，待确认原因和修复。

单项候选无收益、某模型安全BLOCKED、历史字段缺失、普通文档渲染暂不可达，不应自动终止整个campaign；继续不依赖它的任务并保留unknown。材料或有效算子身份无法确认、监督失联等会影响所有PDE的错误必须先解决。不得以用户要求“不轻易停”为由让不可信方程继续计算。

### 9.3 不变的运行安全与数值纪律

所有formal经`python scripts/run_case.py input/...dat`、规定user-service和独立subreaper/watchdog。每次启动前核对实际分支/HEAD/clean、ABI与complex128/IntType、MPI1与数学线程1、接电/电源模式、材料/网格/modes/source/input hash、磁盘与内存余量、任务scope零swap和后代覆盖。此轮不升级ABI，不预设已经安装DOLFINx0.10或int64。

真实物理内存压力和系统/cgroup余量仍是资源依据；PSS不采样记null，快速RSS/status与进程身份、失联、清场保留。不能缩窄进程树、降低安全采样或清零peak制造好结果。编译子进程和输出成本计入本场。全机历史swap页不能直接归因本任务；任务scope实际swap不能用来撑预算。

旧8GiB、历史RSS、126/127/152步、20/40/68分钟都不是新的人工停止线。时间observe_only；实际max迭代和安全数值停止规则保持。不能运行中热改源码、阈值、线程或PC。需要修复时先保存并清理受影响进程，提交后新attempt；不能把续算时间冒作fresh全流程性能。

MUMPS后端、排序/主元、BLR/OOC与线程设置不变；p6/q4与BAL_H不变；A6融合、完整快速A4、H6参考metric对角/自然序和已合格blocked Gram作为回退资产保留。未经过资格的新候选只显式opt-in。

## 10. P7交付、综合判断与后续架构

新增`response_v3.md`，summary增加本轮，旧response/result不覆盖。更新README与`docs/development_progress.md`、`docs/development_model_registry.md`，保持两级记录。建议轻量交付如下，可合理合并而不能只给状态标签：

```text
outcomes/review_v2_campaign.md
outcomes/records/review_v2_plan.json
outcomes/records/volume_h_agreement_v2.json
outcomes/records/reference_metric_tensor_v2.json
outcomes/records/channel_study_v2.json
outcomes/records/electrical_size_v2.json
outcomes/records/resource_components_v2.json
outcomes/records/repair_ledger_v2.json
outcomes/test_summary.md
outcomes/summary.md
response_v3.md
```

每场列setup/KSP/后处理、真实残差、strict identity、完整/散射E/H、独立curl、全部模式和功率、A_volume及区域值、树RSS峰与该时刻成员/阶段、任务swap、JIT命中/冷编译、矩阵/因子/模板/临时载荷。每个关键数绑定实际文件路径/字段和hash；scope不同不相加，不从UTC与monotonic差推造一个阶段时间。

报告首先回答：

- 原80传播模式是否在本模型上足够？M*的证据范围、未通过项和新增成本是什么？
- 体积/散射/curl证据是否支持G0/G1的已有采样结论？误差集中在哪些区域？
- 精确metric复用是否真正更快、增加多少常驻/临时内存，是否改变了full strict结果？
- 在lambda固定时增大电尺寸，factor、local cache、port、Krylov与每数量级残差成本分别如何增长？
- 下一项面向目标规模的唯一主候选是什么，为什么不是重做旧42宏块/低内存强逆参数扫描？

本轮不实施新DD/AMG/LOR/NN/GPU求解器。理由不是这些路线不值得做，而是本轮先形成边界/离散和电尺寸成本的可判别基线；同时做未冻结的多种PC会混淆失败归因。P7必须给出**一个可执行的下一阶段设计**，不能只复述“有界局部+多层纠错”。至少明确局部问题上限、局部因子总和、接口条件、粗空间如何表示真实波传播、粗层递归/最低层规模上限、内外工作量、准确p4对照和停止规则。读取[父历史](../task039_extra_physical_multilevel/prior_attempts_retrospective.md)，不要将旧负结果换名为新方案。全域p4 reference继续保留，但最终生产候选不能偷偷再依赖一个同样膨胀的全局粗LU。

阶段提交建议：C0冻结基线/入口与已有证据；C1必要参数化及唯一内核/小测试；C2固定各场dat/source；C3各场轻量结果；C4综合回应与两级总账。组件选定后直接执行已授权的对应formal，不停在WAITING_FOR_MAIN_REVIEW。运行结束或真正阻碍用尽本轮可独立工作后，集中推送同一分支，回读完整远端HEAD，等待下一审阅；不迁移工作站、不合并master。

## 11. 技术依据与审阅边界

- [当前task](task.md)、[Review V1](review_report_v1.md)、[Response V2](response_v2.md)、[本轮前summary](outcomes/summary.md)与[compact](outcomes/records/identity_recovery_v1_results.json)定义已验证身份和失败历史。
- [h比较记录](outcomes/records/h_agreement_v1.json)区分固定样本、体积积分和由H推得的curl；本review未把未做检查改写为通过。
- [模式生成](../../src/common/modes_3d.py)和[实际输入](../../input/task40extra_0p7nm_engineering/nonseparable_g1_p6_q4_review_v1.dat)显示auto_propagating/manual差异；P3优先复用已有生产能力。
- [装配时凝聚](../../src/solvers/hcurl_assembly_time_condensation.py)是精确几何与局部矩阵候选的主要入口；[p6作用](../../src/solvers/p6_cell_condensed_action.py)和[外层FGMRES](../../src/solvers/physical_retained_fgmres.py)的数学与严格检查保持。
- Jiang等，An Adaptive Finite Element DtN Method for Maxwell's Equations in Biperiodic Structures，arXiv:1811.12449：有限元离散与DtN截断误差应区分。其理论条件不能直接当作本轮有限模式序列的误差上界；本轮不声称实现了该论文的自适应估计器。
- Kirby与Logg，Efficient Compilation of a Class of Variational Forms，arXiv:1205.3014：参考张量和几何张量分离的背景。其原定理的单元/形式范围不等于本项目全部几何已覆盖；第4节六面体公式是按当前仿射Piola变换具体推导，仍须与真实FFCx验证。

本报告为远程记录和源码审阅及下一轮设计，未执行FE/PDE或重放大型场数组。独立公式使用fenced math；表格按scope分列。提交后的实际GitHub视觉渲染及执行端文档检查应如实记录，不能把文件成功提交等同于渲染或数值资格通过。
